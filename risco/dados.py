"""Transações do titular, buscadas no Agente de Armazenamento via MCP."""

from comum.cliente_armazenamento import conectar


async def transacoes(titular_id: str) -> list[dict]:
    async with conectar() as cliente:
        resp = await cliente.chamar("consultar_titular", {"titular_id": titular_id})
    return sorted((r["dados"] for r in resp["registros"] if r["dados"].get("data")), key=lambda t: t["data"])
