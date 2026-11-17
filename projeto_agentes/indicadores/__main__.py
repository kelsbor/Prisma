import argparse
import json

from indicadores import consultas
from indicadores.series import SERIES


def mostrar(x):
    print(json.dumps(x, ensure_ascii=False, indent=2))


ap = argparse.ArgumentParser(prog="python -m indicadores", description="Prisma · Agente de Indicadores (Banco Central)")
sub = ap.add_subparsers(dest="comando")
sv = sub.add_parser("servidor", help="servidor MCP (stdio; com --http, serviço local)")
sv.add_argument("--http", action="store_true")
sv.add_argument("--port", type=int, default=8004)
sub.add_parser("juros", help="juros médios do crédito para pessoas físicas, com a Selic")
v = sub.add_parser("ver", help="último valor de um indicador")
v.add_argument("nome", choices=list(SERIES))
s = sub.add_parser("simular", help="quanto uma dívida cresce com a taxa média")
s.add_argument("--valor", type=float, required=True)
s.add_argument("--modalidade", choices=["rotativo", "cheque_especial", "credito_pessoal"], required=True)
s.add_argument("--meses", type=int, default=3)
h = sub.add_parser("historico", help="últimos valores de um indicador")
h.add_argument("nome", choices=list(SERIES))
h.add_argument("-n", type=int, default=12)
args = ap.parse_args()

try:
    if args.comando is None or (args.comando == "servidor" and not args.http):
        from indicadores.app import mcp
        mcp.run(transport="stdio")
    elif args.comando == "servidor":
        from comum.servidor_http import app_com_token, rodar
        from indicadores.app import mcp
        rodar(app_com_token(mcp, "agente-indicadores"), "agente-indicadores", args.port)
    elif args.comando == "juros":
        r = consultas.juros_do_credito()
        print("\n".join(r["resumo"]) or "Sem dados.")
        print(f"\nFonte: {r['fonte']}")
    elif args.comando == "ver":
        mostrar(consultas.indicador(args.nome))
    elif args.comando == "simular":
        r = consultas.simular(args.valor, args.modalidade, args.meses)
        print(r["texto"])
        print(f"Fonte: {r['fonte']} · {r['observacao']}")
    elif args.comando == "historico":
        r = consultas.historico(args.nome, args.n)
        print(f"{r['nome']} ({r['unidade']}) · {r['fonte']}")
        for p in r["pontos"]:
            print(f"  {p['referencia']:>10}  {p['valor']:>10.2f}")
except Exception as e:
    raise SystemExit(f"Erro: {e}")
