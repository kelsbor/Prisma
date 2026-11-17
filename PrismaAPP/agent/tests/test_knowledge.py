"""Prompt do gerador: exemplos com a data do dia e sem sobreposição com os evals."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml

from prisma_agent.knowledge import PROMPTS, prompt_gerador, trocas_de_data


def test_exemplos_usam_a_data_de_hoje():
    texto = prompt_gerador(date(2027, 1, 10))
    assert "HOJE = 2027-01-10" in texto
    assert "ano = 2027 AND mes = 1" in texto        # "este mês"
    assert "ano = 2026 AND mes = 12" in texto       # "mês passado" atravessa o ano
    assert not any(m in texto for m in trocas_de_data(date(2027, 1, 10)))  # nenhum marcador sobrando
    assert "{{" not in texto


def test_evals_nao_repetem_os_exemplos():
    exemplos = {e["pergunta"].strip().lower() for e in yaml.safe_load((PROMPTS / "exemplos.yaml").read_text("utf-8"))}
    evals = Path(__file__).resolve().parents[1] / "evals" / "perguntas.yaml"
    perguntas = {c["pergunta"].strip().lower() for c in yaml.safe_load(evals.read_text("utf-8"))}
    assert not exemplos & perguntas
