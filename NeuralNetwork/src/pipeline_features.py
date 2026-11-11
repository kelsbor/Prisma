#!/usr/bin/env python3
"""
Pipeline de features + baselines para a tarefa:

    "Dado o histórico dos últimos L meses de um usuário, prever quanto ele vai gastar
     em cada categoria no PRÓXIMO mês."

Uso:
    python src/pipeline_features.py data/generated/transactions.csv        # previsão do mês seguinte
    python src/pipeline_features.py data/generated/transactions.csv 15     # projeção do mês em curso,
                                                                           # sabendo o gasto até o dia 15

O que este arquivo faz (nesta ordem):
  1. Agrega as transações em uma matriz mensal  [usuário, mês, categoria]
  2. Cria janelas deslizantes: X = últimos L meses, y = mês seguinte
  3. Divide por TEMPO (treino -> validação -> teste), nunca aleatoriamente
  4. Padroniza usando apenas estatísticas do treino
  5. Calcula baselines (o "piso" que a rede neural precisa superar)

O módulo também é importado por treinar_mlp.py.
"""
import argparse
from dataclasses import dataclass

import numpy as np
import pandas as pd

import tracking

L = 6  # tamanho da janela de histórico, em meses


# -----------------------------------------------------------------------------
# 1) Agregação mensal
# -----------------------------------------------------------------------------
def load_monthly(tx_path, drop_anomalies=True, partial_day=None):
    """Retorna spend[U,T,K] (R$ gastos, positivo), income[U,T], partial[U,T,K] (gasto até o dia
    `partial_day` de cada mês; None se não pedido), months, cats, users."""
    tx = pd.read_csv(tx_path, parse_dates=["timestamp"],
                     usecols=["user_id", "timestamp", "category", "type", "amount", "is_anomaly"])
    if drop_anomalies:  # para a PREVISÃO, treinamos em dados "limpos" (ver observação no README)
        tx = tx[tx.is_anomaly == 0]
    tx["ym"] = tx.timestamp.dt.to_period("M")

    months = pd.period_range(tx.ym.min(), tx.ym.max(), freq="M")
    users = pd.Index(np.sort(tx.user_id.unique()))
    deb = tx[tx.type == "debit"]
    cats = pd.Index(sorted(deb.category.unique()))

    g = deb.groupby(["user_id", "ym", "category"]).amount.sum().abs()
    spend = np.zeros((len(users), len(months), len(cats)), dtype=np.float32)
    spend[users.get_indexer(g.index.get_level_values(0)),
          months.get_indexer(g.index.get_level_values(1)),
          cats.get_indexer(g.index.get_level_values(2))] = g.values

    partial = None
    if partial_day:
        gp = deb[deb.timestamp.dt.day <= partial_day].groupby(["user_id", "ym", "category"]).amount.sum().abs()
        partial = np.zeros_like(spend)
        partial[users.get_indexer(gp.index.get_level_values(0)),
                months.get_indexer(gp.index.get_level_values(1)),
                cats.get_indexer(gp.index.get_level_values(2))] = gp.values

    # renda = apenas a categoria "Renda" (Pix recebidos e estornos são créditos, mas NÃO são renda)
    inc = tx[(tx.type == "credit") & (tx.category == "Renda")].groupby(["user_id", "ym"]).amount.sum()
    income = np.zeros((len(users), len(months)), dtype=np.float32)
    income[users.get_indexer(inc.index.get_level_values(0)),
           months.get_indexer(inc.index.get_level_values(1))] = inc.values
    return spend, income, partial, months, list(cats), users


# -----------------------------------------------------------------------------
# 2) Janelas deslizantes + features
# -----------------------------------------------------------------------------
def make_windows(spend, income, months, partial=None, L=L):
    """
    Para cada mês-alvo t (a partir de t = L) e cada usuário:
      X = [gastos dos meses t-L..t-1 por categoria, ÷ renda média da janela]   (K*L números)
          + [renda de cada mês ÷ renda média]                                    (L números)
          + [log da renda média]                                                 (1 número)
          + [mês-alvo em one-hot, captura sazonalidade: Black Friday, Natal...] (12 números)
      y = gasto do mês t por categoria ÷ renda média da janela                  (K números)

    Se `partial` for dado (modo "projeção do mês em curso"), acrescenta:
      + [gasto já feito no mês t até o dia D, por categoria ÷ renda]            (K números)
      + [gasto médio até o dia D nos meses da janela, por categoria ÷ renda]    (K números)

    Dividir pela renda média torna os dados comparáveis entre quem ganha R$ 2 mil e R$ 20 mil.
    O log da renda média devolve à rede a informação de "escala".
    """
    U, T, K = spend.shape
    X, Y, REF, TI, UI = [], [], [], [], []
    base = {"last": [], "ma3": [], "ma6": [], "seasonal": []}
    if partial is not None:
        base["parcial+resto"] = []
    for t in range(L, T):
        hist = spend[:, t - L:t, :]                       # [U, L, K]
        inc_h = income[:, t - L:t]                        # [U, L]
        ref = inc_h.mean(axis=1)                          # [U]
        ok = ref > 0
        r = np.where(ok, ref, 1.0)
        month_oh = np.zeros((U, 12), dtype=np.float32)
        month_oh[:, months[t].month - 1] = 1.0
        parts = [
            (hist / r[:, None, None]).reshape(U, -1),
            inc_h / r[:, None],
            np.log(r)[:, None],
            month_oh,
        ]
        if partial is not None:
            p_now = partial[:, t, :]
            p_hist = partial[:, t - L:t, :].mean(axis=1)
            parts += [p_now / r[:, None], p_hist / r[:, None]]
        x = np.concatenate(parts, axis=1)
        y = spend[:, t, :] / r[:, None]
        X.append(x[ok]); Y.append(y[ok]); REF.append(ref[ok])
        TI.append(np.full(ok.sum(), t)); UI.append(np.where(ok)[0])
        # baselines (já em R$)
        base["last"].append(spend[ok, t - 1, :])
        base["ma3"].append(spend[ok, t - 3:t, :].mean(axis=1))
        base["ma6"].append(hist[ok].mean(axis=1))
        base["seasonal"].append(spend[ok, t - 12, :] if t >= 12 else hist[ok].mean(axis=1))
        if partial is not None:   # "o que já gastei" + "o que costumo gastar no resto do mês"
            resto = hist[ok].mean(axis=1) - p_hist[ok]
            base["parcial+resto"].append(p_now[ok] + np.maximum(resto, 0))
    out = {k: np.concatenate(v) for k, v in
           dict(X=X, Y=Y, ref=REF, t=TI, u=UI).items()}
    out["baselines"] = {k: np.concatenate(v) for k, v in base.items()}
    return out


# -----------------------------------------------------------------------------
# 3 + 4) Split temporal e padronização
# -----------------------------------------------------------------------------
@dataclass
class Dataset:
    Xtr: np.ndarray; Ytr: np.ndarray
    Xva: np.ndarray; Yva: np.ndarray
    Xte: np.ndarray; Yte: np.ndarray
    ref: dict            # renda de referência por amostra (para voltar a R$)
    true_rs: dict        # gasto real em R$ por split
    base_rs: dict        # baselines em R$ (apenas no teste)
    y_mu: np.ndarray; y_sd: np.ndarray
    cats: list
    info: dict


def build_dataset(tx_path, val_months=6, test_months=6, drop_anomalies=True, partial_day=None):
    spend, income, partial, months, cats, users = load_monthly(tx_path, drop_anomalies, partial_day)
    w = make_windows(spend, income, months, partial)
    T = len(months)
    t = w["t"]
    te = t >= T - test_months
    va = (t >= T - test_months - val_months) & ~te
    tr = ~(te | va)                    # tudo o que é mais antigo que a validação

    # padronização: média/desvio calculados SÓ no treino (senão há vazamento de informação)
    mu, sd = w["X"][tr].mean(0), w["X"][tr].std(0) + 1e-6
    y_mu, y_sd = w["Y"][tr].mean(0), w["Y"][tr].std(0) + 1e-6
    sx = lambda a: ((a - mu) / sd).astype(np.float32)
    sy = lambda a: ((a - y_mu) / y_sd).astype(np.float32)

    rs = lambda m: w["Y"][m] * w["ref"][m, None]    # y real em R$
    return Dataset(
        sx(w["X"][tr]), sy(w["Y"][tr]), sx(w["X"][va]), sy(w["Y"][va]), sx(w["X"][te]), sy(w["Y"][te]),
        ref={"tr": w["ref"][tr], "va": w["ref"][va], "te": w["ref"][te]},
        true_rs={"tr": rs(tr), "va": rs(va), "te": rs(te)},
        base_rs={k: v[te] for k, v in w["baselines"].items()},
        y_mu=y_mu, y_sd=y_sd, cats=cats,
        info=dict(n_train=int(tr.sum()), n_val=int(va.sum()), n_test=int(te.sum()),
                  n_features=w["X"].shape[1], n_outputs=w["Y"].shape[1],
                  test_months=[str(m) for m in months[T - test_months:]]),
    )


def to_rs(pred_std, ref, ds):
    """Converte a saída da rede (padronizada) de volta para R$."""
    ratio = pred_std * ds.y_sd + ds.y_mu
    return np.maximum(ratio, 0) * ref[:, None]


# -----------------------------------------------------------------------------
# 5) Métricas e baselines
# -----------------------------------------------------------------------------
def wape(pred, true):
    """Erro absoluto total / gasto total. 0,20 = erra 20% do valor gasto, em média."""
    if true.sum() < 1.0:      # categoria sem gasto no período (ex.: IPVA fora de jan/fev)
        return float("nan")
    return float(np.abs(pred - true).sum() / true.sum())


def report(preds_rs: dict, true_rs, cats, title="Teste"):
    """Tabela: WAPE geral e por categoria, uma linha por método."""
    rows = {}
    for name, p in preds_rs.items():
        row = {"GERAL": wape(p, true_rs)}
        for k, c in enumerate(cats):
            row[c] = wape(p[:, k], true_rs[:, k])
        rows[name] = row
    df = pd.DataFrame(rows).T
    pd.set_option("display.width", 200, "display.max_columns", 30)
    print(f"\n=== {title}: WAPE (menor é melhor) ===")
    print(df.round(3).to_string())
    return df


def main(path, partial_day=None, use_mlflow=False, experiment="previsao-gastos", run_name=None):
    task = f"projecao-dia{partial_day}" if partial_day else "mes-seguinte"
    with tracking.run(use_mlflow, experiment, run_name or f"baselines-{task}", tags={"modelo": "baselines", "tarefa": task},
                      params={"csv": path, "dia_parcial": partial_day}, data_path=path) as trk:
        ds = build_dataset(path, partial_day=partial_day)
        print("Tamanhos:", ds.info)
        trk.params({k: v for k, v in ds.info.items() if k != "test_months"})
        preds = {k: v for k, v in ds.base_rs.items()}

        try:  # baseline forte: regressão linear regularizada nas MESMAS features
            from sklearn.linear_model import Ridge
            m = Ridge(alpha=10.0).fit(ds.Xtr, ds.Ytr)
            preds["ridge"] = to_rs(m.predict(ds.Xte), ds.ref["te"], ds)
        except ImportError:
            print("(instale scikit-learn para ver o baseline Ridge)")

        df = report(preds, ds.true_rs["te"], ds.cats)
        for method, row in df.iterrows():
            trk.metric(f"teste/wape_geral/{method}", row["GERAL"])
        trk.table(df.round(4), "wape_por_categoria.csv")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("dia_parcial", nargs="?", type=int, default=None,
                    help="opcional: projeta o mês em curso sabendo o gasto até este dia (ex.: 15)")
    ap.add_argument("--mlflow", action="store_true")
    ap.add_argument("--experiment", default="previsao-gastos")
    ap.add_argument("--run-name", default=None)
    a = ap.parse_args()
    main(a.csv, a.dia_parcial, a.mlflow, a.experiment, a.run_name)
