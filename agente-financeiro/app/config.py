import os

# Token de acesso ao servidor MCP (Authorization: Bearer <MCP_TOKEN>)
MCP_TOKEN = os.getenv("MCP_TOKEN", "")

# Chave de criptografia dos dados (Fernet). Gere com:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "")

# Chave para pseudonimizar o identificador do titular (qualquer texto longo e aleatório)
HASH_KEY = os.getenv("HASH_KEY", "")

if not (MCP_TOKEN and ENCRYPTION_KEY and HASH_KEY):
    raise RuntimeError("Defina MCP_TOKEN, ENCRYPTION_KEY e HASH_KEY nas variáveis de ambiente.")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./dados.db")
for prefixo in ("postgres://", "postgresql://"):
    if DATABASE_URL.startswith(prefixo):
        DATABASE_URL = DATABASE_URL.replace(prefixo, "postgresql+psycopg://", 1)

_render_host = os.getenv("RENDER_EXTERNAL_HOSTNAME", "")
ALLOWED_HOSTS = ["localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*"]
if _render_host:
    ALLOWED_HOSTS += [_render_host, f"{_render_host}:*"]
