"""Prisma · Agente Especialista (MCP).

Ferramentas:
- buscar_conhecimento: consulta a RAG (base_conhecimento) e devolve trechos com fonte e página.
- resumo_do_mes: resume o mês com os dados da Pluggy (banco gerado pelo agente-sql), somente leitura.
- perguntar: junta a base, as taxas do Banco Central (Agente de Indicadores, via MCP) e, se pedido,
  o resumo do mês; o Gemini escreve a resposta.
- status_base / atualizar_base: manutenção da RAG.
"""

import asyncio

from mcp.server.mcpserver import MCPServer

from especialista import agente, dados, rag

mcp = MCPServer(
    name="agente-especialista",
    instructions=(
        "Agente Especialista do Prisma. Use buscar_conhecimento para conceitos financeiros (com fonte e página), "
        "resumo_do_mes para os números da pessoa (dados da Pluggy) e perguntar para uma resposta pronta. "
        "Os números vêm dos dados; não invente valores. Não recomende produtos financeiros específicos."
    ),
)


@mcp.tool()
async def buscar_conhecimento(pergunta: str, k: int = 4) -> dict:
    """Busca na base de conhecimento os trechos mais relevantes para a pergunta, com fonte, página e nota (0 a 1)."""
    return {"trechos": await asyncio.to_thread(rag.buscar, pergunta, max(1, min(k, 10)))}


@mcp.tool()
async def resumo_do_mes(periodo: str | None = None) -> dict:
    """Resumo do mês (AAAA-MM) com os dados da Pluggy: entradas, gastos, saldo do mês, maiores categorias
    e saldo/fatura/limite das contas. Sem período, usa o mês atual."""
    try:
        return await asyncio.to_thread(dados.resumo, periodo)
    except dados.SemDados as e:
        return {"erro": str(e)}


@mcp.tool()
async def perguntar(pergunta: str, usar_meus_dados: bool = False, periodo: str | None = None) -> dict:
    """Responde uma dúvida financeira com a base de conhecimento e as taxas do Banco Central. Com
    usar_meus_dados, inclui o resumo do mês (dados da Pluggy), que então também vai para o Gemini."""
    resumo = None
    if usar_meus_dados:
        try:
            resumo = await asyncio.to_thread(dados.resumo, periodo)
        except dados.SemDados as e:
            resumo = {"erro": str(e)}
    taxas = await dados.indicadores()                                         # Agente de Indicadores (MCP)
    return await asyncio.to_thread(agente.perguntar, pergunta, resumo, taxas)


@mcp.tool()
def status_base() -> dict:
    """Quantos arquivos da base estão indexados e quais estão pendentes."""
    return rag.status()


@mcp.tool()
async def atualizar_base() -> dict:
    """Indexa arquivos novos ou alterados da pasta base_conhecimento e remove os apagados."""
    return await asyncio.to_thread(rag.indexar)
