"""Proteção da execução do SQL no agente-sql (só biblioteca padrão).

O próprio SQLite confere cada leitura (authorizer): só SELECT, só nas fontes permitidas, sem PRAGMA,
ATTACH, escrita ou funções perigosas, e uma instrução por vez. Fica aqui porque o SQL só existe dentro
deste agente: quem executa é quem consegue barrar.

O filtro de entrada (manipulação, "só finanças") e o guardião dos valores da resposta ficam no
orquestrador (projeto_agentes/orquestrador/guardas.py), que é o ponto de entrada único.
"""

import re
import sqlite3

MAX_SQL = 4000

# Fontes que o SQL pode consultar diretamente.
FONTES_PERMITIDAS = {"vw_registers", "account_dim", "item_dim"}
# Tabelas que a view vw_registers lê por dentro (liberadas só quando a leitura vem da view).
INTERNAS_DA_VIEW = {"transaction_fact", "category_dim", "category_override", "account_dim", "item_dim"}
FUNCOES_PROIBIDAS = {"load_extension", "readfile", "writefile", "edit", "fts3_tokenizer"}


class SqlRejeitado(ValueError):
    """SQL fora das regras. A mensagem é curta e segura para devolver ao modelo."""


def checar_texto_sql(sql: str) -> str:
    """Checagens baratas antes de ir ao banco; o authorizer faz o resto."""
    texto = (sql or "").strip().rstrip(";").strip()
    if not texto:
        raise SqlRejeitado("SQL vazio")
    if len(texto) > MAX_SQL:
        raise SqlRejeitado("SQL longo demais")
    if not re.match(r"(?is)^(select|with)\b", texto):
        raise SqlRejeitado("apenas SELECT é permitido")
    # Uma CTE com o nome de uma fonte permitida esconderia o que ela lê de verdade.
    if re.search(r"(?i)\b(" + "|".join(sorted(FONTES_PERMITIDAS)) + r")\s+as\s*\(", texto):
        raise SqlRejeitado("não crie CTE com o nome de uma fonte do banco")
    return texto


def instalar_autorizador(banco: sqlite3.Connection) -> list[str]:
    """Faz o SQLite recusar tudo que não for leitura das fontes permitidas.

    Devolve uma lista que recebe o motivo de cada recusa (para explicar o erro ao modelo).
    """
    recusas: list[str] = []

    def autorizar(acao, arg1, arg2, nome_banco, origem):
        if acao == sqlite3.SQLITE_SELECT:
            return sqlite3.SQLITE_OK
        if acao == sqlite3.SQLITE_READ:
            if nome_banco not in (None, "main"):
                recusas.append("não use outro banco")
                return sqlite3.SQLITE_DENY
            tabela = (arg1 or "").lower()
            if tabela in FONTES_PERMITIDAS or (origem == "vw_registers" and tabela in INTERNAS_DA_VIEW):
                return sqlite3.SQLITE_OK
            recusas.append(f"a tabela {arg1} não pode ser consultada; use só "
                           + ", ".join(sorted(FONTES_PERMITIDAS)))
            return sqlite3.SQLITE_DENY
        if acao == sqlite3.SQLITE_FUNCTION:
            nome = (arg2 or "").lower()
            if nome in FUNCOES_PROIBIDAS or nome.startswith(("sqlite_", "pragma_")):
                recusas.append(f"a função {arg2} não é permitida")
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK
        if acao == sqlite3.SQLITE_RECURSIVE:
            return sqlite3.SQLITE_OK
        recusas.append("apenas SELECT é permitido")
        return sqlite3.SQLITE_DENY

    banco.set_authorizer(autorizar)
    return recusas
