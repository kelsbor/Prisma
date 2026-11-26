"""Comparador do benchmark: fatos esperados precisam estar na resposta; fatos a mais não reprovam."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from avaliar import carregar_casos, comparar, faltando, fatos_da_resposta  # noqa: E402


class ComparadorTest(unittest.TestCase):
    def test_extrai_valores_datas_meses_e_inteiros(self):
        f = fatos_da_resposta("De 01/10/2026 a 31/10/2026 você gastou R$ 662,55 em 9 compras (12% do mês). "
                              "O maior mês foi setembro de 2026, e em out/2026 foram R$ 1.000.")
        self.assertEqual(f["valores_centavos"], {66255, 100000})
        self.assertEqual(f["datas"], {"2026-10-01", "2026-10-31"})
        self.assertIn((2026, 9), f["meses"])
        self.assertIn((2026, 10), f["meses"])
        self.assertEqual(f["inteiros"], {9, 2026})                 # sem os números de R$, datas e %

    def test_fatos_a_mais_nao_reprovam(self):
        esperados = [("brl", 66255)]
        self.assertEqual(faltando(esperados, "De 01/10/2026 a 31/10/2026: R$ 662,55, em 9 compras."), [])
        self.assertEqual(faltando(esperados, "R$ 662,56"), ["R$ 662,55"])

    def test_texto_casa_pela_palavra_principal(self):
        esperados = [("texto", "Banco Santander Pessoa Física"), ("texto", "Nu Pagamentos S.A."),
                     ("contagem", 28), ("mes", (2026, 9)), ("data", "2026-09-07")]
        resposta = "Suas contas estão no Santander e no Nu Pagamentos. Savegnago: 28 vezes; set/2026; 07/09/2026."
        self.assertEqual(faltando(esperados, resposta), [])
        self.assertEqual(faltando([("texto", "Savegnago")], "Shopee"), ["Savegnago"])

    def test_csv_antigo_compara_por_inclusao(self):
        self.assertTrue(comparar("R$ 46.245,50.", "Entre 06/11/2025 e 25/11/2026: R$ 46.245,50."))
        self.assertFalse(comparar("R$ 46.245,50.", "R$ 45.107,07."))

    def test_casos_do_benchmark_sao_validos(self):
        casos = carregar_casos(Path(__file__).resolve().parent / "benchmark" / "casos.jsonl")
        self.assertGreaterEqual(len(casos), 40)
        self.assertEqual(len({c["pergunta"] for c in casos}), len(casos))
        for c in casos:
            self.assertTrue(set(c["fatos"].values()) <= {"brl", "contagem", "data", "mes", "texto"})


if __name__ == "__main__":
    unittest.main()
