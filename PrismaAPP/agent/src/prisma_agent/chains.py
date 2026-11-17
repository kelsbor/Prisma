"""As duas chamadas ao Gemini via LangChain: gerador de SQL e redator da resposta."""

from __future__ import annotations

import json
from typing import Protocol

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from .config import Settings
from .knowledge import prompt_gerador, prompt_redator
from .schemas import DecisaoSql, GerarSqlRequest, Redacao, ResponderRequest


class GeradorSql(Protocol):
    def __call__(self, req: GerarSqlRequest, pergunta: str) -> DecisaoSql: ...


class Redator(Protocol):
    def __call__(self, req: ResponderRequest, pergunta: str) -> Redacao: ...


def _llm(settings: Settings) -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model=settings.gemini_model,
        google_api_key=settings.google_api_key,
        timeout=settings.llm_timeout_s,
        # Sem nova tentativa automática: cada uma pode levar llm_timeout_s e estouraria o PRAZO_TOTAL_S
        # (api.py). As repetições ficam só no laço de correção da api, que controla o prazo.
        max_retries=0,
    )


def mensagem_gerador(req: GerarSqlRequest, pergunta: str) -> str:
    partes = [
        f"DATA DE HOJE: {req.hoje.isoformat()} (fuso America/Sao_Paulo)",
        "CATEGORIAS EXISTENTES: " + json.dumps(req.contexto.categorias, ensure_ascii=False),
        "CONTAS: " + json.dumps(req.contexto.contas, ensure_ascii=False),
        "BANCOS: " + json.dumps(req.contexto.bancos, ensure_ascii=False),
    ]
    if req.historico:
        conversa = [{"pergunta": t.pergunta, "sql": t.sql} for t in req.historico]
        partes.append("CONVERSA ANTERIOR (mais antiga primeiro), para entender perguntas de seguimento:\n"
                      + json.dumps(conversa, ensure_ascii=False))
    partes.append(f"<pergunta_do_usuario>\n{pergunta}\n</pergunta_do_usuario>")
    if req.erro_anterior:
        partes.append(
            "A TENTATIVA ANTERIOR FALHOU. Corrija o SQL.\n"
            f"SQL anterior: {req.erro_anterior.sql}\nErro: {req.erro_anterior.erro}"
        )
    return "\n\n".join(partes)


def mensagem_redator(req: ResponderRequest, pergunta: str) -> str:
    resultado = {
        "colunas": req.colunas,
        "linhas": req.linhas,
        "total_de_linhas": req.total_linhas,
        "linhas_enviadas": len(req.linhas),
    }
    return (
        f"DATA DE HOJE: {req.hoje.isoformat()}\n\n"
        f"<pergunta_do_usuario>\n{pergunta}\n</pergunta_do_usuario>\n\n"
        f"<sql_executado>\n{req.sql}\n</sql_executado>\n\n"
        f"<resultado>\n{json.dumps(resultado, ensure_ascii=False)}\n</resultado>"
    )


def criar_gerador(settings: Settings) -> GeradorSql:
    modelo = _llm(settings).with_structured_output(DecisaoSql)

    def gerar(req: GerarSqlRequest, pergunta: str) -> DecisaoSql:
        sistema = SystemMessage(content=prompt_gerador(req.hoje))
        return modelo.invoke([sistema, HumanMessage(content=mensagem_gerador(req, pergunta))])

    return gerar


def criar_redator(settings: Settings) -> Redator:
    modelo = _llm(settings).with_structured_output(Redacao)
    sistema = SystemMessage(content=prompt_redator())

    def redigir(req: ResponderRequest, pergunta: str) -> Redacao:
        return modelo.invoke([sistema, HumanMessage(content=mensagem_redator(req, pergunta))])

    return redigir
