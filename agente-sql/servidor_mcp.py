"""Prisma · Agente SQL (MCP).

Responde perguntas sobre as transações do app (banco do celular / Pluggy) gerando SQL sobre a
vw_registers e a account_dim com o Gemini. Mesmo fluxo do agente.py, exposto como ferramenta MCP.

    python servidor_mcp.py          # servidor MCP via stdio (orquestrador, Claude Desktop/Code, VS Code)
"""

import asyncio

from mcp.server.mcpserver import MCPServer

import agente

mcp = MCPServer(
    name="agente-sql",
    instructions=(
        "Agente SQL do Prisma: consulta as transações e contas do app do usuário. Use consultar_financas "
        "para perguntas sobre gastos, entradas, categorias, lojas, parcelas, saldo, fatura e limite dos "
        "cartões. Os números da resposta vêm do banco; o campo 'sql' mostra a consulta usada."
    ),
)


@mcp.tool()
async def consultar_financas(pergunta: str) -> dict:
    """Responde uma pergunta em português sobre as finanças do usuário no app: quanto gastou ou recebeu
    (por período, categoria, loja, conta ou cartão), parcelas futuras, saldo das contas, fatura atual e
    limite dos cartões. Envie a pergunta completa, com o período (ex.: "quanto gastei com iFood em
    outubro de 2026?"). Devolve 'resposta' (texto), 'sql' (consulta executada) e 'dados' (linhas)."""
    try:
        return await asyncio.to_thread(agente.responder_detalhado, pergunta)
    except Exception as e:  # erro do Gemini, de rede etc.: devolve em vez de derrubar o servidor
        agente.log(f"[Erro] {e}")
        return {"erro": f"Não consegui consultar agora: {e}"}


if __name__ == "__main__":
    mcp.run(transport="stdio")
