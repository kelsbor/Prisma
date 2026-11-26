"""Benchmark do agente-sql: confere se os fatos esperados aparecem nas respostas do agente.

Casos (padrão: benchmark/casos.jsonl), um por linha:
    {"pergunta": "...", "sql": "SQL de referência", "fatos": {"coluna": "brl|contagem|data|mes|texto"}}

O gabarito é gerado rodando o SQL de referência no banco configurado (use o snapshot do benchmark).
Regras do conjunto:
- toda pergunta tem período explícito; "até hoje" usa a data de --hoje (padrão 2026-11-25);
- "gastei" = valor_gasto até hoje; parcelas futuras têm perguntas próprias ("quanto ainda vou pagar");
- o caso passa se TODOS os fatos esperados estiverem na resposta. Fatos a mais (período, contagens)
  não reprovam: o agente é orientado a dizer o período.

Também aceita o CSV antigo (--csv), com colunas pergunta e resposta; os fatos vêm do texto da resposta.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import unicodedata
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import agente
from metricas import MetricasExecucao

PASTA = Path(__file__).resolve().parent
CASOS_PADRAO = PASTA / "benchmark" / "casos.jsonl"

VALOR = re.compile(r"R\$\s*-?\s*(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{2}))?", re.IGNORECASE)
DATA = re.compile(r"(?<!\d)(\d{2})/(\d{2})/(\d{4})(?!\d)")
PERCENTUAL = re.compile(r"\d+(?:[.,]\d+)*\s?%")
INTEIRO = re.compile(r"(?<![\d,.])(\d{1,3}(?:\.\d{3})+|\d+)(?![\d,])")
MESES = ["janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto", "setembro",
         "outubro", "novembro", "dezembro"]
PALAVRAS_COMUNS = {"banco", "pessoa", "fisica", "instituicao", "pagamento", "pagamentos", "conta", "contas",
                   "ltda", "de", "da", "do", "e", "com", "para", "online", "agencia"}
# CSV antigo: contagens precisam vir com a unidade
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


def normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", sem_acento.casefold())


# ------------------------------------------------------------------ fatos de uma resposta
def _centavos(inteiro: str, decimais: str | None) -> int:
    return int(Decimal(f"{inteiro.replace('.', '')}.{decimais or '00'}") * 100)


def fatos_da_resposta(texto: str) -> dict[str, set]:
    """Tudo o que a resposta afirma: valores em R$, datas, meses, números inteiros e o texto normalizado."""
    valores = {_centavos(i, d) for i, d in VALOR.findall(texto)}
    datas = {f"{a}-{m}-{d}" for d, m, a in DATA.findall(texto)}
    norm = normalizar(texto)
    meses = set()
    for n, nome in enumerate(MESES, 1):
        for ano in re.findall(rf"\b(?:{nome}|{nome[:3]})\b\.?\s*(?:de\s+|/\s*)?(\d{{4}})", norm):
            meses.add((int(ano), n))
    meses |= {(int(a), int(m)) for m, a in re.findall(r"(?<![\d/])(\d{2})/(\d{4})(?!\d)", texto)}
    meses |= {(int(a), int(m)) for _, m, a in DATA.findall(texto)}
    resto = PERCENTUAL.sub(" ", DATA.sub(" ", VALOR.sub(" ", texto)))
    inteiros = {int(n.replace(".", "")) for n in INTEIRO.findall(resto)}
    return {"valores_centavos": valores, "datas": datas, "meses": meses, "inteiros": inteiros, "texto": {norm}}


# ------------------------------------------------------------------ gabarito pelo SQL de referência
def _texto_casa(esperado: str, texto_normalizado: str) -> bool:
    """Nome casa se aparecer inteiro ou se a palavra principal aparecer (o agente encurta nomes longos)."""
    alvo = normalizar(esperado)
    if alvo in texto_normalizado:
        return True
    tokens = re.findall(r"[a-z0-9]+", alvo)
    palavras = [p for p in tokens if len(p) >= 4 and p not in PALAVRAS_COMUNS] or tokens[:1]
    return bool(palavras) and re.search(rf"\b{re.escape(palavras[0])}\b", texto_normalizado) is not None


def gabarito(caso: dict) -> list[tuple[str, object]]:
    """Fatos esperados: [(tipo, valor)], gerados rodando o SQL de referência no banco."""
    r = agente.executar_sql(caso["sql"])
    esperados = []
    for linha in r["linhas"]:
        celulas = dict(zip(r["colunas"], linha))
        for coluna, tipo in caso["fatos"].items():
            v = celulas.get(coluna)
            if v is None:
                continue
            if tipo == "brl":
                esperados.append(("brl", int((Decimal(str(abs(v))) * 100).quantize(Decimal(1), ROUND_HALF_UP))))
            elif tipo == "contagem":
                esperados.append(("contagem", int(v)))
            elif tipo == "data":
                esperados.append(("data", str(v)[:10]))
            elif tipo == "mes":
                esperados.append(("mes", (int(celulas["ano"]), int(v))))
            elif tipo == "texto":
                esperados.append(("texto", str(v).strip()))
            else:
                raise ValueError(f"tipo de fato desconhecido: {tipo}")
    return esperados


def faltando(esperados: list[tuple[str, object]], resposta: str) -> list[str]:
    """Fatos esperados que NÃO aparecem na resposta (vazio = passou)."""
    obtido = fatos_da_resposta(resposta)
    texto = next(iter(obtido["texto"]))
    verificar = {"brl": lambda v: v in obtido["valores_centavos"],
                 "contagem": lambda v: v in obtido["inteiros"],
                 "data": lambda v: v in obtido["datas"],
                 "mes": lambda v: v in obtido["meses"],
                 "texto": lambda v: _texto_casa(v, texto)}
    return [descrever(tipo, v) for tipo, v in esperados if not verificar[tipo](v)]


def descrever(tipo: str, v) -> str:
    if tipo == "brl":
        return "R$ " + f"{v / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if tipo == "data":
        a, m, d = v.split("-")
        return f"{d}/{m}/{a}"
    if tipo == "mes":
        return f"{MESES[v[1] - 1]}/{v[0]}"
    return str(v)


# ------------------------------------------------------------------ CSV antigo
def fatos(texto: str) -> dict[str, set]:
    """Fatos do CSV antigo (gabarito escrito à mão)."""
    valores = {_centavos(i, d) for i, d in VALOR.findall(texto)}
    datas = {f"{ano}-{mes}-{dia}" for dia, mes, ano in DATA.findall(texto)}
    contagens = {(int(n.replace(".", "")), u.casefold()) for n, u in CONTAGEM.findall(texto)}
    tipos = {"gasto": "gasto", "gastos": "gasto", "entrada": "entrada", "entradas": "entrada",
             "transferencia": "transferencia", "transferencias": "transferencia",
             "transferência": "transferencia", "transferências": "transferencia",
             "estorno": "estorno", "estornos": "estorno", "bank": "conta_bank", "credit": "conta_credit"}
    contagens.update((int(n), f"tipo:{tipos[t.casefold()]}") for n, t in CONTAGEM_TIPO.findall(texto))
    return {"valores_centavos": valores, "datas": datas, "contagens": contagens}


def comparar(referencia: str, resposta: str) -> bool | None:
    """CSV antigo: passa se todos os fatos do gabarito estiverem na resposta (fatos a mais não reprovam)."""
    esperado, obtido = fatos(referencia), fatos(resposta)
    if not any(esperado.values()):
        return None
    return all(esperado[k] <= obtido[k] for k in esperado)


def carregar_casos(caminho: Path) -> list[dict]:
    if caminho.suffix == ".jsonl":
        casos = [json.loads(linha) for linha in caminho.read_text(encoding="utf-8").splitlines() if linha.strip()]
        for caso in casos:
            if not caso.get("pergunta") or not caso.get("sql") or not caso.get("fatos"):
                raise ValueError("cada caso precisa de pergunta, sql e fatos")
        return casos
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


# ------------------------------------------------------------------ execução
def avaliar_caso(caso: dict, hoje: date) -> tuple[str, str, str, str]:
    """Devolve (estado, detalhe, referência em texto, resposta do agente)."""
    if "sql" in caso:
        try:
            esperados = gabarito(caso)
        except Exception as erro:
            return "GABARITO_ERRO", str(erro)[:120], "", ""
        if not esperados:
            return "GABARITO_VAZIO", "o SQL de referência não devolveu fatos", "", ""
        referencia = "; ".join(descrever(t, v) for t, v in esperados)
        resposta = agente.responder_detalhado(caso["pergunta"], hoje, log_detalhes=False)["resposta"]
        falta = faltando(esperados, resposta)
        if falta:
            return "FATOS_FALTANDO", "falta: " + "; ".join(falta), referencia, resposta
        return "FATOS_OK", "", referencia, resposta
    referencia = caso["resposta"]
    resposta = agente.responder_detalhado(caso["pergunta"], hoje, log_detalhes=False)["resposta"]
    correto = comparar(referencia, resposta)
    if correto is None:
        return "REVISÃO", "", referencia, resposta
    return ("FATOS_OK" if correto else "FATOS_FALTANDO"), "", referencia, resposta


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--casos", "--csv", dest="casos", type=Path, default=CASOS_PADRAO,
                        help="benchmark/casos.jsonl (padrão) ou o CSV antigo com pergunta e resposta")
    parser.add_argument("--hoje", type=date.fromisoformat, default=date(2026, 11, 25),
                        help="data usada nos prompts (padrão: data do snapshot de referência)")
    parser.add_argument("--juiz-llm", action="store_true",
                        help="envia pergunta, gabarito e resposta ao Gemini para avaliação textual")
    parser.add_argument("--so-gabarito", action="store_true",
                        help="só mostra o gabarito gerado pelo SQL de referência, sem chamar o agente")
    parser.add_argument("--mostrar-respostas", action="store_true", help="mostra a resposta de cada caso que falhou")
    args = parser.parse_args()

    casos = carregar_casos(args.casos)
    if args.so_gabarito:
        for caso in casos:
            print(f"{id_caso(caso['pergunta'])}  {caso['pergunta']}\n    "
                  + "; ".join(descrever(t, v) for t, v in gabarito(caso)))
        return 0

    acertos = avaliaveis = falhas = 0
    juiz_acertos = juiz_total = 0
    for caso in casos:
        identificador = id_caso(caso["pergunta"])
        try:
            estado, detalhe, referencia, resposta = avaliar_caso(caso, args.hoje)
        except Exception as erro:
            estado, detalhe, referencia, resposta = f"FALHA_{type(erro).__name__}", str(erro)[:120], "", ""
            falhas += 1
        if estado in ("FATOS_OK", "FATOS_FALTANDO") or estado.startswith("FALHA_"):
            avaliaveis += 1
            acertos += estado == "FATOS_OK"
        if args.juiz_llm and referencia and resposta:
            juiz_total += 1
            try:
                aprovado = julgar(caso["pergunta"], referencia, resposta)
                juiz_acertos += aprovado
                estado += f" JUIZ_{'OK' if aprovado else 'DIVERGE'}"
            except Exception as erro:
                estado += f" JUIZ_FALHA_{type(erro).__name__}"
        linha = f"{estado:16} {identificador}  {caso['pergunta'][:70]}"
        if detalhe:
            linha += f"\n{'':16} {detalhe}"
        if args.mostrar_respostas and estado != "FATOS_OK" and resposta:
            linha += f"\n{'':16} resposta: {' '.join(resposta.split())[:300]}"
        print(linha, flush=True)

    taxa = f"{acertos}/{avaliaveis} ({100 * acertos / avaliaveis:.0f}%)" if avaliaveis else "n/a"
    print(f"\nAcerto de fatos: {taxa}; falhas do agente: {falhas}; casos: {len(casos)}")
    if args.juiz_llm:
        print(f"Juiz LLM: {juiz_acertos}/{juiz_total} aprovadas (métrica complementar)")
    print(f"Data de referência: {args.hoje.isoformat()}")
    return 0 if avaliaveis and acertos == avaliaveis else 1


if __name__ == "__main__":
    raise SystemExit(main())
