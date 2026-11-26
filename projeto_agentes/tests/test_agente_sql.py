"""agente-sql (da equipe, em ../agente-sql): configuração pelo .env único, download da Pluggy simulado e
compatibilidade do banco gerado com o Agente de Consultas e o Especialista. Sem internet."""

import importlib
import json
import sqlite3
import sys
import types
import urllib.parse
from datetime import date

import pytest

from comum.config import RAIZ

PASTA_SQL = RAIZ.parent / "agente-sql"
pytestmark = pytest.mark.skipif(not (PASTA_SQL / "agente.py").exists(), reason="pasta agente-sql não encontrada")

CATEGORIAS = [{"id": "11020000", "description": "Food delivery", "descriptionTranslated": "Delivery de alimentos"},
              {"id": "11000000", "description": "Food", "descriptionTranslated": "Alimentação"},
              {"id": "05100000", "description": "Credit card payment", "descriptionTranslated": "Pagamento de cartão"}]
CONTAS = [{"id": "c1", "type": "BANK", "name": "Banco X - Conta", "balance": 1500.25},
          {"id": "k1", "type": "CREDIT", "name": "Cartão Platinum", "balance": 820.0,
           "creditData": {"creditLimit": 5000, "availableCreditLimit": 4180, "balanceDueDate": "2026-12-10T00:00:00Z"}}]
TRANSACOES = {
    "c1": [{"id": "t1", "date": "2026-10-05T12:00:00Z", "description": "SALARIO", "amount": 4500, "type": "CREDIT"},
           {"id": "t2", "date": "2026-10-10T12:00:00Z", "description": "PAGAMENTO FATURA", "amount": -800,
            "type": "DEBIT", "categoryId": "05100000"}],
    "k1": [{"id": "t3", "date": "2026-10-12T15:00:00Z", "description": "IFOOD", "amount": 48.7, "type": "DEBIT",
            "categoryId": "11020000", "merchant": {"name": "iFood"}}],
}


def _pluggy_falsa(metodo, caminho, api_key=None, corpo=None):
    if caminho == "/auth":
        return {"apiKey": "k"}
    if caminho.startswith("/categories"):
        return {"results": CATEGORIAS, "totalPages": 1}
    if caminho.startswith("/items/"):
        return {"id": "item1", "connector": {"name": "MeuPluggy", "imageUrl": ""}, "status": "UPDATED"}
    if caminho.startswith("/accounts"):
        return {"results": CONTAS}
    if caminho.startswith("/v2/transactions"):
        conta = urllib.parse.parse_qs(caminho.split("?", 1)[1])["accountId"][0]
        return {"results": TRANSACOES[conta], "next": None}
    raise AssertionError(caminho)


@pytest.fixture
def agente_sql(tmp_path, monkeypatch):
    banco = tmp_path / "app" / "prisma.db"
    monkeypatch.setenv("PRISMA_ENV_FILE", str(tmp_path / "nao-existe.env"))
    monkeypatch.setenv("PRISMA_APP_DB", str(banco))
    monkeypatch.setenv("GOOGLE_API_KEY", "chave-falsa")
    monkeypatch.setenv("PLUGGY_CLIENT_ID", "id")
    monkeypatch.setenv("PLUGGY_CLIENT_SECRET", "segredo")
    monkeypatch.setenv("PLUGGY_ITEM_IDS", "item1")
    monkeypatch.syspath_prepend(str(PASTA_SQL))
    for nome in ("configuracao", "agente", "gerar_banco"):
        sys.modules.pop(nome, None)
    configuracao = importlib.import_module("configuracao")
    monkeypatch.setattr(configuracao, "PASTA", tmp_path)              # ignora um config.json local, se houver
    gerar = importlib.import_module("gerar_banco")
    agente = importlib.import_module("agente")
    monkeypatch.setattr(gerar, "chamar", _pluggy_falsa)
    yield types.SimpleNamespace(banco=banco, gerar=gerar, agente=agente, configuracao=configuracao)
    for nome in ("configuracao", "agente", "gerar_banco"):
        sys.modules.pop(nome, None)


def test_config_vem_do_env_unico(agente_sql):
    c = agente_sql.configuracao.carregar()
    assert c["gemini_api_key"] == "chave-falsa" and c["pluggy_item_ids"] == ["item1"]
    assert c["banco"] == str(agente_sql.banco)


def test_download_da_pluggy_e_compatibilidade(agente_sql, monkeypatch):
    agente_sql.gerar.main()
    con = sqlite3.connect(agente_sql.banco)
    linhas = {r[0]: r[1:] for r in con.execute("SELECT transacao_id, tipo, valor_gasto, valor_entrada FROM vw_registers")}
    assert linhas["t1"] == ("entrada", 0, 4500.0)
    assert linhas["t2"][0] == "transferencia" and linhas["t2"][1] == 0          # fatura não conta como gasto
    assert linhas["t3"][0] == "gasto" and linhas["t3"][1] == 48.7
    assert con.execute("SELECT balanceCents FROM account_dim WHERE type='CREDIT'").fetchone()[0] == 82000
    con.close()

    from consultas import motor                                                # o Agente de Consultas lê o banco gerado
    monkeypatch.setattr(motor, "BANCO_APP", agente_sql.banco)
    assert motor.status()["transacoes"] == 3
    r = motor.executar("SELECT ROUND(SUM(valor_gasto), 2), ROUND(SUM(valor_entrada), 2) FROM vw_registers")
    assert r["linhas"] == [[48.7, 4500.0]]

    from especialista import dados                                             # e o Especialista também
    monkeypatch.setattr(dados, "BANCO_APP", agente_sql.banco)
    resumo = dados.resumo("2026-10", hoje=date(2026, 11, 18))
    assert resumo["entradas"] == 4500.0 and resumo["gastos"] == 48.7
    assert {c["conta"] for c in resumo["contas"]} == {"Banco X - Conta", "Cartão Platinum"}

    resultado = json.loads(agente_sql.agente.executar_sql("SELECT ROUND(SUM(valor_gasto), 2) FROM vw_registers"))
    assert resultado["linhas"] == [[48.7]]
    assert agente_sql.agente.executar_sql("DELETE FROM transaction_fact").startswith("ERRO")   # somente leitura
