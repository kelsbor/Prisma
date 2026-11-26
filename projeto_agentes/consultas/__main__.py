import argparse
import json

ap = argparse.ArgumentParser(prog="python -m consultas", description="Prisma · Agente de Consultas (PrismaAPP)")
sub = ap.add_subparsers(dest="comando")
sv = sub.add_parser("servidor", help="servidor MCP (stdio; com --http, serviço local)")
sv.add_argument("--http", action="store_true")
sv.add_argument("--port", type=int, default=8006)
p = sub.add_parser("perguntar", help="pergunta sobre as transações do app")
p.add_argument("pergunta")
sub.add_parser("status", help="banco do app e assistente encontrados?")
args = ap.parse_args()

if args.comando is None or (args.comando == "servidor" and not args.http):
    from consultas.app import mcp
    mcp.run(transport="stdio")
elif args.comando == "servidor":
    from comum.servidor_http import app_com_token, rodar
    from consultas.app import mcp
    rodar(app_com_token(mcp, "agente-consultas"), "agente-consultas", args.port)
else:
    from consultas import motor
    if args.comando == "status":
        print(json.dumps(motor.status(), ensure_ascii=False, indent=2))
    else:
        r = motor.perguntar(args.pergunta)
        print(r["resposta"])
        if r.get("sql"):
            print(f"\nSQL: {r['sql']}")
            print(" | ".join(r["colunas"]))
            for linha in r["linhas"][:20]:
                print(" | ".join("" if c is None else str(c) for c in linha))
            if r["total_linhas"] > 20:
                print(f"... ({r['total_linhas']} linhas)")
