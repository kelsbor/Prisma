"""Limites por token: requisições por minuto e perguntas por dia (em memória)."""

from __future__ import annotations

import hashlib
import threading
import time
from collections import defaultdict, deque
from datetime import date
from typing import Callable


class LimiteExcedido(Exception):
    def __init__(self, mensagem: str, retry_after_s: int):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.retry_after_s = retry_after_s


class RateLimiter:
    def __init__(self, per_minute: int, per_day: int, now: Callable[[], float] = time.monotonic,
                 today: Callable[[], date] = date.today):
        self._per_minute = per_minute
        self._per_day = per_day
        self._now = now
        self._today = today
        self._lock = threading.Lock()
        self._janela: dict[str, deque[float]] = defaultdict(deque)
        self._dia: dict[str, tuple[date, int]] = {}

    @staticmethod
    def _chave(token: str) -> str:  # nunca guardar o token em si
        return hashlib.sha256(token.encode()).hexdigest()[:16]

    def requisicao(self, token: str) -> None:
        chave = self._chave(token)
        with self._lock:
            agora = self._now()
            fila = self._janela[chave]
            while fila and agora - fila[0] >= 60:
                fila.popleft()
            if len(fila) >= self._per_minute:
                espera = int(60 - (agora - fila[0])) + 1
                raise LimiteExcedido("Muitas perguntas em pouco tempo. Aguarde um instante.", espera)
            fila.append(agora)

    def pergunta(self, token: str) -> None:
        chave = self._chave(token)
        with self._lock:
            hoje = self._today()
            dia, usadas = self._dia.get(chave, (hoje, 0))
            if dia != hoje:
                usadas = 0
            if usadas >= self._per_day:
                raise LimiteExcedido("Você atingiu o limite de perguntas de hoje. Tente amanhã.", 3600)
            self._dia[chave] = (hoje, usadas + 1)
