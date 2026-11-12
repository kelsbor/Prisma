"""Checagens de qualidade, conciliação de saldo e consolidação entre arquivos.

Portado do notebook (seções 8 e 9). Nada é corrigido automaticamente: os problemas viram
alertas gravados junto da transação, para que cada decisão seja explicável.

- repetido_no_mesmo_dia: mesmo lançamento duas vezes (mantido: pode ser cobrança dupla real)
- valor_irrisorio: valor abaixo de R$ 1,00 (ex.: PIX de teste)
- descricao_parecida_com:X: possível erro de digitação
- estorna:<data>: estorno ligado ao débito original
- conciliação: saldo inicial + movimentos = saldo final, e saldo linha a linha
"""

import difflib
import hashlib
from collections import Counter, defaultdict

# Fonte mais confiável primeiro: CSV/OFX > planilha/TXT > PDF > imagem e demais (3)
PRIORIDADE = {"csv": 0, "tsv": 0, "ofx": 0, "xlsx": 1, "xls": 1, "txt": 1, "pdf": 2}


def chave(t):
    """Identidade da transação, independente da descrição (que muda entre PDF, imagem e CSV)."""
    return hashlib.sha256(f"{t['data']}|{t['valor']}|{t['ocorrencia']}".encode()).hexdigest()[:16]


def checar_arquivo(r):
    ts = sorted(r["transacoes"], key=lambda t: t["data"])  # sort estável: mantém a ordem do extrato no dia
    cont = Counter()
    for t in ts:
        cont[(t["data"], t["valor"])] += 1
        t["ocorrencia"] = cont[(t["data"], t["valor"])]
        t["chave"] = chave(t)
        t["alertas"] = []

    # 1) lançamento idêntico repetido no mesmo arquivo
    iguais = Counter((t["data"], t["descricao"], t["valor"]) for t in ts)
    for t in ts:
        if iguais[(t["data"], t["descricao"], t["valor"])] > 1:
            t["alertas"].append("repetido_no_mesmo_dia")
    # 2) valor irrisório
    for t in ts:
        if abs(t["valor"]) < 1:
            t["alertas"].append("valor_irrisorio")
    # 3) descrição quase igual a outra mais frequente
    freq = Counter(t["descricao"] for t in ts)
    comuns = [d for d, n in freq.items() if n >= 2]
    for t in ts:
        if freq[t["descricao"]] == 1:
            par = difflib.get_close_matches(t["descricao"], comuns, n=1, cutoff=0.85)
            if par:
                t["alertas"].append(f"descricao_parecida_com:{par[0]}")
    # 4) estornos ligados ao débito de mesmo valor anterior
    for t in ts:
        if t["valor"] > 0 and "ESTORNO" in t["descricao"]:
            orig = [o for o in ts if o["valor"] == -t["valor"] and o["data"] <= t["data"] and o is not t]
            if orig:
                t["alertas"].append(f"estorna:{orig[-1]['data']}")
    # 5) conciliação de saldos
    r["conciliacao"] = []
    if r["saldo_inicial"] is not None and r["saldo_final"] is not None:
        calc = r["saldo_inicial"] + sum(t["valor"] for t in ts)
        ok = calc == r["saldo_final"]
        r["conciliacao"].append(f"saldo inicial + movimentos = {calc} · extrato diz {r['saldo_final']} → "
                                + ("confere" if ok else f"diferença de {r['saldo_final'] - calc}"))
    if ts and all(t.get("saldo") is not None for t in ts):
        anterior = r["saldo_inicial"] if r["saldo_inicial"] is not None else ts[0]["saldo"] - ts[0]["valor"]
        quebras = 0
        for t in ts:
            if anterior + t["valor"] != t["saldo"]:
                t["alertas"].append("saldo_nao_confere")
                quebras += 1
            anterior = t["saldo"]
        r["conciliacao"].append("saldo linha a linha: " + ("confere" if not quebras else f"{quebras} linha(s) não batem"))
    if not r["conciliacao"]:
        r["conciliacao"].append("sem saldos no arquivo: não dá para conciliar")
    r["transacoes"] = ts
    return r


def consolidar(resultados):
    """Junta os arquivos (assume que são extratos da MESMA conta) e devolve (consolidado, faltas)."""
    por_chave = defaultdict(list)
    for r in resultados:
        for t in r["transacoes"]:
            por_chave[t["chave"]].append((r, t))

    consolidado = []
    for k, ocorr in por_chave.items():
        ocorr.sort(key=lambda rt: PRIORIDADE.get(rt[0]["tipo"], 3))
        _, t0 = ocorr[0]
        descricoes = sorted({t["descricao"] for _, t in ocorr} - {t0["descricao"]})
        alertas = sorted({a for _, t in ocorr for a in t["alertas"] if a != "saldo_nao_confere"})
        consolidado.append({
            "data": t0["data"].isoformat(), "descricao": t0["descricao"], "valor": float(t0["valor"]),
            "moeda": "BRL", "chave": k,
            "fontes": [{"arquivo": r["arquivo"], "tipo": r["tipo"], "metodo": r["metodo"]} for r, _ in ocorr],
            **({"descricoes_alternativas": descricoes} if descricoes else {}),
            **({"alertas": alertas} if alertas else {}),
        })
    consolidado.sort(key=lambda d: (d["data"], d["chave"]))

    # Transações que aparecem em uns arquivos e não em outros
    nomes = [r["arquivo"] for r in resultados if r["transacoes"]]
    faltas = []
    if len(nomes) > 1:
        for d in consolidado:
            ausente = sorted(set(nomes) - {f["arquivo"] for f in d["fontes"]})
            if ausente:
                faltas.append({"data": d["data"], "descricao": d["descricao"], "valor": d["valor"],
                               "ausente_em": ausente})
    return consolidado, faltas
