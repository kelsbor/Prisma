#!/usr/bin/env python3
"""
Gerador de transações sintéticas de finanças pessoais (Brasil).

Gera N personas com ~3 anos de histórico, com:
  - renda (salário, 13º, autônomo irregular, mesada)
  - gastos fixos (aluguel, contas, assinaturas, mensalidades)
  - gastos variáveis (Poisson + lognormal, modulados por dia da semana,
    proximidade do dia de pagamento e sazonalidade)
  - eventos sazonais (IPVA, IPTU, viagens, Black Friday/Natal)
  - anomalias rotuladas (compra atípica, cobrança duplicada, fraude, conta inflada)

Uso:
  python gerar_dados_sinteticos.py --n-users 1000 --seed 42 --out dados_sinteticos
  python gerar_dados_sinteticos.py --merchants meus_estabelecimentos.json   # opcional (ex.: gerado por LLM)

Formato do JSON opcional de estabelecimentos:
  {"Mercado": ["CARREFOUR", "PAO DE ACUCAR", ...], "Lazer": [...]}
Categorias não informadas usam a lista padrão.

Saídas: transactions.csv, personas.csv

FONTES DE CALIBRAÇÃO (consultadas em nov/2026; confira antes de citar):
  - IBGE, POF 2017-2018: participação por grupo na despesa de consumo (habitação 36,6%,
    transporte 18,1%, alimentação 17,5%, saúde 8,0%, educação 4,7%); ~1/3 da alimentação é
    fora do domicílio (urbano: 33,9%); despesa total média R$ 4.649 vs. rendimento médio
    R$ 5.426,70 (razão ≈ 0,86).
  - IBGE, PNAD Contínua 1T/2026: rendimento médio do trabalho R$ 3.722 (média, não mediana).
    Salário mínimo 2026: R$ 1.621.
  - ANEEL (InfoTarifas 2026): reajuste médio 2026 ~8-9%, ICMS médio 17,3% + PIS/Cofins 5,2%;
    consumo residencial médio ~160 kWh/mês (EPE).
  - FipeZAP Locação Residencial: ~R$ 52/m² (jan/2026), alta de ~9% em 12 meses.
  - ANP: gasolina comum ~R$ 6,3-6,6/L em 2026.
  - Preços públicos de streaming no Brasil (Netflix, Prime, Disney+, Globoplay, HBO Max) em 2025/2026.
  - IPCA ~4,5%/ano (2023-2025).
LIMITAÇÃO: a POF é de 2017-18 e mede FAMÍLIAS; os parâmetros por transação (taxa, mediana, sigma)
continuam sendo calibrados para reproduzir esses agregados, não medidos diretamente.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

# ----------------------------------------------------------------------------
# Configuração
# ----------------------------------------------------------------------------
INCOME_GROWTH = 1.07   # reajuste nominal anual médio de renda
IPCA = 0.047           # inflação anual média aplicada aos gastos variáveis
PROFILES = ["clt", "autonomo", "servidor", "estudante"]
PROFILE_P = [0.50, 0.20, 0.12, 0.18]
# mediana, sigma (lognormal), mínimo, máximo (renda mensal em R$)
INCOME = {
    "clt": (2700, 0.55, 1320, 25000),        # média PNAD 2026 (R$ 3.722) deflacionada p/ 2023 e ajustada p/ quem tem conta/app
    "autonomo": (2500, 0.70, 800, 30000),
    "servidor": (5400, 0.45, 2500, 30000),
    "estudante": (1100, 0.45, 400, 4000),
}
PAYDAYS = {
    "clt": [5, 5, 5, 7, 10, 15, 20, 30],
    "servidor": [1, 5, 10, 28, 30],
    "estudante": [1, 5, 10],
}

# categoria: (taxa/dia, mediana R$, sigma, elasticidade à renda,
#             peso por dia da semana seg..dom, boost pós-pagamento, hora média, hora dp, requisito)
VAR = {
    "Mercado": (0.13, 95, 0.7, 0.50, [0.8, 0.8, 0.8, 0.9, 1.1, 1.6, 1.4], 0.8, 17, 3.0, None),
    "Restaurantes e Delivery": (0.12, 52, 0.55, 0.6, [0.7, 0.7, 0.8, 0.9, 1.4, 1.6, 1.5], 0.5, 20, 2.5, None),
    "Transporte": (0.32, 19, 0.6, 0.3, [1.3, 1.3, 1.2, 1.2, 1.1, 0.6, 0.4], 0.2, 12, 4.5, None),
    "Combustível": (0.13, 190, 0.35, 0.3, [1.1, 1.0, 1.0, 1.0, 1.2, 1.0, 0.7], 0.4, 14, 4.0, "car"),
    "Saúde": (0.03, 80, 0.8, 0.5, [1.2, 1.2, 1.1, 1.1, 1.0, 0.6, 0.3], 0.2, 13, 3.5, None),
    "Lazer": (0.042, 75, 0.7, 0.7, [0.6, 0.6, 0.7, 0.9, 1.4, 1.8, 1.5], 0.6, 20, 3.0, None),
    "Compras": (0.032, 140, 0.9, 0.8, [0.9, 0.9, 0.9, 1.0, 1.1, 1.3, 1.0], 0.8, 15, 3.5, None),
    "Transferências": (0.05, 90, 0.9, 0.6, [1.1, 1.0, 1.0, 1.0, 1.1, 0.9, 0.8], 0.5, 14, 4.0, None),
}
SEASON = {  # multiplicador de taxa por mês
    "Compras": {11: 1.6, 12: 1.5, 1: 0.9},
    "Restaurantes e Delivery": {12: 1.25, 7: 1.1},
    "Lazer": {7: 1.3, 12: 1.3, 1: 1.2, 2: 1.3},
    "Mercado": {12: 1.2},
    "Saúde": {6: 1.1, 7: 1.1},
}

MERCHANTS = {
    "Mercado": ["CARREFOUR", "PAO DE ACUCAR", "ASSAI ATACADISTA", "EXTRA", "DIA SUPERMERCADOS",
                "ATACADAO", "SUPERMERCADO BH", "SAMS CLUB", "HORTIFRUTI", "MERCADO LIVRE MERCADO"],
    "Restaurantes e Delivery": ["IFOOD *RESTAURANTE", "RAPPI", "MCDONALDS", "BURGER KING", "SUBWAY",
                                "OUTBACK", "PADARIA PAO QUENTE", "RESTAURANTE SABOR CASEIRO",
                                "STARBUCKS", "99FOOD", "ZE DELIVERY", "COCO BAMBU"],
    "Transporte": ["UBER *TRIP", "99 TAXI", "BILHETE UNICO", "RIOCARD", "METRO SP", "CABIFY",
                   "ESTACIONAMENTO ESTAPAR", "SEM PARAR PEDAGIO"],
    "Combustível": ["POSTO IPIRANGA", "POSTO SHELL", "POSTO PETROBRAS", "POSTO ALE", "AUTO POSTO CENTRAL"],
    "Saúde": ["DROGASIL", "DROGA RAIA", "PACHECO FARMACIA", "PAGUE MENOS", "LABORATORIO FLEURY",
              "CLINICA SAO LUCAS", "DASA EXAMES", "DENTISTA ODONTOCLIN"],
    "Lazer": ["CINEMARK", "INGRESSO.COM", "SYMPLA", "STEAM GAMES", "PLAYSTATION STORE", "BAR DO ZE",
              "LIVRARIA CULTURA", "SPOTIFY SHOW", "PARQUE AQUATICO", "SHOW TICKETS"],
    "Compras": ["AMAZON BR", "MERCADO LIVRE", "SHOPEE", "MAGAZINE LUIZA", "AMERICANAS", "RENNER",
                "C&A", "ZARA", "LEROY MERLIN", "KABUM", "CASAS BAHIA", "SHEIN", "NETSHOES"],
    "Transferências": ["PIX ENVIADO", "TED ENVIADA", "TRANSFERENCIA ENVIADA"],
}
SUBSCRIPTIONS = {  # nome: (preços dos planos, probabilidade de cada plano) - preços públicos 2025/2026
    "NETFLIX": ([20.90, 44.90, 59.90], [0.30, 0.50, 0.20]),
    "SPOTIFY": ([21.90, 34.90], [0.8, 0.2]),
    "AMAZON PRIME": ([19.90, 29.90], [0.8, 0.2]),
    "DISNEY PLUS": ([33.90, 45.90], [0.6, 0.4]),
    "YOUTUBE PREMIUM": ([24.90, 34.90], [0.8, 0.2]),
    "GLOBOPLAY": ([22.90, 39.90], [0.6, 0.4]),
    "ICLOUD": ([14.90, 44.90], [0.8, 0.2]),
    "HBO MAX": ([29.90, 55.90], [0.6, 0.4]),
}
TEMPLATES = ["{m}", "COMPRA CARTAO {m}", "{m} {c}", "COMPRA DEB {m}", "{m} *{n}", "PAG*{m}", "{m} BR"]
CITIES = ["SAO PAULO", "RIO DE JANEIRO", "CAMPINAS", "BELO HORIZONTE", "CURITIBA", "POA", "SALVADOR"]
FRAUD_MERCHANTS = ["INTL*GAMING-STORE", "WWW.PAYSAFE-XYZ", "CRYPTOEXCH LTD", "ALIEXPRESS INTL",
                   "DIGITALGOODS-US", "GIFTCARD ONLINE"]


# ----------------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------------
def prev_business_day(d: pd.Timestamp) -> pd.Timestamp:
    while d.weekday() >= 5:
        d -= pd.Timedelta(days=1)
    return d


def noisy_desc(rng, merchants, size):
    """Aplica templates de descrição bancária para simular ruído textual."""
    tpl = rng.integers(0, len(TEMPLATES), size)
    cities = rng.choice(CITIES, size)
    nums = rng.integers(10, 9999, size)
    return [TEMPLATES[t].format(m=m, c=c, n=n) for t, m, c, n in zip(tpl, merchants, cities, nums)]


def make_persona(rng, i):
    profile = str(rng.choice(PROFILES, p=PROFILE_P))
    mu, sig, lo, hi = INCOME[profile]
    income = float(np.clip(rng.lognormal(np.log(mu), sig), lo, hi))
    tier = int(rng.choice([1, 2, 3], p=[0.35, 0.45, 0.20]))
    housing_p = {"estudante": [0.15, 0.05, 0.80]}.get(profile, [0.50, 0.38, 0.12])
    return {
        "user_id": f"u{i:05d}",
        "profile": profile,
        "income": round(income, 2),
        "payday": int(rng.choice(PAYDAYS[profile])) if profile in PAYDAYS else None,
        "city_tier": tier,
        "cost_factor": {1: 1.2, 2: 1.0, 3: 0.85}[tier],
        "propensity": float(rng.lognormal(0, 0.25)),
        "has_car": bool(rng.random() < np.clip(0.10 + income / 12000, 0.10, 0.80)),
        "housing": str(rng.choice(["aluguel", "proprio", "familia"], p=housing_p)),
        "save_rate": float(np.clip(rng.beta(2, 8), 0, 0.4)),
        "raise_month": int(rng.integers(0, 12)),
        "n_subs": min(int(rng.choice([0, 1, 2, 3, 4], p=[0.1, 0.25, 0.3, 0.25, 0.1])),
                      1 if income < 2500 else 4),
        "gym": bool(rng.random() < 0.25),
        "health_plan": bool(rng.random() < (0.30 if profile in ("clt", "servidor") else 0.08)),
        "tuition": bool(rng.random() < (0.1 if profile == "estudante" else 0.12)),
    }


# ----------------------------------------------------------------------------
# Renda e gastos fixos (mensais)
# ----------------------------------------------------------------------------
def monthly_events(rng, p, start, end):
    rows = []  # (date, desc, category, amount, kind, merchant_key)
    months = pd.period_range(start, end, freq="M")

    def add(date, desc, cat, amt, kind="fixed", mk=None):
        if start <= date <= end:
            rows.append((date + pd.Timedelta(hours=int(rng.integers(6, 22)),
                                              minutes=int(rng.integers(0, 60))),
                         desc, cat, round(float(amt), 2), kind, mk or desc))

    # itens fixos: (descrição, categoria, valor base, dia, jitter, crescimento anual)
    fixed = []
    inc = p["income"]
    if p["housing"] == "aluguel":
        fixed.append(("ALUGUEL IMOBILIARIA", "Moradia", inc * float(np.clip(0.36 - 0.10 * np.log2(inc / 2700.0), 0.12, 0.45)) * rng.uniform(0.85, 1.15)
                      * p["cost_factor"],
                      int(rng.integers(1, 11)), 0, 0.09))  # FipeZAP ~9% a.a.
        if rng.random() < np.clip(inc / 12000.0, 0.05, 0.6):
            fixed.append(("CONDOMINIO", "Moradia", rng.uniform(250, 700), int(rng.integers(1, 11)), 0, 0.05))
    elif p["housing"] == "proprio" and rng.random() < 0.5:
        fixed.append(("FINANCIAMENTO IMOBILIARIO CEF", "Moradia", inc * rng.uniform(0.15, 0.28),
                      int(rng.integers(1, 11)), 0, 0.0))
    if p["housing"] != "familia":
        kwh = float(np.clip(rng.lognormal(np.log(150 * (inc / 4000.0) ** 0.25), 0.40), 60, 600))
        # tarifa residencial com impostos ~R$ 0,85/kWh em 2023 + COSIP ~R$ 12; reajuste ~7% a.a. (ANEEL)
        fixed.append(("ENEL ENERGIA", "Contas", kwh * 0.85 + 12, int(rng.integers(8, 26)), 2, 0.07))
        fixed.append(("SABESP AGUA", "Contas", rng.uniform(50, 130), int(rng.integers(8, 26)), 2, 0.07))
    if p["has_car"] and rng.random() < 0.4:
        fixed.append(("PORTO SEGURO AUTO", "Transporte", rng.uniform(180, 450), int(rng.integers(1, 28)), 0, 0.06))
    fixed.append(("VIVO FIBRA INTERNET", "Telecom", rng.choice([99.9, 119.9, 149.9]),
                  int(rng.integers(1, 28)), 1, 0.06))
    fixed.append(("TIM CELULAR", "Telecom", rng.choice([39.9, 59.9, 89.9]), int(rng.integers(1, 28)), 1, 0.05))
    subs = rng.choice(list(SUBSCRIPTIONS), p["n_subs"], replace=False) if p["n_subs"] else []
    for s in subs:
        prices, wts = SUBSCRIPTIONS[s]
        fixed.append((s, "Assinaturas", float(rng.choice(prices, p=wts)), int(rng.integers(1, 28)), 0, 0.06))
    if p["gym"]:
        fixed.append(("SMART FIT ACADEMIA", "Saúde", rng.choice([99.9, 129.9, 149.9]),
                      int(rng.integers(1, 28)), 0, 0.06))
    if p["health_plan"]:
        fixed.append(("UNIMED PLANO SAUDE", "Saúde", rng.uniform(220, 700), int(rng.integers(1, 20)), 0, 0.07))
    if p["tuition"]:
        fixed.append(("MENSALIDADE FACULDADE", "Educação", rng.uniform(400, 1800),
                      int(rng.integers(1, 15)), 0, 0.07))

    # contas, telecom, plano de saúde etc. escalam (suavemente) com a renda
    fs = float(np.clip((inc / 4000.0) ** 0.5, 0.45, 2.2))
    fixed = [(n, c, b if c in ("Moradia", "Assinaturas") else b * fs, d, j, g) for n, c, b, d, j, g in fixed]

    for mi, per in enumerate(months):
        first = per.start_time
        dim = per.days_in_month
        # gastos fixos
        for name, cat, base, day, jit, g in fixed:
            step = (1 + g) ** ((mi + p["raise_month"]) // 12)
            amt = base * step
            if cat == "Contas" and name.startswith("ENEL"):
                amt *= 1.0 + 0.15 * np.cos((per.month - 2) / 12 * 2 * np.pi)  # verão mais caro
            if cat == "Contas":
                amt *= rng.lognormal(0, 0.08)
            amt = round(amt, 2)
            d = first + pd.Timedelta(days=min(day, dim) - 1 + int(rng.integers(-jit, jit + 1)))
            add(d, name, cat, -amt)
        # impostos anuais
        if per.month == 1 and p["has_car"]:
            add(first + pd.Timedelta(days=int(rng.integers(5, 25))), "IPVA DETRAN", "Impostos",
                -inc * rng.uniform(0.3, 0.9) * 0.1 * 4, "seasonal")
        if per.month == 2 and p["housing"] == "proprio":
            add(first + pd.Timedelta(days=int(rng.integers(5, 25))), "IPTU PREFEITURA", "Impostos",
                -rng.uniform(300, 1800), "seasonal")

        # renda
        prof = p["profile"]
        raise_f = INCOME_GROWTH ** ((mi + p["raise_month"]) // 12)
        if prof in ("clt", "servidor", "estudante"):
            pay = prev_business_day(first + pd.Timedelta(days=min(p["payday"], dim) - 1))
            label = {"clt": "SALARIO EMPRESA", "servidor": "PROVENTOS ORGAO PUBLICO",
                     "estudante": "MESADA PIX"}[prof]
            gross = inc * (raise_f if prof != "estudante" else 1.0)
            add(pay.replace(hour=0), label, "Renda", gross, "income", label)
            if prof in ("clt", "servidor"):
                if per.month == 11:
                    add(first + pd.Timedelta(days=27), "13 SALARIO 1A PARCELA", "Renda", gross * 0.5, "income")
                if per.month == 12:
                    add(first + pd.Timedelta(days=19), "13 SALARIO 2A PARCELA", "Renda", gross * 0.5, "income")
        else:  # autônomo: receitas irregulares
            total = inc * raise_f * rng.lognormal(0, 0.3)
            n = int(rng.poisson(5)) + 1
            parts = rng.dirichlet(np.ones(n)) * total
            for part in parts:
                d = first + pd.Timedelta(days=int(rng.integers(0, dim)))
                add(d, rng.choice(["PIX RECEBIDO CLIENTE", "TED RECEBIDA CLIENTE"]), "Renda",
                    part, "income", "RECEITA AUTONOMO")

        # investimento logo após o pagamento
        if p["save_rate"] > 0.03:
            ref = p["payday"] or 5
            d = first + pd.Timedelta(days=min(ref, dim) - 1 + int(rng.integers(1, 4)))
            add(d, rng.choice(["APLICACAO CDB", "TESOURO DIRETO", "PIX CORRETORA"]), "Investimentos",
                -inc * p["save_rate"] * rng.uniform(0.5, 1.2), "fixed")

        # viagens (planejadas, não anômalas): passagem antes e gastos no destino
    n_trips = int(rng.poisson(0.7 if inc > 3000 else 0.2) * (len(months) / 12))
    for _ in range(n_trips):
        t = pd.Timestamp(rng.choice(pd.date_range(start + pd.Timedelta(days=45), end, freq="D")))
        if t.month not in (1, 2, 7, 12) and rng.random() < 0.6:
            continue
        cost = inc * rng.uniform(0.3, 0.9)
        add(t - pd.Timedelta(days=int(rng.integers(30, 60))), "LATAM PASSAGEM AEREA", "Viagem",
            -cost * 0.5, "seasonal")
        add(t, "BOOKING.COM HOSPEDAGEM", "Viagem", -cost * 0.35, "seasonal")
        for k in range(int(rng.integers(4, 10))):
            add(t + pd.Timedelta(days=int(rng.integers(0, 7))),
                rng.choice(["RESTAURANTE LOCAL", "PASSEIO TURISTICO", "LOJA SOUVENIR"]), "Viagem",
                -cost * 0.15 / 6 * rng.lognormal(0, 0.4), "seasonal")
    return rows


# ----------------------------------------------------------------------------
# Gastos variáveis (diários)
# ----------------------------------------------------------------------------
def variable_events(rng, p, days, merchants):
    rows = []
    dow = days.dayofweek.values
    dom = days.day.values
    month = days.month.values
    base_scale_income = p["income"] / 3500.0
    for cat, (rate, med, sigma, elast, wd, boost, hm, hs, req) in VAR.items():
        if req == "car" and not p["has_car"]:
            continue
        if cat == "Transporte" and p["has_car"]:
            rate *= 0.5
        wd = np.array(wd) / np.mean(wd)
        w = wd[dow]
        if p["payday"]:
            since = (dom - p["payday"]) % 30
            pay = 1 + boost * np.exp(-since / 7.0)
        else:
            pay = np.ones(len(days))
        seas = np.array([SEASON.get(cat, {}).get(m, 1.0) for m in month])
        lam = rate * w * pay * seas * np.sqrt(p["propensity"])
        counts = rng.poisson(lam)
        n = int(counts.sum())
        if n == 0:
            continue
        day_idx = np.repeat(np.arange(len(days)), counts)
        scale = med * (base_scale_income ** elast) * p["cost_factor"] * p["propensity"] * 0.75
        if p["housing"] == "familia" and cat == "Mercado":
            scale *= 0.6
        infl = (1 + IPCA) ** ((days - days[0]).days.values / 365.25)
        amt = rng.lognormal(np.log(scale), sigma, n) * infl[day_idx]
        amt = np.where(amt > 50, np.round(amt), np.round(amt, 2))
        hours = np.clip(rng.normal(hm, hs, n), 0, 23.9)
        ts = days.values[day_idx] + (hours * 3600).astype("timedelta64[s]").astype("timedelta64[ns]")
        # estabelecimentos favoritos (Zipf)
        pool = merchants[cat]
        k = min(len(pool), int(rng.integers(3, 7)))
        favs = rng.choice(pool, k, replace=False)
        wz = 1.0 / np.arange(1, k + 1)
        wz /= wz.sum()
        chosen = rng.choice(favs, n, p=wz)
        desc = noisy_desc(rng, chosen, n)
        rows.append(pd.DataFrame({
            "timestamp": ts, "description": desc, "merchant": chosen, "category": cat,
            "amount": -amt, "kind": "variable"}))
    return rows


# ----------------------------------------------------------------------------
# Anomalias
# ----------------------------------------------------------------------------
def inject_anomalies(rng, p, df, start, end):
    years = (end - start).days / 365.25
    exp = df[(df.amount < 0) & (df.kind.isin(["variable", "fixed"]))]
    out = []
    if exp.empty:
        return df
    # 1) compra atípica
    for _ in range(rng.poisson(0.8 * years)):
        ts = start + pd.Timedelta(days=int(rng.integers(0, (end - start).days)),
                                  hours=int(rng.integers(9, 21)))
        cat = rng.choice(["Compras", "Saúde", "Lazer"])
        out.append((ts, f"COMPRA CARTAO {rng.choice(MERCHANTS[cat])}", rng.choice(MERCHANTS[cat]), cat,
                    -p["income"] * rng.uniform(0.4, 1.3), "anomaly", "compra_atipica"))
    # 2) cobrança duplicada
    for _ in range(rng.poisson(1.0 * years)):
        r = exp.iloc[int(rng.integers(0, len(exp)))]
        out.append((r.timestamp + pd.Timedelta(minutes=int(rng.integers(1, 30))), r.description, r.merchant,
                    r.category, r.amount, "anomaly", "cobranca_duplicada"))
    # 3) fraude: rajada de 1-3 transações de madrugada em estabelecimento incomum
    for _ in range(rng.poisson(0.5 * years)):
        base = start + pd.Timedelta(days=int(rng.integers(0, (end - start).days)), hours=int(rng.integers(1, 5)))
        m = rng.choice(FRAUD_MERCHANTS)
        for k in range(int(rng.integers(1, 4))):
            out.append((base + pd.Timedelta(minutes=5 * k), m, m, "Compras",
                        -rng.uniform(150, 2500), "anomaly", "fraude"))
    # 4) conta de consumo inflada (erro de faturamento)
    bills = exp[exp.description.str.contains("ENEL|SABESP", regex=True)]
    for _ in range(rng.poisson(0.3 * years)):
        if bills.empty:
            break
        r = bills.iloc[int(rng.integers(0, len(bills)))]
        out.append((r.timestamp + pd.Timedelta(days=int(rng.integers(1, 4))), r.description + " 2A VIA",
                    r.merchant, r.category, r.amount * rng.uniform(2.0, 3.5), "anomaly", "conta_inflada"))
    if not out:
        return df
    adf = pd.DataFrame(out, columns=["timestamp", "description", "merchant", "category", "amount", "kind",
                                     "anomaly_type"])
    adf = adf[(adf.timestamp >= start) & (adf.timestamp <= end + pd.Timedelta(days=1))]
    adf["amount"] = adf.amount.round(2)
    return pd.concat([df, adf], ignore_index=True)


# ----------------------------------------------------------------------------
# Pipeline
# ----------------------------------------------------------------------------
def build_user(rng, p, start, end, merchants):
    days = pd.date_range(start, end, freq="D")
    ev = monthly_events(rng, p, start, end)
    fixed_df = pd.DataFrame(ev, columns=["timestamp", "description", "category", "amount", "kind", "merchant"])
    var_df = pd.concat(variable_events(rng, p, days, merchants), ignore_index=True)
    df = pd.concat([fixed_df, var_df], ignore_index=True)
    df["anomaly_type"] = None
    df = inject_anomalies(rng, p, df, start, end)
    df["is_anomaly"] = (df.kind == "anomaly").astype(int)
    df["type"] = np.where(df.amount >= 0, "credit", "debit")
    df["user_id"] = p["user_id"]
    return df.sort_values("timestamp").reset_index(drop=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-users", type=int, default=1000)
    ap.add_argument("--start", default="2023-01-01")
    ap.add_argument("--end", default="2025-12-31")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="dados_sinteticos")
    ap.add_argument("--merchants", default=None, help="JSON opcional com estabelecimentos por categoria")
    a = ap.parse_args()

    merchants = dict(MERCHANTS)
    if a.merchants:
        merchants.update(json.loads(Path(a.merchants).read_text(encoding="utf-8")))

    start, end = pd.Timestamp(a.start), pd.Timestamp(a.end)
    rng_master = np.random.default_rng(a.seed)
    seeds = rng_master.integers(0, 2**31 - 1, a.n_users)  # seed por usuário => reprodutível e paralelizável

    personas, frames = [], []
    for i, s in enumerate(seeds):
        rng = np.random.default_rng(int(s))
        p = make_persona(rng, i)
        personas.append(p)
        frames.append(build_user(rng, p, start, end, merchants))
        if (i + 1) % 100 == 0:
            print(f"  {i + 1}/{a.n_users} usuários")

    tx = pd.concat(frames, ignore_index=True)
    tx.insert(0, "txn_id", np.arange(len(tx)))
    tx["date"] = tx.timestamp.dt.date
    tx["hour"] = tx.timestamp.dt.hour
    cols = ["txn_id", "user_id", "timestamp", "date", "hour", "description", "merchant", "category",
            "type", "amount", "is_anomaly", "anomaly_type"]
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    tx[cols].to_csv(out / "transactions.csv", index=False)
    pd.DataFrame(personas).to_csv(out / "personas.csv", index=False)

    # resumo / sanity check
    m = tx.assign(ym=tx.timestamp.dt.to_period("M"))
    spend = m[(m.type == "debit") & (m.category != "Investimentos")].groupby(["user_id", "ym"]).amount.sum().abs()
    income = m[m.type == "credit"].groupby(["user_id", "ym"]).amount.sum()
    ratio = (spend / income).replace([np.inf], np.nan).dropna()
    print(f"\nTransações: {len(tx):,} | usuários: {a.n_users} | anomalias: {tx.is_anomaly.sum():,} "
          f"({tx.is_anomaly.mean():.3%})")
    print(f"Razão gasto/renda mensal: mediana={ratio.median():.2f}  p10={ratio.quantile(.1):.2f}  "
          f"p90={ratio.quantile(.9):.2f}")
    print(tx[tx.type == "debit"].groupby("category").amount.agg(["count", "median"]).round(1))
    print(f"\nSalvo em {out.resolve()}")


if __name__ == "__main__":
    main()
