"""Prisma · Agente de Armazenamento (MCP).

Guarda, consulta e apaga transações financeiras por titular, criptografadas, em SQLite.
Agente reativo simples: cada ferramenta MCP corresponde a uma ação fixa. Serve de
provedor de ferramentas para os outros agentes (Coletor de extratos, Análise).

Tudo roda localmente, a partir da raiz do projeto:
    python -m armazenamento            # stdio (Claude Code, Claude Desktop e o próprio Coletor)
    python -m armazenamento --http     # HTTP em http://127.0.0.1:8000/mcp, com token
"""

import argparse
import hashlib
import hmac
import json
import os
import re
import sqlite3
from contextlib import closing
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from mcp.server.mcpserver import MCPServer

from comum.config import DATA_DIR, carregar_chaves, log as _log
from comum.servidor_http import app_com_token, rodar

NOME_AGENTE = "agente-armazenamento"
MAX_LOTE = 500


def log(msg: str) -> None:
    _log(NOME_AGENTE, msg)


# --- Configuração ---
CHAVES = carregar_chaves()
MCP_TOKEN = CHAVES["MCP_TOKEN"]
FERNET = Fernet(CHAVES["ENCRYPTION_KEY"].encode())
HASH_KEY = CHAVES["HASH_KEY"].encode()
DB_PATH = os.getenv("DB_PATH") or str(DATA_DIR / "dados.db")


# --- Banco ---
def init_db() -> None:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(DB_PATH)) as conn, conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS registros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titular TEXT NOT NULL,
            dados TEXT NOT NULL,
            criado_em TEXT DEFAULT CURRENT_TIMESTAMP)""")
        colunas = {c[1] for c in conn.execute("PRAGMA table_info(registros)")}
        if "chave_hash" not in colunas:  # migração de bancos criados pela versão anterior
            conn.execute("ALTER TABLE registros ADD COLUMN chave_hash TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_titular ON registros (titular)")
        # Uma mesma chave de transação só entra uma vez por titular (NULL não conflita)
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_titular_chave ON registros (titular, chave_hash)")


def db():
    return closing(sqlite3.connect(DB_PATH))


def _hmac(texto: str) -> str:
    return hmac.new(HASH_KEY, texto.encode(), hashlib.sha256).hexdigest()


def normalizar_id(titular_id: str) -> str:
    # "000.000.000-00", " 00000000000 " e "000 000 000/00" viram o mesmo titular
    return re.sub(r"[\s.\-/]", "", titular_id).casefold()


def titular_hash(titular_id: str) -> str:
    return _hmac(normalizar_id(titular_id))


def chave_hash(titular: str, dados: dict) -> str | None:
    # A chave da transação também é pseudonimizada, e amarrada ao titular
    chave = dados.get("chave")
    return _hmac(f"{titular}|{chave}") if chave else None


def _inserir(conn, titular: str, dados: dict) -> int | None:
    cifrado = FERNET.encrypt(json.dumps(dados, ensure_ascii=False).encode()).decode()
    cur = conn.execute("INSERT OR IGNORE INTO registros (titular, dados, chave_hash) VALUES (?, ?, ?)",
                       (titular, cifrado, chave_hash(titular, dados)))
    return cur.lastrowid if cur.rowcount else None


init_db()


# --- Ferramentas MCP ---
mcp = MCPServer(
    name=NOME_AGENTE,
    instructions=(
        "Agente de Armazenamento do Prisma. Guarda transações financeiras por titular, criptografadas. "
        "Use salvar_transacao ou salvar_lote para gravar (se a transação tiver o campo 'chave', "
        "ela não é gravada duas vezes), consultar_titular para ler e eliminar_titular para apagar "
        "tudo de um titular (LGPD, art. 18)."
    ),
)


@mcp.tool()
def salvar_transacao(titular_id: str, dados: dict) -> dict:
    """Guarda qualquer JSON de transação financeira, criptografado. Se 'dados' tiver o campo
    'chave' e ela já existir para o titular, nada é gravado e o status é 'ja_existia'."""
    with db() as conn, conn:
        novo_id = _inserir(conn, titular_hash(titular_id), dados)
    return {"status": "ok", "id": novo_id} if novo_id else {"status": "ja_existia"}


@mcp.tool()
def salvar_lote(titular_id: str, transacoes: list[dict]) -> dict:
    """Guarda várias transações de uma vez (até 500), numa única operação. As que têm 'chave'
    já gravada para o titular são ignoradas, então reenviar o mesmo lote não duplica nada."""
    if len(transacoes) > MAX_LOTE:
        raise ValueError(f"No máximo {MAX_LOTE} transações por lote (recebidas: {len(transacoes)}).")
    titular = titular_hash(titular_id)
    with db() as conn, conn:
        ids = [_inserir(conn, titular, t) for t in transacoes]
    gravados = [i for i in ids if i]
    return {"status": "ok", "gravadas": len(gravados), "ja_existiam": len(ids) - len(gravados), "ids": gravados}


@mcp.tool()
def consultar_titular(titular_id: str) -> dict:
    """Retorna os dados guardados de um titular."""
    with db() as conn:
        linhas = conn.execute("SELECT id, dados, criado_em FROM registros WHERE titular = ? ORDER BY id",
                              (titular_hash(titular_id),)).fetchall()
    registros, ilegiveis = [], []
    for i, d, c in linhas:
        try:
            registros.append({"id": i, "criado_em": c, "dados": json.loads(FERNET.decrypt(d))})
        except InvalidToken:
            ilegiveis.append(i)  # cifrado com outra chave
    resposta = {"registros": registros}
    if ilegiveis:
        resposta["ilegiveis"] = ilegiveis
    return resposta


@mcp.tool()
def eliminar_titular(titular_id: str) -> dict:
    """Apaga todos os dados de um titular."""
    with db() as conn, conn:
        n = conn.execute("DELETE FROM registros WHERE titular = ?", (titular_hash(titular_id),)).rowcount
    return {"status": "ok", "apagados": n}


# --- App HTTP local com token (modo --http) ---
app = app_com_token(mcp, NOME_AGENTE)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prisma · Agente de Armazenamento (MCP)")
    parser.add_argument("--http", action="store_true", help="servir via HTTP em vez de stdio")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    log(f"Banco: {DB_PATH}")
    if args.http:
        rodar(app, NOME_AGENTE, args.port)
    else:
        mcp.run(transport="stdio")
