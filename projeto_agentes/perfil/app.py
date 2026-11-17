"""Prisma · Agente de Perfil Financeiro (MCP).

Calcula o perfil financeiro de um titular (score de risco de endividamento, transações atípicas e
classificação de endividamento) a partir das transações guardadas no
Agente de Armazenamento: indicadores de fluxo de caixa em Python + a rede neural do projeto
NeuralNetwork/ (autoencoder), que aponta transações fora do padrão da própria pessoa.
"""

import asyncio

from mcp.server.mcpserver import MCPServer

from perfil import classificador, dados, rede, score

mcp = MCPServer(
    name="agente-perfil-financeiro",
    instructions=(
        "Agente de Perfil Financeiro do Prisma. Use perfil_financeiro para o score de 0 a 100 (baixo, moderado, alto) com os "
        "fatores que o explicam, classificar_endividamento para a estimativa da rede neural de se a pessoa está "
        "endividada, e "
        "transacoes_atipicas para as transações que a rede neural achou fora do padrão "
        "da pessoa. O score orienta o tom da conversa; não é julgamento nem análise de crédito. Transações "
        "atípicas são perguntas para a pessoa, nunca acusações."
    ),
)


@mcp.tool()
async def perfil_financeiro(titular_id: str) -> dict:
    """Score de risco de endividamento (0 a 100), faixa, fatores que o explicam e alertas da rede neural."""
    ts = await dados.transacoes(titular_id)
    return await asyncio.to_thread(score.calcular, ts)


@mcp.tool()
async def transacoes_atipicas(titular_id: str, limite: int = 10) -> dict:
    """Transações que o autoencoder considerou fora do padrão do titular, com os motivos."""
    ts = await dados.transacoes(titular_id)
    p = await asyncio.to_thread(score.calcular, ts)
    info = p.get("rede_neural", {})
    return {"disponivel": info.get("disponivel", False), "motivo": info.get("motivo"),
            "alertas": info.get("alertas", [])[:max(1, min(limite, 50))]}


@mcp.tool()
async def classificar_endividamento(titular_id: str) -> dict:
    """Classificação por rede neural: a pessoa está ou não endividada (no vermelho em pelo menos 25% dos
    dias de 3 meses), com a probabilidade estimada e os sinais que mais pesaram. É uma estimativa."""
    ts = await dados.transacoes(titular_id)
    return await asyncio.to_thread(classificador.classificar, ts)


@mcp.tool()
def status_modelo() -> dict:
    """Se a rede neural está treinada, com qual motor, quando e com que métricas no sintético."""
    def info(m, arquivo):
        return {"treinado": False, "arquivo": str(arquivo)} if m is None else \
            {"treinado": True, "arquivo": str(arquivo), "limiar": m["threshold"], **m["meta"]}
    return {"autoencoder": info(rede.carregar(), rede.ARQUIVO_MODELO),
            "classificador": info(classificador.carregar(), classificador.ARQUIVO_MODELO)}
