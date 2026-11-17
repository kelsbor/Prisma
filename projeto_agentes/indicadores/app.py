"""Prisma · Agente de Indicadores (MCP).

Busca indicadores oficiais na API pública do Banco Central (SGS): juros médios do rotativo, do cheque
especial e do crédito pessoal, Selic e inflação. Só os códigos das séries saem da máquina.
"""

import asyncio

from mcp.server.mcpserver import MCPServer

from indicadores import consultas

mcp = MCPServer(
    name="agente-indicadores",
    instructions=(
        "Agente de Indicadores do Prisma: dados oficiais do Banco Central. Use juros_do_credito para comparar as "
        "taxas médias do rotativo, do cheque especial e do crédito pessoal com a Selic; indicador para um valor "
        "(selic, ipca_mes, ipca_12m, rotativo, cheque_especial, credito_pessoal...); simular_custo para mostrar "
        "quanto uma dívida cresce; historico para a evolução. Cite sempre a fonte e o mês de referência."
    ),
)


@mcp.tool()
async def juros_do_credito() -> dict:
    """Juros médios do rotativo, do cheque especial e do crédito pessoal (pessoas físicas), com a Selic."""
    return await asyncio.to_thread(consultas.juros_do_credito)


@mcp.tool()
async def indicador(nome: str) -> dict:
    """Último valor de um indicador do Banco Central, com mês de referência e fonte. Nomes: selic, ipca_mes,
    ipca_12m, rotativo, rotativo_mes, cheque_especial, cheque_especial_mes, credito_pessoal, credito_pf_total."""
    return await asyncio.to_thread(consultas.indicador, nome)


@mcp.tool()
async def simular_custo(valor: float, modalidade: str, meses: int) -> dict:
    """Quanto uma dívida de `valor` cresce em `meses` (1 a 60) numa modalidade (rotativo, cheque_especial,
    credito_pessoal), com a taxa média do mercado. É uma estimativa."""
    return await asyncio.to_thread(consultas.simular, valor, modalidade, meses)


@mcp.tool()
async def historico(nome: str, n: int = 12) -> dict:
    """Últimos n valores (até 60) de um indicador do Banco Central."""
    return await asyncio.to_thread(consultas.historico, nome, n)
