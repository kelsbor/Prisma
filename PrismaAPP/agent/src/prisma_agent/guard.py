"""Barreiras de segurança: entrada do usuário e SQL gerado.

O app valida o SQL de novo antes de executar (quem executa sempre se protege),
e executa numa conexão somente leitura. Esta é a primeira barreira.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from .schemas import MAX_PERGUNTA, MAX_SQL

VIEW = "vw_registers"

# ---------------- Entrada (pergunta) ----------------

_TENTATIVAS = [
    # tentativas de mudar as regras / extrair o prompt
    r"\bignore\b.{0,40}\b(instru|regra|anterior|acima)",
    r"\b(esque[cç]a|desconsidere)\b.{0,40}\b(instru|regra|anterior|acima)",
    r"\b(prompt|instru[cç][oõ]es)\s+(do\s+)?(sistema|system)\b",
    r"\bsystem\s+prompt\b",
    r"\bjailbreak\b",
    r"\bmodo\s+(desenvolvedor|developer|dan)\b",
    # SQL escrito diretamente na pergunta
    r"\b(drop|delete|insert|update|alter|attach|pragma|truncate)\s+(table|from|into|database|\w+\s+set)\b",
    r";\s*(select|drop|delete|insert|update)\b",
]
_TENTATIVAS_RE = [re.compile(p, re.IGNORECASE | re.DOTALL) for p in _TENTATIVAS]


@dataclass(frozen=True)
class EntradaVerificada:
    texto: str
    bloqueada: bool


def verificar_pergunta(pergunta: str) -> EntradaVerificada:
    """Normaliza a pergunta e bloqueia tentativas óbvias de manipulação."""
    texto = unicodedata.normalize("NFKC", pergunta)
    texto = re.sub(r"\s+", " ", texto)
    texto = "".join(c for c in texto if c.isprintable()).strip()[:MAX_PERGUNTA]
    bloqueada = not texto or any(r.search(texto) for r in _TENTATIVAS_RE)
    return EntradaVerificada(texto=texto, bloqueada=bloqueada)


# ---------------- SQL ----------------

class SqlRejeitado(ValueError):
    """SQL fora das regras. A mensagem é curta e segura para devolver ao modelo."""


_PROIBIDOS = (
    exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter,
    exp.Command, exp.Pragma, exp.Transaction, exp.Commit, exp.Rollback,
)
_FUNCOES_PROIBIDAS = {"load_extension", "readfile", "writefile", "edit", "fts3_tokenizer"}


def validar_sql(sql: str) -> str:
    """Devolve o SQL limpo se seguir as regras; senão levanta SqlRejeitado."""
    if not sql or not sql.strip():
        raise SqlRejeitado("SQL vazio")
    texto = sql.strip().rstrip(";").strip()
    if len(texto) > MAX_SQL:
        raise SqlRejeitado("SQL longo demais")
    if "--" in texto or "/*" in texto:
        raise SqlRejeitado("comentários não são permitidos")

    try:
        comandos = [c for c in sqlglot.parse(texto, read="sqlite") if c is not None]
    except ParseError:
        raise SqlRejeitado("SQL inválido") from None
    if len(comandos) != 1:
        raise SqlRejeitado("apenas uma instrução é permitida")
    raiz = comandos[0]

    if not isinstance(raiz, exp.Query):
        raise SqlRejeitado("apenas SELECT é permitido")
    if any(raiz.find(t) for t in _PROIBIDOS):
        raise SqlRejeitado("apenas SELECT é permitido")

    ctes = {c.alias_or_name.lower() for c in raiz.find_all(exp.CTE)}
    usa_view = False
    for tabela in raiz.find_all(exp.Table):
        nome = tabela.name.lower()
        if tabela.args.get("catalog") or (tabela.args.get("db") and tabela.text("db").lower() != "main"):
            raise SqlRejeitado("não use prefixo de banco")
        if nome == VIEW:
            usa_view = True
        elif nome not in ctes:
            raise SqlRejeitado(f"apenas a view {VIEW} pode ser consultada")
    if not usa_view:
        raise SqlRejeitado(f"a consulta precisa usar a view {VIEW}")

    for funcao in raiz.find_all(exp.Anonymous):
        nome = str(funcao.name).lower()
        if nome in _FUNCOES_PROIBIDAS or nome.startswith(("sqlite_", "pragma_")):
            raise SqlRejeitado("função não permitida")

    return texto
