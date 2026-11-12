"""Agente de Risco sem internet: categorias, rede neural (forward, exportação do PyTorch, treino rápido)
e o perfil de risco com e sem a rede."""

import numpy as np

from coletor import pipeline
from risco import perfil, rede
from risco.categorias import categorizar, estabelecimento


def test_categorias_do_extrato():
    assert categorizar("PAG*IFOOD", -48.7) == "Restaurantes e Delivery"
    assert categorizar("CRED SALARIO EMPRESA LTDA", 3450) == "Renda"
    assert categorizar("PIX RECEBIDO - M OLIVEIRA", 150) == "Transferências"     # não é renda
    assert categorizar("JUROS CHEQUE ESPECIAL", -30) == "Juros e encargos"
    assert categorizar("RESGATE CDB LIQUIDEZ DIARIA", 200) == "Investimentos"
    assert categorizar("MERCADO LIVRE", -90) == "Compras"
    assert estabelecimento("SPOTIFY P1A2B3C4") == "SPOTIFY"
    assert estabelecimento("COMPRA CARTAO DEB POSTO ESTRELA") == "POSTO ESTRELA"


def test_forward_em_numpy_igual_ao_sklearn():
    from sklearn.neural_network import MLPRegressor
    X = np.random.default_rng(0).normal(size=(200, 7)).astype(np.float32)
    ae = MLPRegressor(hidden_layer_sizes=(5, 2, 5), max_iter=50, random_state=0).fit(X, X)
    modelo = {"W": ae.coefs_, "b": ae.intercepts_, "ativ": ["relu"] * 3 + ["linear"]}
    assert np.allclose(rede.reconstruir(modelo, X), ae.predict(X), atol=1e-5)


def test_exportacao_do_checkpoint_pytorch():
    # mesmo layout do AutoEncoder de treinar_autoencoder.py: Linear+ReLU, sem ReLU no gargalo e na saída
    rng = np.random.default_rng(1)
    dims = [5, 4, 3, 2, 3, 4, 5]
    sd = {}
    for k in range(6):
        parte, idx = ("encoder", 2 * k) if k < 3 else ("decoder", 2 * (k - 3))
        sd[f"{parte}.{idx}.weight"] = rng.normal(size=(dims[k + 1], dims[k]))   # [saída, entrada]
        sd[f"{parte}.{idx}.bias"] = rng.normal(size=dims[k + 1])
    W, b, ativ = rede.exportar_torch({"state_dict": sd})
    assert ativ == ["relu", "relu", "linear", "relu", "relu", "linear"]
    x = rng.normal(size=(3, 5))
    h = x
    for k in range(6):                       # forward "à mão", como o nn.Sequential faria
        parte, idx = ("encoder", 2 * k) if k < 3 else ("decoder", 2 * (k - 3))
        h = h @ sd[f"{parte}.{idx}.weight"].T + sd[f"{parte}.{idx}.bias"]
        if k not in (2, 5):
            h = np.maximum(h, 0)
    assert np.allclose(rede.reconstruir({"W": W, "b": b, "ativ": ativ}, x), h)


def _extrato_ficticio():
    _, consolidado = pipeline.analisar()
    return consolidado


def test_perfil_sem_rede_reescala_para_100():
    p = perfil.calcular(_extrato_ficticio(), usar_rede=False)
    assert 0 <= p["score"] <= 100 and p["faixa"] in {"baixo", "moderado", "alto"}
    nomes = [c["componente"] for c in p["componentes"]]
    assert "comportamento atípico (rede neural)" not in nomes
    assert p["meses"] == ["2026-08", "2026-09", "2026-10"]
    juros = next(c for c in p["componentes"] if c["componente"].startswith("crédito caro"))
    assert juros["pontos"] > 0                                    # há JUROS CHEQUE ESPECIAL no extrato


def test_treino_rapido_e_perfil_com_rede():
    meta = rede.treinar(n_usuarios=20, motor="sklearn", epocas=5)
    assert meta["arquitetura"][0] == meta["arquitetura"][-1] == 27     # extratos sem horário: 27 features
    assert 0.5 <= meta["metricas_teste_sintetico"]["ROC-AUC"] <= 1.0
    p = perfil.calcular(_extrato_ficticio())
    r = p["rede_neural"]
    assert r["disponivel"] and r["transacoes_analisadas"] > 0
    assert any(c["componente"] == "comportamento atípico (rede neural)" for c in p["componentes"])
    for a in r["alertas"]:
        assert a["score"] >= r["limiar"]
