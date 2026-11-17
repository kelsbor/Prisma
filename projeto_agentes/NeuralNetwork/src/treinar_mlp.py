#!/usr/bin/env python3
"""
Treina um MLP (PyTorch) para prever o gasto por categoria e compara com os baselines.

Exemplos:
    python src/treinar_mlp.py data/generated/transactions.csv
    python src/treinar_mlp.py data/generated/transactions.csv --dia-parcial 15
    python src/treinar_mlp.py data/generated/transactions.csv --dia-parcial 15 --loss l1 --wd 1e-2
    python src/treinar_mlp.py data/generated/transactions.csv --dia-parcial 15 --mlflow

Requer: pip install torch numpy pandas scikit-learn

----------------------------------------------------------------------------------
MAPA MENTAL DO PYTORCH (cada item aparece marcado como [N] no código abaixo)
  [1] Tensor ........ array NumPy que pode ir para GPU e guarda histórico para derivadas
  [2] Dataset/Loader  entrega os dados em lotes (batches) embaralhados
  [3] nn.Module ..... a rede: define camadas (__init__) e como o dado flui (forward)
  [4] Loss .......... mede o erro entre previsão e valor real (um único número)
  [5] Optimizer ..... usa as derivadas do erro para ajustar os pesos (AdamW)
  [6] Loop de treino  zerar gradientes -> forward -> loss -> backward -> step
  [7] Validação ..... mesmo cálculo SEM atualizar pesos; decide quando parar (early stopping)
  [8] Teste ......... usado UMA vez no final, comparando com os baselines
----------------------------------------------------------------------------------
"""
import argparse
import copy
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

import tracking
from pipeline_features import build_dataset, report, to_rs

PROJECT_ROOT = Path(__file__).resolve().parents[1]


# [3] A REDE ------------------------------------------------------------------------
class MLP(nn.Module):
    """
    Perceptron multicamadas: [Linear -> ReLU -> Dropout] repetido, e uma Linear final.

    - Linear(a, b): multiplica por uma matriz de pesos (a x b) e soma um viés.
    - ReLU: zera valores negativos; é o que permite aprender relações NÃO lineares.
    - Dropout: desliga neurônios aleatoriamente no treino para reduzir overfitting.
    - A última camada NÃO tem ativação, pois é regressão (prevê números, não classes).
    """

    def __init__(self, n_in, n_out, hidden=(64, 32), dropout=0.1):
        super().__init__()
        layers, d = [], n_in
        for h in hidden:
            layers += [nn.Linear(d, h), nn.ReLU(), nn.Dropout(dropout)]
            d = h
        layers.append(nn.Linear(d, n_out))
        self.net = nn.Sequential(*layers)

    def forward(self, x):          # define como o dado atravessa a rede
        return self.net(x)


def predict(model, X, device):
    model.eval()                   # desliga o Dropout
    with torch.no_grad():          # não precisamos de gradientes para prever
        return model(torch.from_numpy(X).to(device)).cpu().numpy()


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--dia-parcial", type=int, default=None, help="usa o gasto até este dia do mês como entrada")
    ap.add_argument("--hidden", type=int, nargs="+", default=[64, 32])
    ap.add_argument("--dropout", type=float, default=0.1)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--wd", type=float, default=1e-3, help="weight decay (regularização L2)")
    ap.add_argument("--loss", choices=["mse", "l1", "huber"], default="mse")
    ap.add_argument("--batch", type=int, default=256)
    ap.add_argument("--epochs", type=int, default=200)
    ap.add_argument("--patience", type=int, default=15)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=str(PROJECT_ROOT / "artifacts" / "models" / "modelo_mlp.pt"))
    ap.add_argument("--mlflow", action="store_true", help="registra parâmetros, métricas e modelo no MLflow")
    ap.add_argument("--experiment", default="previsao-gastos")
    ap.add_argument("--run-name", default=None)
    return ap.parse_args()


def treinar(a, trk):
    torch.manual_seed(a.seed)
    np.random.seed(a.seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"dispositivo: {device}")

    # dados (já divididos no tempo e padronizados) -----------------------------------
    ds = build_dataset(a.csv, partial_day=a.dia_parcial)
    print("tamanhos:", ds.info)

    # [1][2] tensores e lotes -------------------------------------------------------
    train_loader = DataLoader(
        TensorDataset(torch.from_numpy(ds.Xtr), torch.from_numpy(ds.Ytr)),
        batch_size=a.batch, shuffle=True)               # embaralha só o TREINO
    Xva = torch.from_numpy(ds.Xva).to(device)
    Yva = torch.from_numpy(ds.Yva).to(device)

    # [3][4][5] modelo, perda e otimizador --------------------------------------------
    model = MLP(ds.info["n_features"], ds.info["n_outputs"], tuple(a.hidden), a.dropout).to(device)
    n_params = sum(p.numel() for p in model.parameters())
    print(f"modelo: {a.hidden} | {n_params:,} parâmetros | {ds.info['n_train']:,} amostras de treino")
    trk.params({"n_params": n_params, **{k: v for k, v in ds.info.items() if k != "test_months"}})

    loss_fn = {"mse": nn.MSELoss(), "l1": nn.L1Loss(), "huber": nn.SmoothL1Loss()}[a.loss]
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=a.wd)

    # [6][7] loop de treino com early stopping --------------------------------------
    best_val, best_state, wait = float("inf"), None, 0
    for epoch in range(1, a.epochs + 1):
        model.train()                                   # liga o Dropout
        total = 0.0
        for xb, yb in train_loader:
            xb, yb = xb.to(device), yb.to(device)
            opt.zero_grad()                             # 1) zera gradientes do lote anterior
            loss = loss_fn(model(xb), yb)               # 2) forward + erro
            loss.backward()                             # 3) backward: calcula as derivadas
            opt.step()                                  # 4) atualiza os pesos
            total += loss.item() * len(xb)
        train_loss = total / len(train_loader.dataset)

        model.eval()
        with torch.no_grad():                           # validação: sem atualizar nada
            val_loss = loss_fn(model(Xva), Yva).item()

        trk.metric("loss/treino", train_loss, step=epoch)
        trk.metric("loss/validacao", val_loss, step=epoch)
        if val_loss < best_val - 1e-5:                  # melhorou: guarda uma cópia dos pesos
            best_val, best_state, wait = val_loss, copy.deepcopy(model.state_dict()), 0
        else:
            wait += 1
        if epoch == 1 or epoch % 10 == 0:
            print(f"época {epoch:3d} | treino {train_loss:.4f} | validação {val_loss:.4f}")
        if wait >= a.patience:                          # early stopping
            print(f"parou na época {epoch} (melhor validação: {best_val:.4f})")
            break

    model.load_state_dict(best_state)                   # volta ao melhor ponto, não ao último
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    torch.save(best_state, out)

    # [8] teste final, em R$, ao lado dos baselines -------------------------------------
    preds = dict(ds.base_rs)
    try:
        from sklearn.linear_model import Ridge
        preds["ridge"] = to_rs(Ridge(alpha=10.0).fit(ds.Xtr, ds.Ytr).predict(ds.Xte), ds.ref["te"], ds)
    except ImportError:
        pass
    preds["mlp"] = to_rs(predict(model, ds.Xte, device), ds.ref["te"], ds)
    df = report(preds, ds.true_rs["te"], ds.cats)

    # registro no MLflow: WAPE geral de cada método, WAPE por categoria do MLP, tabela completa e o modelo
    for method, row in df.iterrows():
        trk.metric(f"teste/wape_geral/{method}", row["GERAL"])
    for cat in ds.cats:
        trk.metric(f"teste/wape_categoria/mlp/{cat}", df.loc["mlp", cat])
    trk.metric("validacao/melhor_loss", best_val)
    trk.table(df.round(4), "wape_por_categoria.csv")
    trk.artifact(out, "modelo")


def main():
    a = parse_args()
    task = f"projecao-dia{a.dia_parcial}" if a.dia_parcial else "mes-seguinte"
    name = a.run_name or f"mlp-{task}-{a.loss}-h{'x'.join(map(str, a.hidden))}-s{a.seed}"
    with tracking.run(a.mlflow, a.experiment, name, tags={"modelo": "mlp", "tarefa": task},
                      params=vars(a), data_path=a.csv) as trk:
        treinar(a, trk)


if __name__ == "__main__":
    main()
