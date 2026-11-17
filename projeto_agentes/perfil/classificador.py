"""Classificador de endividamento: uma rede neural (MLP) que diz se a pessoa está ou não endividada.

DEFINIÇÃO (o rótulo): numa janela de 3 meses, a pessoa está "endividada" se a conta ficou no vermelho
(saldo negativo, ou seja, usando o limite do banco) em pelo menos 25% dos dias.

POR QUE ISSO PRECISA DE UMA REDE: o extrato que o Prisma lê não traz o saldo da conta, só as entradas e
saídas. Duas pessoas com o mesmo fluxo podem estar em situações opostas, porque uma tem reserva e a
outra não. A rede aprende, com os dados sintéticos (que têm o saldo verdadeiro), a reconhecer pelo
padrão do fluxo de caixa quem costuma estar no vermelho.

As features são calculadas só a partir das transações (data, descrição/categoria e valor), do mesmo
jeito para os dados sintéticos e para o extrato do titular.
"""

from datetime import datetime, timezone

import numpy as np
import pandas as pd

from comum.config import DATA_DIR, log
from perfil import rede
from perfil.categorias import categorizar

ARQUIVO_MODELO = DATA_DIR / "modelos" / "perfil_classificador.npz"
JANELA_MESES = 3
FRACAO_DIAS_NO_VERMELHO = 0.25

ESSENCIAIS = {"Moradia", "Contas", "Mercado", "Saúde", "Transporte", "Combustível", "Telecom", "Educação", "Impostos"}
DISCRICIONARIOS = {"Restaurantes e Delivery", "Lazer", "Compras", "Viagem", "Assinaturas"}
NOMES = ["comprometimento", "fluxo_liquido_sobre_renda", "fluxo_ultimo_mes_sobre_renda", "meses_fluxo_negativo",
         "variacao_renda", "fatia_essenciais", "fatia_discricionarios", "transferencias_sobre_renda",
         "aporte_liquido_sobre_renda", "tendencia_saidas", "maior_gasto_sobre_renda", "log_renda",
         "log_transacoes_mes"]
EXPLICACAO = {
    "comprometimento": "saídas em relação à renda",
    "fluxo_liquido_sobre_renda": "sobra ou falta de dinheiro no período",
    "fluxo_ultimo_mes_sobre_renda": "sobra ou falta no último mês",
    "meses_fluxo_negativo": "meses em que saiu mais do que entrou",
    "variacao_renda": "renda irregular",
    "fatia_essenciais": "peso dos gastos essenciais",
    "fatia_discricionarios": "peso de delivery, lazer e compras",
    "transferencias_sobre_renda": "transferências enviadas",
    "aporte_liquido_sobre_renda": "quanto guardou ou aplicou",
    "tendencia_saidas": "saídas do último mês acima da média",
    "maior_gasto_sobre_renda": "maior gasto do período",
    "log_renda": "nível de renda",
    "log_transacoes_mes": "quantidade de transações",
}


def _log(msg):
    log("agente-perfil", msg)


# ------------------------------------------------------------------ features (iguais no sintético e no real)
def features_da_janela(t: pd.DataFrame) -> dict:
    """t: transações de uma janela, com colunas mes, category, amount (negativo = saída)."""
    t = t[t.category != "Estorno"]
    meses = sorted(t.mes.unique())
    n = max(len(meses), 1)
    inv = t[t.category == "Investimentos"]
    fluxo = t[t.category != "Investimentos"]
    entra, sai = fluxo[fluxo.amount > 0], fluxo[fluxo.amount < 0]
    renda_mes = t[t.category == "Renda"].groupby("mes").amount.sum().reindex(meses, fill_value=0.0)
    base = renda_mes if renda_mes.sum() > 0 else entra.groupby("mes").amount.sum().reindex(meses, fill_value=0.0)
    renda = max(float(base.mean()), 1.0)
    saidas_mes = (-sai.groupby("mes").amount.sum()).reindex(meses, fill_value=0.0)
    liquido_mes = fluxo.groupby("mes").amount.sum().reindex(meses, fill_value=0.0)
    gastos_cat = -sai.groupby("category").amount.sum()
    categorizados = gastos_cat[gastos_cat.index.isin(ESSENCIAIS | DISCRICIONARIOS)].sum()
    return {
        "comprometimento": float(saidas_mes.mean() / renda),
        "fluxo_liquido_sobre_renda": float(liquido_mes.sum() / renda),
        "fluxo_ultimo_mes_sobre_renda": float(liquido_mes.iloc[-1] / renda),
        "meses_fluxo_negativo": float((liquido_mes < 0).mean()),
        "variacao_renda": float(base.std(ddof=0) / renda) if n > 1 else 0.0,
        "fatia_essenciais": float(gastos_cat[gastos_cat.index.isin(ESSENCIAIS)].sum() / categorizados) if categorizados else 0.0,
        "fatia_discricionarios": float(gastos_cat[gastos_cat.index.isin(DISCRICIONARIOS)].sum() / categorizados) if categorizados else 0.0,
        "transferencias_sobre_renda": float(gastos_cat.get("Transferências", 0.0) / n / renda),
        "aporte_liquido_sobre_renda": float(-inv.amount.sum() / n / renda),
        "tendencia_saidas": float(saidas_mes.iloc[-1] / max(saidas_mes.mean(), 1.0)),
        "maior_gasto_sobre_renda": float(-sai.amount.min() / renda) if len(sai) else 0.0,
        "log_renda": float(np.log1p(renda)),
        "log_transacoes_mes": float(np.log1p(len(t) / n)),
    }


def tabela_do_titular(transacoes: list[dict]) -> pd.DataFrame:
    linhas = [{"mes": t["data"][:7], "amount": float(t["valor"]),
               "category": categorizar(t.get("descricao", ""), float(t["valor"]))} for t in transacoes]
    return pd.DataFrame(linhas)


# ------------------------------------------------------------------ dados de treino (sintético)
def montar_dataset(tx: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por usuário e janela de 3 meses: features do fluxo + rótulo pelo saldo verdadeiro."""
    tx = tx.sort_values(["user_id", "timestamp"])
    tx = tx.assign(mes=tx.timestamp.dt.strftime("%Y-%m"), dia=tx.timestamp.dt.normalize())
    linhas = []
    for uid, u in tx.groupby("user_id", sort=False):
        saldo_dia = u.groupby("dia").balance.last()
        saldo_dia = saldo_dia.reindex(pd.date_range(saldo_dia.index.min(), saldo_dia.index.max()), method="ffill")
        meses = sorted(u.mes.unique())
        for i in range(len(meses) - JANELA_MESES + 1):
            janela = meses[i:i + JANELA_MESES]
            t = u[u.mes.isin(janela)]
            s = saldo_dia[(saldo_dia.index >= f"{janela[0]}-01") & (saldo_dia.index < pd.Period(janela[-1]).end_time)]
            if len(t) < 10 or s.empty:
                continue
            frac = float((s < 0).mean())
            linhas.append({"user_id": uid, "inicio": janela[0], **features_da_janela(t),
                           "fracao_dias_no_vermelho": frac, "endividado": int(frac >= FRACAO_DIAS_NO_VERMELHO)})
    return pd.DataFrame(linhas)


def _split_por_usuario(ds, seed=0):
    usuarios = np.array(sorted(ds.user_id.unique()))
    np.random.default_rng(seed).shuffle(usuarios)
    n = len(usuarios)
    grupos = {"treino": usuarios[:int(.7 * n)], "validacao": usuarios[int(.7 * n):int(.85 * n)],
              "teste": usuarios[int(.85 * n):]}
    return {k: ds.user_id.isin(v).values for k, v in grupos.items()}


def _metricas(y, p, limiar):
    from sklearn.metrics import (average_precision_score, f1_score, precision_score, recall_score,
                                 roc_auc_score)
    if len(set(y)) < 2:
        return {"aviso": "conjunto de teste com uma classe só (poucos usuários sintéticos)"}
    yhat = (p >= limiar).astype(int)
    return {"ROC-AUC": round(float(roc_auc_score(y, p)), 4), "PR-AUC": round(float(average_precision_score(y, p)), 4),
            "precisão": round(float(precision_score(y, yhat, zero_division=0)), 4),
            "recall": round(float(recall_score(y, yhat, zero_division=0)), 4),
            "F1": round(float(f1_score(y, yhat, zero_division=0)), 4)}


def _melhor_limiar(y, p):
    """Limiar que maximiza o F1 (equilíbrio entre não deixar passar e não alarmar à toa)."""
    from sklearn.metrics import f1_score
    candidatos = np.unique(np.round(p, 3)) if len(np.unique(p)) < 50 else np.linspace(0.02, 0.98, 97)
    return float(max(candidatos, key=lambda c: f1_score(y, p >= c, zero_division=0)))


def treinar(n_usuarios: int = 1000, epocas: int = 300) -> dict:
    from sklearn.linear_model import LogisticRegression
    from sklearn.neural_network import MLPClassifier

    csv = rede._gerar_dados(n_usuarios, rede.PASTA_DADOS_TREINO / f"n{n_usuarios}")
    _log("Montando janelas de 3 meses com o saldo verdadeiro (rótulo)...")
    ds = montar_dataset(pd.read_csv(csv, parse_dates=["timestamp"]))
    parte = _split_por_usuario(ds)
    X, y = ds[NOMES].values.astype(float), ds.endividado.values
    media, desvio = X[parte["treino"]].mean(0), X[parte["treino"]].std(0) + 1e-9
    Z = ((X - media) / desvio).clip(-10, 10)

    _log("Treinando a rede (MLP 13 → 32 → 16 → 1)...")
    mlp = MLPClassifier(hidden_layer_sizes=(32, 16), alpha=1e-3, early_stopping=True, n_iter_no_change=15,
                        max_iter=epocas, random_state=0).fit(Z[parte["treino"]], y[parte["treino"]])
    va = parte["validacao"]
    limiar = _melhor_limiar(y[va], mlp.predict_proba(Z[va])[:, 1])

    te = parte["teste"]
    p_te = mlp.predict_proba(Z[te])[:, 1]
    # comparações, com o limiar escolhido do mesmo jeito (na validação)
    log_reg = LogisticRegression(max_iter=2000).fit(Z[parte["treino"]], y[parte["treino"]])
    limiar_lr = _melhor_limiar(y[va], log_reg.predict_proba(Z[va])[:, 1])
    regra = X[:, NOMES.index("meses_fluxo_negativo")]                 # só "meses com fluxo negativo"
    limiar_regra = _melhor_limiar(y[va], regra[va])
    meta = {
        "tipo": "classificador", "arquitetura": [len(NOMES), 32, 16, 1], "usuarios_sinteticos": n_usuarios,
        "definicao": f"no vermelho em pelo menos {FRACAO_DIAS_NO_VERMELHO:.0%} dos dias de uma janela de "
                     f"{JANELA_MESES} meses",
        "janelas": int(len(ds)), "endividados_no_sintetico": round(float(y.mean()), 3),
        "treinado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "metricas_teste": {"rede neural (MLP)": _metricas(y[te], p_te, limiar),
                           "regressão logística": _metricas(y[te], log_reg.predict_proba(Z[te])[:, 1], limiar_lr),
                           "regra: meses com fluxo negativo": _metricas(y[te], regra[te], limiar_regra)},
    }
    rede.salvar(ARQUIVO_MODELO, mlp.coefs_, mlp.intercepts_, ["relu", "relu", "sigmoid"], media, desvio,
                NOMES, limiar, meta)
    _log(f"Classificador salvo em {ARQUIVO_MODELO}")
    return meta


# ------------------------------------------------------------------ uso
def carregar():
    return rede.carregar(ARQUIVO_MODELO)


def classificar(transacoes: list[dict], modelo: dict | None = None) -> dict:
    modelo = modelo or carregar()
    if modelo is None:
        return {"disponivel": False, "motivo": "classificador não treinado (rode: ./prisma.sh perfil treinar)"}
    t = tabela_do_titular(transacoes)
    if t.empty:
        return {"disponivel": False, "motivo": "sem transações"}
    meses = sorted(t.mes.unique())[-JANELA_MESES:]
    f = features_da_janela(t[t.mes.isin(meses)])
    x = np.array([f[n] for n in modelo["names"]], dtype=float)
    z = ((x - modelo["mean"]) / modelo["std"]).clip(-10, 10)
    p = float(rede.reconstruir(modelo, z[None, :])[0, 0])
    # o que mais pesou: as features mais distantes do típico (em desvios), com o sentido
    ordem = np.argsort(-np.abs(z))[:3]
    sinais = [f"{EXPLICACAO[modelo['names'][j]]} ({'acima' if z[j] > 0 else 'abaixo'} do típico)" for j in ordem]
    avisos = []
    if len(meses) < JANELA_MESES:
        avisos.append(f"Só {len(meses)} mês(es) de dados; a rede foi treinada com janelas de {JANELA_MESES}.")
    return {"disponivel": True, "classe": "endividado" if p >= modelo["threshold"] else "não endividado",
            "probabilidade": round(p, 3), "limiar": round(modelo["threshold"], 3), "meses": meses,
            "definicao": modelo["meta"]["definicao"], "sinais": sinais,
            "features": {k: round(v, 3) for k, v in f.items()}, "avisos": avisos}

