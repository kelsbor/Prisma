#!/usr/bin/env python3
"""
Autoencoder (PyTorch) para detecção de anomalias em transações bancárias.

Exemplos:
    python src/treinar_autoencoder.py data/generated/transactions.csv
    python src/treinar_autoencoder.py data/generated/transactions.csv --contaminado --sem-hora
    python src/treinar_autoencoder.py data/generated/transactions.csv --noise 0.1 --bottleneck 4
    python src/treinar_autoencoder.py data/generated/transactions.csv --contaminado --mlflow

Requer: pip install torch numpy pandas scikit-learn

COMO FUNCIONA
  1. Cada transação vira um vetor de ~29 números (features_anomalia.py): valor relativo ao usuário,
     familiaridade do estabelecimento, horário, rajadas, duplicatas, categoria...
  2. O autoencoder aprende a COMPRIMIR esse vetor num gargalo pequeno (6 números) e a RECONSTRUÍ-LO:
         x  ->  [Encoder 29->32->16->6]  ->  z  ->  [Decoder 6->16->32->29]  ->  x_hat
  3. Treinamos só com transações "normais" (ou quase). Como o gargalo é estreito, a rede só consegue
     reconstruir bem os padrões que viu com frequência.
  4. Uma transação estranha (valor fora do padrão, estabelecimento novo de madrugada, duplicata)
     é reconstruída mal. O ERRO DE RECONSTRUÇÃO  mean((x - x_hat)^2)  é o score de anomalia.
  5. O limiar é escolhido na validação: alertamos os `alert_rate` (ex.: 1%) maiores scores.

  Nenhum rótulo de anomalia é usado no treino. Os rótulos servem só para AVALIAR (sintético) -
  em dados reais (Open Finance) você não os terá, e a avaliação exige injetar anomalias artificiais.

MAPA DO PYTORCH (igual ao treinar_mlp.py): [1] tensores, [2] DataLoader, [3] nn.Module, [4] loss,
[5] optimizer, [6] loop (zero_grad -> forward -> loss -> backward -> step), [7] validação + early stopping.
"""
import argparse
import copy
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

import tracking
from features_anomalia import ALERT_RATE, build_features, evaluate, log_results, print_table, run_baselines

PROJECT_ROOT = Path(__file__).resolve().parents[1]


# [3] A REDE ------------------------------------------------------------------------------
class AutoEncoder(nn.Module):
    """
    Encoder: afunila (n_in -> 32 -> 16 -> bottleneck). Decoder: espelho (bottleneck -> 16 -> 32 -> n_in).

    - O GARGALO (bottleneck) sem ativação é o ponto-chave: força a rede a resumir a transação. Se ele for
      grande demais (≈ n_in), a rede aprende a "copiar" o input e reconstrói TUDO bem, até anomalias.
    - ReLU nas camadas escondidas dá a não linearidade. Sem ela, o autoencoder equivale ao PCA.
    - A saída não tem ativação: estamos reconstruindo números padronizados (média 0, desvio 1).
    """

    def __init__(self, n_in, hidden=(32, 16), bottleneck=6):
        super().__init__()
        enc, d = [], n_in
        for h in hidden:
            enc += [nn.Linear(d, h), nn.ReLU()]
            d = h
        enc.append(nn.Linear(d, bottleneck))
        dec, d = [], bottleneck
        for h in reversed(hidden):
            dec += [nn.Linear(d, h), nn.ReLU()]
            d = h
        dec.append(nn.Linear(d, n_in))
        self.encoder, self.decoder = nn.Sequential(*enc), nn.Sequential(*dec)

    def forward(self, x):
        return self.decoder(self.encoder(x))


@torch.no_grad()                                     # não precisamos de gradientes para pontuar
def reconstruction_error(model, X, device, batch=8192, per_feature=False):
    model.eval()                                     # (sem Dropout aqui, mas é boa prática)
    out = []
    for i in range(0, len(X), batch):
        xb = torch.from_numpy(X[i:i + batch]).to(device)
        err = (xb - model(xb)) ** 2                  # erro ao quadrado de cada feature
        out.append((err if per_feature else err.mean(dim=1)).cpu().numpy())
    return np.concatenate(out)


def explain(ds, rows, k=3):
    """Mostra as k features mais fora do padrão (|valor padronizado|) de cada transação sinalizada.
    Obs.: NÃO usamos o erro de reconstrução por feature como explicação - quando o input é estranho, o
    decodificador erra várias features ao mesmo tempo (inclusive as normais) e a atribuição engana."""
    for r in rows:
        info = ds.raw.iloc[r]
        top = np.argsort(-np.abs(ds.X[r]))[:k]
        why = ", ".join(f"{ds.names[j]}={ds.X[r][j]:+.1f}" for j in top)
        print(f"  {info.timestamp} | {info.description[:34]:34s} | R$ {abs(info.amount):9.2f} | "
              f"{ds.atype[r] or 'normal':22s} | {why}")


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--contaminado", action="store_true", help="treina com anomalias misturadas (realista)")
    ap.add_argument("--sem-hora", action="store_true", help="ignora o horário (extratos só com data)")
    ap.add_argument("--hidden", type=int, nargs="+", default=[32, 16])
    ap.add_argument("--bottleneck", type=int, default=6)
    ap.add_argument("--noise", type=float, default=0.0, help=">0 = autoencoder com ruído (denoising)")
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--wd", type=float, default=1e-5)
    ap.add_argument("--batch", type=int, default=1024)
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--patience", type=int, default=8)
    ap.add_argument("--alert-rate", type=float, default=ALERT_RATE)
    ap.add_argument("--sem-baselines", action="store_true")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=str(PROJECT_ROOT / "artifacts" / "models" / "autoencoder.pt"))
    ap.add_argument("--mlflow", action="store_true", help="registra parâmetros, métricas e modelo no MLflow")
    ap.add_argument("--experiment", default="anomalias")
    ap.add_argument("--run-name", default=None)
    return ap.parse_args()


def treinar(a, trk):
    torch.manual_seed(a.seed)
    np.random.seed(a.seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"

    tx = pd.read_csv(a.csv, parse_dates=["timestamp"])
    ds = build_features(tx, use_time=not a.sem_hora, contaminated=a.contaminado)
    tr = np.where(ds.fit_mask & (ds.split == "train"))[0]
    va = np.where(ds.fit_mask & (ds.split == "val"))[0]
    print(f"dispositivo: {device} | features: {ds.X.shape[1]} | treino {len(tr):,} | validação {len(va):,} | "
          f"modo: {'contaminado' if a.contaminado else 'limpo'}")

    # [1][2] tensores e lotes (o alvo é o PRÓPRIO input: o autoencoder reconstrói x) ----------------
    loader = DataLoader(TensorDataset(torch.from_numpy(ds.X[tr])), batch_size=a.batch, shuffle=True)
    Xva = ds.X[va]

    # [3][4][5] modelo, perda e otimizador ----------------------------------------------------------
    model = AutoEncoder(ds.X.shape[1], tuple(a.hidden), a.bottleneck).to(device)
    print(f"autoencoder: {ds.X.shape[1]} -> {' -> '.join(map(str, a.hidden))} -> {a.bottleneck} (gargalo) -> ... "
          f"| {sum(p.numel() for p in model.parameters()):,} parâmetros")
    n_params = sum(p.numel() for p in model.parameters())
    trk.params({"n_features": ds.X.shape[1], "n_treino": len(tr), "n_validacao": len(va), "n_params": n_params})
    loss_fn = nn.MSELoss()
    opt = torch.optim.Adam(model.parameters(), lr=a.lr, weight_decay=a.wd)

    # [6][7] loop de treino com early stopping ----------------------------------------------------------
    best, best_state, wait = float("inf"), None, 0
    for epoch in range(1, a.epochs + 1):
        model.train()
        total = 0.0
        for (xb,) in loader:
            xb = xb.to(device)
            inp = xb + a.noise * torch.randn_like(xb) if a.noise > 0 else xb   # denoising: corrompe a entrada
            opt.zero_grad()
            loss = loss_fn(model(inp), xb)                                      # compara com o original limpo
            loss.backward()
            opt.step()
            total += loss.item() * len(xb)
        train_loss = total / len(tr)
        val_loss = float(reconstruction_error(model, Xva, device).mean())
        trk.metric("loss/treino", train_loss, step=epoch)
        trk.metric("loss/validacao", val_loss, step=epoch)
        if val_loss < best - 1e-6:
            best, best_state, wait = val_loss, copy.deepcopy(model.state_dict()), 0
        else:
            wait += 1
        if epoch == 1 or epoch % 5 == 0:
            print(f"época {epoch:3d} | treino {train_loss:.4f} | validação {val_loss:.4f}")
        if wait >= a.patience:
            print(f"parou na época {epoch} (melhor validação: {best:.4f})")
            break
    model.load_state_dict(best_state)

    # limiar de alerta: percentil dos scores de validação; depois avaliamos no teste -------------------------
    scores = reconstruction_error(model, ds.X, device)
    thr = float(np.quantile(scores[va], 1 - a.alert_rate))
    te = ds.split == "test"
    alerts = (scores >= thr) & te
    tp = int((alerts & (ds.y == 1)).sum())
    print(f"\nLimiar (percentil {1 - a.alert_rate:.0%} da validação) = {thr:.3f}")
    print(f"No teste: {int(alerts.sum()):,} alertas ({alerts.sum() / te.sum():.2%} das transações) | "
          f"precisão {tp / max(alerts.sum(), 1):.1%} | recall {tp / max(ds.y[te].sum(), 1):.1%}")
    trk.metrics({"limiar": thr, "alertas": int(alerts.sum()), "precisao_no_limiar": tp / max(alerts.sum(), 1),
                 "recall_no_limiar": tp / max(ds.y[te].sum(), 1), "melhor_loss_validacao": best}, prefix="teste/ae_torch/")

    results = {"autoencoder (PyTorch)": evaluate(scores, ds, a.alert_rate)}
    if not a.sem_baselines:
        results.update(run_baselines(ds))
    print()
    print_table(results, ["ROC-AUC", "PR-AUC", f"Recall@{a.alert_rate:.0%}"])
    print("\nAUC por tipo de anomalia:")
    print_table(results, [c for c in next(iter(results.values())) if c.startswith("AUC ")])
    log_results(trk, results)
    trk.table(pd.DataFrame(results).T.round(4), "metricas_por_metodo.csv")

    print("\nOs 8 maiores scores do teste e as features mais fora do padrão (valores em desvios-padrão):")
    explain(ds, np.where(te)[0][np.argsort(-scores[te])[:8]])

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"state_dict": best_state, "mean": ds.mean, "std": ds.std, "names": ds.names, "threshold": thr,
                "hidden": a.hidden, "bottleneck": a.bottleneck}, out)
    print(f"\nmodelo salvo em {out}")
    trk.artifact(out, "modelo")


def main():
    a = parse_args()
    mode = f"{'cont' if a.contaminado else 'limpo'}-{'semhora' if a.sem_hora else 'hora'}"
    name = a.run_name or f"ae-{mode}-b{a.bottleneck}-n{a.noise}-s{a.seed}"
    with tracking.run(a.mlflow, a.experiment, name, tags={"modelo": "autoencoder", "modo": mode},
                      params=vars(a), data_path=a.csv) as trk:
        treinar(a, trk)


if __name__ == "__main__":
    main()
