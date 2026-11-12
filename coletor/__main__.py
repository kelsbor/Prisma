import argparse
import asyncio
import json
import sys

from coletor import pipeline
from coletor.app import mcp
from comum.cliente_armazenamento import conectar


def _imprimir(relatorio):
    for a in relatorio["arquivos"]:
        print(f"\n{a['arquivo']} ({a['metodo']})")
        print(f"   {a['transacoes']} transações · entradas {a['entradas']:.2f} · saídas {a['saidas']:.2f}"
              f" · líquido {a['liquido']:.2f}")
        for c in a["conciliacao"]:
            print("  ", c)
        for aviso in a["avisos"]:
            print("   aviso:", aviso)
        for t in a["alertas"]:
            print(f"   alerta: {t['data']} {t['descricao'][:32]:<32} {t['valor']:>10.2f} → {', '.join(t['alertas'])}")
    for i in relatorio["ignorados"]:
        print("ignorado:", i)
    print(f"\n{relatorio['transacoes_unicas']} transações únicas · líquido {relatorio['liquido_consolidado']:.2f}")
    for f in relatorio["nao_aparecem_em_todos_os_arquivos"]:
        print(f"   {f['data']} {f['descricao'][:30]:<30} {f['valor']:>10.2f}  ausente em: {', '.join(f['ausente_em'])}")


async def _importar(args):
    relatorio, consolidado = pipeline.analisar(args.caminhos)
    _imprimir(relatorio)
    async with conectar() as cliente:
        envio = await pipeline.enviar(cliente, args.titular, consolidado)
        print(f"\nArmazenamento ({cliente.destino}): {envio['gravadas']} gravadas · "
              f"{envio['ja_existiam']} já existiam")


def main():
    if len(sys.argv) == 1:
        mcp.run(transport="stdio")
        return
    parser = argparse.ArgumentParser(prog="python -m coletor", description="Prisma · Agente Coletor")
    sub = parser.add_subparsers(dest="comando", required=True)
    p_an = sub.add_parser("analisar", help="lê e confere, sem gravar")
    p_an.add_argument("caminhos", nargs="*", help="arquivos ou pastas (padrão: extratos_ficticios/)")
    p_an.add_argument("--json", action="store_true", help="imprime o relatório em JSON")
    p_im = sub.add_parser("importar", help="lê, confere e grava no Agente de Armazenamento")
    p_im.add_argument("caminhos", nargs="*", help="arquivos ou pastas (padrão: extratos_ficticios/)")
    p_im.add_argument("--titular", required=True, help="ID do titular (use dados fictícios em testes)")
    p_sv = sub.add_parser("servidor", help="servidor MCP (stdio; com --http, serviço local)")
    p_sv.add_argument("--http", action="store_true", help="servir via HTTP em 127.0.0.1, com token")
    p_sv.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()

    if args.comando == "servidor":
        if args.http:
            from comum.servidor_http import app_com_token, rodar
            rodar(app_com_token(mcp, "agente-coletor"), "agente-coletor", args.port)
        else:
            mcp.run(transport="stdio")
    elif args.comando == "analisar":
        relatorio, _ = pipeline.analisar(args.caminhos)
        print(json.dumps(relatorio, ensure_ascii=False, indent=2) if args.json else "", end="")
        if not args.json:
            _imprimir(relatorio)
    else:
        try:
            asyncio.run(_importar(args))
        except Exception as e:
            while getattr(e, "exceptions", None):  # ExceptionGroup (também no Python 3.10)
                e = e.exceptions[0]
            sys.exit(f"\nFalha ao falar com o Agente de Armazenamento: {e}\n"
                     "Confira ARMAZENAMENTO_URL e o token (ARMAZENAMENTO_TOKEN ou MCP_TOKEN).")


main()
