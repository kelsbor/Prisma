"""Agente de Consultas: perguntas em português sobre as transações do PrismaAPP, respondidas com SQL.

Reaproveita o assistente text-to-SQL do PrismaAPP (PrismaAPP/agent/src/prisma_agent): o mesmo prompt,
os mesmos exemplos, o mesmo filtro de manipulação e a mesma validação de SQL. O que o app faz no celular
(executar o SQL somente leitura e conferir os valores da resposta) é feito aqui, em Python, sobre uma
cópia do banco do app (prisma.db) exportada do aparelho.

Fluxo, igual ao do app:
  pergunta → filtro de manipulação → Gemini escreve o SQL → validação (sqlglot) → execução SOMENTE
  LEITURA (até 200 linhas, 3 s; 1 correção se der erro) → Gemini redige → todo "R$" citado precisa
  existir no resultado, senão a resposta é descartada.
"""

import os
import re
import sqlite3
import sys
import time
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from comum.config import RAIZ

SRC_APP = Path(os.getenv("PRISMA_APP_AGENT_SRC") or RAIZ.parent / "PrismaAPP" / "agent" / "src").expanduser()
from comum.config import BANCO_APP  # noqa: E402  (mesmo banco da Pluggy para todos os agentes)
MAX_LINHAS, TIMEOUT_S, LINHAS_PARA_O_MODELO, MAX_CELULA = 200, 3.0, 50, 200

# Mensagens iguais às do servidor do PrismaAPP (agent/src/prisma_agent/api.py)
MSG_BLOQUEADO = "Não posso atender esse pedido. Pergunte sobre seus gastos, entradas ou compras."
MSG_FORA = "Só consigo responder perguntas sobre as suas transações no app, como gastos, entradas, categorias e compras."
MSG_SEM_DADOS = "Não sei responder isso: essa informação não está nos seus dados do app."
MSG_NAO_SEI = "Não sei responder isso com segurança. Tente perguntar de outro jeito."
MSG_VAZIO = "Não encontrei registros para essa pergunta."
MSG_SEM_CONFIANCA = "Não sei responder isso com os dados que encontrei."


class ErroConsulta(Exception):
    pass


def biblioteca_do_app():
    """Importa o prisma_agent do PrismaAPP (fonte única do prompt e das regras de segurança)."""
    if not (SRC_APP / "prisma_agent").exists():
        raise RuntimeError(f"Não encontrei o assistente do PrismaAPP em {SRC_APP}. "
                           "Defina PRISMA_APP_AGENT_SRC com o caminho de PrismaAPP/agent/src.")
    if str(SRC_APP) not in sys.path:
        sys.path.insert(0, str(SRC_APP))
    from prisma_agent import guard, schemas
    return guard, schemas


# ------------------------------------------------------------------ banco do app, somente leitura
def _conectar() -> sqlite3.Connection:
    if not BANCO_APP.exists():
        raise ErroConsulta(f"Banco da Pluggy não encontrado em {BANCO_APP}. Rode ./prisma.sh pluggy "
                           "(ou copie o prisma.db do celular para essa pasta).")
    con = sqlite3.connect(f"file:{BANCO_APP}?mode=ro", uri=True, timeout=TIMEOUT_S)
    con.execute("PRAGMA query_only = 1")
    return con


def contexto() -> dict:
    """Categorias, contas e bancos existentes: ajudam o modelo a usar os nomes exatos (como no app)."""
    with _conectar() as con:
        def distintos(coluna, limite):
            return [str(r[0])[:120] for r in con.execute(
                f"SELECT DISTINCT {coluna} FROM vw_registers WHERE {coluna} IS NOT NULL ORDER BY 1 LIMIT {limite}")]
        return {"categorias": distintos("categoria", 300), "contas": distintos("conta", 30),
                "bancos": distintos("banco", 10)}


def executar(sql: str, max_linhas: int = MAX_LINHAS, timeout_s: float = TIMEOUT_S) -> dict:
    """Executa um SQL já validado; o LIMIT externo vale mesmo que o SQL não tenha LIMIT."""
    fim = time.monotonic() + timeout_s
    with _conectar() as con:
        con.set_progress_handler(lambda: 1 if time.monotonic() > fim else 0, 10_000)
        try:
            cur = con.execute(f"SELECT * FROM ({sql}) LIMIT {max_linhas + 1}")
            linhas = cur.fetchall()
        except sqlite3.OperationalError as e:
            raise ErroConsulta("A consulta demorou demais." if "interrupted" in str(e) else str(e)[:200]) from None
        colunas = [d[0][:64] for d in cur.description]
    truncado = len(linhas) > max_linhas
    linhas = [[(c[:MAX_CELULA] if isinstance(c, str) else c) for c in linha] for linha in linhas[:max_linhas]]
    return {"colunas": colunas, "linhas": linhas, "truncado": truncado}


# ------------------------------------------------------------------ guardião da resposta (AnswerGuardian.kt)
_DINHEIRO = re.compile(r"R\$\s?-?\s?(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{1,2}))?")


def resposta_fundamentada(texto: str, linhas: list[list]) -> bool:
    """Todo valor em R$ citado precisa existir no resultado (em reais, ou em centavos nas colunas inteiras)."""
    citados = [Decimal(f"{m[1].replace('.', '')}.{(m[2] or '').ljust(2, '0')}") for m in _DINHEIRO.finditer(texto)]
    if not citados:
        return True
    permitidos = set()
    for linha in linhas:
        for c in linha:
            if isinstance(c, bool) or not isinstance(c, (int, float)):
                continue
            v = Decimal(str(c)).copy_abs()
            permitidos.add(v.quantize(Decimal("0.01"), ROUND_HALF_UP))
            if isinstance(c, int):
                permitidos.add((v / 100).quantize(Decimal("0.01"), ROUND_HALF_UP))
    return all(c.quantize(Decimal("0.01")) in permitidos for c in citados)


# ------------------------------------------------------------------ orquestração (AssistantOrchestrator.kt)
def _modelos():
    if not os.getenv("GOOGLE_API_KEY"):
        raise RuntimeError("GOOGLE_API_KEY não definida")
    biblioteca_do_app()
    from prisma_agent.chains import criar_gerador, criar_redator
    from prisma_agent.config import DEFAULT_MODEL, Settings
    s = Settings(google_api_key=os.environ["GOOGLE_API_KEY"],
                 gemini_model=os.getenv("PRISMA_MODELO_LLM") or os.getenv("GEMINI_MODEL") or DEFAULT_MODEL, app_tokens=frozenset(),
                 per_minute=0, questions_per_day=0, llm_timeout_s=float(os.getenv("LLM_TIMEOUT_S") or "40"))
    return criar_gerador(s), criar_redator(s)


def perguntar(pergunta: str, gerador=None, redator=None, hoje: date | None = None) -> dict:
    guard, schemas = biblioteca_do_app()
    hoje = hoje or date.today()
    entrada = guard.verificar_pergunta(pergunta)
    if entrada.bloqueada:
        return {"status": "bloqueado", "resposta": MSG_BLOQUEADO}
    if gerador is None or redator is None:
        try:
            gerador, redator = _modelos()
        except Exception as e:
            return {"status": "indisponivel", "resposta": f"Assistente indisponível: {e}"}

    req = schemas.GerarSqlRequest(pergunta=entrada.texto, hoje=hoje, contexto=schemas.Contexto(**contexto()))
    resultado, sql = None, None
    for _ in range(2):                                   # 1 tentativa + 1 correção, como no app
        decisao = gerador(req, entrada.texto)
        if decisao.classificacao == "fora_do_escopo":
            return {"status": "fora_do_escopo", "resposta": MSG_FORA}
        if decisao.classificacao == "sem_dados" or not decisao.sql:
            return {"status": "nao_sei", "resposta": MSG_SEM_DADOS}
        try:
            sql = guard.validar_sql(decisao.sql)
            resultado = executar(sql)
            break
        except (guard.SqlRejeitado, ErroConsulta) as e:
            req = req.model_copy(update={"erro_anterior": schemas.ErroAnterior(sql=decisao.sql[:4000], erro=str(e)[:300])})
    if resultado is None:
        return {"status": "nao_sei", "resposta": MSG_NAO_SEI}

    base = {"sql": sql, "colunas": resultado["colunas"], "linhas": resultado["linhas"][:LINHAS_PARA_O_MODELO],
            "total_linhas": len(resultado["linhas"]), "truncado": resultado["truncado"]}
    if not resultado["linhas"] or all(c is None for linha in resultado["linhas"] for c in linha):
        return {"status": "nao_sei", "resposta": MSG_VAZIO, **base}

    rreq = schemas.ResponderRequest(pergunta=entrada.texto, hoje=hoje, sql=sql, colunas=base["colunas"],
                                    linhas=base["linhas"], total_linhas=base["total_linhas"])
    redacao = redator(rreq, entrada.texto)
    texto = (redacao.resposta or "").replace("**", "").replace("__", "").strip()
    if not redacao.responde_a_pergunta or not texto:
        return {"status": "nao_sei", "resposta": MSG_SEM_CONFIANCA, **base}
    if not resposta_fundamentada(texto, resultado["linhas"]):
        return {"status": "nao_sei", "resposta": MSG_SEM_CONFIANCA + " (a resposta citava um valor que não está nos dados)",
                **base}
    return {"status": "ok", "resposta": texto[:1200], **base}


def status() -> dict:
    info = {"banco": str(BANCO_APP), "existe": BANCO_APP.exists(), "assistente_do_app": str(SRC_APP),
            "assistente_encontrado": (SRC_APP / "prisma_agent").exists()}
    if info["existe"]:
        try:
            with _conectar() as con:
                n, ini, fim = con.execute("SELECT COUNT(*), MIN(data), MAX(data) FROM vw_registers").fetchone()
            info.update({"transacoes": n, "de": ini, "ate": fim})
        except Exception as e:
            info["erro"] = str(e)[:200]
    return info
