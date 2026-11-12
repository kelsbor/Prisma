import argparse
import asyncio
import json


def mostrar(x):
    print(json.dumps(x, ensure_ascii=False, indent=2))


def imprimir_perfil(p):
    if p.get("score") is None:
        print(p.get("erro"))
        return
    print(f"\nScore de risco: {p['score']}/100 ({p['faixa']}) · meses {', '.join(p['meses'])}\n")
    for c in p["componentes"]:
        print(f"  {c['pontos']:5.1f}/{c['teto']:<3} {c['componente']:38} {c['explicacao']}")
    r = p["rede_neural"]
    if r["disponivel"]:
        print(f"\nRede neural ({r['modelo']['motor']}, limiar {r['limiar']}): "
              f"{r['atipicas']} de {r['transacoes_analisadas']} compras atípicas")
        for a in r["alertas"]:
            print(f"  {a['data']} {a['descricao'][:38]:38} {a['valor']:>10.2f}  score {a['score']:.2f}  "
                  f"{', '.join(a['motivos'])}")
    else:
        print(f"\nRede neural indisponível: {r.get('motivo')}")
    for aviso in p["avisos"]:
        print("Aviso:", aviso)


ap = argparse.ArgumentParser(prog="python -m risco", description="Prisma · Agente de Risco")
sub = ap.add_subparsers(dest="comando")
sv = sub.add_parser("servidor", help="servidor MCP (stdio; com --http, serviço local)")
sv.add_argument("--http", action="store_true")
sv.add_argument("--port", type=int, default=8003)
pf = sub.add_parser("perfil", help="perfil de risco de um titular")
pf.add_argument("--titular", required=True)
pf.add_argument("--json", action="store_true", help="saída em JSON")
pf.add_argument("--sem-rede", action="store_true", help="só os indicadores, sem a rede neural")
tr = sub.add_parser("treinar", help="gera dados sintéticos e treina o autoencoder")
tr.add_argument("--usuarios", type=int, default=200, help="usuários sintéticos (padrão: 200)")
tr.add_argument("--motor", choices=["auto", "torch", "sklearn"], default="auto",
                help="auto = PyTorch se instalado, senão scikit-learn")
tr.add_argument("--epocas", type=int, default=60)
tr.add_argument("--refazer-dados", action="store_true", help="gera os dados sintéticos de novo")
sub.add_parser("status", help="mostra se a rede está treinada e suas métricas")
args = ap.parse_args()

if args.comando is None or (args.comando == "servidor" and not args.http):
    from risco.app import mcp
    mcp.run(transport="stdio")
elif args.comando == "servidor":
    from comum.servidor_http import app_com_token, rodar
    from risco.app import mcp
    rodar(app_com_token(mcp, "agente-risco"), "agente-risco", args.port)
elif args.comando == "perfil":
    from risco import dados, perfil
    p = perfil.calcular(asyncio.run(dados.transacoes(args.titular)), usar_rede=not args.sem_rede)
    mostrar(p) if args.json else imprimir_perfil(p)
elif args.comando == "treinar":
    from risco import rede
    mostrar(rede.treinar(args.usuarios, args.motor, args.epocas, args.refazer_dados))
elif args.comando == "status":
    from risco.app import status_modelo
    mostrar(status_modelo())
