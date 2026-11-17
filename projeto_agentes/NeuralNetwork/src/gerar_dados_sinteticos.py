#!/usr/bin/env python3
"""
Gerador de transações sintéticas de finanças pessoais (Brasil) - v2

Gera N personas com ~3 anos de histórico, com:
  - renda (salário, 13º, autônomo irregular, mesada) + Pix recebidos + estornos
  - gastos fixos (aluguel, contas, assinaturas, mensalidades, IPVA/IPTU estáveis)
  - gastos variáveis (Poisson + lognormal, modulados por dia da semana, proximidade do
    pagamento e sazonalidade) com restrição orçamentária por persona
  - aportes de investimento realistas (só ~40% das pessoas investem)
  - anomalias rotuladas (5 tipos, sem "vazamento" de rótulo por texto ou estabelecimento)
  - saldo corrido (coluna `balance`) a partir de um saldo inicial por persona

Uso:
  python src/gerar_dados_sinteticos.py --n-users 1000 --seed 42 --out data/generated
  python src/gerar_dados_sinteticos.py --n-users 2000 --jobs 4 --format parquet
  python src/gerar_dados_sinteticos.py --merchants meus_estabelecimentos.json

Formato do JSON opcional de estabelecimentos: {"Mercado": ["CARREFOUR", ...], "Lazer": [...]}

Saídas: transactions.(csv|parquet), personas.csv

FONTES DE CALIBRAÇÃO (consultadas em nov/2026; confira antes de citar):
  - IBGE, POF 2017-2018: participação por grupo no consumo (habitação 36,6%, transporte 18,1%,
    alimentação 17,5%, saúde 8,0%, educação 4,7%); ~1/3 da alimentação urbana é fora de casa;
    despesa total média R$ 4.649 vs. rendimento médio R$ 5.426,70 (razão ≈ 0,86).
  - IBGE, PNAD Contínua 1T/2026: rendimento médio do trabalho R$ 3.722 (média, não mediana).
  - ANEEL (InfoTarifas 2026): reajuste ~8-9%, ICMS médio 17,3% + PIS/Cofins 5,2%; consumo ~160 kWh/mês (EPE).
  - FipeZAP Locação Residencial: ~R$ 52/m² (jan/2026), alta de ~9% em 12 meses.
  - ANP: gasolina comum ~R$ 6,3-6,6/L em 2026.  Preços públicos de streaming 2025/2026.
  - IPCA ~4,5%/ano (2023-2025).
  - Anbima (Raio X do Investidor 2025): ~36% dos brasileiros investem; Itaú/BCB: poupança agregada das
    famílias de poucos % da renda; CNC: ~81% das famílias endividadas (abr/2026).
LIMITAÇÃO: a POF é de 2017-18 e mede FAMÍLIAS; os parâmetros por transação (taxa, mediana, sigma)
são calibrados para reproduzir agregados, não medidos diretamente. `income` = valor CREDITADO na conta
(não modelamos INSS/IR, férias, FGTS, PLR). Feriados não são modelados (dia útil = seg-sex).

CHANGELOG v2 (auditoria): inclui correções no fluxo de caixa, sazonalidade e geração de anomalias.
  fluxo de caixa consistente (orçamento por persona, poupança realista, saldo inicial, Pix recebido, estorno)
  | créditos <R$1 de autônomos | descrição x estabelecimento divergentes nas anomalias | vazamento de rótulo
  ("2A VIA", estabelecimentos exclusivos de fraude) | cidade aleatória por transação | descrições de Pix
  sem sentido | pico artificial às 23:54 (clip de horário) | valores sempre inteiros acima de R$ 50
  | viagens em múltiplos de 3 | eventos do último dia descartados | IPVA/IPTU sorteados de novo todo ano
  | "dias desde o pagamento" errado no dia 31 | internet para quem mora com a família | duplicatas de
  aportes/impostos | anomalia sutil (acima do padrão do usuário) | dtype de payday | --jobs/--format.
"""
import argparse
import json
from itertools import product
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

# ----------------------------------------------------------------------------
# Configuração
# ----------------------------------------------------------------------------
INCOME_GROWTH = 1.07   # reajuste nominal anual médio de renda
IPCA = 0.047           # inflação anual média aplicada aos gastos variáveis
SAVER_SHARE = 0.40     # fração que investe todo mês (Anbima: ~36% investem)

PROFILES = ["clt", "autonomo", "servidor", "estudante"]
PROFILE_P = [0.50, 0.20, 0.12, 0.18]
# mediana, sigma (lognormal), mínimo, máximo (renda mensal em R$, valores de 2023)
INCOME = {
    "clt": (2700, 0.55, 1320, 25000),
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
                "ATACADAO", "SUPERMERCADO BH", "SAMS CLUB", "HORTIFRUTI", "SUPERMERCADO NOVA ERA"],
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
    # ALIEXPRESS INTL e GIFTCARD ONLINE aparecem também em compras legítimas (não identificam fraude sozinhos)
    "Compras": ["AMAZON BR", "MERCADO LIVRE", "SHOPEE", "MAGAZINE LUIZA", "AMERICANAS", "RENNER",
                "C&A", "ZARA", "LEROY MERLIN", "KABUM", "CASAS BAHIA", "SHEIN", "NETSHOES",
                "ALIEXPRESS INTL", "GIFTCARD ONLINE"],
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
TRANSFER_PREFIX = ["PIX ENVIADO", "TED ENVIADA", "TRANSF ENVIADA"]
CITIES_BY_TIER = {  # exemplos ilustrativos por porte de cidade
    1: ["SAO PAULO", "RIO DE JANEIRO", "BRASILIA", "BELO HORIZONTE"],
    2: ["CURITIBA", "SALVADOR", "RECIFE", "GOIANIA", "CAMPINAS"],
    3: ["LONDRINA", "PIRACICABA", "UBERLANDIA", "MARILIA"],
}
ALL_CITIES = [c for v in CITIES_BY_TIER.values() for c in v]
FRAUD_MERCHANTS = ["INTL*GAMING-STORE", "WWW.PAYSAFE-XYZ", "CRYPTOEXCH LTD", "DIGITALGOODS-US",
                   "ALIEXPRESS INTL", "GIFTCARD ONLINE"]
FIRST = ["JOAO", "MARIA", "JOSE", "ANA", "PEDRO", "JULIA", "LUCAS", "FERNANDA", "CARLOS", "PATRICIA",
         "RAFAEL", "CAMILA", "BRUNO", "AMANDA", "DIEGO", "LARISSA", "MARCOS", "BEATRIZ", "THIAGO", "LETICIA"]
LAST = ["SILVA", "SANTOS", "OLIVEIRA", "SOUZA", "LIMA", "PEREIRA", "COSTA", "RODRIGUES", "ALMEIDA",
        "NASCIMENTO", "CARVALHO", "GOMES", "MARTINS", "ARAUJO", "RIBEIRO", "BARBOSA", "FERREIRA",
        "ROCHA", "DIAS", "MOURA"]
NAMES = [f"{a} {b}" for a, b in product(FIRST, LAST)]


# ----------------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------------
def prev_business_day(d: pd.Timestamp) -> pd.Timestamp:
    while d.weekday() >= 5:
        d -= pd.Timedelta(days=1)
    return d


def noisy_desc(rng, merchants, size, city, cat):
    """Descrição bancária com ruído. A cidade é a da persona (com 4% de chance de outra: viagem)."""
    if cat == "Transferências":
        pre = rng.choice(TRANSFER_PREFIX, size)
        return [f"{a} {m}" for a, m in zip(pre, merchants)]
    tpl = rng.integers(0, len(TEMPLATES), size)
    cities = np.where(rng.random(size) < 0.04, rng.choice(ALL_CITIES, size), city)
    nums = rng.integers(10, 9999, size)
    return [TEMPLATES[t].format(m=m, c=c, n=n) for t, m, c, n in zip(tpl, merchants, cities, nums)]


def apply_cents(rng, amt):
    """Valores com centavos realistas: ~40% terminam em ,00 / ,90 / ,99 (preço 'redondo'), o resto livre."""
    amt = np.round(np.maximum(amt, 1.0), 2)
    ends = rng.choice([0.0, 0.90, 0.99, -1.0], size=len(amt), p=[0.15, 0.12, 0.13, 0.60])
    return np.where((ends >= 0) & (amt > 15), np.floor(amt) + ends, amt)


def days_since_payday(days, payday):
    """Dias desde o último pagamento, respeitando o tamanho real de cada mês."""
    dom = days.day.values
    dim = days.days_in_month.values
    prev_dim = (days.to_period("M") - 1).days_in_month.values
    pay_this = np.minimum(payday, dim)
    pay_prev = np.minimum(payday, prev_dim)
    return np.where(dom >= pay_this, dom - pay_this, dom + prev_dim - pay_prev)


def make_persona(rng, i):
    profile = str(rng.choice(PROFILES, p=PROFILE_P))
    mu, sig, lo, hi = INCOME[profile]
    income = float(np.clip(rng.lognormal(np.log(mu), sig), lo, hi))
    tier = int(rng.choice([1, 2, 3], p=[0.35, 0.45, 0.20]))
    housing_p = {"estudante": [0.15, 0.05, 0.80]}.get(profile, [0.50, 0.38, 0.12])
    housing = str(rng.choice(["aluguel", "proprio", "familia"], p=housing_p))
    has_car = bool(rng.random() < np.clip(0.10 + income / 12000, 0.10, 0.80))
    saver = rng.random() < SAVER_SHARE
    tau_mean = float(np.clip(0.95 - 0.06 * np.log2(income / 2000.0), 0.70, 0.95))
    return {
        "user_id": f"u{i:05d}",
        "profile": profile,
        "income": round(income, 2),                    # renda mensal creditada em jan/2023
        "payday": int(rng.choice(PAYDAYS[profile])) if profile in PAYDAYS else None,
        "city_tier": tier,
        "cost_factor": {1: 1.2, 2: 1.0, 3: 0.85}[tier],
        "home_city": str(rng.choice(CITIES_BY_TIER[tier])),
        "propensity": float(rng.lognormal(0, 0.25)),   # traço latente (NÃO usar como feature)
        "has_car": has_car,
        "car_value": round(float(rng.lognormal(np.log(35000 * (income / 4000.0) ** 0.5), 0.4)), 0) if has_car else 0.0,
        "housing": housing,
        "iptu_annual": round(float(rng.uniform(400, 2200) * (income / 4000.0) ** 0.3), 2) if housing == "proprio" else 0.0,
        "save_rate": float(np.clip(rng.beta(2, 14), 0.02, 0.40)) if saver else 0.0,
        "raise_month": int(rng.integers(0, 12)),
        "n_subs": min(int(rng.choice([0, 1, 2, 3, 4], p=[0.1, 0.25, 0.3, 0.25, 0.1])), 1 if income < 2500 else 4),
        "gym": bool(rng.random() < 0.25),
        "health_plan": bool(rng.random() < (0.30 if profile in ("clt", "servidor") else 0.08)),
        "tuition": bool(rng.random() < (0.04 if profile == "estudante" else 0.12)),
        "internet": bool(housing != "familia" or rng.random() < 0.25),
        "spend_ratio_target": float(np.clip(rng.normal(tau_mean, 0.10), 0.55, 1.00)),  # saídas/renda desejadas (<=1: sem crédito)
        "initial_balance": round(income * float(np.clip(rng.lognormal(np.log(1.0), 0.9), 0.02, 8)), 2),
    }


# ----------------------------------------------------------------------------
# Renda e gastos fixos (mensais)
# ----------------------------------------------------------------------------
def monthly_events(rng, p, start, end_excl):
    rows = []  # (timestamp, desc, category, amount, kind, merchant)
    months = pd.period_range(start, end_excl - pd.Timedelta(days=1), freq="M")
    years = len(months) / 12.0
    inc = p["income"]

    def add(date, desc, cat, amt, kind="fixed", mk=None):
        ts = date + pd.Timedelta(hours=int(rng.integers(6, 22)), minutes=int(rng.integers(0, 60)))
        if start <= ts < end_excl:
            rows.append((ts, desc, cat, round(float(amt), 2), kind, mk or desc))

    # itens fixos: (descrição, categoria, valor base, dia, jitter, crescimento anual)
    fixed = []
    if p["housing"] == "aluguel":
        share = float(np.clip(0.33 - 0.09 * np.log2(inc / 2700.0), 0.12, 0.40))
        fixed.append(("ALUGUEL IMOBILIARIA", "Moradia", inc * share * rng.uniform(0.85, 1.15) * p["cost_factor"],
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
    if p["internet"]:
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
        step_idx = (mi + p["raise_month"]) // 12
        for name, cat, base, day, jit, g in fixed:
            amt = base * (1 + g) ** step_idx
            if name.startswith("ENEL"):
                amt *= 1.0 + 0.15 * np.cos((per.month - 2) / 12 * 2 * np.pi)  # verão mais caro
            if cat == "Contas":
                amt *= rng.lognormal(0, 0.08)
            if cat in ("Moradia", "Educação"):
                amt = round(amt / 10.0) * 10.0                                 # aluguel/mensalidade "redondos"
            d = first + pd.Timedelta(days=min(day, dim) - 1 + int(rng.integers(-jit, jit + 1)))
            add(d, name, cat, -round(amt, 2))
        # impostos anuais: valor estável (depende do bem), não sorteado de novo todo ano
        yidx = per.year - start.year
        if per.month == 1 and p["has_car"]:
            add(first + pd.Timedelta(days=int(rng.integers(5, 25))), "IPVA DETRAN", "Impostos",
                -p["car_value"] * 0.04 * (0.94 ** yidx), "seasonal")
        if per.month == 2 and p["housing"] == "proprio":
            add(first + pd.Timedelta(days=int(rng.integers(5, 25))), "IPTU PREFEITURA", "Impostos",
                -p["iptu_annual"] * (1.05 ** yidx), "seasonal")

        # renda
        prof = p["profile"]
        raise_f = INCOME_GROWTH ** step_idx
        if prof in ("clt", "servidor", "estudante"):
            pay = prev_business_day(first + pd.Timedelta(days=min(p["payday"], dim) - 1))
            label = {"clt": "SALARIO EMPRESA", "servidor": "PROVENTOS ORGAO PUBLICO", "estudante": "MESADA PIX"}[prof]
            gross = inc * (raise_f if prof != "estudante" else 1.0)
            add(pay, label, "Renda", gross, "income", label)
            if prof in ("clt", "servidor"):
                if per.month == 11:
                    add(first + pd.Timedelta(days=27), "13 SALARIO 1A PARCELA", "Renda", gross * 0.5, "income")
                if per.month == 12:
                    add(first + pd.Timedelta(days=19), "13 SALARIO 2A PARCELA", "Renda", gross * 0.5, "income")
        else:  # autônomo: receitas irregulares (mínimo de R$ 50 por recebimento)
            total = inc * raise_f * rng.lognormal(0, 0.3)
            n = int(rng.poisson(5)) + 1
            parts = np.maximum(rng.dirichlet(np.full(n, 2.0)) * total, 50.0)
            for part in parts:
                add(first + pd.Timedelta(days=int(rng.integers(0, dim))),
                    str(rng.choice(["PIX RECEBIDO CLIENTE", "TED RECEBIDA CLIENTE"])), "Renda",
                    part, "income")

        # investimento logo após o pagamento (só quem investe)
        if p["save_rate"] > 0:
            ref = p["payday"] or 5
            d = first + pd.Timedelta(days=min(ref, dim) - 1 + int(rng.integers(1, 4)))
            add(d, str(rng.choice(["APLICACAO CDB", "TESOURO DIRETO", "PIX CORRETORA"])), "Investimentos",
                -inc * p["save_rate"] * rng.uniform(0.5, 1.2), "fixed")

    # viagens (planejadas, não anômalas): nº de viagens ~ Poisson(taxa anual x anos)
    for _ in range(int(rng.poisson((0.7 if inc > 3000 else 0.2) * years))):
        t = pd.Timestamp(rng.choice(pd.date_range(start + pd.Timedelta(days=45), end_excl - pd.Timedelta(days=1), freq="D")))
        if t.month not in (1, 2, 7, 12) and rng.random() < 0.6:
            continue
        cost = inc * rng.uniform(0.3, 0.9)
        add(t - pd.Timedelta(days=int(rng.integers(30, 60))), "LATAM PASSAGEM AEREA", "Viagem", -cost * 0.5, "seasonal")
        add(t, "BOOKING.COM HOSPEDAGEM", "Viagem", -cost * 0.35, "seasonal")
        for _k in range(int(rng.integers(4, 10))):
            add(t + pd.Timedelta(days=int(rng.integers(0, 7))),
                str(rng.choice(["RESTAURANTE LOCAL", "PASSEIO TURISTICO", "LOJA SOUVENIR"])), "Viagem",
                -cost * 0.15 / 6 * rng.lognormal(0, 0.4), "seasonal")
    return rows


# ----------------------------------------------------------------------------
# Gastos variáveis (diários) e Pix recebidos
# ----------------------------------------------------------------------------
def variable_events(rng, p, days, merchants):
    """Retorna gastos variáveis com valores BRUTOS (sem arredondar; o orçamento escala depois)."""
    frames = []
    dow, month = days.dayofweek.values, days.month.values
    base_scale_income = p["income"] / 3500.0
    infl = (1 + IPCA) ** ((days - days[0]).days.values / 365.25)
    for cat, (rate, med, sigma, elast, wd, boost, hm, hs, req) in VAR.items():
        if req == "car" and not p["has_car"]:
            continue
        if cat == "Transporte" and p["has_car"]:
            rate *= 0.5
        wd = np.array(wd) / np.mean(wd)
        pay = 1 + boost * np.exp(-days_since_payday(days, p["payday"]) / 7.0) if p["payday"] else np.ones(len(days))
        seas = np.array([SEASON.get(cat, {}).get(m, 1.0) for m in month])
        lam = rate * wd[dow] * pay * seas * np.sqrt(p["propensity"])
        counts = rng.poisson(lam)
        n = int(counts.sum())
        if n == 0:
            continue
        day_idx = np.repeat(np.arange(len(days)), counts)
        scale = med * (base_scale_income ** elast) * p["cost_factor"] * p["propensity"] * 0.75
        if p["housing"] == "familia" and cat == "Mercado":
            scale *= 0.6
        amt = rng.lognormal(np.log(scale), sigma, n) * infl[day_idx]
        hours = rng.normal(hm, hs, n) % 24.0            # dá a volta à meia-noite (sem acúmulo em 23:54)
        ts = days.values[day_idx] + (hours * 3600).astype("timedelta64[s]").astype("timedelta64[ns]")
        pool = NAMES if cat == "Transferências" else merchants[cat]
        k = min(len(pool), int(rng.integers(3, 7)))
        favs = rng.choice(pool, k, replace=False)
        wz = 1.0 / np.arange(1, k + 1)
        chosen = rng.choice(favs, n, p=wz / wz.sum())
        frames.append(pd.DataFrame({
            "timestamp": ts, "description": noisy_desc(rng, chosen, n, p["home_city"], cat), "merchant": chosen,
            "category": cat, "amount": -amt, "kind": "variable"}))
    return pd.concat(frames, ignore_index=True)


def incoming_transfers(rng, p, days):
    """Pix recebidos de pessoas (crédito que NÃO é renda): ~0,035/dia, mediana ~R$ 80."""
    counts = rng.poisson(0.035, len(days))
    n = int(counts.sum())
    if n == 0:
        return pd.DataFrame(columns=["timestamp", "description", "merchant", "category", "amount", "kind"])
    day_idx = np.repeat(np.arange(len(days)), counts)
    infl = (1 + IPCA) ** ((days - days[0]).days.values / 365.25)
    amt = rng.lognormal(np.log(80 * (p["income"] / 3500.0) ** 0.5), 0.9, n) * infl[day_idx]
    hours = rng.normal(14, 4, n) % 24.0
    ts = days.values[day_idx] + (hours * 3600).astype("timedelta64[s]").astype("timedelta64[ns]")
    who = rng.choice(rng.choice(NAMES, int(rng.integers(3, 7)), replace=False), n)
    return pd.DataFrame({"timestamp": ts, "description": [f"PIX RECEBIDO {w}" for w in who], "merchant": who,
                         "category": "Transferências", "amount": apply_cents(rng, amt), "kind": "credit_other"})


# ----------------------------------------------------------------------------
# Anomalias
# ----------------------------------------------------------------------------
def inject_anomalies(rng, p, df, start, end_excl):
    years = (end_excl - start).days / 365.25
    span = (end_excl - start).days

    def rand_ts(h0, h1):
        return start + pd.Timedelta(days=int(rng.integers(0, span)), hours=int(rng.integers(h0, h1)),
                                    minutes=int(rng.integers(0, 60)))

    debit = df[df.amount < 0]
    dup_pool = debit[debit.kind.isin(["variable", "fixed"]) &
                     ~debit.category.isin(["Investimentos", "Impostos", "Moradia", "Transferências"])]
    var_pool = debit[(debit.kind == "variable") & (debit.category != "Transferências")]
    bills = debit[debit.description.str.contains("ENEL|SABESP", regex=True)]
    q95 = var_pool.groupby("category").amount.apply(lambda s: s.abs().quantile(0.95)) if len(var_pool) else {}
    out = []
    # 1) compra atípica (grande, como fração da renda)
    for _ in range(rng.poisson(0.8 * years)):
        cat = str(rng.choice(["Compras", "Saúde", "Lazer"]))
        m = str(rng.choice(MERCHANTS[cat]))
        out.append((rand_ts(9, 21), f"COMPRA CARTAO {m}", m, cat, -max(p["income"] * rng.uniform(0.10, 0.50), 150.0),
                    "anomaly", "compra_atipica"))
    # 2) cobrança duplicada (mesmo valor/estabelecimento, minutos depois)
    for _ in range(rng.poisson(0.8 * years)):
        if dup_pool.empty:
            break
        r = dup_pool.iloc[int(rng.integers(0, len(dup_pool)))]
        out.append((r.timestamp + pd.Timedelta(minutes=int(rng.integers(1, 30))), r.description, r.merchant,
                    r.category, r.amount, "anomaly", "cobranca_duplicada"))
    # 3) fraude: rajada de 1-3 transações de madrugada
    for _ in range(rng.poisson(0.5 * years)):
        base, m = rand_ts(1, 5), str(rng.choice(FRAUD_MERCHANTS))
        for k in range(int(rng.integers(1, 4))):
            out.append((base + pd.Timedelta(minutes=5 * k), f"COMPRA CARTAO {m}", m, "Compras",
                        -float(np.clip(p["income"] * rng.uniform(0.04, 0.40), 100.0, 3000.0)), "anomaly", "fraude"))
    # 4) conta de consumo inflada (mesma descrição, só o valor muda: sem vazamento por texto)
    for _ in range(rng.poisson(0.3 * years)):
        if bills.empty:
            break
        r = bills.iloc[int(rng.integers(0, len(bills)))]
        out.append((r.timestamp + pd.Timedelta(days=int(rng.integers(1, 4))), r.description, r.merchant,
                    r.category, r.amount * rng.uniform(2.0, 3.5), "anomaly", "conta_inflada"))
    # 5) gasto acima do padrão do próprio usuário (sutil: 1,4-2,5x o p95 da categoria dele)
    for _ in range(rng.poisson(0.8 * years)):
        if var_pool.empty:
            break
        r = var_pool.iloc[int(rng.integers(0, len(var_pool)))]
        ts = start + pd.Timedelta(days=int(rng.integers(0, span)), hours=r.timestamp.hour, minutes=r.timestamp.minute)
        out.append((ts, r.description, r.merchant, r.category, -q95[r.category] * rng.uniform(1.4, 2.5),
                    "anomaly", "gasto_acima_do_padrao"))
    if not out:
        return df
    adf = pd.DataFrame(out, columns=["timestamp", "description", "merchant", "category", "amount", "kind",
                                     "anomaly_type"])
    adf = adf[(adf.timestamp >= start) & (adf.timestamp < end_excl)]
    adf["amount"] = adf.amount.round(2)
    return pd.concat([df, adf], ignore_index=True)


# ----------------------------------------------------------------------------
# Pipeline por usuário
# ----------------------------------------------------------------------------
def build_user(rng, p, start, end_excl, merchants):
    days = pd.date_range(start, end_excl - pd.Timedelta(days=1), freq="D")
    n_months = len(pd.period_range(start, end_excl - pd.Timedelta(days=1), freq="M"))
    fixed_df = pd.DataFrame(monthly_events(rng, p, start, end_excl),
                            columns=["timestamp", "description", "category", "amount", "kind", "merchant"])
    var_df = variable_events(rng, p, days, merchants)

    # --- restrição orçamentária: a pessoa ajusta o gasto variável (e, se preciso, o aporte) à renda ---
    is_inv = fixed_df.category == "Investimentos"
    income_avg = fixed_df.loc[fixed_df.category == "Renda", "amount"].sum() / n_months
    fixed_out = -fixed_df.loc[(fixed_df.amount < 0) & ~is_inv, "amount"].sum() / n_months
    inv_out = -fixed_df.loc[is_inv, "amount"].sum() / n_months
    var_out = max(-var_df.amount.sum() / n_months, 1.0)
    target = p["spend_ratio_target"] * income_avg
    # custos fixos que estouram a renda mesmo com consumo mínimo: a pessoa "renegocia" (moradia/contas/planos mais baratos)
    flex = fixed_df.category.isin(["Moradia", "Contas", "Telecom", "Assinaturas", "Educação", "Saúde"]) & (fixed_df.amount < 0)
    flex_out = -fixed_df.loc[flex, "amount"].sum() / n_months
    room = income_avg - 0.4 * var_out - (fixed_out - flex_out)
    if flex_out > 0 and fixed_out + 0.4 * var_out > income_avg:
        f = float(np.clip(room / flex_out, 0.6, 1.0))
        fixed_df.loc[flex, "amount"] = (fixed_df.loc[flex, "amount"] * f).round(2)
        fixed_out = -fixed_df.loc[(fixed_df.amount < 0) & ~is_inv, "amount"].sum() / n_months
    k, k_inv = (target - fixed_out - inv_out) / var_out, 1.0
    if k < 0.4:                                   # primeiro sacrifica o aporte, depois o consumo
        k = 0.4
        k_inv = float(np.clip((target - fixed_out - k * var_out) / inv_out, 0, 1)) if inv_out > 0 else 1.0
    k = float(np.clip(k, 0.4, 2.0))
    p["budget_k"], p["invest_k"] = round(k, 3), round(k_inv, 3)
    var_df["amount"] = -apply_cents(rng, -var_df.amount.values * k)
    fixed_df.loc[is_inv, "amount"] = (fixed_df.loc[is_inv, "amount"] * k_inv).round(2)
    fixed_df = fixed_df[~(is_inv & (fixed_df.amount.abs() < 1.0))]      # aporte cortado a zero = sem transação
    p["save_rate_effective"] = round(p["save_rate"] * k_inv, 4)

    # --- Pix recebidos e estornos (créditos que não são renda) ---
    pix_df = incoming_transfers(rng, p, days)
    elig = var_df[var_df.category != "Transferências"]
    ref = elig.sample(frac=0.004, random_state=int(rng.integers(0, 2**31 - 1)))
    est_df = pd.DataFrame({
        "timestamp": ref.timestamp + pd.to_timedelta(rng.integers(1, 6, len(ref)), unit="D"),
        "description": "ESTORNO " + ref.description, "merchant": ref.merchant, "category": "Estorno",
        "amount": -ref.amount, "kind": "credit_other"})

    df = pd.concat([fixed_df, var_df, pix_df, est_df], ignore_index=True)
    df = df[df.timestamp < end_excl]
    df["anomaly_type"] = None
    df = inject_anomalies(rng, p, df, start, end_excl)
    df["is_anomaly"] = (df.kind == "anomaly").astype(int)
    df["type"] = np.where(df.amount >= 0, "credit", "debit")
    df["user_id"] = p["user_id"]
    df = df.sort_values("timestamp", kind="stable").reset_index(drop=True)
    df["balance"] = (p["initial_balance"] + df.amount.cumsum()).round(2)
    return df


def _task(args):
    i, seed, start, end_excl, merchants = args
    rng = np.random.default_rng(seed)
    p = make_persona(rng, i)
    df = build_user(rng, p, start, end_excl, merchants)
    return p, df


COLS = ["txn_id", "user_id", "timestamp", "date", "hour", "description", "merchant", "category", "type",
        "amount", "balance", "is_anomaly", "anomaly_type"]


def generate(n_users, seed=42, start="2023-01-01", end="2025-12-31", merchants=None, jobs=1, verbose=True):
    merchants = {**MERCHANTS, **(merchants or {})}
    start, end_excl = pd.Timestamp(start), pd.Timestamp(end) + pd.Timedelta(days=1)   # fim INCLUSIVO
    seeds = np.random.default_rng(seed).integers(0, 2**31 - 1, n_users)  # 1 seed por usuário
    tasks = [(i, int(s), start, end_excl, merchants) for i, s in enumerate(seeds)]
    if jobs > 1:
        with Pool(jobs) as pool:
            results = pool.map(_task, tasks, chunksize=max(1, n_users // (jobs * 4)))
    else:
        results = []
        for t in tasks:
            results.append(_task(t))
            if verbose and (t[0] + 1) % 100 == 0:
                print(f"  {t[0] + 1}/{n_users} usuários")
    personas = pd.DataFrame([r[0] for r in results])
    personas["payday"] = personas["payday"].astype("Int64")
    tx = pd.concat([r[1] for r in results], ignore_index=True)
    tx.insert(0, "txn_id", np.arange(len(tx)))
    tx["date"] = tx.timestamp.dt.date
    tx["hour"] = tx.timestamp.dt.hour
    return tx[COLS], personas


def summary(tx, pe):
    m = tx.assign(ym=tx.timestamp.dt.to_period("M"))
    inc = m[m.category == "Renda"].groupby(["user_id", "ym"]).amount.sum()
    out = m[(m.type == "debit") & (m.category != "Investimentos")].groupby(["user_id", "ym"]).amount.sum().abs()
    allin = m[m.type == "credit"].groupby(["user_id", "ym"]).amount.sum()
    allout = m[m.type == "debit"].groupby(["user_id", "ym"]).amount.sum().abs()
    r = (out / inc).replace([np.inf], np.nan).dropna()
    flow = pd.concat([allin.rename("i"), allout.rename("o")], axis=1).fillna(0)
    flow = flow[flow.i > 0]
    last = tx.groupby("user_id").balance.last()
    low = tx.groupby("user_id").balance.min()
    print(f"\nTransações: {len(tx):,} | usuários: {len(pe)} | anomalias: {tx.is_anomaly.sum():,} ({tx.is_anomaly.mean():.3%})")
    print(tx[tx.is_anomaly == 1].anomaly_type.value_counts().to_dict())
    print(f"Saídas (exceto aportes)/renda: mediana={r.median():.2f}  p10={r.quantile(.1):.2f}  p90={r.quantile(.9):.2f}")
    print(f"Fluxo de caixa: saída total/entrada total por usuário-mês: mediana={(flow.o / flow.i).median():.2f} | "
          f"% usuário-mês com saída > entrada: {(flow.o > flow.i).mean():.0%}")
    print(f"Saldo: % usuários com saldo final negativo: {(last < 0).mean():.0%} | % que ficou negativo em algum momento: {(low < 0).mean():.0%}")
    inv = pe.save_rate_effective > 0
    print(f"Quem investe: {inv.mean():.0%} | aporte médio/renda (entre quem investe): {pe.save_rate_effective[inv].mean():.1%}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-users", type=int, default=1000)
    ap.add_argument("--start", default="2023-01-01")
    ap.add_argument("--end", default="2025-12-31", help="data final INCLUSIVA")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=Path(__file__).resolve().parents[1] / "data" / "generated")
    ap.add_argument("--merchants", default=None, help="JSON opcional com estabelecimentos por categoria")
    ap.add_argument("--jobs", type=int, default=1, help="processos em paralelo")
    ap.add_argument("--format", choices=["csv", "parquet"], default="csv")
    a = ap.parse_args()

    merchants = json.loads(Path(a.merchants).read_text(encoding="utf-8")) if a.merchants else None
    tx, pe = generate(a.n_users, a.seed, a.start, a.end, merchants, a.jobs)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if a.format == "parquet":
        tx.to_parquet(out / "transactions.parquet", index=False)
    else:
        tx.to_csv(out / "transactions.csv", index=False)
    pe.to_csv(out / "personas.csv", index=False)
    summary(tx, pe)
    print(f"\nSalvo em {out.resolve()}")


if __name__ == "__main__":
    main()
