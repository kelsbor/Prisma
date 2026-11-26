"""Ambiente isolado para os testes: token, índice e bancos descartáveis, sem internet."""

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["PRISMA_DIR"] = tempfile.mkdtemp(prefix="prisma-teste-")
os.environ["PRISMA_EMBEDDINGS"] = "falso"       # embeddings determinísticos, sem chamar o Gemini
os.environ["PRISMA_ENV_FILE"] = os.path.join(os.environ["PRISMA_DIR"], "nao-existe.env")   # ignora o .env real
for _var in ("INDICADORES_URL", "GOOGLE_API_KEY", "PRISMA_APP_DB"):
    os.environ.pop(_var, None)

COLUNAS = ("transacao_id, data, ano, mes, descricao, estabelecimento, valor_centavos, valor, categoria_id, categoria, "
           "categoria_manual, grupo_categoria, tipo, valor_gasto, valor_entrada, conta, tipo_conta, banco, pendente, "
           "parcela, total_parcelas")
# Banco pequeno com a mesma view do app/agente-sql (sem dados reais)
LINHAS = [
    ("a1", "2026-10-05", 2026, 10, "SALARIO EMPRESA", None, 500000, 5000.0, "01", "Salário", 0, None, "entrada", 0, 5000.0, "Conta", "conta", "Banco X", 0, None, None),
    ("a2", "2026-10-07", 2026, 10, "SUPERMERCADO BOM", "Bom", -25050, -250.5, "08", "Supermercado", 0, None, "gasto", 250.5, 0, "Cartão", "cartao", "Banco X", 0, None, None),
    ("a3", "2026-10-09", 2026, 10, "PAGAMENTO FATURA", None, -100000, -1000.0, "05100000", "Pagamento de cartão", 0, None, "transferencia", 0, 0, "Conta", "conta", "Banco X", 0, None, None),
    ("a4", "2026-10-20", 2026, 10, "LOJA", None, -9900, -99.0, "09", "Compras", 0, None, "gasto", 99.0, 0, "Cartão", "cartao", "Banco X", 1, None, None),
    ("a5", "2027-03-01", 2027, 3, "PARCELA FUTURA", None, -5000, -50.0, "09", "Compras", 0, None, "gasto", 50.0, 0, "Cartão", "cartao", "Banco X", 1, 5, 6),
]


@pytest.fixture
def banco_app(tmp_path, monkeypatch):
    """Banco da Pluggy de teste, ligado ao Especialista e ao Agente de Consultas."""
    caminho = tmp_path / "prisma.db"
    con = sqlite3.connect(caminho)
    con.execute(f"CREATE TABLE base ({COLUNAS})")
    con.executemany(f"INSERT INTO base VALUES ({', '.join('?' * 21)})", LINHAS)
    con.execute("CREATE VIEW vw_registers AS SELECT * FROM base")
    con.execute("CREATE TABLE account_dim (id, itemId, type, name, balanceCents, creditLimitCents, availableLimitCents)")
    con.execute("INSERT INTO account_dim VALUES ('c1', 'i1', 'BANK', 'Conta ', 150025, NULL, NULL)")
    con.execute("INSERT INTO account_dim VALUES ('k1', 'i1', 'CREDIT', 'Cartão', 82000, 500000, 418000)")
    con.commit()
    con.close()
    from consultas import motor
    from especialista import dados
    monkeypatch.setattr(dados, "BANCO_APP", caminho)
    monkeypatch.setattr(motor, "BANCO_APP", caminho)
    return caminho
