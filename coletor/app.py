"""Prisma · Agente Coletor de extratos (MCP).

Lê extratos em vários formatos, padroniza, confere a qualidade e grava as transações no
Agente de Armazenamento, conversando com ele via MCP.

    python -m coletor                                   # servidor MCP via stdio (Claude Desktop/Code)
    python -m coletor analisar [arquivos ou pastas]     # só lê e confere (nada é gravado)
    python -m coletor importar --titular ID [arquivos]  # lê, confere e grava no armazenamento
"""

from mcp.server.mcpserver import MCPServer

from coletor import pipeline
from comum.cliente_armazenamento import conectar

NOME_AGENTE = "agente-coletor"

mcp = MCPServer(
    name=NOME_AGENTE,
    instructions=(
        "Agente Coletor do Prisma. Lê extratos bancários (CSV, TXT, XLSX, OFX, PDF, imagens), padroniza "
        "as transações e aponta problemas como alertas, sem corrigir nada sozinho. Use analisar_extratos "
        "primeiro e mostre o resultado ao usuário; só use importar_extratos depois que ele confirmar. "
        "Sem caminhos, usa a pasta extratos_ficticios/ do projeto."
    ),
)


@mcp.tool()
def analisar_extratos(caminhos: list[str] | None = None) -> dict:
    """Lê e confere extratos (arquivos ou pastas) sem gravar nada. Mostra transações por arquivo,
    alertas de qualidade, conciliação de saldo e diferenças entre arquivos."""
    relatorio, _ = pipeline.analisar(caminhos)
    return relatorio


@mcp.tool()
async def importar_extratos(titular_id: str, caminhos: list[str] | None = None) -> dict:
    """Lê, confere e grava as transações no Agente de Armazenamento. Reimportar os mesmos
    extratos não duplica nada: transações já gravadas são ignoradas."""
    relatorio, consolidado = pipeline.analisar(caminhos)
    async with conectar() as cliente:
        envio = await pipeline.enviar(cliente, titular_id, consolidado)
        envio["armazenamento"] = cliente.destino
    return {**relatorio, "envio": envio}
