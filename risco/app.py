"""Prisma · Agente de Risco (MCP).

Calcula o perfil de risco de endividamento de um titular a partir das transações guardadas no
Agente de Armazenamento: indicadores de fluxo de caixa em Python + a rede neural do projeto
NeuralNetwork/ (autoencoder), que aponta transações fora do padrão da própria pessoa.
"""

import asyncio

from mcp.server.mcpserver import MCPServer

from risco import dados, perfil, rede

mcp = MCPServer(
    name="agente-risco",
    instructions=(
        "Agente de Risco do Prisma. Use perfil_de_risco para o score de 0 a 100 (baixo, moderado, alto) com os "
        "fatores que o explicam, e transacoes_atipicas para as transações que a rede neural achou fora do padrão "
        "da pessoa. O score orienta o tom da conversa; não é julgamento nem análise de crédito. Transações "
        "atípicas são perguntas para a pessoa, nunca acusações."
    ),
)


@mcp.tool()
async def perfil_de_risco(titular_id: str) -> dict:
    """Score de risco de endividamento (0 a 100), faixa, fatores que o explicam e alertas da rede neural."""
    ts = await dados.transacoes(titular_id)
    return await asyncio.to_thread(perfil.calcular, ts)


@mcp.tool()
async def transacoes_atipicas(titular_id: str, limite: int = 10) -> dict:
    """Transações que o autoencoder considerou fora do padrão do titular, com os motivos."""
    ts = await dados.transacoes(titular_id)
    p = await asyncio.to_thread(perfil.calcular, ts)
    info = p.get("rede_neural", {})
    return {"disponivel": info.get("disponivel", False), "motivo": info.get("motivo"),
            "alertas": info.get("alertas", [])[:max(1, min(limite, 50))]}


@mcp.tool()
def status_modelo() -> dict:
    """Se a rede neural está treinada, com qual motor, quando e com que métricas no sintético."""
    m = rede.carregar()
    return {"treinado": False, "arquivo": str(rede.ARQUIVO_MODELO)} if m is None else \
        {"treinado": True, "arquivo": str(rede.ARQUIVO_MODELO), "limiar": m["threshold"], **m["meta"]}
