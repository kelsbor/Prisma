"""Chamadas do orquestrador aos agentes do Prisma, sempre por MCP: uma ferramenta por agente.

- Especialista e Indicadores: pelo comum/cliente_mcp.py (HTTP se ESPECIALISTA_URL / INDICADORES_URL
  estiverem definidas, como no prisma.sh; senão sobe o agente por stdio).
- agente-sql: sobe ../agente-sql/servidor_mcp.py por stdio (ele não tem modo HTTP), com o mesmo .env.

Cada chamada devolve um Resultado com:
- texto: a resposta do agente;
- evidencias: o que o próprio agente devolveu como base da resposta, para o guardião conferir
  (agente-sql: linhas do SQL; Indicadores: os dados do Banco Central; Especialista: 'evidencias',
  com os trechos, o resumo do mês e as taxas que entraram no prompt);
- alternativa: o que mostrar se o guardião descartar o texto.
Erros não derrubam o orquestrador: viram um Resultado com ok=False.
"""

import asyncio
import os
import sys
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from comum.cliente_mcp import ClienteMCP, conectar
from comum.config import RAIZ, log

SQL_DIR = Path(os.getenv("PRISMA_SQL_DIR") or RAIZ.parent / "agente-sql").expanduser().resolve()
TIMEOUT_AGENTE_S = float(os.getenv("PRISMA_TIMEOUT_AGENTE_S") or "120")

NOMES = {"dados": "agente-sql", "conceitos": "Especialista", "indicadores": "Indicadores"}
MSG_SEM_CONFIRMACAO = "Não consegui confirmar os números dessa resposta."


@dataclass
class Resultado:
    destino: str                 # dados | conceitos | indicadores
    ok: bool
    texto: str
    fontes: list[str] = field(default_factory=list)
    evidencias: list = field(default_factory=list)
    alternativa: str = ""
    detalhes: dict = field(default_factory=dict)

    def como_dict(self) -> dict:
        return asdict(self)


@asynccontextmanager
async def _conectar_sql():
    if not (SQL_DIR / "servidor_mcp.py").exists():
        raise RuntimeError(f"Não encontrei o agente-sql em {SQL_DIR} (defina PRISMA_SQL_DIR).")
    env = {**os.environ}
    env.setdefault("PRISMA_ENV_FILE", str(RAIZ / ".env"))
    params = StdioServerParameters(
        command=os.getenv("PRISMA_SQL_PYTHON") or sys.executable,
        args=[str(SQL_DIR / "servidor_mcp.py")], cwd=str(SQL_DIR), env=env,
    )
    async with stdio_client(params) as (leitura, escrita):
        async with ClientSession(leitura, escrita) as sessao:
            await sessao.initialize()
            yield ClienteMCP(sessao, "agente-sql (stdio)")


async def _chamar(agente: str, ferramenta: str, argumentos: dict) -> dict:
    conexao = _conectar_sql() if agente == "agente-sql" else conectar(agente)
    async with conexao as cliente:
        return await cliente.chamar(ferramenta, argumentos)


# ------------------------------------------------------------------ texto em tabela
def tabela_em_texto(colunas: list, linhas: list, maximo: int = 20) -> str:
    def celula(c):
        if isinstance(c, float):
            return f"{c:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return "-" if c is None else str(c)

    if not linhas:
        return "(nenhum registro)"
    texto = [" | ".join(map(str, colunas))]
    texto += [" | ".join(celula(c) for c in linha) for linha in linhas[:maximo]]
    if len(linhas) > maximo:
        texto.append(f"... e mais {len(linhas) - maximo} linhas")
    return "\n".join(texto)


# ------------------------------------------------------------------ um formatador por agente
def _de_sql(r: dict) -> Resultado:
    if "erro" in r:
        return Resultado("dados", False, r["erro"])
    dados = r.get("dados") or {}
    if r.get("status", "sucesso") != "sucesso" or "linhas" not in dados:
        return Resultado("dados", False, r.get("resposta", ""), detalhes={"status": r.get("status")})
    alternativa = f"{MSG_SEM_CONFIRMACAO} Este é o resultado da consulta:\n" + \
        tabela_em_texto(dados.get("colunas", []), dados["linhas"])
    return Resultado("dados", True, r.get("resposta", ""), evidencias=[dados["linhas"]], alternativa=alternativa,
                     detalhes={"status": r.get("status"), "sql": r.get("sql")})


def _trechos_em_texto(trechos: list) -> str:
    return "\n".join(f"- {t['texto'][:400]} ({t['fonte']}, p. {t['pagina']})" for t in trechos[:3])


def _de_especialista(r: dict) -> Resultado:
    if "erro" in r:
        return Resultado("conceitos", False, r["erro"])
    ev = r.get("evidencias") or {}
    trechos = ev.get("trechos") or r.get("trechos") or []
    gerado = r.get("gerado_por") == "gemini"
    texto = r.get("resposta", "")
    if not gerado and r.get("trechos"):                    # sem Gemini: o próprio agente devolve os trechos
        texto += "\n" + _trechos_em_texto(r["trechos"])
    alternativa = MSG_SEM_CONFIRMACAO + (" Estes são os trechos mais próximos da sua pergunta:\n"
                                         + _trechos_em_texto(trechos) if trechos else "")
    # Evidências = o que entrou no prompt do Especialista (trechos, resumo do mês, taxas do Banco Central).
    evidencias = [[t["texto"] for t in trechos], [t["texto"] for t in r.get("trechos") or []],
                  ev.get("dados_do_usuario"), ev.get("indicadores")]
    return Resultado("conceitos", gerado or bool(r.get("trechos")), texto, fontes=r.get("fontes", []),
                     evidencias=[e for e in evidencias if e], alternativa=alternativa,
                     detalhes={"gerado_por": r.get("gerado_por")})


def _de_indicadores(acao: str, r: dict) -> Resultado:
    if "erro" in r:
        return Resultado("indicadores", False, r["erro"])
    if acao == "juros_do_credito":
        texto = "\n".join(r.get("resumo", [])) or "Sem dados do Banco Central agora."
    elif acao == "simular_custo":
        texto = f"{r['texto']} {r.get('observacao', '')}".strip()
    elif acao == "historico":
        pontos = ", ".join(f"{p['referencia']}: {p['valor']:.2f}".replace(".", ",") for p in r.get("pontos", []))
        texto = f"{r['nome']} ({r['unidade']}): {pontos}"
    else:                                                 # indicador
        texto = f"{r['texto']} ({r['referencia']}). {r.get('explicacao', '').capitalize()}.".replace("..", ".")
        if r.get("aviso"):
            texto += f" {r['aviso']}"
    return Resultado("indicadores", True, texto, fontes=[r.get("fonte", "Banco Central do Brasil")],
                     evidencias=[r], alternativa=MSG_SEM_CONFIRMACAO)


# ------------------------------------------------------------------ chamada com proteção
async def consultar(destino: str, pergunta: str, pedido_indicadores: dict | None = None,
                    usar_meus_dados: bool = False) -> Resultado:
    """Chama o agente certo para o destino e devolve um Resultado (nunca levanta exceção)."""
    try:
        if destino == "dados":
            r = await asyncio.wait_for(_chamar("agente-sql", "consultar_financas", {"pergunta": pergunta}),
                                       TIMEOUT_AGENTE_S)
            return _de_sql(r)
        if destino == "conceitos":
            r = await asyncio.wait_for(_chamar("especialista", "perguntar",
                                               {"pergunta": pergunta, "usar_meus_dados": usar_meus_dados}),
                                       TIMEOUT_AGENTE_S)
            return _de_especialista(r)
        if destino == "indicadores":
            pedido = pedido_indicadores or {"acao": "juros_do_credito"}
            acao = pedido.get("acao") or "juros_do_credito"
            argumentos = {
                "juros_do_credito": {},
                "indicador": {"nome": pedido.get("nome") or "selic"},
                "historico": {"nome": pedido.get("nome") or "selic", "n": pedido.get("meses") or 12},
                "simular_custo": {"valor": pedido.get("valor"), "modalidade": pedido.get("modalidade"),
                                  "meses": pedido.get("meses") or 3},
            }[acao]
            if acao == "simular_custo" and (not argumentos["valor"] or not argumentos["modalidade"]):
                acao, argumentos = "juros_do_credito", {}  # faltou valor ou modalidade: mostra as taxas
            r = await asyncio.wait_for(_chamar("indicadores", acao, argumentos), TIMEOUT_AGENTE_S)
            return _de_indicadores(acao, r)
        return Resultado(destino, False, f"Destino desconhecido: {destino}")
    except asyncio.TimeoutError:
        log("orquestrador", f"{NOMES.get(destino, destino)} demorou mais de {TIMEOUT_AGENTE_S:.0f} s")
        return Resultado(destino, False, f"O {NOMES.get(destino, destino)} demorou demais para responder.")
    except Exception as e:  # agente fora do ar, dependência faltando, erro da ferramenta...
        log("orquestrador", f"{NOMES.get(destino, destino)} falhou: {type(e).__name__}: {e}")
        return Resultado(destino, False, f"O {NOMES.get(destino, destino)} não está disponível agora.")
