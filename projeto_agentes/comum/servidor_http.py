"""Modo HTTP local, igual para todos os agentes: só em 127.0.0.1, com token (o MCP_TOKEN de
~/.prisma/chaves.json) e com /health liberado para o script de inicialização saber se subiu."""

import hmac

from starlette.responses import JSONResponse

from comum.config import carregar_chaves, log


def app_com_token(mcp, nome: str):
    from mcp.server.transport_security import TransportSecuritySettings

    @mcp.custom_route("/health", methods=["GET"])
    async def health(_):
        return JSONResponse({"status": "ok", "agente": nome})

    mcp_app = mcp.streamable_http_app(
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(allowed_hosts=["localhost:*", "127.0.0.1:*"]),
    )
    esperado = f"Bearer {carregar_chaves()['MCP_TOKEN']}".encode()

    async def app(scope, receive, send):
        if scope["type"] == "http" and scope["path"] != "/health":
            auth = dict(scope["headers"]).get(b"authorization", b"")
            if not hmac.compare_digest(auth, esperado):
                await JSONResponse({"erro": "Não autorizado"}, status_code=401)(scope, receive, send)
                return
        await mcp_app(scope, receive, send)

    return app


def rodar(app, nome: str, porta: int) -> None:
    import uvicorn

    log(nome, f"Servindo em http://127.0.0.1:{porta}/mcp (só nesta máquina, com token)")
    uvicorn.run(app, host="127.0.0.1", port=porta, access_log=False, log_level="warning")
