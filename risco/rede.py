"""A rede neural do Agente de Risco: o autoencoder de anomalias do projeto NeuralNetwork/.

O código de features e de treino é o de NeuralNetwork/src (fonte única). Aqui só fazemos três coisas:

1. treinar(): gera dados sintéticos com o gerador do projeto e treina o autoencoder no modo "sem hora"
   (os extratos do Prisma só têm a data) e "contaminado" (como em dados reais, sem rótulos). Usa o
   autoencoder em PyTorch (treinar_autoencoder.py) se o torch estiver instalado; se não, o autoencoder
   MLP do scikit-learn, que o próprio projeto usa como comparação.
2. Exporta os pesos para um .npz: no dia a dia o agente só precisa do NumPy, sem PyTorch.
3. pontuar(): calcula as mesmas features para as transações de UM titular, passa pela rede e devolve o
   erro de reconstrução de cada transação. Erro acima do limiar da validação = transação atípica.
"""

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from comum.config import DATA_DIR, RAIZ, log
from risco.categorias import CATEGORIAS_DA_REDE, categorizar, estabelecimento

PASTA_NN = RAIZ / "NeuralNetwork"
SRC_NN = PASTA_NN / "src"
ARQUIVO_MODELO = DATA_DIR / "modelos" / "risco_autoencoder.npz"
PASTA_DADOS_TREINO = DATA_DIR / "risco_dados"

# Motivo de cada feature conforme o sinal (acima ou abaixo do normal), para explicar os alertas
MOTIVOS = {
    ("z_amt", +1): "valor acima do padrão desta categoria",
    ("z_amt", -1): "valor muito abaixo do padrão desta categoria",
    ("log_over_income", +1): "valor alto em relação à renda",
    ("new_merchant", +1): "estabelecimento novo ou pouco usado",
    ("has_prev", -1): "estabelecimento novo ou pouco usado",
    ("log_mcount", -1): "estabelecimento novo ou pouco usado",
    ("dup_score", +1): "possível cobrança repetida",
    ("burst", +1): "várias transações no mesmo dia",
    ("d_prev", +1): "valor maior que da última vez no mesmo lugar",
    ("d_prev", -1): "valor menor que da última vez no mesmo lugar",
    ("log_dt_prev", -1): "logo depois de outra transação",
    ("log_dt_prev", +1): "depois de muitos dias sem movimento",
    ("dow_sin", +1): "dia incomum", ("dow_sin", -1): "dia incomum",
    ("dow_cos", +1): "dia incomum", ("dow_cos", -1): "dia incomum",
    ("dom", +1): "dia incomum", ("dom", -1): "dia incomum",
}


def _log(msg):
    log("agente-risco", msg)


def _importar_nn():
    if not SRC_NN.exists():
        raise RuntimeError(f"Pasta da rede neural não encontrada: {SRC_NN}")
    if str(SRC_NN) not in sys.path:
        sys.path.insert(0, str(SRC_NN))
    import features_anomalia
    return features_anomalia


# ------------------------------------------------------------------ formato .npz (só NumPy em produção)
def _relu(x):
    return np.maximum(x, 0)


def reconstruir(modelo: dict, X: np.ndarray) -> np.ndarray:
    """Passa X pela rede: camadas lineares com ReLU onde o modelo indicar."""
    h = X
    for W, b, ativ in zip(modelo["W"], modelo["b"], modelo["ativ"]):
        h = h @ W + b
        if ativ == "relu":
            h = _relu(h)
    return h


def salvar(caminho: Path, W, b, ativ, mean, std, names, threshold, meta: dict) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    pesos = {f"W{i}": np.asarray(w, dtype=np.float32) for i, w in enumerate(W)}
    pesos.update({f"b{i}": np.asarray(x, dtype=np.float32) for i, x in enumerate(b)})
    np.savez(caminho, **pesos, ativ=np.array(ativ), mean=np.asarray(mean, dtype=np.float64),
             std=np.asarray(std, dtype=np.float64), names=np.array(names), threshold=np.float64(threshold),
             meta=np.array(json.dumps(meta, ensure_ascii=False)))


def carregar(caminho: Path = ARQUIVO_MODELO) -> dict | None:
    if not caminho.exists():
        return None
    z = np.load(caminho, allow_pickle=False)
    n = len(z["ativ"])
    return {"W": [z[f"W{i}"] for i in range(n)], "b": [z[f"b{i}"] for i in range(n)],
            "ativ": [str(a) for a in z["ativ"]], "mean": z["mean"], "std": z["std"],
            "names": [str(x) for x in z["names"]], "threshold": float(z["threshold"]),
            "meta": json.loads(str(z["meta"]))}


def exportar_torch(checkpoint: dict) -> tuple:
    """Converte o checkpoint do treinar_autoencoder.py (state_dict do AutoEncoder) em W, b, ativações.
    No AutoEncoder, toda Linear é seguida de ReLU, menos a última do encoder (gargalo) e a da saída."""
    def _np(t):
        return t.detach().cpu().numpy() if hasattr(t, "detach") else np.asarray(t)

    sd = checkpoint["state_dict"]
    W, b, ativ = [], [], []
    for parte in ("encoder", "decoder"):
        idx = sorted({int(k.split(".")[1]) for k in sd if k.startswith(parte + ".") and k.endswith(".weight")})
        for j, i in enumerate(idx):
            W.append(_np(sd[f"{parte}.{i}.weight"]).T)        # PyTorch guarda [saída, entrada]
            b.append(_np(sd[f"{parte}.{i}.bias"]))
            ativ.append("linear" if j == len(idx) - 1 else "relu")
    return W, b, ativ


# ------------------------------------------------------------------ treino
def _gerar_dados(n_usuarios: int, pasta: Path) -> Path:
    csv = pasta / "transactions.csv"
    if csv.exists():
        _log(f"Usando dados sintéticos já gerados em {pasta}")
        return csv
    _log(f"Gerando dados sintéticos de {n_usuarios} usuários (gerador do projeto NeuralNetwork)...")
    subprocess.run([sys.executable, str(SRC_NN / "gerar_dados_sinteticos.py"), "--n-users", str(n_usuarios),
                    "--out", str(pasta)], check=True, cwd=PASTA_NN, stdout=sys.stderr)
    return csv


def _torch_disponivel() -> bool:
    import importlib.util
    return importlib.util.find_spec("torch") is not None


def treinar(n_usuarios: int = 200, motor: str = "auto", epocas: int = 60, refazer_dados: bool = False) -> dict:
    fa = _importar_nn()
    pasta = PASTA_DADOS_TREINO / f"n{n_usuarios}"
    if refazer_dados and pasta.exists():
        for f in pasta.glob("*"):
            f.unlink()
    csv = _gerar_dados(n_usuarios, pasta)
    if motor == "auto":
        motor = "torch" if _torch_disponivel() else "sklearn"
    inicio = time.time()

    tx = pd.read_csv(csv, parse_dates=["timestamp"])
    ds = fa.build_features(tx, use_time=False, contaminated=True)
    tr = np.where(ds.fit_mask & (ds.split == "train"))[0]
    va = np.where(ds.fit_mask & (ds.split == "val"))[0]

    if motor == "torch":
        pt = pasta / "autoencoder_sem_hora.pt"
        _log("Treinando o autoencoder em PyTorch (treinar_autoencoder.py, sem hora, contaminado)...")
        subprocess.run([sys.executable, str(SRC_NN / "treinar_autoencoder.py"), str(csv), "--contaminado",
                        "--sem-hora", "--sem-baselines", "--epochs", str(epocas), "--out", str(pt)],
                       check=True, cwd=PASTA_NN, stdout=sys.stderr)
        import torch
        ck = torch.load(pt, map_location="cpu", weights_only=False)   # arquivo gerado agora, por nós
        W, b, ativ = exportar_torch(ck)
        mean, std, names, threshold = ck["mean"], ck["std"], ck["names"], float(ck["threshold"])
        arquitetura = [len(names), *ck["hidden"], ck["bottleneck"], *reversed(ck["hidden"]), len(names)]
    elif motor == "sklearn":
        from sklearn.neural_network import MLPRegressor
        _log("Treinando o autoencoder MLP do scikit-learn (sem hora, contaminado)...")
        ocultas = (32, 16, 6, 16, 32)
        ae = MLPRegressor(hidden_layer_sizes=ocultas, alpha=1e-4, early_stopping=True, n_iter_no_change=5,
                          max_iter=epocas, random_state=0).fit(ds.X[tr], ds.X[tr])
        W, b = list(ae.coefs_), list(ae.intercepts_)
        ativ = ["relu"] * len(ocultas) + ["linear"]
        mean, std, names = ds.mean, ds.std, ds.names
        modelo_tmp = {"W": W, "b": b, "ativ": ativ}
        erro_va = ((ds.X[va] - reconstruir(modelo_tmp, ds.X[va])) ** 2).mean(1)
        threshold = float(np.quantile(erro_va, 1 - fa.ALERT_RATE))   # mesmo critério do treinar_autoencoder.py
        arquitetura = [len(names), *ocultas, len(names)]
    else:
        raise ValueError("motor deve ser auto, torch ou sklearn")

    # avaliação no teste do sintético, com as métricas do próprio projeto
    modelo = {"W": W, "b": b, "ativ": ativ}
    scores = ((ds.X - reconstruir(modelo, ds.X)) ** 2).mean(1)   # ds.X usa a mesma padronização do treino
    metricas = {k: round(float(v), 4) for k, v in fa.evaluate(scores, ds).items()}

    meta = {"motor": motor, "arquitetura": arquitetura, "usuarios_sinteticos": n_usuarios,
            "treinado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "transacoes_treino": int(len(tr)), "metricas_teste_sintetico": metricas,
            "segundos": round(time.time() - inicio, 1)}
    salvar(ARQUIVO_MODELO, W, b, ativ, mean, std, names, threshold, meta)
    _log(f"Modelo salvo em {ARQUIVO_MODELO}")
    return meta


# ------------------------------------------------------------------ uso: pontuar um titular
def para_tabela(transacoes: list[dict]) -> pd.DataFrame:
    """Transações do Armazenamento -> tabela no formato do gerador sintético."""
    linhas = []
    for t in transacoes:
        valor = float(t["valor"])
        linhas.append({
            "user_id": "titular", "timestamp": pd.Timestamp(t["data"][:10]),
            "description": t.get("descricao", ""), "merchant": estabelecimento(t.get("descricao", "")),
            "category": categorizar(t.get("descricao", ""), valor), "type": "debit" if valor < 0 else "credit",
            "amount": valor, "is_anomaly": 0, "anomaly_type": "",
        })
    return pd.DataFrame(linhas)


def pontuar(transacoes: list[dict], modelo: dict | None = None) -> pd.DataFrame | None:
    """Erro de reconstrução de cada saída que a rede conhece. Devolve None se não houver modelo."""
    modelo = modelo or carregar()
    if modelo is None:
        return None
    fa = _importar_nn()
    tab = para_tabela(transacoes)
    # a rede só entende as categorias do sintético; renda e créditos entram para calcular a renda
    tab = tab[tab.category.isin(CATEGORIAS_DA_REDE | {"Renda", "Estorno", "Investimentos"})]
    debitos = tab[(tab.type == "debit") & tab.category.isin(CATEGORIAS_DA_REDE)]
    if debitos.empty:
        return pd.DataFrame()

    # todo o histórico do titular é a "referência" dele (o padrão contra o qual cada transação é medida)
    fim = tab.timestamp.max() + pd.Timedelta(days=1)
    ds = fa.build_features(tab, use_time=False, contaminated=True, train_end=fim, val_end=fim)
    F = ds.raw.reindex(columns=modelo["names"])
    for j, nome in enumerate(modelo["names"]):                 # sem renda registrada etc.: valor típico
        F[nome] = F[nome].fillna(0.0 if nome.startswith("cat_") else modelo["mean"][j])
    X = ((F.values - modelo["mean"]) / modelo["std"]).clip(-10, 10).astype(np.float32)
    erro = ((X - reconstruir(modelo, X)) ** 2).mean(1)

    nomes = modelo["names"]
    motivos = []
    for x in X:              # como o explain() do projeto: as features mais fora do padrão (em desvios)
        top = [j for j in np.argsort(-np.abs(x)) if abs(x[j]) >= 1.5 and not nomes[j].startswith("cat_")]
        textos = [MOTIVOS.get((nomes[j], 1 if x[j] > 0 else -1)) for j in top]
        motivos.append(list(dict.fromkeys(t for t in textos if t))[:3])
    out = ds.raw[["timestamp", "description", "category", "amount"]].copy()
    out["score"] = erro
    out["atipica"] = erro >= modelo["threshold"]
    out["motivos"] = motivos
    return out.reset_index(drop=True)
