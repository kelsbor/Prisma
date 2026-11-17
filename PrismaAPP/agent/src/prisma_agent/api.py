"""Servidor HTTP do assistente: POST /v1/gerar-sql e POST /v1/responder.

Rodar (a partir de agent/):  uv run uvicorn prisma_agent.api:app --app-dir src --host 127.0.0.1 --port 8000

Privacidade: nada do conteúdo (perguntas, SQL, resultados, respostas) é gravado em log;
só o nome do endpoint, o status e o tempo.
"""

from __future__ import annotations

import hmac
import logging
import time

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from .chains import GeradorSql, Redator, criar_gerador, criar_redator
from .config import Settings, load_settings
from .guard import SqlRejeitado, validar_sql, verificar_pergunta
from .ratelimit import LimiteExcedido, RateLimiter
from .schemas import (
    ErroAnterior,
    GerarSqlRequest,
    GerarSqlResponse,
    ResponderRequest,
    ResponderResponse,
    Status,
)

log = logging.getLogger("prisma_agent")

MAX_CORPO = 64 * 1024
MAX_RESPOSTA = 1200

# Prazo total de uma requisição. Precisa ficar abaixo do callTimeout do app (90 s, em AssistantModule.kt):
# se o app desistir antes, o servidor gastaria cota numa resposta que ninguém recebe.
PRAZO_TOTAL_S = 75

MSG_BLOQUEADO = "Não posso atender esse pedido. Pergunte sobre seus gastos, entradas ou compras."
MSG_FORA = "Só consigo responder perguntas sobre as suas transações no app, como gastos, entradas, categorias e compras."
MSG_SEM_DADOS = "Não sei responder isso: essa informação não está nos seus dados do app."
MSG_NAO_SEI = "Não sei responder isso com segurança. Tente perguntar de outro jeito."
MSG_VAZIO = "Não encontrei registros para essa pergunta."
MSG_SEM_CONFIANCA = "Não sei responder isso com os dados que encontrei."


class Indisponivel(Exception):
    pass


def limite_do_provedor(e: Exception) -> bool:
    """O Gemini recusou por cota (plano gratuito: poucas chamadas por minuto)."""
    return "RateLimit" in type(e).__name__ or "RESOURCE_EXHAUSTED" in str(e)


def create_app(
    settings: Settings | None = None,
    gerador: GeradorSql | None = None,
    redator: Redator | None = None,
) -> FastAPI:
    settings = settings or load_settings()
    gerador = gerador or criar_gerador(settings)
    redator = redator or criar_redator(settings)
    limiter = RateLimiter(settings.per_minute, settings.questions_per_day)

    app = FastAPI(title="Prisma Agent", docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def limites_e_log(request: Request, call_next):
        inicio = time.perf_counter()
        if request.method == "POST":
            tamanho = request.headers.get("content-length")
            if tamanho is None:
                return JSONResponse({"detail": "Content-Length obrigatório"}, status_code=411)
            if int(tamanho) > MAX_CORPO:
                return JSONResponse({"detail": "corpo grande demais"}, status_code=413)
        resposta = await call_next(request)
        log.info("%s %s -> %s (%.0f ms)", request.method, request.url.path, resposta.status_code,
                 (time.perf_counter() - inicio) * 1000)
        return resposta

    @app.exception_handler(LimiteExcedido)
    async def _limite(_: Request, e: LimiteExcedido):
        return JSONResponse({"detail": e.mensagem}, status_code=429, headers={"Retry-After": str(e.retry_after_s)})

    @app.exception_handler(Indisponivel)
    async def _indisponivel(_: Request, __: Indisponivel):
        return JSONResponse({"detail": "Assistente indisponível no momento."}, status_code=503)

    def autenticar(authorization: str = Header(default="")) -> str:
        token = authorization.removeprefix("Bearer ").strip()
        if not token or not any(hmac.compare_digest(token, t) for t in settings.app_tokens):
            raise HTTPException(status_code=401, detail="não autorizado")
        limiter.requisicao(token)
        return token

    def chamar(funcao, *args):
        try:
            return funcao(*args)
        except Exception as e:  # erro do Gemini/rede: não vazar detalhes ao cliente nem logar conteúdo
            log.warning("falha na chamada ao modelo: %s", type(e).__name__)
            if limite_do_provedor(e):
                raise LimiteExcedido("O limite de uso do Gemini foi atingido. Aguarde um minuto.", 60) from None
            raise Indisponivel() from None

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/v1/gerar-sql", response_model=GerarSqlResponse)
    def gerar_sql(req: GerarSqlRequest, token: str = Depends(autenticar)) -> GerarSqlResponse:
        if req.erro_anterior is None:  # nova pergunta (a correção após erro não conta de novo)
            limiter.pergunta(token)

        entrada = verificar_pergunta(req.pergunta)
        if entrada.bloqueada:
            return GerarSqlResponse(status=Status.bloqueado, mensagem=MSG_BLOQUEADO)

        # 1 tentativa + 1 correção. Se o próprio app já está pedindo uma correção (o SQL falhou ao
        # executar no aparelho), esta já é a segunda chance: só 1 chamada.
        tentativas = 1 if req.erro_anterior else 2
        inicio = time.monotonic()
        tentativa = req
        for i in range(tentativas):
            if i > 0 and time.monotonic() - inicio + settings.llm_timeout_s > PRAZO_TOTAL_S:
                break  # não dá tempo de corrigir antes de o app desistir; não gastar cota à toa
            decisao = chamar(gerador, tentativa, entrada.texto)
            if decisao.classificacao == "fora_do_escopo":
                return GerarSqlResponse(status=Status.fora_do_escopo, mensagem=MSG_FORA)
            if decisao.classificacao == "sem_dados" or not decisao.sql:
                return GerarSqlResponse(status=Status.nao_sei, mensagem=MSG_SEM_DADOS)
            try:
                return GerarSqlResponse(status=Status.ok, sql=validar_sql(decisao.sql))
            except SqlRejeitado as e:
                tentativa = req.model_copy(update={
                    "erro_anterior": ErroAnterior(sql=decisao.sql[:4000], erro=str(e)),
                })
        return GerarSqlResponse(status=Status.nao_sei, mensagem=MSG_NAO_SEI)

    @app.post("/v1/responder", response_model=ResponderResponse)
    def responder(req: ResponderRequest, _: str = Depends(autenticar)) -> ResponderResponse:
        try:
            validar_sql(req.sql)
        except SqlRejeitado:
            raise HTTPException(status_code=400, detail="sql inválido") from None

        entrada = verificar_pergunta(req.pergunta)
        if entrada.bloqueada:
            return ResponderResponse(status="nao_sei", resposta=MSG_BLOQUEADO)
        if req.total_linhas == 0 or all(c is None for linha in req.linhas for c in linha):
            return ResponderResponse(status="nao_sei", resposta=MSG_VAZIO)

        redacao = chamar(redator, req, entrada.texto)
        texto = (redacao.resposta or "").replace("**", "").replace("__", "").strip()
        if not redacao.responde_a_pergunta or not texto:
            return ResponderResponse(status="nao_sei", resposta=MSG_SEM_CONFIANCA)
        if len(texto) > MAX_RESPOSTA:
            texto = texto[:MAX_RESPOSTA].rsplit(" ", 1)[0] + "…"
        return ResponderResponse(status="ok", resposta=texto)

    return app


def _criar_app_padrao() -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    return create_app()


def __getattr__(nome: str):  # `uvicorn prisma_agent.api:app` cria o app só quando pedido
    if nome == "app":
        global app
        app = _criar_app_padrao()
        return app
    raise AttributeError(nome)
