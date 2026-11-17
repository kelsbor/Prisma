"""Monta os prompts de sistema a partir dos arquivos em prompts/ (textos fora do código)."""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path

import yaml

PROMPTS = Path(__file__).resolve().parent / "prompts"


def _ler(nome: str) -> str:
    return (PROMPTS / nome).read_text(encoding="utf-8").strip()


def trocas_de_data(hoje: date) -> dict[str, str]:
    """Marcadores de data usados nos exemplos do prompt e nos evals."""
    ano_ant, mes_ant = (hoje.year, hoje.month - 1) if hoje.month > 1 else (hoje.year - 1, 12)
    return {"{hoje}": hoje.isoformat(), "{ano}": str(hoje.year), "{mes}": str(hoje.month),
            "{ano_ant}": str(ano_ant), "{mes_ant}": str(mes_ant)}


def aplicar_datas(texto: str, hoje: date) -> str:
    for marcador, valor in trocas_de_data(hoje).items():
        texto = texto.replace(marcador, valor)
    return texto


def _exemplos(hoje: date) -> str:
    itens = yaml.safe_load(_ler("exemplos.yaml"))
    blocos = [f"(Nos exemplos abaixo, HOJE = {hoje.isoformat()}.)"]
    for e in itens:
        sql = aplicar_datas(e.get("sql") or "null", hoje)
        blocos.append(f"Pergunta: {e['pergunta']}\nclassificacao: {e['classificacao']}\nsql: {sql}")
    return "\n\n".join(blocos)


@lru_cache(maxsize=4)
def prompt_gerador(hoje: date) -> str:
    """Muda só uma vez por dia (exemplos com a data de hoje); dentro do dia o texto é idêntico."""
    return (
        _ler("gerador.md")
        .replace("{{ESQUEMA}}", _ler("esquema_vw_registers.md"))
        .replace("{{REGRAS}}", _ler("regras_negocio.md"))
        .replace("{{GLOSSARIO}}", _ler("glossario.md"))
        .replace("{{EXEMPLOS}}", _exemplos(hoje))
    )


@lru_cache(maxsize=1)
def prompt_redator() -> str:
    return _ler("redator.md")
