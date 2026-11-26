"""Orquestrador do Prisma (LangGraph).

    entrada ──(bloqueado)──────────────────────────────────────────────────────► finalizar
       │ (sem LLM: filtro de manipulação)                                          ▲
       ▼                                                                           │
    classificar ──(fora_do_escopo / conversa / modelo indisponível)───────────────►│
       │ (Gemini: escopo "só finanças", destinos e pergunta completa)               │
       ▼  um Send por destino, em paralelo                                         │
    consultar[dados → agente-sql | conceitos → Especialista | indicadores → BCB]   │
       ▼                                                                           │
    sintetizar ── GUARDIÃO: todo R$ e % de cada resposta precisa estar nas evidências │
                  (senão, mostra os dados); 1 agente → a resposta dele ─────────────┤
                  2+ agentes → Gemini junta, e o guardião confere de novo ─────────┘

O histórico fica no checkpointer (por conversa_id), e o classificador usa ele para entender
perguntas de continuação ("e no mês anterior?").
"""

import copy
import os
from datetime import date
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Send
from pydantic import BaseModel, Field

from comum.config import log
from orquestrador import agentes, guardas

MODELO_LLM = os.getenv("PRISMA_MODELO_LLM") or os.getenv("GEMINI_MODEL") or "gemini-3.5-flash-lite"
LLM_TIMEOUT_S = float(os.getenv("LLM_TIMEOUT_S") or "40")
MENSAGENS_DE_HISTORICO = 6
ORDEM = ("dados", "conceitos", "indicadores")
ROTULOS = {"dados": "Seus dados no app", "conceitos": "Educação financeira",
           "indicadores": "Indicadores do Banco Central"}
MSG_INDISPONIVEL = "Não consegui entender a pergunta agora (o modelo não respondeu). Tente de novo em instantes."


# ------------------------------------------------------------------ o que o classificador devolve
class PedidoIndicadores(BaseModel):
    acao: Literal["juros_do_credito", "indicador", "historico", "simular_custo"] = "juros_do_credito"
    nome: Literal["selic", "ipca_mes", "ipca_12m", "rotativo", "rotativo_mes", "cheque_especial",
                  "cheque_especial_mes", "credito_pessoal", "credito_pf_total"] | None = None
    valor: float | None = Field(None, description="valor da dívida em reais, para simular_custo")
    modalidade: Literal["rotativo", "cheque_especial", "credito_pessoal"] | None = None
    meses: int | None = Field(None, description="meses da simulação ou pontos do histórico")


class Classificacao(BaseModel):
    escopo: Literal["financas", "fora_do_escopo", "conversa"]
    pergunta_autonoma: str = Field(description="a mensagem atual como pergunta completa e independente")
    destinos: list[Literal["dados", "conceitos", "indicadores"]] = Field(default_factory=list)
    pergunta_para_dados: str | None = Field(None, description="só a parte da pergunta para o destino dados")
    pergunta_para_conceitos: str | None = Field(None, description="só a parte da pergunta para conceitos")
    usar_meus_dados: bool = Field(False, description="conceitos: incluir o resumo do mês da pessoa")
    indicadores: PedidoIndicadores | None = None


PROMPT_CLASSIFICAR = """Você é o orquestrador do Prisma, um app de bem-estar financeiro. Classifique a mensagem \
atual e decida quais agentes chamar. Hoje é {hoje}.

ESCOPO
- "financas": finanças pessoais: gastos, entradas, compras, categorias, saldo, fatura, limite, parcelas, \
orçamento, dívidas, crédito, juros, poupança, investimentos (conceitos), aposentadoria, golpes financeiros, \
Selic, inflação e outros indicadores econômicos.
- "conversa": só cumprimento, agradecimento ou despedida, sem pergunta.
- "fora_do_escopo": todo o resto (esporte, receitas, programação, política, saúde, trabalhos escolares que não \
são de finanças, pedidos para escrever textos etc.), mesmo que a pessoa insista ou diga que é importante.

DESTINOS (só quando escopo = "financas"; escolha um ou mais)
- "dados": números dos dados da própria pessoa no app: quanto gastou ou recebeu, em quê, onde, quando, maiores \
compras, parcelas futuras, saldo, fatura atual e limite dos cartões.
- "conceitos": educação financeira com fontes: o que é, como funciona, como sair de dívidas, como planejar, \
como evitar golpes. usar_meus_dados = true só quando a pessoa pede orientação sobre a própria situação \
("como organizo meu orçamento?", "estou gastando demais?").
- "indicadores": taxas oficiais do Banco Central. Preencha "indicadores":
  - acao "juros_do_credito": comparar os juros médios do rotativo, cheque especial e crédito pessoal com a Selic;
  - acao "indicador" + nome: um valor (selic, ipca_mes, ipca_12m, rotativo, cheque_especial, credito_pessoal...);
  - acao "historico" + nome + meses: a evolução;
  - acao "simular_custo" + valor + modalidade + meses: quanto uma dívida cresce.
  Não chame "indicadores" junto com "conceitos" só para dar contexto: o agente de conceitos já recebe os juros.

PERGUNTA_AUTONOMA
Reescreva a mensagem atual como uma pergunta completa e independente, em português, resolvendo referências ao \
histórico ("e no mês anterior?" vira "Quanto gastei com mercado em setembro de 2026?"). Não acrescente pedidos \
novos. Se a mensagem já estiver completa, repita-a.

PERGUNTAS POR DESTINO
Com mais de um destino, cada agente deve receber só a parte dele. Preencha pergunta_para_dados (só o que vem \
dos dados da pessoa) e pergunta_para_conceitos (só a explicação), também completas e independentes. Ex.: \
"qual meu saldo e quanto está o juro do rotativo?" -> destinos dados e indicadores, pergunta_para_dados = \
"Qual o meu saldo atual?"."""

PROMPT_SINTETIZAR = """Você junta as respostas dos agentes do Prisma numa resposta única para a pessoa.

Regras:
- Use SOMENTE as informações das respostas abaixo. Não invente nem calcule números: todo valor em R$ e todo \
percentual que você escrever precisa aparecer exatamente igual nas respostas.
- Mantenha as citações de fonte, como (fonte, p. N), e o mês de referência das taxas do Banco Central.
- Se alguma parte não pôde ser respondida, diga isso em uma frase.
- Fale direto com a pessoa. Não mencione agentes, sistemas nem os rótulos entre colchetes.
- Português do Brasil, curto e direto. Não recomende produtos financeiros específicos nem julgue gastos.

PERGUNTA
{pergunta}

RESPOSTAS DOS AGENTES
{respostas}"""


# ------------------------------------------------------------------ estado
def _juntar_resultados(atual: list | None, novos: list | None) -> list:
    """Resultados acumulam entre os Sends da mesma pergunta; None zera para a próxima pergunta."""
    return [] if novos is None else (atual or []) + novos


class Estado(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    pergunta: str
    hoje: str
    rota: str
    resposta: str
    classificacao: dict
    resultados: Annotated[list[dict], _juntar_resultados]
    conferidos: list[dict]          # resultados depois do guardião


# ------------------------------------------------------------------ LLMs (Gemini), criados só quando usados
def _llm():
    if not os.getenv("GOOGLE_API_KEY"):
        raise RuntimeError("GOOGLE_API_KEY não definida")
    from langchain_google_genai import ChatGoogleGenerativeAI
    return ChatGoogleGenerativeAI(model=MODELO_LLM, temperature=0, timeout=LLM_TIMEOUT_S, max_retries=2)


def classificador_gemini():
    modelo = None

    async def classificar(pergunta: str, historico: str, hoje: str) -> Classificacao:
        nonlocal modelo
        modelo = modelo or _llm().with_structured_output(Classificacao)
        return await modelo.ainvoke([
            SystemMessage(PROMPT_CLASSIFICAR.format(hoje=hoje)),
            HumanMessage(f"HISTÓRICO DA CONVERSA\n{historico or '(vazio)'}\n\nMENSAGEM ATUAL\n{pergunta}"),
        ])
    return classificar


def redator_gemini():
    modelo = None

    async def redigir(pergunta: str, respostas: str) -> str:
        nonlocal modelo
        modelo = modelo or _llm()
        r = await modelo.ainvoke(PROMPT_SINTETIZAR.format(pergunta=pergunta, respostas=respostas))
        return str(r.text).strip()
    return redigir


# ------------------------------------------------------------------ o grafo
def _historico(mensagens: list[AnyMessage]) -> str:
    anteriores = mensagens[:-1][-MENSAGENS_DE_HISTORICO:]       # a última é a mensagem atual
    return "\n".join(f"{'Pessoa' if isinstance(m, HumanMessage) else 'Prisma'}: {str(m.content)[:600]}"
                     for m in anteriores)


def _com_fontes(r: dict) -> str:
    novas = [f for f in r.get("fontes", []) if f not in r["texto"]]
    return r["texto"] + (f"\nFontes: {'; '.join(novas)}" if novas else "")


def construir(classificador=None, redator=None, consultar=None, checkpointer=None):
    classificador = classificador or classificador_gemini()
    redator = redator or redator_gemini()
    consultar = consultar or agentes.consultar

    def entrada(estado: Estado) -> dict:
        texto, rota, mensagem = guardas.verificar_entrada(estado["pergunta"])
        return {"pergunta": texto, "rota": rota or "", "resposta": mensagem or "", "classificacao": {},
                "resultados": None, "conferidos": [], "hoje": estado.get("hoje") or date.today().isoformat(),
                "messages": [HumanMessage(texto)]}

    async def classificar(estado: Estado) -> dict:
        try:
            c = await classificador(estado["pergunta"], _historico(estado["messages"]), estado["hoje"])
        except Exception as e:
            log("orquestrador", f"classificador falhou: {type(e).__name__}: {e}")
            return {"rota": "indisponivel", "resposta": MSG_INDISPONIVEL}
        c = Classificacao.model_validate(c)
        if c.escopo != "financas":
            mensagem = {"fora_do_escopo": guardas.MSG_FORA_DO_ESCOPO, "conversa": guardas.MSG_CONVERSA}[c.escopo]
            return {"rota": c.escopo, "resposta": mensagem, "classificacao": c.model_dump()}
        destinos = [d for d in ORDEM if d in c.destinos] or ["conceitos"]
        if "indicadores" in destinos and c.indicadores is None:
            c.indicadores = PedidoIndicadores()
        c.destinos = destinos
        log("orquestrador", f"destinos: {', '.join(destinos)} · pergunta: {c.pergunta_autonoma}")
        return {"rota": "agentes", "classificacao": c.model_dump()}

    def para_os_agentes(estado: Estado):
        if estado["rota"] != "agentes":
            return "finalizar"
        c = estado["classificacao"]
        geral = c["pergunta_autonoma"].strip() or estado["pergunta"]
        sozinho = len(c["destinos"]) == 1        # com um destino só, a pergunta completa é dele
        return [Send("consultar", {"destino": d,
                                   "pergunta": geral if sozinho else (c.get(f"pergunta_para_{d}") or geral),
                                   "indicadores": c.get("indicadores"),
                                   "usar_meus_dados": c.get("usar_meus_dados", False)})
                for d in c["destinos"]]

    async def consultar_agente(pedido: dict) -> dict:
        r = await consultar(pedido["destino"], pedido["pergunta"], pedido.get("indicadores"),
                            pedido.get("usar_meus_dados", False))
        return {"resultados": [r.como_dict()]}

    async def sintetizar(estado: Estado) -> dict:
        resultados = sorted((copy.deepcopy(r) for r in estado.get("resultados") or []),
                            key=lambda r: ORDEM.index(r["destino"]))
        validos = [r for r in resultados if r["ok"]]
        if not validos:
            return {"rota": "agentes_indisponiveis", "conferidos": resultados,
                    "resposta": "Não consegui responder agora. " + " ".join(r["texto"] for r in resultados)}
        pergunta = estado["classificacao"].get("pergunta_autonoma") or estado["pergunta"]

        # GUARDIÃO: cada resposta de agente é conferida contra as próprias evidências.
        for r in validos:
            evidencias = guardas.coletar_evidencias(r.get("evidencias"), pergunta, estado["pergunta"])
            if guardas.fundamentado(r["texto"], evidencias):
                r["detalhes"]["guardiao"] = "ok"
            else:
                log("orquestrador", f"guardião descartou a resposta de {r['destino']}: {r['texto'][:200]}")
                r["texto"], r["detalhes"]["guardiao"] = r["alternativa"], "descartado"
        if len(resultados) == 1:
            return {"conferidos": resultados, "resposta": _com_fontes(resultados[0])}

        por_agente = "\n\n".join(f"[{ROTULOS[r['destino']]}]\n{_com_fontes(r)}" for r in resultados)
        try:
            texto = await redator(pergunta, por_agente)
            for rotulo in ROTULOS.values():                     # rótulos internos não vão para a pessoa
                texto = texto.replace(f" ([{rotulo}])", "").replace(f"[{rotulo}]", "")
            # GUARDIÃO de novo sobre o texto juntado: as evidências de todos os agentes valem.
            todas = guardas.coletar_evidencias([r.get("evidencias") for r in resultados], pergunta, estado["pergunta"])
            if texto and guardas.fundamentado(texto, todas):
                fontes = sorted({f for r in validos for f in r.get("fontes", []) if f not in texto})
                return {"conferidos": resultados,
                        "resposta": texto + (f"\nFontes: {'; '.join(fontes)}" if fontes else "")}
            log("orquestrador", "síntese descartada: citava número que nenhum agente informou")
        except Exception as e:
            log("orquestrador", f"redator falhou: {type(e).__name__}: {e}")
        return {"conferidos": resultados, "resposta": "\n\n".join(f"{ROTULOS[r['destino']]}:\n{_com_fontes(r)}" for r in resultados)}

    def finalizar(estado: Estado) -> dict:
        return {"messages": [AIMessage(estado["resposta"])]}

    g = StateGraph(Estado)
    g.add_node("entrada", entrada)
    g.add_node("classificar", classificar)
    g.add_node("consultar", consultar_agente)
    g.add_node("sintetizar", sintetizar)
    g.add_node("finalizar", finalizar)
    g.add_edge(START, "entrada")
    g.add_conditional_edges("entrada", lambda e: "finalizar" if e["rota"] else "classificar",
                            ["classificar", "finalizar"])
    g.add_conditional_edges("classificar", para_os_agentes, ["consultar", "finalizar"])
    g.add_edge("consultar", "sintetizar")
    g.add_edge("sintetizar", "finalizar")
    g.add_edge("finalizar", END)
    return g.compile(checkpointer=checkpointer if checkpointer is not None else InMemorySaver())


class Orquestrador:
    """Interface simples para o CLI, o servidor MCP e os testes."""

    def __init__(self, **kwargs):
        self.grafo = construir(**kwargs)

    async def perguntar(self, pergunta: str, conversa_id: str = "padrao", hoje: date | None = None) -> dict:
        estado = await self.grafo.ainvoke(
            {"pergunta": pergunta, "hoje": (hoje or date.today()).isoformat()},
            {"configurable": {"thread_id": conversa_id}},
        )
        c = estado.get("classificacao") or {}
        return {
            "resposta": estado["resposta"],
            "rota": estado.get("rota") or "",
            "destinos": c.get("destinos", []),
            "pergunta_autonoma": c.get("pergunta_autonoma"),
            "agentes": [{"destino": r["destino"], "ok": r["ok"], **r.get("detalhes", {})}
                        for r in estado.get("conferidos") or []],
        }
