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
    c = p.get("classificacao", {})
    if c.get("disponivel"):
        print(f"\nClassificação (rede neural): {c['classe'].upper()} · probabilidade estimada "
              f"{c['probabilidade']:.0%} (limiar {c['limiar']:.0%})")
        print(f"  definição: {c['definicao']}")
        print(f"  o que mais pesou: {'; '.join(c['sinais'])}")
    else:
        print(f"\nClassificação indisponível: {c.get('motivo')}")
    for aviso in p["avisos"] + c.get("avisos", []):
        print("Aviso:", aviso)


ap = argparse.ArgumentParser(prog="python -m perfil", description="Prisma · Agente de Perfil Financeiro")
sub = ap.add_subparsers(dest="comando")
sv = sub.add_parser("servidor", help="servidor MCP (stdio; com --http, serviço local)")
sv.add_argument("--http", action="store_true")
sv.add_argument("--port", type=int, default=8003)
pf = sub.add_parser("ver", help="perfil financeiro de um titular: score de risco, atípicas e classificação")
pf.add_argument("--titular", required=True)
pf.add_argument("--json", action="store_true", help="saída em JSON")
pf.add_argument("--sem-rede", action="store_true", help="só os indicadores, sem a rede neural")
cl = sub.add_parser("classificar", help="a rede diz se a pessoa está ou não endividada")
cl.add_argument("--titular", required=True)
tr = sub.add_parser("treinar", help="gera dados sintéticos e treina as duas redes")
tr.add_argument("--so", choices=["autoencoder", "classificador"], help="treina só uma das redes")
tr.add_argument("--usuarios", type=int, default=200, help="usuários sintéticos do autoencoder (padrão: 200)")
tr.add_argument("--usuarios-classificador", type=int, default=1000,
                help="usuários sintéticos do classificador (padrão: 1000)")
tr.add_argument("--motor", choices=["auto", "torch", "sklearn"], default="auto",
                help="auto = PyTorch se instalado, senão scikit-learn")
tr.add_argument("--epocas", type=int, default=60)
tr.add_argument("--refazer-dados", action="store_true", help="gera os dados sintéticos de novo")
sub.add_parser("status", help="mostra se a rede está treinada e suas métricas")
args = ap.parse_args()

if args.comando is None or (args.comando == "servidor" and not args.http):
    from perfil.app import mcp
    mcp.run(transport="stdio")
elif args.comando == "servidor":
    from comum.servidor_http import app_com_token, rodar
    from perfil.app import mcp
    rodar(app_com_token(mcp, "agente-perfil"), "agente-perfil", args.port)
elif args.comando == "ver":
    from perfil import dados, score
    p = score.calcular(asyncio.run(dados.transacoes(args.titular)), usar_rede=not args.sem_rede)
    mostrar(p) if args.json else imprimir_perfil(p)
elif args.comando == "classificar":
    from perfil import classificador, dados
    mostrar(classificador.classificar(asyncio.run(dados.transacoes(args.titular))))
elif args.comando == "treinar":
    from perfil import classificador, rede
    saida = {}
    if args.so != "classificador":
        saida["autoencoder"] = rede.treinar(args.usuarios, args.motor, args.epocas, args.refazer_dados)
    if args.so != "autoencoder":
        saida["classificador"] = classificador.treinar(args.usuarios_classificador)
    mostrar(saida)
elif args.comando == "status":
    from perfil.app import status_modelo
    mostrar(status_modelo())
