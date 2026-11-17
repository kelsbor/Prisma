"""Cliente MCP para falar com outro agente do Prisma (Armazenamento, Indicadores...).

- Padrão: inicia o Agente de Armazenamento deste projeto como subprocesso e
  conversa com ele via stdio (um comando só, nada fica escutando na rede).
- Com ARMAZENAMENTO_URL=http://127.0.0.1:8000: conversa com um Armazenamento já iniciado
  com `python -m armazenamento --http`, usando o token de ~/.prisma/chaves.json.
"""

import json
import os
import sys
from contextlib import asynccontextmanager

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

from comum.config import RAIZ, carregar_chaves


class ErroAgente(Exception):
    pass


class ClienteMCP:
    def __init__(self, sessao: ClientSession, destino: str):
        self.sessao = sessao
        self.destino = destino

    async def chamar(self, ferramenta: str, argumentos: dict) -> dict:
        res = await self.sessao.call_tool(ferramenta, argumentos)
        texto = res.content[0].text if res.content else "{}"
        if res.is_error:
            raise ErroAgente(f"{ferramenta} falhou: {texto}")
        return json.loads(texto)


def _timeout_http():
    try:
        import httpx2 as httpx  # nome usado pelo SDK mcp 2.x
    except ImportError:
        import httpx
    return httpx.Timeout(60.0, connect=10.0)


@asynccontextmanager
async def conectar(agente: str = "armazenamento"):
    """Abre uma sessão MCP com o agente: por HTTP se <AGENTE>_URL estiver definida, senão por stdio."""
    url = os.getenv(f"{agente.upper()}_URL")
    if url:
        token = os.getenv(f"{agente.upper()}_TOKEN") or carregar_chaves()["MCP_TOKEN"]
        http = create_mcp_http_client(headers={"Authorization": f"Bearer {token}"}, timeout=_timeout_http())
        async with http, streamable_http_client(f"{url.rstrip('/')}/mcp", http_client=http) as streams:
            async with ClientSession(streams[0], streams[1]) as sessao:
                await sessao.initialize()
                yield ClienteMCP(sessao, url)
    else:
        params = StdioServerParameters(
            command=sys.executable, args=["-m", agente], cwd=str(RAIZ),
            env={**os.environ, "PYTHONPATH": str(RAIZ)},
        )
        async with stdio_client(params) as (leitura, escrita):
            async with ClientSession(leitura, escrita) as sessao:
                await sessao.initialize()
                yield ClienteMCP(sessao, "local (stdio)")
