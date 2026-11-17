"""Configuração lida do ambiente (arquivo agent/.env). Nenhum segredo fica no código."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

AGENT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_MODEL = "gemini-3.5-flash-lite"


@dataclass(frozen=True)
class Settings:
    google_api_key: str
    gemini_model: str
    app_tokens: frozenset[str]
    per_minute: int
    questions_per_day: int
    llm_timeout_s: float

    def __repr__(self) -> str:  # nunca expor segredos em logs/tracebacks
        return f"Settings(model={self.gemini_model!r}, tokens={len(self.app_tokens)}, per_minute={self.per_minute})"


class ConfigError(RuntimeError):
    pass


def load_settings() -> Settings:
    load_dotenv(AGENT_DIR / ".env")
    key = os.getenv("GOOGLE_API_KEY", "").strip()
    tokens = frozenset(t.strip() for t in os.getenv("APP_TOKENS", "").split(",") if t.strip())
    if not key:
        raise ConfigError("GOOGLE_API_KEY não definido em agent/.env")
    if not tokens:
        raise ConfigError("APP_TOKENS não definido em agent/.env")
    if any(len(t) < 24 for t in tokens):
        raise ConfigError("Cada APP_TOKEN precisa ter pelo menos 24 caracteres")
    return Settings(
        google_api_key=key,
        # Versão fixa (não um apelido "-latest"): o comportamento só muda quando alguém troca aqui ou no .env.
        gemini_model=os.getenv("GEMINI_MODEL", DEFAULT_MODEL).strip(),
        app_tokens=tokens,
        per_minute=int(os.getenv("LIMITE_POR_MINUTO", "20")),
        questions_per_day=int(os.getenv("LIMITE_PERGUNTAS_POR_DIA", "100")),
        llm_timeout_s=float(os.getenv("LLM_TIMEOUT_S", "40")),
    )
