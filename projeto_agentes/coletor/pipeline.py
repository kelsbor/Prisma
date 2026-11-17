"""Fluxo do Coletor: arquivos → extração → qualidade → consolidação → envio ao Agente de Armazenamento."""

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from comum.config import RAIZ
from coletor.extracao import SUPORTADOS, extrair
from coletor.qualidade import checar_arquivo, consolidar

PASTA_PADRAO = RAIZ / "extratos_ficticios"
TAMANHO_LOTE = 200
NOME_COLETOR = "prisma-coletor-v2"


def listar_arquivos(caminhos=None):
    """Expande pastas e filtra pelos formatos aceitos. Sem caminhos, usa a pasta extratos_ficticios/ do projeto."""
    caminhos = caminhos or [PASTA_PADRAO]
    arquivos, ignorados = [], []
    for c in caminhos:
        p = Path(c).expanduser()
        if p.is_dir():
            itens = sorted(x for x in p.iterdir() if x.is_file() and not x.name.startswith("."))
        elif p.is_file():
            itens = [p]
        else:
            ignorados.append(f"{c}: não encontrado")
            continue
        for x in itens:
            if x.suffix.lower() in SUPORTADOS:
                arquivos.append(x.resolve())
            elif x.suffix.lower() != ".ipynb":
                ignorados.append(f"{x.name}: formato não suportado")
    return list(dict.fromkeys(arquivos)), ignorados


def _resumo_arquivo(r):
    entradas = sum((t["valor"] for t in r["transacoes"] if t["valor"] > 0), Decimal(0))
    saidas = sum((t["valor"] for t in r["transacoes"] if t["valor"] < 0), Decimal(0))
    return {
        "arquivo": r["arquivo"], "metodo": r["metodo"], "transacoes": len(r["transacoes"]),
        "entradas": float(entradas), "saidas": float(saidas), "liquido": float(entradas + saidas),
        "periodo": [d.isoformat() for d in r["periodo"]] if r["periodo"] else None,
        "conciliacao": r["conciliacao"], "avisos": r["avisos"],
        "alertas": [{"data": t["data"].isoformat(), "descricao": t["descricao"],
                     "valor": float(t["valor"]), "alertas": t["alertas"]}
                    for t in r["transacoes"] if t["alertas"]],
    }


def analisar(caminhos=None):
    """Lê e confere os extratos, sem enviar nada. Devolve (relatório, transações consolidadas)."""
    arquivos, ignorados = listar_arquivos(caminhos)
    resultados = [checar_arquivo(extrair(p)) for p in arquivos]
    consolidado, faltas = consolidar(resultados)
    relatorio = {
        "arquivos": [_resumo_arquivo(r) for r in resultados],
        "ignorados": ignorados,
        "transacoes_unicas": len(consolidado),
        "liquido_consolidado": round(sum(d["valor"] for d in consolidado), 2),
        "nao_aparecem_em_todos_os_arquivos": faltas,
    }
    return relatorio, consolidado


async def enviar(cliente, titular_id, consolidado):
    """Grava no Agente de Armazenamento em lotes. Ele ignora chaves já gravadas, então reenviar não duplica."""
    agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    gravadas = ja_existiam = 0
    for i in range(0, len(consolidado), TAMANHO_LOTE):
        lote = [{**d, "ingerido_em": agora, "coletor": NOME_COLETOR} for d in consolidado[i:i + TAMANHO_LOTE]]
        resp = await cliente.chamar("salvar_lote", {"titular_id": titular_id, "transacoes": lote})
        gravadas += resp["gravadas"]
        ja_existiam += resp["ja_existiam"]
    return {"gravadas": gravadas, "ja_existiam": ja_existiam}
