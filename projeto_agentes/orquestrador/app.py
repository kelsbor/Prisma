"""Prisma · Orquestrador (MCP).

Uma ferramenta só, `conversar`: recebe a mensagem da pessoa, aplica as barreiras (manipulação,
"só finanças"), chama o agente-sql, o Especialista e/ou o Indicadores e devolve uma
resposta. O histórico de cada conversa fica na memória do processo, por conversa_id.
"""

from mcp.server.mcpserver import MCPServer

from comum.config import log
from orquestrador.grafo import Orquestrador

mcp = MCPServer(
    name="agente-orquestrador",
    instructions=(
        "Orquestrador do Prisma: ponto de entrada único para perguntas de finanças pessoais. Use conversar "
        "com a mensagem da pessoa e um conversa_id estável para manter o contexto. Ele decide sozinho entre "
        "os dados do app (agente-sql), a educação financeira (Especialista) e o Banco Central (Indicadores), "
        "e recusa assuntos fora de finanças."
    ),
)
_orquestrador: Orquestrador | None = None


@mcp.tool()
async def conversar(mensagem: str, conversa_id: str = "padrao") -> dict:
    """Responde uma mensagem da pessoa sobre finanças. Devolve 'resposta' (texto), 'rota' (agentes,
    fora_do_escopo, conversa, bloqueado...), 'destinos' (agentes chamados), 'pergunta_autonoma'
    (a pergunta como foi entendida) e 'agentes' (status de cada agente)."""
    global _orquestrador
    _orquestrador = _orquestrador or Orquestrador()
    try:
        return await _orquestrador.perguntar(mensagem, conversa_id)
    except Exception as e:
        log("orquestrador", f"falha: {type(e).__name__}: {e}")
        return {"erro": f"Não consegui responder agora: {e}"}
