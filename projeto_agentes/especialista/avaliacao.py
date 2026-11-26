"""Avaliação da RAG do Especialista: perguntas com as fontes esperadas e perguntas fora do tema.

    ./prisma.sh especialista avaliar [-k 4] [--json]

Mede, com o índice e o modo de embeddings atuais:
  - acerto@1 e acerto@k: a fonte esperada aparece no 1º trecho / entre os k primeiros;
  - MRR: média de 1/posição do primeiro acerto (1,0 = sempre em 1º);
  - as notas dos acertos e das perguntas fora do tema, e uma sugestão de PRISMA_NOTA_MINIMA que separa
    os dois grupos (cada modo de embeddings tem uma escala própria: calibre sempre que trocar).

As perguntas ficam em especialista/perguntas_teste.jsonl: acrescente as da equipe ("esperado" é a lista
de arquivos da base que respondem; vazio = fora do tema).
"""

import json
from pathlib import Path

from especialista import rag

ARQUIVO = Path(__file__).with_name("perguntas_teste.jsonl")


def carregar(arquivo: Path = ARQUIVO) -> list[dict]:
    return [json.loads(linha) for linha in arquivo.read_text(encoding="utf-8").splitlines() if linha.strip()]


def _sugerir_nota(notas_acerto: list[float], notas_fora: list[float]) -> float | None:
    """Limiar que mais separa: maximiza perguntas do tema acima + fora do tema abaixo."""
    if not notas_acerto or not notas_fora:
        return None
    candidatos = sorted(set(notas_acerto + notas_fora))
    melhor = max(candidatos, key=lambda t: sum(n >= t for n in notas_acerto) + sum(n < t for n in notas_fora))
    abaixo = [n for n in notas_fora if n < melhor]
    return round((melhor + (max(abaixo) if abaixo else melhor)) / 2, 3)


def avaliar(k: int = 4, perguntas: list[dict] | None = None) -> dict:
    perguntas = perguntas if perguntas is not None else carregar()
    linhas, notas_acerto, notas_fora = [], [], []
    for p in perguntas:
        achados = rag.buscar(p["pergunta"], k=k)
        arquivos = [Path(a.get("arquivo", "")).stem for a in achados]
        topo = achados[0]["nota"] if achados else 0.0
        if p["esperado"]:
            posicao = next((i + 1 for i, a in enumerate(arquivos) if a in p["esperado"]), None)
            if posicao:
                notas_acerto.append(achados[posicao - 1]["nota"])
            linhas.append({"pergunta": p["pergunta"], "tema": True, "posicao": posicao, "nota_topo": topo,
                           "topo": f"{achados[0]['fonte']}, p. {achados[0]['pagina']}" if achados else None})
        else:
            notas_fora.append(topo)
            linhas.append({"pergunta": p["pergunta"], "tema": False, "nota_topo": topo,
                           "topo": f"{achados[0]['fonte']}, p. {achados[0]['pagina']}" if achados else None})
    do_tema = [li for li in linhas if li["tema"]]
    n = len(do_tema) or 1
    return {
        "modo_embeddings": rag.MODO_EMBEDDINGS, "k": k,
        "modelo": rag.MODELO_EMBEDDING if rag.MODO_EMBEDDINGS in ("local", "gemini") else "sem modelo",
        "perguntas_do_tema": len(do_tema), "perguntas_fora_do_tema": len(linhas) - len(do_tema),
        "acerto@1": round(sum(li["posicao"] == 1 for li in do_tema) / n, 3),
        f"acerto@{k}": round(sum(bool(li["posicao"]) for li in do_tema) / n, 3),
        "mrr": round(sum(1 / li["posicao"] for li in do_tema if li["posicao"]) / n, 3),
        "notas_acertos": [min(notas_acerto), max(notas_acerto)] if notas_acerto else None,
        "notas_fora_do_tema": [min(notas_fora), max(notas_fora)] if notas_fora else None,
        "nota_minima_sugerida": _sugerir_nota(notas_acerto, notas_fora),
        "nota_minima_atual": float(__import__("os").getenv("PRISMA_NOTA_MINIMA") or 0.5),
        "linhas": linhas,
    }


def imprimir(r: dict) -> None:
    print(f"Modo de embeddings: {r['modo_embeddings']} ({r['modelo']}) · k = {r['k']}\n")
    for li in r["linhas"]:
        if li["tema"]:
            marca = f"{li['posicao']}º" if li["posicao"] else "não achou"
            print(f"  [{marca:>9}] {li['nota_topo']:.3f}  {li['pergunta']}")
        else:
            print(f"  [fora tema] {li['nota_topo']:.3f}  {li['pergunta']}")
        print(f"               1º trecho: {li['topo']}")
    k = r["k"]
    print(f"\nAcerto no 1º trecho: {r['acerto@1']:.0%} · entre os {k}: {r[f'acerto@{k}']:.0%} · MRR {r['mrr']:.2f}"
          f" ({r['perguntas_do_tema']} perguntas do tema)")
    if r["notas_acertos"] and r["notas_fora_do_tema"]:
        print(f"Notas dos acertos: {r['notas_acertos'][0]:.3f} a {r['notas_acertos'][1]:.3f} · "
              f"fora do tema: {r['notas_fora_do_tema'][0]:.3f} a {r['notas_fora_do_tema'][1]:.3f}")
        print(f"Nota mínima atual: {r['nota_minima_atual']} · sugerida para este modo: {r['nota_minima_sugerida']}"
              "  (PRISMA_NOTA_MINIMA no .env)")
