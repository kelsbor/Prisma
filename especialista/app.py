"""Prisma · Agente Especialista (MCP).

Ferramentas:
- buscar_conhecimento: consulta a RAG (base_conhecimento) e devolve trechos com fonte e página.
- consultar_transacoes: busca as transações no Agente de Armazenamento (via MCP) e resume o mês.
- perguntar: junta as duas coisas e o Gemini escreve a resposta.
- status_base / atualizar_base: manutenção da RAG.
"""

import asyncio

from mcp.server.mcpserver import MCPServer

from especialista import agente, dados, rag

mcp = MCPServer(
    name="agente-especialista",
    instructions=(
        "Agente Especialista do Prisma. Use buscar_conhecimento para conceitos financeiros (com fonte e página), "
        "consultar_transacoes para os números da pessoa e perguntar para uma resposta pronta que junta os dois. "
        "Os números vêm dos dados; não invente valores. Não recomende produtos financeiros específicos."
    ),
)


@mcp.tool()
async def buscar_conhecimento(pergunta: str, k: int = 4) -> dict:
    """Busca na base de conhecimento os trechos mais relevantes para a pergunta, com fonte, página e nota (0 a 1)."""
    return {"trechos": await asyncio.to_thread(rag.buscar, pergunta, max(1, min(k, 10)))}


@mcp.tool()
async def consultar_transacoes(titular_id: str, periodo: str | None = None) -> dict:
    """Resumo do mês (AAAA-MM) do titular, com dados do Agente de Armazenamento: entradas, saídas, saldo,
    maiores gastos e transações com alerta. Sem período, usa o mês mais recente com dados."""
    return dados.resumo(await dados.transacoes(titular_id), periodo)


@mcp.tool()
async def perguntar(pergunta: str, titular_id: str | None = None, periodo: str | None = None) -> dict:
    """Responde uma dúvida financeira usando a base de conhecimento e, se houver titular, o resumo do mês
    e o perfil de risco dele."""
    if titular_id:
        ts = await dados.transacoes(titular_id)
        resumo = await asyncio.to_thread(dados.dados_do_usuario, ts, periodo)   # resumo do mês + perfil de risco
    else:
        resumo = None
    return await asyncio.to_thread(agente.perguntar, pergunta, resumo)


@mcp.tool()
def status_base() -> dict:
    """Quantos arquivos da base estão indexados e quais estão pendentes."""
    return rag.status()


@mcp.tool()
async def atualizar_base() -> dict:
    """Indexa arquivos novos ou alterados da pasta base_conhecimento e remove os apagados."""
    return await asyncio.to_thread(rag.indexar)
