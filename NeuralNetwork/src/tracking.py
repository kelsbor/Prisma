#!/usr/bin/env python3
"""
Camada fina sobre o MLflow para organizar os experimentos.

Princípios:
  - Desligada por padrão: sem --mlflow, tudo roda e imprime como antes (Tracker "no-op").
  - Cada run registra: parâmetros, métricas por época, métricas finais, artefatos (modelo, tabelas) e
    TAGS de reprodutibilidade (hash MD5 do CSV de dados, versões das bibliotecas, commit do git).
  - Backend local em results/mlflow.db e artefatos em results/mlartifacts. Troque com variáveis de ambiente:
        MLFLOW_TRACKING_URI
        MLFLOW_ARTIFACT_ROOT

Uso típico dentro de um script:
    import tracking
    with tracking.run(args.mlflow, "anomalias", run_name="ae-b6", params=vars(args), data_path=csv) as trk:
        trk.metric("loss/train", 0.12, step=epoch)
        trk.metrics({"ROC-AUC": 0.91}, prefix="teste/")
        trk.artifact("autoencoder.pt")

Ver resultados:   mlflow ui --backend-store-uri sqlite:///results/mlflow.db
"""
import contextlib
import hashlib
import math
import os
import platform
import re
import subprocess
import unicodedata
from importlib import metadata
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_URI = f"sqlite:///{PROJECT_ROOT / 'results' / 'mlflow.db'}"
DEFAULT_ARTIFACTS = str(PROJECT_ROOT / "results" / "mlartifacts")


def slug(s, maxlen=240):
    """Nomes de métricas/parâmetros do MLflow: só ASCII, letras, números e _ . - / espaço."""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9_.\-/ ]+", "_", s).strip("_ ")
    return (s or "x")[:maxlen]


def file_fingerprint(path):
    """MD5 e tamanho do arquivo de dados: garante que dois runs usaram exatamente os mesmos dados."""
    h, n = hashlib.md5(), 0
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
            n += len(chunk)
    return h.hexdigest(), n


def env_info():
    info = {"env.python": platform.python_version(), "env.platform": platform.platform()}
    for pkg in ("numpy", "pandas", "scipy", "scikit-learn", "torch", "mlflow"):
        try:
            info[f"lib.{pkg}"] = metadata.version(pkg)
        except metadata.PackageNotFoundError:
            pass
    try:
        info["git.commit"] = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL, text=True).strip()
    except Exception:
        pass
    return info


class Tracker:
    """Fachada: todos os métodos são seguros de chamar mesmo com o MLflow desligado."""

    def __init__(self, mlflow=None):
        self._m = mlflow

    @property
    def enabled(self):
        return self._m is not None

    def params(self, d):
        if self.enabled:
            self._m.log_params({slug(k): str(v)[:500] for k, v in d.items()})

    def tags(self, d):
        if self.enabled:
            self._m.set_tags({slug(k): str(v)[:5000] for k, v in d.items()})

    def metric(self, name, value, step=None):
        if not self.enabled or value is None:
            return
        try:
            v = float(value)
        except (TypeError, ValueError):
            return
        if math.isfinite(v):                      # NaN/inf (ex.: categoria sem gasto) são ignorados
            self._m.log_metric(slug(name), v, step=step)

    def metrics(self, d, prefix="", step=None):
        for k, v in d.items():
            self.metric(f"{prefix}{k}", v, step)

    def artifact(self, path, subdir=None):
        if self.enabled and Path(path).exists():
            self._m.log_artifact(str(path), subdir)

    def text(self, content, filename):
        if self.enabled:
            self._m.log_text(content, filename)

    def table(self, df, filename):
        if self.enabled:
            self._m.log_text(df.to_csv(), filename)


@contextlib.contextmanager
def run(enabled, experiment, run_name=None, tags=None, params=None, data_path=None):
    """Abre um run do MLflow (ou um Tracker vazio se `enabled` for falso)."""
    if not enabled:
        yield Tracker()
        return
    try:
        import mlflow
    except ImportError:
        raise SystemExit("MLflow não está instalado. Rode `pip install mlflow` ou execute sem --mlflow.")
    (PROJECT_ROOT / "results").mkdir(parents=True, exist_ok=True)
    mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", DEFAULT_URI))
    if mlflow.get_experiment_by_name(experiment) is None:     # define onde os artefatos ficam (explícito)
        root = Path(os.environ.get("MLFLOW_ARTIFACT_ROOT", DEFAULT_ARTIFACTS)).resolve()
        mlflow.create_experiment(experiment, artifact_location=(root / slug(experiment)).as_uri())
    mlflow.set_experiment(experiment)
    with mlflow.start_run(run_name=run_name):
        trk = Tracker(mlflow)
        trk.tags({**env_info(), **(tags or {})})
        if data_path:
            md5, size = file_fingerprint(data_path)
            trk.tags({"data.path": str(data_path), "data.md5": md5, "data.size_mb": round(size / 1e6, 1)})
        if params:
            trk.params(params)
        yield trk
