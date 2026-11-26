import json
import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from metricas import MetricasExecucao


class MetricasTest(unittest.TestCase):
    def test_persiste_tempos_tokens_e_apenas_metadados(self):
        with tempfile.TemporaryDirectory() as pasta:
            banco = Path(pasta) / "metricas.db"
            metricas = MetricasExecucao(banco)
            with metricas.etapa("geracao_sql_ms"):
                metricas.registrar_tentativa_llm()
                metricas.registrar_chamada_llm({
                    "promptTokenCount": 11,
                    "candidatesTokenCount": 7,
                    "totalTokenCount": 18,
                })
            metricas.registrar_resultado_sql(2, False)
            metricas.finalizar("sucesso")

            with closing(sqlite3.connect(banco)) as con, con:
                linha = con.execute(
                    "SELECT resultado, etapas_ms, chamadas_llm, tentativas_llm, "
                    "tokens_entrada, tokens_saida, tokens_total, tokens_completos, "
                    "linhas_sql, cortado FROM operacoes"
                ).fetchone()
                colunas = [c[1] for c in con.execute("PRAGMA table_info(operacoes)")]

            self.assertEqual(linha[0], "sucesso")
            self.assertGreaterEqual(json.loads(linha[1])["geracao_sql_ms"], 0)
            self.assertEqual(linha[2:10], (1, 1, 11, 7, 18, 1, 2, 0))
            self.assertNotIn("pergunta", colunas)
            self.assertNotIn("sql", colunas)
            self.assertNotIn("resposta", colunas)

    def test_tokens_ausentes_nao_sao_estimados_e_retries_contam(self):
        with tempfile.TemporaryDirectory() as pasta:
            banco = Path(pasta) / "metricas.db"
            metricas = MetricasExecucao(banco)
            metricas.registrar_tentativa_llm()
            metricas.registrar_chamada_llm(None)
            metricas.registrar_tentativa_llm()
            metricas.registrar_chamada_llm(None)
            metricas.finalizar("sucesso")

            with closing(sqlite3.connect(banco)) as con, con:
                linha = con.execute(
                    "SELECT chamadas_llm, tentativas_llm, tokens_total, tokens_completos "
                    "FROM operacoes"
                ).fetchone()
            self.assertEqual(linha, (2, 2, None, 0))

    def test_erro_ao_persistir_e_reportado_sem_escapar(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho_diretorio = Path(pasta)
            metricas = MetricasExecucao(caminho_diretorio)
            with patch("metricas._log.warning") as aviso:
                metricas.finalizar("falha", "RuntimeError")
            aviso.assert_called_once()


if __name__ == "__main__":
    unittest.main()
