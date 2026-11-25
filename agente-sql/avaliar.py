"""Avalia as respostas do agente contra os fatos expressos no CSV de referência."""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
from datetime import date
from decimal import Decimal
from pathlib import Path

import agente
from metricas import MetricasExecucao

RAIZ = Path(__file__).resolve().parent.parent
CSV_PADRAO = RAIZ / "projeto_agentes" / "perguntas_respostas_prisma(in).csv"
VALOR = re.compile(r"R\$\s*([\d.]+,\d{2})", re.IGNORECASE)
DATA = re.compile(r"(?<!\d)(\d{2})/(\d{2})/(\d{4})(?!\d)")
CONTAGEM = re.compile(
    r"\b(\d{1,3}(?:\.\d{3})*|\d+)\s+"
    r"(transaç(?:ão|ões)|transacoes|categorias?|grupos?|contas?|"
    r"aplicaç(?:ão|ões)|aplicacoes|lançamentos|lancamentos|"
    r"estabelecimentos|parcelas)\b",
    re.IGNORECASE,
)
CONTAGEM_TIPO = re.compile(
    r'\b(\d+)\s+(?:do\s+tipo\s+)?["“]?'
    r'(gastos?|entradas?|transfer[eê]ncias?|estornos?|BANK|CREDIT)\b',
    re.IGNORECASE,
)
TIPOS = {
    "gasto": "gasto", "gastos": "gasto",
    "entrada": "entrada", "entradas": "entrada",
    "transferencia": "transferencia", "transferencias": "transferencia",
    "transferência": "transferencia", "transferências": "transferencia",
    "estorno": "estorno", "estornos": "estorno",
    "bank": "conta_bank", "credit": "conta_credit",
}


def fatos(texto: str) -> dict[str, set]:
    valores = {
        int(Decimal(valor.replace(".", "").replace(",", ".")) * 100)
        for valor in VALOR.findall(texto)
    }
    datas = {f"{ano}-{mes}-{dia}" for dia, mes, ano in DATA.findall(texto)}
    contagens = {
        (int(numero.replace(".", "")), unidade.casefold())
        for numero, unidade in CONTAGEM.findall(texto)
    }
    contagens.update(
        (int(numero), f"tipo:{TIPOS[tipo.casefold()]}")
        for numero, tipo in CONTAGEM_TIPO.findall(texto)
    )
    return {"valores_centavos": valores, "datas": datas, "contagens": contagens}


def comparar(referencia: str, resposta: str) -> bool | None:
    esperado, obtido = fatos(referencia), fatos(resposta)
    if not any(esperado.values()):
        return None
    return esperado == obtido


def carregar_casos(caminho: Path) -> list[dict[str, str]]:
    with caminho.open(encoding="utf-8-sig", newline="") as arquivo:
        casos = list(csv.DictReader(arquivo))
    for caso in casos:
        if not caso.get("pergunta") or not caso.get("resposta"):
            raise ValueError("CSV precisa conter colunas pergunta e resposta preenchidas")
    return casos


def id_caso(pergunta: str) -> str:
    normalizada = " ".join(pergunta.casefold().split())
    return "q-" + hashlib.sha256(normalizada.encode("utf-8")).hexdigest()[:10]


def julgar(pergunta: str, referencia: str, resposta: str) -> bool:
    metricas = MetricasExecucao(componente="juiz_llm")
    try:
        with metricas.etapa("avaliacao_textual_ms"):
            avaliacao = agente.perguntar_ao_llm(
                "Você avalia respostas de um assistente financeiro. Compare a resposta com o gabarito. "
                "Aprove somente se responder à pergunta, preservar os fatos e não inventar dados. "
                "Responda apenas APROVADO ou REPROVADO.",
                f"Pergunta: {pergunta}\nGabarito: {referencia}\nResposta: {resposta}",
                metricas,
            )
    except Exception as erro:
        metricas.finalizar("falha", type(erro).__name__)
        raise
    aprovada = avaliacao.strip().upper() == "APROVADO"
    metricas.finalizar("aprovado" if aprovada else "reprovado")
    return aprovada


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=CSV_PADRAO)
    parser.add_argument("--hoje", type=date.fromisoformat, default=date(2026, 11, 25),
                        help="data usada nos prompts (padrão: data do snapshot de referência)")
    parser.add_argument("--juiz-llm", action="store_true",
                        help="envia pergunta, gabarito e resposta ao Gemini para avaliação textual")
    args = parser.parse_args()

    casos = carregar_casos(args.csv)
    acertos = avaliaveis = revisao_manual = falhas_agente = 0
    juiz_acertos = juiz_total = 0
    for caso in casos:
        identificador = id_caso(caso["pergunta"])
        tem_fatos = any(fatos(caso["resposta"]).values())
        if tem_fatos:
            avaliaveis += 1
        else:
            revisao_manual += 1
        try:
            saida = agente.responder_detalhado(caso["pergunta"], args.hoje, log_detalhes=False)
            correto = comparar(caso["resposta"], saida["resposta"])
            if correto is None:
                estado = "REVISÃO"
            else:
                acertos += correto
                estado = "FATOS_OK" if correto else "FATOS_DIVERGEM"
        except Exception as erro:
            estado = f"FALHA_{type(erro).__name__}"
            falhas_agente += 1
            print(f"{estado:28} {identificador}", flush=True)
            continue
        if args.juiz_llm:
            juiz_total += 1
            try:
                aprovado = julgar(caso["pergunta"], caso["resposta"], saida["resposta"])
                juiz_acertos += aprovado
                estado += f" JUIZ_{'OK' if aprovado else 'DIVERGE'}"
            except Exception as erro:
                estado += f" JUIZ_FALHA_{type(erro).__name__}"
        print(f"{estado:28} {identificador}", flush=True)

    taxa = f"{acertos}/{avaliaveis}" if avaliaveis else "n/a"
    print(f"\nAcerto de fatos: {taxa}; revisão manual: {revisao_manual}/{len(casos)}")
    print(f"Falhas do agente: {falhas_agente}")
    if args.juiz_llm:
        print(f"Juiz LLM: {juiz_acertos}/{juiz_total} aprovadas (métrica complementar)")
    print(f"Data de referência: {args.hoje.isoformat()}")
    return 0 if avaliaveis and acertos == avaliaveis and not falhas_agente else 1


if __name__ == "__main__":
    raise SystemExit(main())
