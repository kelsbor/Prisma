"""Agente de Indicadores sem internet: a API do Banco Central é simulada com respostas no formato real."""

import json

import pytest

from indicadores import bcb, consultas
from indicadores.series import SERIES

# formato real da API SGS: lista de {"data": "dd/mm/aaaa", "valor": "texto"}
FALSO = {
    432: [{"data": "13/11/2026", "valor": "15.00"}],
    433: [{"data": "01/10/2026", "valor": "0.36"}],
    13522: [{"data": "01/10/2026", "valor": "4.68"}],
    22022: [{"data": "01/05/2026", "valor": "439.90"}],
    25477: [{"data": "01/05/2026", "valor": "15.08"}],
    20741: [{"data": "01/05/2026", "valor": "138.30"}],
    25463: [{"data": "01/05/2026", "valor": "7.50"}],
    20748: [{"data": "01/05/2026", "valor": "60.10"}],
    20740: [{"data": "01/05/2026", "valor": "58.20"}],
}


@pytest.fixture
def api(monkeypatch, tmp_path):
    chamadas = []

    def baixar(codigo, n):
        chamadas.append(codigo)
        return FALSO[codigo] * n
    monkeypatch.setattr(bcb, "_baixar", baixar)
    monkeypatch.setattr(bcb, "CACHE", tmp_path / "cache.json")
    return chamadas


def test_codigos_das_series():
    assert {s["codigo"] for s in SERIES.values()} == set(FALSO)


def test_indicador_e_cache(api):
    r = consultas.indicador("rotativo")
    assert r["valor"] == 439.9 and r["referencia"] == "mai/2026" and "22022" in r["fonte"]
    assert r["origem"] == "api"
    assert consultas.indicador("rotativo")["origem"] == "cache"          # segunda vez não chama a API
    assert api.count(22022) == 1


def test_api_fora_do_ar_usa_cache_antigo(api, monkeypatch):
    consultas.indicador("selic")
    cache = json.loads(bcb.CACHE.read_text())
    for item in cache.values():
        item["ts"] = 0                                                   # cache vencido
    bcb.CACHE.write_text(json.dumps(cache))

    def fora(codigo, n):
        raise OSError("sem rede")
    monkeypatch.setattr(bcb, "_baixar", fora)
    r = consultas.indicador("selic")
    assert r["origem"] == "cache antigo" and "aviso" in r and r["valor"] == 15.0
    with pytest.raises(Exception, match="sem cache"):
        consultas.indicador("ipca_mes")                                  # nunca baixado: erro claro


def test_juros_do_credito(api):
    r = consultas.juros_do_credito()
    rot = next(m for m in r["modalidades"] if m["modalidade"].startswith("cartão"))
    assert rot["ao_ano"] == 439.9 and rot["ao_mes"] == 15.08 and rot["vezes_a_selic"] == 29.3
    assert any("Selic: 15,00%" in linha for linha in r["resumo"])


def test_simulacao_com_teto_do_rotativo(api):
    r = consultas.simular(1000, "rotativo", 3)                          # 15,08% ao mês por 3 meses
    assert r["juros"] == round(1000 * (1.1508 ** 3 - 1), 2) and not r["teto_aplicado"]
    longo = consultas.simular(1000, "rotativo", 12)                     # passaria de 100%: para no teto
    assert longo["teto_aplicado"] and longo["juros"] == 1000.0 and longo["total"] == 2000.0
    pessoal = consultas.simular(1000, "credito_pessoal", 12)            # anual convertido em mensal
    assert pessoal["juros"] == pytest.approx(601.0, abs=0.5)
