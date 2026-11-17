#!/usr/bin/env python3
"""
Compara um dataset de transações (sintético OU real do Open Finance, mesmas colunas)
com benchmarks públicos da POF 2017-2018 / IBGE.

Colunas necessárias: user_id, timestamp, category, type, amount
Uso: python src/relatorio_calibracao.py data/generated/transactions.csv data/generated/personas.csv
(personas.csv é opcional; sem ele a análise por faixa de renda usa a renda mensal observada)
"""
import sys

import numpy as np
import pandas as pd

# Participação na despesa de consumo, POF 2017-2018 (Brasil)
POF_SHARE = {"Habitação": 36.6, "Transporte": 18.1, "Alimentação": 17.5, "Saúde": 8.0, "Educação": 4.7}
POF_RATIO_DESPESA_RENDA = 4649.03 / 5426.70   # despesa total média / rendimento total médio
POF_FORA_DE_CASA = 33.9                        # % da alimentação fora do domicílio (urbano)

GROUPS = {
    "Habitação": ["Moradia", "Contas", "Telecom"],
    "Alimentação": ["Mercado", "Restaurantes e Delivery"],
    "Transporte": ["Transporte", "Combustível"],
    "Saúde": ["Saúde"],
    "Educação": ["Educação"],
    "Outros (vestuário, lazer, assinaturas, viagem...)": ["Compras", "Lazer", "Assinaturas", "Viagem", "Impostos"],
}


def main(tx_path, personas_path=None):
    tx = pd.read_csv(tx_path, parse_dates=["timestamp"])
    tx["ym"] = tx.timestamp.dt.to_period("M")
    exp = tx[(tx.type == "debit") & (~tx.category.isin(["Investimentos", "Transferências"]))].copy()
    exp["spent"] = exp.amount.abs()

    # 1) composição do consumo
    total = exp.spent.sum()
    print("1) Composição da despesa de consumo (simulado vs. POF 2017-18)\n")
    print(f"{'grupo':50s} {'simulado':>9s} {'POF':>7s}")
    for g, cats in GROUPS.items():
        sim = 100 * exp[exp.category.isin(cats)].spent.sum() / total
        pof = POF_SHARE.get(g)
        print(f"{g:50s} {sim:8.1f}% {('%.1f%%' % pof) if pof else '   -':>7s}")

    # 2) alimentação fora de casa
    mer = exp[exp.category == "Mercado"].spent.sum()
    res = exp[exp.category == "Restaurantes e Delivery"].spent.sum()
    print(f"\n2) Alimentação fora de casa: simulado {100 * res / (mer + res):.1f}%  | POF (urbano) {POF_FORA_DE_CASA}%")

    # 3) razão despesa/renda mensal
    inc = tx[tx.category == "Renda"].groupby(["user_id", "ym"]).amount.sum().rename("income")   # só renda
    sp = tx[(tx.type == "debit") & (tx.category != "Investimentos")].groupby(["user_id", "ym"]).amount.sum().abs()
    r = pd.concat([sp.rename("spend"), inc], axis=1).dropna()
    r = r[r.income > 0]
    ratio = r.spend / r.income
    print(f"\n3) Razão despesa/renda mensal: mediana {ratio.median():.2f} (p10 {ratio.quantile(.1):.2f}, "
          f"p90 {ratio.quantile(.9):.2f}) | POF (média agregada) {POF_RATIO_DESPESA_RENDA:.2f}")

    # 3b) fluxo de caixa e saldo (se o dataset tiver a coluna balance)
    if "balance" in tx.columns:
        allin = tx[tx.type == "credit"].groupby(["user_id", "ym"]).amount.sum()
        allout = tx[tx.type == "debit"].groupby(["user_id", "ym"]).amount.sum().abs()
        f = pd.concat([allin.rename("i"), allout.rename("o")], axis=1).dropna()
        last = tx.sort_values("timestamp").groupby("user_id").balance.last()
        print(f"   Fluxo: saída total/entrada total mediana {(f.o / f.i).median():.2f} | usuário-meses com saída > entrada: "
              f"{(f.o > f.i).mean():.0%} | usuários com saldo final negativo: {(last < 0).mean():.0%}")

    # 4) peso de alimentação+habitação por faixa de renda (Lei de Engel)
    user_inc = r.groupby(level=0).income.median()
    bands = pd.cut(user_inc, [0, 2000, 4000, 8000, 15000, np.inf],
                   labels=["<2k", "2-4k", "4-8k", "8-15k", ">15k"])
    e2 = exp.merge(bands.rename("band"), left_on="user_id", right_index=True)
    print("\n4) Alimentação + habitação como % da despesa de consumo, por faixa de renda mensal do usuário")
    print("   (POF: ~61% para famílias até R$ 1,9 mil e ~30% para as de maior renda)\n")
    for b, g in e2.groupby("band", observed=True):
        ah = g[g.category.isin(GROUPS["Habitação"] + GROUPS["Alimentação"])].spent.sum() / g.spent.sum()
        print(f"   {str(b):7s} {100 * ah:5.1f}%   (n usuários = {g.user_id.nunique()})")

    # 5) frequência
    per_user_month = tx.groupby(["user_id", "ym"]).size()
    print(f"\n5) Transações por usuário/mês: mediana {per_user_month.median():.0f}")
    print("\nObs.: POF mede FAMÍLIAS em 2017-18; use como ordem de grandeza, não como verdade absoluta.")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
