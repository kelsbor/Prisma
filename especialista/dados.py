"""Dados do usuário, buscados no Agente de Armazenamento via MCP. As contas são feitas em Python."""

import re
from collections import defaultdict

from comum.cliente_armazenamento import conectar


# Dinheiro que só mudou de lugar (aplicação, resgate, transferência para a mesma titularidade):
# não é ganho nem gasto, então fica fora das somas.
MOVIMENTACAO_INTERNA = re.compile(r"APLICACAO|RESGATE|MESMA TITULARIDADE", re.I)


async def transacoes(titular_id: str) -> list[dict]:
    async with conectar() as cliente:
        resp = await cliente.chamar("consultar_titular", {"titular_id": titular_id})
    return sorted((r["dados"] for r in resp["registros"] if r["dados"].get("data")), key=lambda t: t["data"])


def resumo(ts: list[dict], periodo: str | None = None) -> dict:
    """Resumo de um mês (AAAA-MM). Sem período, usa o mês mais recente que tem transações."""
    meses = sorted({t["data"][:7] for t in ts})
    if not meses:
        return {"erro": "Nenhuma transação para este titular. Importe extratos com o Coletor."}
    periodo = periodo or meses[-1]
    do_mes = [t for t in ts if t["data"].startswith(periodo)
              and not MOVIMENTACAO_INTERNA.search(t.get("descricao", ""))]
    entradas = sum(t["valor"] for t in do_mes if t["valor"] > 0)
    saidas = -sum(t["valor"] for t in do_mes if t["valor"] < 0)
    por_descricao = defaultdict(float)
    for t in do_mes:
        if t["valor"] < 0:
            por_descricao[t["descricao"]] -= t["valor"]
    return {
        "periodo": periodo,
        "meses_com_dados": meses,
        "entradas": round(entradas, 2),
        "saidas": round(saidas, 2),
        "saldo": round(entradas - saidas, 2),
        "maiores_gastos_por_descricao": [{"descricao": d, "total": round(v, 2)}
                                         for d, v in sorted(por_descricao.items(), key=lambda x: -x[1])[:8]],
        "transacoes_com_alerta": [{"data": t["data"], "descricao": t["descricao"], "valor": t["valor"],
                                   "alertas": t["alertas"]} for t in do_mes if t.get("alertas")],
    }


def dados_do_usuario(ts: list[dict], periodo: str | None = None) -> dict:
    """O que vai para o Gemini como DADOS DO USUÁRIO: o resumo do mês e o perfil de risco (Agente de Risco)."""
    dados = resumo(ts, periodo)
    try:
        from risco.perfil import calcular, resumo_para_prompt
        dados["perfil_de_risco"] = resumo_para_prompt(calcular(ts))
    except Exception as e:                      # o risco é um extra: a resposta não depende dele
        dados["perfil_de_risco"] = {"disponivel": False, "motivo": str(e)}
    return dados
