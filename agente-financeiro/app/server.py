from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from sqlalchemy import delete, insert, select
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.auth import BearerAuth
from app.config import ALLOWED_HOSTS
from app.db import auditoria, engine, registros
from app.seguranca import cifrar, decifrar, pseudonimizar

mcp = MCPServer(
    name="cofre-financeiro",
    instructions=(
        "Armazena dados de transações financeiras de forma criptografada. "
        "Sempre informe o titular_id (ex.: CPF ou ID interno) e a finalidade do tratamento."
    ),
)


def _auditar(conn, acao: str, titular_hash: str, quantidade: int) -> None:
    conn.execute(insert(auditoria).values(acao=acao, titular_hash=titular_hash, quantidade=quantidade))


@mcp.tool()
def salvar_transacao(titular_id: str, dados: dict[str, Any], finalidade: str = "gestao_financeira") -> dict:
    """Guarda os dados de uma transação financeira (qualquer formato JSON), criptografados."""
    h = pseudonimizar(titular_id)
    with engine.begin() as conn:
        novo_id = conn.execute(
            insert(registros)
            .values(titular_hash=h, finalidade=finalidade, dados_cifrados=cifrar(dados))
            .returning(registros.c.id)
        ).scalar_one()
        _auditar(conn, "salvar", h, 1)
    return {"status": "ok", "id": novo_id}


@mcp.tool()
def consultar_titular(titular_id: str) -> dict:
    """Retorna todos os dados guardados de um titular (direito de acesso, LGPD art. 18, II)."""
    h = pseudonimizar(titular_id)
    with engine.begin() as conn:
        linhas = conn.execute(
            select(registros).where(registros.c.titular_hash == h).order_by(registros.c.id)
        ).all()
        _auditar(conn, "consultar", h, len(linhas))
    return {
        "quantidade": len(linhas),
        "registros": [
            {
                "id": r.id,
                "finalidade": r.finalidade,
                "criado_em": r.criado_em.isoformat() if r.criado_em else None,
                "dados": decifrar(r.dados_cifrados),
            }
            for r in linhas
        ],
    }


@mcp.tool()
def eliminar_titular(titular_id: str) -> dict:
    """Apaga todos os dados de um titular (direito de eliminação, LGPD art. 18, VI)."""
    h = pseudonimizar(titular_id)
    with engine.begin() as conn:
        apagados = conn.execute(delete(registros).where(registros.c.titular_hash == h)).rowcount
        _auditar(conn, "eliminar", h, apagados)
    return {"status": "ok", "apagados": apagados}


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


app = BearerAuth(
    mcp.streamable_http_app(
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(allowed_hosts=ALLOWED_HOSTS),
        host="0.0.0.0",
    )
)
