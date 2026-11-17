#!/usr/bin/env python3
"""
Executa o projeto inteiro, em ordem, usando o MESMO interpretador Python que rodou este script
(garante o ambiente isolado: ative o venv/conda antes e rode `python src/rodar_tudo.py`).

Etapas disponíveis (use --so para escolher):
  gerar         gera o dataset sintético (pula se já existir; --regerar força)
  calibrar      compara o dataset com a POF/IBGE (relatorio_calibracao.py)
  baselines     baselines de previsão e de anomalia (sem PyTorch)
  mlp           MLP de previsão de gastos (PyTorch)
  autoencoder   autoencoder de anomalias (PyTorch)

Exemplos:
  python src/rodar_tudo.py --rapido                    # teste de fumaça: 200 usuários, poucas épocas
  python src/rodar_tudo.py --mlflow                    # tudo, registrando no MLflow
  python src/rodar_tudo.py --mlflow --seeds 0 1 2      # repete os treinos com 3 seeds
  python src/rodar_tudo.py --so gerar calibrar          # dados e calibração
  python src/rodar_tudo.py --pular-torch               # sem PyTorch instalado

Depois:  mlflow ui --backend-store-uri sqlite:///results/mlflow.db
"""
import argparse
import importlib.util
import subprocess
import sys
import time
from pathlib import Path

import tracking

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = sys.executable
ALL_STAGES = ["gerar", "calibrar", "baselines", "mlp", "autoencoder"]


def sh(cmd, log=None):
    """Executa um comando (no mesmo Python) e devolve (código de saída, segundos)."""
    cmd = [str(c) for c in cmd]
    print(f"\n$ {' '.join(cmd)}", flush=True)
    t = time.time()
    if log:
        with open(log, "w", encoding="utf-8") as f:
            p = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, text=True, cwd=ROOT)
        print(Path(log).read_text(encoding="utf-8")[-1500:])       # mostra o final do log
    else:
        p = subprocess.run(cmd, cwd=ROOT)
    return p.returncode, time.time() - t


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--usuarios", type=int, default=1000)
    ap.add_argument("--seed-dados", type=int, default=42)
    ap.add_argument("--dados", default="data/generated", help="pasta de saída/entrada dos dados")
    ap.add_argument("--jobs", type=int, default=1, help="processos na geração dos dados")
    ap.add_argument("--regerar", action="store_true")
    ap.add_argument("--rapido", action="store_true", help="200 usuários e poucas épocas (teste de fumaça)")
    ap.add_argument("--mlflow", action="store_true", help="registra tudo no MLflow")
    ap.add_argument("--seeds", type=int, nargs="+", default=[0], help="seeds dos treinos (repetir mede a variância)")
    ap.add_argument("--so", nargs="+", choices=ALL_STAGES, help="roda apenas estas etapas")
    ap.add_argument("--pular-torch", action="store_true")
    a = ap.parse_args()

    n_users = 200 if a.rapido else a.usuarios
    epochs = ["--epochs", "15", "--patience", "4"] if a.rapido else ["--epochs", "200", "--patience", "15"]
    ae_epochs = (["--epochs", "15", "--patience", "4"] if a.rapido else ["--epochs", "60", "--patience", "8"])
    ml = ["--mlflow"] if a.mlflow else []
    data = Path(a.dados) if Path(a.dados).is_absolute() else ROOT / a.dados
    csv, pers = data / "transactions.csv", data / "personas.csv"
    stages = a.so or ALL_STAGES
    data.mkdir(parents=True, exist_ok=True)

    has_torch = importlib.util.find_spec("torch") is not None
    if not has_torch and not a.pular_torch and {"mlp", "autoencoder"} & set(stages):
        print("AVISO: PyTorch não encontrado neste ambiente; pulando 'mlp' e 'autoencoder' (veja o README).")
        a.pular_torch = True
    if a.mlflow and importlib.util.find_spec("mlflow") is None:
        sys.exit("MLflow não está instalado neste ambiente: `pip install mlflow` (ou rode sem --mlflow).")

    status = []                                                     # (etapa, comando curto, ok, segundos)

    def step(stage, label, cmd, log=None):
        code, dt = sh(cmd, log)
        status.append((stage, label, code == 0, dt))
        return code == 0

    if "gerar" in stages:
        if csv.exists() and not a.regerar:
            print(f"\n[gerar] {csv} já existe; pulando (use --regerar).")
        else:
            step("gerar", f"{n_users} usuários", [PY, HERE / "gerar_dados_sinteticos.py", "--n-users", n_users, "--seed",
                                                  a.seed_dados, "--out", data, "--jobs", a.jobs])
    if not csv.exists():
        sys.exit(f"{csv} não existe; rode a etapa 'gerar'.")

    if "calibrar" in stages:
        step("calibrar", "POF/IBGE", [PY, HERE / "relatorio_calibracao.py", csv, pers],
             log=data / "calibracao.txt")

    if "baselines" in stages:
        step("baselines", "previsão mês seguinte", [PY, HERE / "pipeline_features.py", csv, *ml])
        step("baselines", "previsão dia 15", [PY, HERE / "pipeline_features.py", csv, "15", *ml])
        step("baselines", "anomalia limpo+hora", [PY, HERE / "features_anomalia.py", csv, *ml])
        step("baselines", "anomalia contaminado", [PY, HERE / "features_anomalia.py", csv, "--contaminado", *ml])
        step("baselines", "anomalia contaminado sem hora",
             [PY, HERE / "features_anomalia.py", csv, "--contaminado", "--sem-hora", *ml])

    if "mlp" in stages and not a.pular_torch:
        for s in a.seeds:
            step("mlp", f"projeção dia 15, L1, seed {s}",
                 [PY, HERE / "treinar_mlp.py", csv, "--dia-parcial", 15, "--loss", "l1", "--seed", s, *epochs,
                  "--out", ROOT / "artifacts" / "models" / f"mlp-projecao-dia15-seed{s}.pt", *ml])
            step("mlp", f"mês seguinte, MSE, seed {s}",
                 [PY, HERE / "treinar_mlp.py", csv, "--seed", s, *epochs,
                  "--out", ROOT / "artifacts" / "models" / f"mlp-mes-seguinte-seed{s}.pt", *ml])

    if "autoencoder" in stages and not a.pular_torch:
        variantes = [("contaminado, com hora", ["--contaminado"]),
                     ("contaminado, sem hora", ["--contaminado", "--sem-hora"]),
                     ("contaminado, com ruído", ["--contaminado", "--noise", "0.1"])]
        for s in a.seeds:
            for label, extra in variantes:
                mode = label.replace(", ", "-").replace(" ", "-")
                step("autoencoder", f"{label}, seed {s}",
                     [PY, HERE / "treinar_autoencoder.py", csv, *extra, "--seed", s, *ae_epochs,
                      "--sem-baselines", "--out",
                      ROOT / "artifacts" / "models" / f"autoencoder-{mode}-seed{s}.pt", *ml])

    # registro da linhagem dos dados no MLflow (parâmetros de geração, validação, calibração)
    if a.mlflow and {"gerar", "calibrar"} & set(stages):
        with tracking.run(True, "dados", f"dados-n{n_users}-s{a.seed_dados}",
                          params={"n_usuarios": n_users, "seed_dados": a.seed_dados}, data_path=csv) as trk:
            trk.artifact(data / "calibracao.txt", "relatorios")
            trk.artifact(pers, "dados")

    print("\n" + "=" * 78 + "\nRESUMO\n" + "=" * 78)
    for stage, label, ok, dt in status:
        print(f"[{'OK ' if ok else 'FALHA'}] {stage:13s} {label:38s} {dt:7.1f}s")
    falhas = [s for s in status if not s[2]]
    print(f"\n{len(status) - len(falhas)}/{len(status)} etapas OK" + ("" if not a.mlflow else
          "  |  ver resultados: mlflow ui --backend-store-uri sqlite:///results/mlflow.db"))
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
