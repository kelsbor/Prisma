import io
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parent))
_read_text = Path.read_text


def _read_config_or_file(path, *args, **kwargs):
    if path.name == "config.json":
        return json.dumps({
            "gemini_model": "test-model",
            "gemini_api_key": "test-key",
            "banco": "test.db",
        })
    return _read_text(path, *args, **kwargs)


with patch.object(Path, "read_text", _read_config_or_file):
    import agente
from avaliar import comparar, fatos, id_caso
from metricas import MetricasExecucao


class RespostaHttp:
    def __init__(self, dados):
        self.dados = json.dumps(dados).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def read(self):
        return self.dados


class AgenteMetricasTest(unittest.TestCase):
    def test_fluxo_completo_grava_latencias_e_estado_sql(self):
        with tempfile.TemporaryDirectory() as pasta:
            pasta_temporaria = Path(pasta)
            banco_dados = pasta_temporaria / "financas.db"
            with sqlite3.connect(banco_dados) as con:
                con.execute("CREATE TABLE valores (valor INTEGER)")
                con.execute("INSERT INTO valores VALUES (42)")
            arquivo_metricas = pasta_temporaria / "metricas.db"
            respostas = iter(("SELECT valor FROM valores", "O valor é 42."))

            def chamar_modelo(_sistema, _mensagem, metricas=None):
                if metricas:
                    metricas.registrar_tentativa_llm()
                    metricas.registrar_chamada_llm(None)
                return next(respostas)

            with (
                patch.object(agente, "PASTA", pasta_temporaria),
                patch.dict(agente.CONFIG, {"banco": "financas.db"}),
                patch.object(agente, "MetricasExecucao",
                             side_effect=lambda: MetricasExecucao(arquivo_metricas)),
                patch.object(agente, "perguntar_ao_llm", side_effect=chamar_modelo),
            ):
                resultado = agente.responder_detalhado("pergunta privada", log_detalhes=False)

            self.assertEqual(resultado["dados"]["linhas"], [[42]])
            with sqlite3.connect(arquivo_metricas) as con:
                linha = con.execute(
                    "SELECT resultado, etapas_ms, chamadas_llm, linhas_sql FROM operacoes"
                ).fetchone()
            self.assertEqual(linha[0], "sucesso")
            self.assertIn("geracao_sql_ms", json.loads(linha[1]))
            self.assertIn("execucao_sql_ms", json.loads(linha[1]))
            self.assertIn("geracao_resposta_ms", json.loads(linha[1]))
            self.assertEqual(linha[2:], (2, 1))

    def test_erro_sql_nao_e_contabilizado_como_sucesso(self):
        with tempfile.TemporaryDirectory() as pasta:
            pasta_temporaria = Path(pasta)
            with sqlite3.connect(pasta_temporaria / "financas.db"):
                pass
            arquivo_metricas = pasta_temporaria / "metricas.db"
            respostas = iter(("SELECT inexistente FROM ausente", "Não consegui consultar."))

            def chamar_modelo(_sistema, _mensagem, metricas=None):
                if metricas:
                    metricas.registrar_tentativa_llm()
                    metricas.registrar_chamada_llm(None)
                return next(respostas)

            with (
                patch.object(agente, "PASTA", pasta_temporaria),
                patch.dict(agente.CONFIG, {"banco": "financas.db"}),
                patch.object(agente, "MetricasExecucao",
                             side_effect=lambda: MetricasExecucao(arquivo_metricas)),
                patch.object(agente, "perguntar_ao_llm", side_effect=chamar_modelo),
            ):
                resultado = agente.responder_detalhado("pergunta privada", log_detalhes=False)

            with sqlite3.connect(arquivo_metricas) as con:
                status = con.execute("SELECT resultado FROM operacoes").fetchone()[0]
            self.assertEqual(status, "erro_sql")
            self.assertIn("erro", resultado["dados"])

    def test_chamada_gemini_registra_tokens_sem_conteudo(self):
        payload = {
            "candidates": [{"content": {"parts": [{"text": "SELECT 1"}]}}],
            "usageMetadata": {
                "promptTokenCount": 13,
                "candidatesTokenCount": 4,
                "totalTokenCount": 17,
            },
        }
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "metrics.db"
            metricas = MetricasExecucao(caminho)
            with patch("agente.urllib.request.urlopen", return_value=RespostaHttp(payload)):
                texto = agente.perguntar_ao_llm("system", "question", metricas)
            metricas.finalizar("sucesso")

            with sqlite3.connect(caminho) as con:
                linha = con.execute(
                    "SELECT chamadas_llm, tentativas_llm, tokens_entrada, tokens_saida, "
                    "tokens_total, tokens_completos FROM operacoes"
                ).fetchone()
                colunas = [c[1] for c in con.execute("PRAGMA table_info(operacoes)")]
            self.assertEqual(texto, "SELECT 1")
            self.assertEqual(linha, (1, 1, 13, 4, 17, 1))
            self.assertNotIn("question", colunas)
            self.assertNotIn("system", colunas)

    def test_retry_http_e_contabilizado_separadamente_de_tokens(self):
        payload = {
            "candidates": [{"content": {"parts": [{"text": "SELECT 1"}]}}],
            "usageMetadata": {
                "promptTokenCount": 13,
                "candidatesTokenCount": 4,
                "totalTokenCount": 17,
            },
        }
        ocupado = HTTPError("https://example.invalid", 429, "busy", {}, io.BytesIO(b""))
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "metrics.db"
            metricas = MetricasExecucao(caminho)
            with (
                patch("agente.urllib.request.urlopen", side_effect=[ocupado, RespostaHttp(payload)]),
                patch("agente.time.sleep"),
            ):
                agente.perguntar_ao_llm("system", "question", metricas)
            metricas.finalizar("sucesso")
            with sqlite3.connect(caminho) as con:
                linha = con.execute(
                    "SELECT chamadas_llm, tentativas_llm, tokens_total, tokens_completos "
                    "FROM operacoes"
                ).fetchone()
            self.assertEqual(linha, (2, 2, 17, 0))

    def test_extrai_fatos_financeiros_normalizados(self):
        esperado = 'R$ 10.288,35 em 28 transações em 07/09/2026.'
        resposta = 'Foram R$ 10.288,35, em 28 transações (07/09/2026).'
        self.assertEqual(fatos(esperado), fatos(resposta))
        self.assertTrue(comparar(esperado, resposta))
        self.assertFalse(comparar(esperado, "Foram R$ 10.288,34 em 28 transações."))
        self.assertIsNone(comparar("Sem números ou datas.", "Resposta textual."))
        self.assertEqual(id_caso("  Quanto gastei? "), id_caso("quanto   gastei?"))
        distribuicao = '588 do tipo "gasto" e 107 do tipo "entrada"'
        self.assertTrue(comparar(distribuicao, "588 gastos e 107 entradas"))


if __name__ == "__main__":
    unittest.main()
