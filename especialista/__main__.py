import argparse
import asyncio
import json

from especialista import agente, dados, rag
from especialista.app import mcp


def mostrar(x):
    print(json.dumps(x, ensure_ascii=False, indent=2))


parser = argparse.ArgumentParser(prog="python -m especialista", description="Prisma · Agente Especialista")
sub = parser.add_subparsers(dest="comando")
sv = sub.add_parser("servidor", help="servidor MCP (stdio; com --http, serviço local)")
sv.add_argument("--http", action="store_true", help="servir via HTTP em 127.0.0.1, com token")
sv.add_argument("--port", type=int, default=8002)
sub.add_parser("status", help="o que está indexado e o que falta")
i = sub.add_parser("indexar", help="indexa arquivos novos ou alterados da base")
i.add_argument("--refazer", action="store_true", help="apaga o índice e indexa tudo de novo")
b = sub.add_parser("buscar", help="mostra os trechos mais relevantes para uma pergunta")
b.add_argument("pergunta")
b.add_argument("-k", type=int, default=4, help="quantos trechos mostrar (padrão: 4)")
r = sub.add_parser("resumo", help="resumo do mês com dados do Armazenamento")
r.add_argument("--titular", required=True)
r.add_argument("--periodo")
p = sub.add_parser("perguntar", help="resposta do especialista (RAG + dados + Gemini)")
p.add_argument("pergunta")
p.add_argument("--titular")
p.add_argument("--periodo")
args = parser.parse_args()

def executar():
    if args.comando is None or (args.comando == "servidor" and not args.http):
        mcp.run(transport="stdio")                      # servidor MCP
    elif args.comando == "servidor":
        from comum.servidor_http import app_com_token, rodar
        rodar(app_com_token(mcp, "agente-especialista"), "agente-especialista", args.port)
    elif args.comando == "status":
        mostrar(rag.status())
    elif args.comando == "indexar":
        mostrar(rag.indexar(refazer=args.refazer))
    elif args.comando == "buscar":
        for t in rag.buscar(args.pergunta, args.k):
            print(f"\n[{t['nota']:.3f}] {t['fonte']}, p. {t['pagina']}\n{t['texto']}")   # trecho inteiro
    elif args.comando == "resumo":
        mostrar(dados.resumo(asyncio.run(dados.transacoes(args.titular)), args.periodo))
    elif args.comando == "perguntar":
        resumo = dados.dados_do_usuario(asyncio.run(dados.transacoes(args.titular)), args.periodo) if args.titular else None
        mostrar(agente.perguntar(args.pergunta, resumo))


try:
    executar()
except RuntimeError as erro:             # ex.: GOOGLE_API_KEY ausente, SQLite antigo
    raise SystemExit(f"Erro: {erro}")
