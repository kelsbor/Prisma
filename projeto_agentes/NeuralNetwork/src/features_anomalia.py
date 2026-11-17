#!/usr/bin/env python3
"""
Features por transação + split temporal + métricas + baselines para detecção de anomalias.
Testável sem PyTorch. O treino do autoencoder (PyTorch) está em treinar_autoencoder.py.

Uso:
  python src/features_anomalia.py data/generated/transactions.csv
  python src/features_anomalia.py data/generated/transactions.csv --contaminado
  python src/features_anomalia.py data/generated/transactions.csv --sem-hora

IDEIA CENTRAL: uma transação só é "estranha" em relação ao histórico DAQUELE usuário. Por isso as
features são relativas: o valor é convertido em z-score robusto dentro de (usuário x categoria), o
estabelecimento vira "familiaridade" (quantas vezes este usuário já o usou) etc. As estatísticas são
calculadas só no período de treino, então nada do futuro vaza para o passado.

Split temporal (padrão): treino < 2024-07-01 | validação < 2025-01-01 | teste = 2025.
"""
import argparse
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

import tracking

TRAIN_END, VAL_END = "2024-07-01", "2025-01-01"
EXCLUDE_CATS = ["Investimentos"]          # aportes não são alvo de detecção
ALERT_RATE = 0.01                         # "Recall@1%": fração das anomalias entre os 1% maiores scores
SHORT_NAMES = {                           # chaves curtas e estáveis para as métricas no MLflow
    "autoencoder (PyTorch)": "ae_torch", "autoencoder MLP (sklearn)": "ae_sklearn", "Isolation Forest": "iforest",
    "PCA (autoencoder linear), k=8": "pca", "z-score do valor (|z|)": "zscore",
}


@dataclass
class AnomalyData:
    X: np.ndarray            # [N, F] padronizado (float32)
    y: np.ndarray            # 1 = anomalia (só para AVALIAR; nunca entra no treino)
    atype: np.ndarray        # tipo da anomalia ("" se normal)
    split: np.ndarray        # "train" | "val" | "test"
    fit_mask: np.ndarray     # linhas usadas para treinar/validar (depende de --contaminado)
    raw: pd.DataFrame        # features sem padronizar + metadados
    names: list              # nome das colunas de X
    mean: np.ndarray
    std: np.ndarray


def build_features(tx, use_time=True, contaminated=False, train_end=TRAIN_END, val_end=VAL_END):
    train_end, val_end = pd.Timestamp(train_end), pd.Timestamp(val_end)
    tx = tx.sort_values(["user_id", "timestamp"]).reset_index(drop=True)
    t0 = tx.timestamp.min().normalize()
    n_train_months = max(1.0, (train_end - t0).days / 30.4)
    income = tx[(tx.category == "Renda") & (tx.timestamp < train_end)].groupby("user_id").amount.sum() / n_train_months

    d = tx[(tx.type == "debit") & (~tx.category.isin(EXCLUDE_CATS))].copy().reset_index(drop=True)
    d["log_amt"] = np.log(d.amount.abs())
    in_train = (d.timestamp < train_end).values
    fit_rows = in_train & ((d.is_anomaly == 0).values | contaminated)   # o que o modelo "pode ver" ao aprender o normal

    # 1) valor relativo ao usuário: z-score robusto (mediana/IQR) por usuário x categoria, só com o treino
    g = d[fit_rows].groupby(["user_id", "category"]).log_amt
    st = pd.DataFrame({"med": g.median(), "q1": g.quantile(0.25), "q3": g.quantile(0.75), "n": g.size()})
    st["sd"] = ((st.q3 - st.q1) / 1.349).clip(lower=0.15)
    gc = d[fit_rows].groupby("category").log_amt
    stc = pd.DataFrame({"med_c": gc.median(), "sd_c": ((gc.quantile(0.75) - gc.quantile(0.25)) / 1.349).clip(lower=0.15)})
    d = d.join(st[["med", "sd", "n"]], on=["user_id", "category"]).join(stc, on="category")
    ok = d.n.fillna(0) >= 5                                    # poucas amostras -> usa a referência da categoria
    d["z_amt"] = ((d.log_amt - np.where(ok, d.med, d.med_c)) / np.where(ok, d.sd, d.sd_c)).clip(-10, 10)
    inc = d.user_id.map(income).fillna(income.median()).clip(lower=1.0)
    d["log_over_income"] = np.log1p(100 * d.amount.abs() / inc)

    # 2) calendário
    ts = d.timestamp
    d["dow_sin"], d["dow_cos"] = np.sin(2 * np.pi * ts.dt.dayofweek / 7), np.cos(2 * np.pi * ts.dt.dayofweek / 7)
    d["dom"] = ts.dt.day / 31.0
    if use_time:
        h = ts.dt.hour + ts.dt.minute / 60.0
        d["hour_sin"], d["hour_cos"] = np.sin(2 * np.pi * h / 24), np.cos(2 * np.pi * h / 24)

    # 3) familiaridade do estabelecimento (leave-one-out: a própria transação não conta a seu favor)
    mc = d[fit_rows].groupby(["user_id", "merchant"]).size().rename("mcount")
    d = d.join(mc, on=["user_id", "merchant"])
    d["mcount"] = (d.mcount.fillna(0) - fit_rows).clip(lower=0)
    d["log_mcount"] = np.log1p(d.mcount)
    d["new_merchant"] = (d.mcount == 0).astype(float)

    # 4) tempo entre transações e "rajadas" (sem horário: usa só a data)
    # minutos desde o início (independe da resolução do datetime: pandas 3 usa microssegundos, pandas 2 usa nanossegundos)
    base = ts if use_time else ts.dt.normalize()
    d["t"] = (base - base.min()).dt.total_seconds() / 60.0
    d["log_dt_prev"] = np.log1p(d.groupby("user_id").t.diff().fillna(1e5))
    user_code = d.user_id.astype("category").cat.codes.values.astype(np.float64)
    key = user_code * 1e8 + d.t.values
    window = 60.0 if use_time else 0.0
    d["burst"] = np.arange(len(d)) - np.searchsorted(key, key - window, side="left")

    # 5) duplicatas e variação em relação à compra anterior no mesmo estabelecimento
    dtd = d.groupby(["user_id", "merchant", "amount"]).t.diff()
    d["dup_score"] = np.where(dtd.notna() & (dtd <= 1440), 1 - np.log1p(dtd.fillna(1440)) / np.log1p(1440), 0.0)
    prev = d.groupby(["user_id", "merchant"]).log_amt.shift(1)
    d["d_prev"] = (d.log_amt - prev).fillna(0.0).clip(-5, 5)
    d["has_prev"] = prev.notna().astype(float)

    num = ["z_amt", "log_over_income", "dow_sin", "dow_cos", "dom", "log_mcount", "new_merchant", "log_dt_prev",
           "burst", "dup_score", "d_prev", "has_prev"] + (["hour_sin", "hour_cos"] if use_time else [])
    cats = sorted(d[in_train].category.unique())
    onehot = pd.get_dummies(d.category).reindex(columns=cats, fill_value=0).astype(float)
    onehot.columns = [f"cat_{c}" for c in cats]
    F = pd.concat([d[num].astype(float), onehot], axis=1)

    split = np.where(ts < train_end, "train", np.where(ts < val_end, "val", "test"))
    fit_mask = (split != "test") & ((d.is_anomaly == 0).values | contaminated)
    tr = fit_mask & (split == "train")
    mean, std = F.values[tr].mean(0), F.values[tr].std(0)
    std = np.where(std < 1e-3, 1.0, std)
    X = ((F.values - mean) / std).clip(-10, 10).astype(np.float32)
    raw = pd.concat([d[["user_id", "timestamp", "category", "merchant", "amount", "description"]], F], axis=1)
    return AnomalyData(X, d.is_anomaly.values.astype(int), d.anomaly_type.fillna("").values, split, fit_mask,
                       raw, list(F.columns), mean, std)


# ----------------------------------------------------------------------------- avaliação
def evaluate(scores, ds, alert_rate=ALERT_RATE):
    """Métricas no TESTE: ROC-AUC, PR-AUC e recall entre os top alert_rate% scores, geral e por tipo."""
    te = ds.split == "test"
    y, s = ds.y[te], np.asarray(scores)[te]
    thr = np.quantile(s, 1 - alert_rate)
    out = {"ROC-AUC": roc_auc_score(y, s), "PR-AUC": average_precision_score(y, s),
           f"Recall@{alert_rate:.0%}": float(((s >= thr) & (y == 1)).sum() / max(y.sum(), 1))}
    at = ds.atype[te]
    for t in sorted(set(at) - {""}):
        m = (at == t) | (y == 0)
        out[f"AUC {t}"] = roc_auc_score((at[m] == t).astype(int), s[m])
    return out


def log_results(trk, results, prefix="teste"):
    """Registra no MLflow as métricas de cada método (ROC-AUC, PR-AUC, Recall@x% e AUC por tipo)."""
    for method, row in results.items():
        for metric, v in row.items():
            trk.metric(f"{prefix}/{SHORT_NAMES.get(method, method)}/{metric}", v)


def print_table(results, cols=None):
    df = pd.DataFrame(results).T
    cols = cols or list(df.columns)
    pd.set_option("display.width", 220, "display.max_columns", 30)
    print(df[cols].round(3).to_string())


# ----------------------------------------------------------------------------- baselines
def run_baselines(ds, n_fit=150_000, seed=0, with_mlp=True, return_scores=False):
    from sklearn.decomposition import PCA
    from sklearn.ensemble import IsolationForest
    rng = np.random.default_rng(seed)
    idx = np.where(ds.fit_mask & (ds.split == "train"))[0]
    idx = rng.choice(idx, min(n_fit, len(idx)), replace=False)
    Xf = ds.X[idx]
    res, sc = {}, {}
    sc["z-score do valor (|z|)"] = np.abs(ds.raw["z_amt"].values)
    iso = IsolationForest(n_estimators=100, random_state=seed, n_jobs=-1).fit(Xf)
    sc["Isolation Forest"] = -iso.score_samples(ds.X)
    pca = PCA(n_components=8).fit(Xf)
    sc["PCA (autoencoder linear), k=8"] = ((ds.X - pca.inverse_transform(pca.transform(ds.X))) ** 2).mean(1)
    if with_mlp:
        from sklearn.neural_network import MLPRegressor
        ae = MLPRegressor(hidden_layer_sizes=(32, 8, 32), alpha=1e-4, early_stopping=True, n_iter_no_change=5,
                          max_iter=60, random_state=seed).fit(Xf, Xf)
        sc["autoencoder MLP (sklearn)"] = ((ds.X - ae.predict(ds.X)) ** 2).mean(1)
    res = {k: evaluate(v, ds) for k, v in sc.items()}
    return (res, sc) if return_scores else res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--contaminado", action="store_true", help="treina com anomalias misturadas (como em dados reais)")
    ap.add_argument("--sem-hora", action="store_true", help="ignora o horário (simula extratos só com data)")
    ap.add_argument("--mlflow", action="store_true", help="registra as métricas dos baselines no MLflow")
    ap.add_argument("--experiment", default="anomalias")
    ap.add_argument("--run-name", default=None)
    a = ap.parse_args()
    mode = f"{'contaminado' if a.contaminado else 'limpo'}-{'sem' if a.sem_hora else 'com'}-hora"
    tx = pd.read_csv(a.csv, parse_dates=["timestamp"])
    with tracking.run(a.mlflow, a.experiment, a.run_name or f"baselines-{mode}", tags={"modelo": "baselines", "modo": mode},
                      params=vars(a), data_path=a.csv) as trk:
        ds = build_features(tx, use_time=not a.sem_hora, contaminated=a.contaminado)
        te = ds.split == "test"
        n_tr, n_va = int(((ds.split == "train") & ds.fit_mask).sum()), int(((ds.split == "val") & ds.fit_mask).sum())
        print(f"features: {len(ds.names)} | treino {n_tr:,} | validação {n_va:,} | teste {int(te.sum()):,} "
              f"({ds.y[te].mean():.2%} anomalias)")
        print(f"modo: {mode}\n")
        trk.params({"n_features": len(ds.names), "n_treino": n_tr, "n_validacao": n_va, "n_teste": int(te.sum()),
                    "taxa_anomalias_teste": round(float(ds.y[te].mean()), 4)})
        res = run_baselines(ds)
        print_table(res, ["ROC-AUC", "PR-AUC", f"Recall@{ALERT_RATE:.0%}"])
        print("\nAUC por tipo de anomalia:")
        print_table(res, [c for c in next(iter(res.values())) if c.startswith("AUC ")])
        log_results(trk, res)
        trk.table(pd.DataFrame(res).T.round(4), "metricas_por_metodo.csv")
