import hmac

from starlette.responses import JSONResponse

from app.config import MCP_TOKEN

ROTAS_PUBLICAS = {"/health"}


class BearerAuth:
    """Middleware ASGI: exige Authorization: Bearer <MCP_TOKEN> em tudo, exceto /health."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"] not in ROTAS_PUBLICAS:
            headers = dict(scope.get("headers", []))
            recebido = headers.get(b"authorization", b"").decode()
            if not MCP_TOKEN or not hmac.compare_digest(recebido, f"Bearer {MCP_TOKEN}"):
                await JSONResponse({"erro": "Não autorizado"}, status_code=401)(scope, receive, send)
                return
        await self.app(scope, receive, send)
