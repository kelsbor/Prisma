"""Agente MCP simples: guarda dados financeiros criptografados em SQLite."""
import hashlib
import hmac
import json
import os
import sqlite3

from cryptography.fernet import Fernet
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse

# --- Configuração (variáveis de ambiente do Render) ---
MCP_TOKEN = os.environ["MCP_TOKEN"]
FERNET = Fernet(os.environ["ENCRYPTION_KEY"].encode())
HASH_KEY = os.environ["HASH_KEY"].encode()
DB_PATH = os.getenv("DB_PATH", "dados.db")
HOST = os.getenv("RENDER_EXTERNAL_HOSTNAME", "localhost")

# --- Banco ---
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS registros (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        titular TEXT NOT NULL,
        dados TEXT NOT NULL,
        criado_em TEXT DEFAULT CURRENT_TIMESTAMP)""")
    return conn

def titular_hash(titular_id: str) -> str:
    return hmac.new(HASH_KEY, titular_id.strip().encode(), hashlib.sha256).hexdigest()

# --- Ferramentas MCP ---
mcp = MCPServer(name="agente-financeiro")

@mcp.tool()
def salvar_transacao(titular_id: str, dados: dict) -> dict:
    """Guarda qualquer JSON de transação financeira, criptografado."""
    cifrado = FERNET.encrypt(json.dumps(dados, ensure_ascii=False).encode()).decode()
    with db() as conn:
        cur = conn.execute("INSERT INTO registros (titular, dados) VALUES (?, ?)",
                           (titular_hash(titular_id), cifrado))
    return {"status": "ok", "id": cur.lastrowid}

@mcp.tool()
def consultar_titular(titular_id: str) -> dict:
    """Retorna os dados guardados de um titular."""
    with db() as conn:
        linhas = conn.execute("SELECT id, dados, criado_em FROM registros WHERE titular = ? ORDER BY id",
                              (titular_hash(titular_id),)).fetchall()
    return {"registros": [{"id": i, "criado_em": c, "dados": json.loads(FERNET.decrypt(d))}
                          for i, d, c in linhas]}

@mcp.tool()
def eliminar_titular(titular_id: str) -> dict:
    """Apaga todos os dados de um titular."""
    with db() as conn:
        n = conn.execute("DELETE FROM registros WHERE titular = ?", (titular_hash(titular_id),)).rowcount
    return {"status": "ok", "apagados": n}

@mcp.custom_route("/health", methods=["GET"])
async def health(_):
    return JSONResponse({"status": "ok"})

# --- App HTTP com token ---
_mcp_app = mcp.streamable_http_app(
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(allowed_hosts=[HOST, f"{HOST}:*", "localhost:*"]),
)

async def app(scope, receive, send):
    if scope["type"] == "http" and scope["path"] != "/health":
        auth = dict(scope["headers"]).get(b"authorization", b"").decode()
        if not hmac.compare_digest(auth, f"Bearer {MCP_TOKEN}"):
            await JSONResponse({"erro": "Não autorizado"}, status_code=401)(scope, receive, send)
            return
    await _mcp_app(scope, receive, send)
