"""Prisma · Agente de Consultas (MCP): perguntas sobre as transações do PrismaAPP, respondidas com SQL."""

import asyncio

from mcp.server.mcpserver import MCPServer

from consultas import motor

mcp = MCPServer(
    name="agente-consultas",
    instructions=(
        "Agente de Consultas do Prisma: responde perguntas exatas sobre as transações do PrismaAPP (dados da "
        "Pluggy/Open Finance), como 'quanto gastei com mercado em outubro?'. Escreve e valida um SQL, executa "
        "somente leitura e confere que todo valor em R$ da resposta existe no resultado. Use para totais, "
        "listas e comparações de gastos; não para conselhos."
    ),
)


@mcp.tool()
async def perguntar_ao_app(pergunta: str) -> dict:
    """Pergunta em português sobre as transações do PrismaAPP (até 300 caracteres). Devolve a resposta, o
    SQL executado e a tabela com o resultado."""
    return await asyncio.to_thread(motor.perguntar, pergunta)


@mcp.tool()
def status_app() -> dict:
    """Se o banco do app foi encontrado, quantas transações tem e de que período."""
    return motor.status()
