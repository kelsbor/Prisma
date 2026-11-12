"""Perfil de risco de endividamento de um titular, de 0 a 100.

O score soma sete componentes, cada um com um teto de pontos. Seis são indicadores calculados em Python
a partir do fluxo de caixa; o sétimo vem da rede neural (autoencoder), que aponta transações fora do
padrão da própria pessoa. Assim o número é sempre explicável: dá para dizer de onde veio cada ponto.

  componente                         teto   0 pontos quando...        teto quando...
  comprometimento da renda             35   saídas <= 70% da renda    saídas >= 120% da renda
  meses no vermelho                    20   nenhum mês negativo       todos os meses negativos
  crédito caro (juros, IOF)            15   nenhum mês com juros      juros em todos os meses
  fatura do cartão                     10   fatura <= 30% da renda    fatura >= 60% da renda
  renda irregular                       5   variação <= 10%           variação >= 50%
  sem reserva                           5   aplicou mais que resgatou aplicou <= resgatou
  comportamento atípico (rede neural)  10   <= 5% atípicas            >= 20% atípicas

Os limites são um ponto de partida da equipe, não uma regra regulatória: calibre com dados reais.
Sem modelo treinado, o componente da rede fica de fora e o score é reescalado para 0 a 100.
Faixas: 0 a 39 baixo, 40 a 69 moderado, 70 a 100 alto.
"""

from collections import defaultdict

import numpy as np

from risco import rede
from risco.categorias import INTERNAS, categorizar

MESES_ANALISADOS = 6


def _escala(valor, zero, cheio, teto):
    """0 pontos até `zero`, `teto` pontos a partir de `cheio`, linear no meio."""
    if valor is None or np.isnan(valor):
        return 0.0
    return float(np.clip((valor - zero) / (cheio - zero), 0, 1) * teto)


def _brl(v):
    s = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"-R$ {s}" if v < 0 else f"R$ {s}"


def _faixa(score):
    return "alto" if score >= 70 else "moderado" if score >= 40 else "baixo"


def indicadores_mensais(transacoes):
    m = defaultdict(lambda: defaultdict(float))
    for t in transacoes:
        mes, valor = t["data"][:7], float(t["valor"])
        cat = categorizar(t.get("descricao", ""), valor)
        if cat in INTERNAS:
            m[mes]["aplicado" if valor < 0 else "resgatado"] += abs(valor)
            continue
        if valor >= 0:
            m[mes]["renda" if cat == "Renda" else "outras_entradas"] += valor
        else:
            m[mes]["saidas"] += -valor
            if cat == "Juros e encargos":
                m[mes]["juros"] += -valor
            if cat == "Fatura do cartão":
                m[mes]["fatura"] += -valor
    meses = sorted(m)[-MESES_ANALISADOS:]
    return meses, {k: dict(m[k]) for k in meses}


def calcular(transacoes: list[dict], usar_rede: bool = True) -> dict:
    meses, mm = indicadores_mensais(transacoes)
    if not meses:
        return {"score": None, "faixa": None, "erro": "Nenhuma transação para este titular."}
    g = lambda k: np.array([mm[x].get(k, 0.0) for x in meses])   # noqa: E731
    renda, outras, saidas = g("renda"), g("outras_entradas"), g("saidas")
    base_renda = renda if renda.sum() > 0 else renda + outras        # sem salário identificado: todas as entradas
    renda_media = base_renda.mean()
    saldo = renda + outras - saidas
    avisos = []
    if renda.sum() == 0:
        avisos.append("Nenhuma renda identificada (salário, pró-labore, cliente): usei todas as entradas como renda.")
    if len(meses) < 3:
        avisos.append(f"Só {len(meses)} mês(es) de dados: o perfil fica mais confiável a partir de 3.")

    comp = []

    def add(nome, pontos, teto, valor, texto):
        comp.append({"componente": nome, "pontos": round(pontos, 1), "teto": teto, "valor": valor, "explicacao": texto})

    ratio = saidas.mean() / renda_media if renda_media > 0 else float("inf")
    add("comprometimento da renda", _escala(min(ratio, 9.99), 0.7, 1.2, 35), 35, round(float(ratio), 2),
        f"saídas médias de {_brl(saidas.mean())} para {_brl(renda_media)} de renda por mês "
        f"({ratio:.0%} da renda)")

    neg = float((saldo < 0).mean())
    add("meses no vermelho", 20 * neg, 20, round(neg, 2),
        f"{int((saldo < 0).sum())} de {len(meses)} meses fecharam negativos")

    juros = g("juros")
    frac_juros = float((juros > 0).mean())
    add("crédito caro (juros, IOF)", 15 * frac_juros, 15, round(float(juros.sum()), 2),
        f"juros ou IOF em {int((juros > 0).sum())} de {len(meses)} meses, total de {_brl(juros.sum())}")

    fat = g("fatura").mean() / renda_media if renda_media > 0 else 0.0
    add("fatura do cartão", _escala(fat, 0.3, 0.6, 10), 10, round(float(fat), 2),
        f"a fatura consome em média {fat:.0%} da renda")

    if len(meses) >= 2 and base_renda.mean() > 0:
        cv = float(base_renda.std() / base_renda.mean())
        add("renda irregular", _escala(cv, 0.1, 0.5, 5), 5, round(cv, 2),
            f"a renda varia {cv:.0%} de um mês para outro")

    liquido = g("aplicado").sum() - g("resgatado").sum()
    add("sem reserva", 0.0 if liquido > 0 else 5.0, 5, round(float(liquido), 2),
        f"guardou ou aplicou {_brl(g('aplicado').sum())} e resgatou {_brl(g('resgatado').sum())} no período")

    info_rede = {"disponivel": False}
    if usar_rede:
        modelo = rede.carregar()
        if modelo is None:
            info_rede["motivo"] = "modelo não treinado (rode: ./prisma.sh risco treinar)"
        else:
            try:
                r = rede.pontuar(transacoes, modelo)
            except Exception as e:                 # ex.: pasta NeuralNetwork/ ausente
                r, info_rede["motivo"] = None, f"erro ao rodar a rede: {e}"
            if r is not None and len(r):
                taxa = float(r.atipica.mean())
                add("comportamento atípico (rede neural)", _escala(taxa, 0.05, 0.20, 10), 10, round(taxa, 3),
                    f"{int(r.atipica.sum())} de {len(r)} compras fora do padrão da própria pessoa")
                atip = r[r.atipica].sort_values("score", ascending=False)
                info_rede = {
                    "disponivel": True, "modelo": modelo["meta"], "limiar": round(modelo["threshold"], 3),
                    "transacoes_analisadas": int(len(r)), "atipicas": int(r.atipica.sum()),
                    "alertas": [{"data": str(x.timestamp.date()), "descricao": x.description,
                                 "valor": round(float(x.amount), 2), "score": round(float(x.score), 3),
                                 "motivos": x.motivos} for x in atip.itertuples()],
                }

    teto_total = sum(c["teto"] for c in comp)
    score = round(100 * sum(c["pontos"] for c in comp) / teto_total)
    principais = [c for c in sorted(comp, key=lambda c: -c["pontos"]) if c["pontos"] > 0][:3]
    return {
        "score": score, "faixa": _faixa(score), "meses": meses,
        "principais_fatores": [f"{c['componente']}: {c['explicacao']}" for c in principais],
        "componentes": comp, "rede_neural": info_rede, "avisos": avisos,
    }


def resumo_para_prompt(perfil: dict) -> dict:
    """Versão curta para o Especialista: só o que ajuda a escolher o tom e o foco da resposta."""
    if perfil.get("score") is None:
        return {"disponivel": False}
    return {"score": perfil["score"], "faixa": perfil["faixa"], "principais_fatores": perfil["principais_fatores"],
            "transacoes_atipicas": [f"{a['data']} {a['descricao']} ({_brl(a['valor'])}): {', '.join(a['motivos'])}"
                                    for a in perfil["rede_neural"].get("alertas", [])[:3]]}
