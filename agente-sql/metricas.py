"""Métricas locais do agente, sem persistir conteúdo de perguntas ou do banco."""

from __future__ import annotations

import json
import logging
import sqlite3
import sys
import time
import uuid
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

PASTA = Path(__file__).parent
BANCO_METRICAS = PASTA / "metricas.db"
_log = logging.getLogger(__name__)


class MetricasExecucao:
    """Agrega métricas de uma operação e persiste uma linha ao final."""

    def __init__(self, caminho: Path = BANCO_METRICAS, componente: str = "agente"):
        self.id = uuid.uuid4().hex
        self._caminho = caminho
        self._componente = componente
        self._iniciado_em = datetime.now(timezone.utc).isoformat()
        self._inicio = time.perf_counter()
        self._etapas: dict[str, float] = {}
        self._chamadas_llm = 0
        self._tentativas = 0
        self._chamadas_com_tokens = 0
        self._tokens_entrada = 0
        self._tokens_saida = 0
        self._tokens_total = 0
        self._linhas = 0
        self._cortado = False
        self._finalizada = False

    @contextmanager
    def etapa(self, nome: str) -> Iterator[None]:
        inicio = time.perf_counter()
        try:
            yield
        finally:
            self._etapas[nome] = self._etapas.get(nome, 0.0) + (time.perf_counter() - inicio) * 1000

    def registrar_tentativa_llm(self) -> None:
        self._tentativas += 1
        self._chamadas_llm += 1

    def registrar_chamada_llm(self, uso: dict | None) -> None:
        if not uso:
            return
        entrada = uso.get("promptTokenCount")
        saida = uso.get("candidatesTokenCount", uso.get("responseTokenCount"))
        total = uso.get("totalTokenCount")
        if not all(isinstance(v, int) and v >= 0 for v in (entrada, saida, total)):
            return
        self._chamadas_com_tokens += 1
        self._tokens_entrada += entrada
        self._tokens_saida += saida
        self._tokens_total += total

    def registrar_resultado_sql(self, quantidade_linhas: int, cortado: bool) -> None:
        self._linhas = quantidade_linhas
        self._cortado = cortado

    def finalizar(self, resultado: str, tipo_erro: str | None = None) -> None:
        if self._finalizada:
            return
        self._finalizada = True
        duracao = (time.perf_counter() - self._inicio) * 1000
        tokens_completos = self._chamadas_llm > 0 and self._chamadas_com_tokens == self._chamadas_llm
        try:
            self._persistir(
                self._iniciado_em,
                duracao,
                resultado,
                tipo_erro,
                tokens_completos,
            )
        except sqlite3.Error as erro:
            _log.warning("Falha ao persistir métricas locais (%s)", type(erro).__name__)
        print(
            f"[Metricas] id={self.id} resultado={resultado} duracao_ms={duracao:.0f} "
            f"chamadas_llm={self._chamadas_llm} tentativas_llm={self._tentativas}",
            file=sys.stderr,
            flush=True,
        )

    def _persistir(
        self, iniciado_em: str, duracao: float, resultado: str, tipo_erro: str | None,
        tokens_completos: bool,
    ) -> None:
        with closing(sqlite3.connect(self._caminho, timeout=10)) as banco, banco:
            banco.execute("""
                CREATE TABLE IF NOT EXISTS operacoes (
                    id TEXT PRIMARY KEY,
                    componente TEXT NOT NULL,
                    iniciado_em TEXT NOT NULL,
                    duracao_ms REAL NOT NULL,
                    resultado TEXT NOT NULL,
                    tipo_erro TEXT,
                    etapas_ms TEXT NOT NULL,
                    chamadas_llm INTEGER NOT NULL,
                    tentativas_llm INTEGER NOT NULL,
                    tokens_entrada INTEGER,
                    tokens_saida INTEGER,
                    tokens_total INTEGER,
                    tokens_completos INTEGER NOT NULL,
                    linhas_sql INTEGER NOT NULL,
                    cortado INTEGER NOT NULL
                )
            """)
            banco.execute(
                """INSERT INTO operacoes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    self.id,
                    self._componente,
                    iniciado_em,
                    duracao,
                    resultado,
                    tipo_erro,
                    json.dumps(self._etapas, sort_keys=True),
                    self._chamadas_llm,
                    self._tentativas,
                    self._tokens_entrada if self._chamadas_com_tokens else None,
                    self._tokens_saida if self._chamadas_com_tokens else None,
                    self._tokens_total if self._chamadas_com_tokens else None,
                    int(tokens_completos),
                    self._linhas,
                    int(self._cortado),
                ),
            )


def _percentil(valores: list[float], percentil: float) -> float | None:
    if not valores:
        return None
    ordenados = sorted(valores)
    return ordenados[min(len(ordenados) - 1, int((len(ordenados) - 1) * percentil))]


def resumo(caminho: Path = BANCO_METRICAS) -> str:
    if not caminho.exists():
        return "Ainda não há métricas registradas."
    with closing(sqlite3.connect(caminho)) as banco:
        linhas = banco.execute(
            "SELECT componente, resultado, duracao_ms, tokens_total, tokens_completos FROM operacoes"
        ).fetchall()
    if not linhas:
        return "Ainda não há métricas registradas."
    agentes = [linha for linha in linhas if linha[0] == "agente"]
    if not agentes:
        return f"Sem operações do agente; operações registradas pelo juiz LLM: {len(linhas)}."
    resultados: dict[str, int] = {}
    for _, resultado, *_ in agentes:
        resultados[resultado] = resultados.get(resultado, 0) + 1
    duracoes = [linha[2] for linha in agentes]
    tokens_conhecidos = [linha[3] for linha in agentes if linha[3] is not None]
    tokens_completos = sum(linha[4] for linha in agentes)
    taxa_sucesso = 100 * resultados.get("sucesso", 0) / len(agentes) if agentes else 0
    juiz = [linha for linha in linhas if linha[0] == "juiz_llm"]
    tokens_juiz = sum(linha[3] for linha in juiz if linha[3] is not None)
    return (
        f"Operações do agente: {len(agentes)}; taxa de sucesso: {taxa_sucesso:.1f}%; "
        f"resultados: {resultados}; "
        f"latência p50: {_percentil(duracoes, 0.50):.0f} ms; "
        f"p95: {_percentil(duracoes, 0.95):.0f} ms; "
        f"tokens reportados: {sum(tokens_conhecidos)} em {tokens_completos}/{len(agentes)} "
        f"operações com medição completa; juiz LLM: {len(juiz)} chamadas, "
        f"{tokens_juiz} tokens reportados"
    )


if __name__ == "__main__":
    print(resumo())
