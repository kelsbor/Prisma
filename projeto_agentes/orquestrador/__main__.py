import argparse
import asyncio
import json
import sys
import uuid

ap = argparse.ArgumentParser(prog="python -m orquestrador",
                             description="Prisma · Orquestrador (LangGraph): um ponto de entrada para todos os agentes")
sub = ap.add_subparsers(dest="comando")
sv = sub.add_parser("servidor", help="servidor MCP (stdio; com --http, serviço local)")
sv.add_argument("--http", action="store_true")
sv.add_argument("--port", type=int, default=8008)
p = sub.add_parser("perguntar", help="uma pergunta só")
p.add_argument("pergunta")
p.add_argument("--json", action="store_true", help="mostra rota, destinos e status dos agentes")
sub.add_parser("chat", help="conversa no terminal, com histórico (ENTER vazio para sair)")
args = ap.parse_args()


def mostrar(r: dict, completo: bool) -> None:
    if completo:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return
    print(f"\n{r['resposta']}")
    if r.get("destinos"):
        print(f"\n[{r['rota']}: {', '.join(r['destinos'])}]", file=sys.stderr)
    elif r.get("rota"):
        print(f"\n[{r['rota']}]", file=sys.stderr)


async def chat() -> None:
    from orquestrador.grafo import Orquestrador
    o, conversa = Orquestrador(), uuid.uuid4().hex
    print("Prisma · pergunte sobre as suas finanças (ENTER vazio para sair).")
    while True:
        try:
            pergunta = input("\nVocê: ").strip()
        except EOFError:
            break
        if not pergunta:
            break
        mostrar(await o.perguntar(pergunta, conversa), False)


try:
    if args.comando is None or (args.comando == "servidor" and not args.http):
        from orquestrador.app import mcp
        mcp.run(transport="stdio")
    elif args.comando == "servidor":
        from comum.servidor_http import app_com_token, rodar
        from orquestrador.app import mcp
        rodar(app_com_token(mcp, "agente-orquestrador"), "agente-orquestrador", args.port)
    elif args.comando == "perguntar":
        from orquestrador.grafo import Orquestrador
        mostrar(asyncio.run(Orquestrador().perguntar(args.pergunta)), args.json)
    elif args.comando == "chat":
        asyncio.run(chat())
except KeyboardInterrupt:
    pass
except Exception as e:
    raise SystemExit(f"Erro: {e}")
