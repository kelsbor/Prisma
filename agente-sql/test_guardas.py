"""Testes da proteção do SQL (guardas.py) e do fluxo do agente com ela. Sem internet."""

import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import agente  # noqa: E402
import guardas  # noqa: E402
from metricas import MetricasExecucao  # noqa: E402

ESQUEMA = """
CREATE TABLE item_dim (id TEXT PRIMARY KEY, bankName TEXT);
CREATE TABLE account_dim (id TEXT PRIMARY KEY, itemId TEXT, name TEXT, type TEXT, balanceCents INTEGER);
CREATE TABLE category_dim (id TEXT PRIMARY KEY, nome TEXT);
CREATE TABLE category_override (transacao_id TEXT, categoria_id TEXT);
CREATE TABLE transaction_fact (id TEXT PRIMARY KEY, accountId TEXT, data TEXT, descricao TEXT,
                               valorCents INTEGER, categoriaId TEXT);
CREATE TABLE sync_state (chave TEXT, valor TEXT);
CREATE VIEW vw_registers AS
  SELECT t.id AS transacao_id, t.data, t.descricao, t.valorCents / 100.0 AS valor,
         CASE WHEN t.valorCents < 0 THEN -t.valorCents / 100.0 ELSE 0 END AS valor_gasto,
         COALESCE(c.nome, 'Sem categoria') AS categoria, a.name AS conta, i.bankName AS banco
  FROM transaction_fact t
  JOIN account_dim a ON a.id = t.accountId
  JOIN item_dim i ON i.id = a.itemId
  LEFT JOIN category_override o ON o.transacao_id = t.id
  LEFT JOIN category_dim c ON c.id = COALESCE(o.categoria_id, t.categoriaId);
INSERT INTO item_dim VALUES ('i1', 'Banco Teste');
INSERT INTO account_dim VALUES ('a1', 'i1', 'corrente', 'BANK', 150000);
INSERT INTO category_dim VALUES ('c1', 'Mercado');
INSERT INTO transaction_fact VALUES ('t1', 'a1', '2026-10-05', 'Supermercado', -12345, 'c1');
INSERT INTO transaction_fact VALUES ('t2', 'a1', '2026-10-06', 'Padaria', -1000, 'c1');
INSERT INTO sync_state VALUES ('token', 'segredo');
"""


class BancoDeTeste(unittest.TestCase):
    def setUp(self):
        self._pasta = tempfile.TemporaryDirectory()
        self.pasta = Path(self._pasta.name)
        with closing(sqlite3.connect(self.pasta / "financas.db")) as con:
            con.executescript(ESQUEMA)
        self._patches = [
            patch.object(agente, "PASTA", self.pasta),
            patch.dict(agente.CONFIG, {"banco": "financas.db"}),
            patch.object(agente, "MetricasExecucao",
                         side_effect=lambda: MetricasExecucao(self.pasta / "metricas.db")),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in reversed(self._patches):
            p.stop()
        self._pasta.cleanup()

    def resultados_das_metricas(self):
        with closing(sqlite3.connect(self.pasta / "metricas.db")) as con:
            return [r[0] for r in con.execute("SELECT resultado FROM operacoes")]


class ValidacaoSqlTest(BancoDeTeste):
    def assertRecusado(self, sql, trecho=""):
        with self.assertRaises(guardas.SqlRejeitado) as ctx:
            agente.executar_sql(sql)
        self.assertIn(trecho, str(ctx.exception))

    def test_fontes_permitidas_funcionam(self):
        r = agente.executar_sql("SELECT ROUND(SUM(valor_gasto), 2) FROM vw_registers")
        self.assertEqual(r["linhas"], [[133.45]])
        r = agente.executar_sql("SELECT trim(a.name), i.bankName, a.balanceCents / 100.0 "
                                "FROM account_dim a JOIN item_dim i ON i.id = a.itemId")
        self.assertEqual(r["linhas"], [["corrente", "Banco Teste", 1500.0]])

    def test_cte_e_subconsulta_sobre_a_view_funcionam(self):
        r = agente.executar_sql("WITH x AS (SELECT categoria, valor_gasto FROM vw_registers) "
                                "SELECT categoria, SUM(valor_gasto) FROM x GROUP BY categoria")
        self.assertEqual(r["linhas"], [["Mercado", 133.45]])
        r = agente.executar_sql("SELECT COUNT(*) FROM (SELECT * FROM vw_registers WHERE valor < 0)")
        self.assertEqual(r["linhas"], [[2]])

    def test_tabelas_fora_da_lista_sao_recusadas(self):
        self.assertRecusado("SELECT * FROM sync_state", "sync_state")
        self.assertRecusado("SELECT * FROM transaction_fact", "transaction_fact")
        self.assertRecusado("SELECT name FROM sqlite_master", "sqlite_master")
        self.assertRecusado("SELECT * FROM vw_registers WHERE conta IN (SELECT valor FROM sync_state)")

    def test_cte_com_nome_de_fonte_e_recusada(self):
        self.assertRecusado("WITH vw_registers AS (SELECT * FROM transaction_fact) SELECT * FROM vw_registers",
                            "CTE")

    def test_escrita_pragma_attach_e_varias_instrucoes_sao_recusadas(self):
        self.assertRecusado("DELETE FROM transaction_fact", "SELECT")
        self.assertRecusado("PRAGMA table_info(account_dim)", "SELECT")
        self.assertRecusado("ATTACH DATABASE 'x.db' AS x", "SELECT")
        self.assertRecusado("SELECT 1; DELETE FROM transaction_fact")
        self.assertRecusado("SELECT * FROM vw_registers; SELECT * FROM sync_state")

    def test_funcoes_perigosas_sao_recusadas(self):
        self.assertRecusado("SELECT load_extension('x')", "load_extension")
        self.assertRecusado("SELECT sqlite_version()", "sqlite_version")

    def test_nada_foi_gravado(self):
        for sql in ("DELETE FROM transaction_fact", "SELECT 1; DELETE FROM transaction_fact"):
            with self.assertRaises(guardas.SqlRejeitado):
                agente.executar_sql(sql)
        with closing(sqlite3.connect(self.pasta / "financas.db")) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM transaction_fact").fetchone()[0], 2)


class FluxoComBarreirasTest(BancoDeTeste):
    def rodar(self, pergunta, respostas_do_modelo):
        respostas = iter(respostas_do_modelo)
        self.chamadas = []

        def modelo(sistema, mensagem, metricas=None):
            self.chamadas.append(mensagem)
            return next(respostas)

        with patch.object(agente, "perguntar_ao_llm", side_effect=modelo):
            return agente.responder_detalhado(pergunta, date(2026, 11, 25), log_detalhes=False)

    def test_sql_recusado_ganha_uma_correcao(self):
        r = self.rodar("quanto gastei?", ["SELECT * FROM transaction_fact",
                                          "SELECT ROUND(SUM(valor_gasto), 2) AS total FROM vw_registers",
                                          "Você gastou R$ 133,45."])
        self.assertEqual(r["status"], "sucesso")
        self.assertEqual(r["resposta"], "Você gastou R$ 133,45.")
        self.assertIn("transaction_fact não pode ser consultada", self.chamadas[1])

    def test_duas_falhas_devolvem_erro_sem_redigir(self):
        r = self.rodar("quanto gastei?", ["SELECT * FROM sync_state", "DELETE FROM account_dim"])
        self.assertEqual(r["status"], "erro_sql")
        self.assertEqual(r["resposta"], agente.MSG_ERRO_SQL)
        self.assertEqual(len(self.chamadas), 2)
        self.assertEqual(self.resultados_das_metricas(), ["erro_sql"])

if __name__ == "__main__":
    unittest.main()
