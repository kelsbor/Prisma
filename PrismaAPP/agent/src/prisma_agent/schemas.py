"""Contratos JSON entre o app e o servidor, e as saídas estruturadas pedidas ao Gemini."""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

MAX_PERGUNTA = 300
MAX_SQL = 4000
MAX_COLUNAS = 20
MAX_LINHAS = 50
MAX_CELULA = 200

Nome = Annotated[str, Field(max_length=120)]
Celula = Annotated[str, Field(max_length=MAX_CELULA)] | int | float | None


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------- Chamada 1: gerar SQL ----------

class Turno(_Strict):
    pergunta: str = Field(max_length=MAX_PERGUNTA)
    sql: str | None = Field(default=None, max_length=MAX_SQL)


class ErroAnterior(_Strict):
    sql: str = Field(max_length=MAX_SQL)
    erro: str = Field(max_length=300)


class Contexto(_Strict):
    categorias: list[Nome] = Field(default_factory=list, max_length=300)
    contas: list[Nome] = Field(default_factory=list, max_length=30)
    bancos: list[Nome] = Field(default_factory=list, max_length=10)


class GerarSqlRequest(_Strict):
    pergunta: str = Field(min_length=1, max_length=MAX_PERGUNTA)
    hoje: date
    historico: list[Turno] = Field(default_factory=list, max_length=3)
    contexto: Contexto = Field(default_factory=Contexto)
    erro_anterior: ErroAnterior | None = None


class Status(str, Enum):
    ok = "ok"
    fora_do_escopo = "fora_do_escopo"
    nao_sei = "nao_sei"
    bloqueado = "bloqueado"


class GerarSqlResponse(BaseModel):
    status: Status
    sql: str | None = None
    mensagem: str | None = None


# ---------- Chamada 2: redigir a resposta ----------

class ResponderRequest(_Strict):
    pergunta: str = Field(min_length=1, max_length=MAX_PERGUNTA)
    hoje: date
    sql: str = Field(min_length=1, max_length=MAX_SQL)
    colunas: list[Annotated[str, Field(max_length=64)]] = Field(max_length=MAX_COLUNAS)
    linhas: list[Annotated[list[Celula], Field(max_length=MAX_COLUNAS)]] = Field(max_length=MAX_LINHAS)
    total_linhas: int = Field(ge=0)


class ResponderResponse(BaseModel):
    status: Literal["ok", "nao_sei"]
    resposta: str


# ---------- Saídas estruturadas do Gemini ----------

class DecisaoSql(BaseModel):
    """Decisão do gerador de consultas.

    `motivo` vem PRIMEIRO de propósito: o modelo gera os campos na ordem do esquema,
    então escrever o motivo antes funciona como um raciocínio curto que orienta a classificação.
    """

    motivo: str = Field(description="Frase curta: o que a pergunta pede e se a view vw_registers tem esse dado")
    classificacao: Literal["consulta", "sem_dados", "fora_do_escopo"] = Field(
        description="consulta | sem_dados | fora_do_escopo"
    )
    sql: str | None = Field(default=None, description="Uma única consulta SELECT sobre vw_registers, ou null")


class Redacao(BaseModel):
    """Resposta final ao usuário."""

    responde_a_pergunta: bool = Field(description="false se o resultado não responde a pergunta com segurança")
    resposta: str = Field(description="Texto final ao usuário, em português")
