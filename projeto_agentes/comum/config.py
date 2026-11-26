"""Configuração compartilhada pelos agentes do Prisma: .env único, pasta de dados, token e logs."""

import json
import os
import secrets
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent          # pasta do projeto (projeto_agentes)


def _carregar_env(arquivo: Path) -> None:
    """Lê KEY=VALOR do .env, sem sobrescrever o que já está no ambiente."""
    if not arquivo.exists():
        return
    for linha in arquivo.read_text(encoding="utf-8-sig").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#") and "=" in linha:
            chave, valor = linha.split("=", 1)
            os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))


_carregar_env(Path(os.getenv("PRISMA_ENV_FILE") or RAIZ / ".env").expanduser())
DATA_DIR = Path(os.getenv("PRISMA_DIR") or Path.home() / ".prisma").expanduser()
# Banco com os dados da Pluggy (gerado pelo agente-sql: ./prisma.sh pluggy). Mesmas tabelas do PrismaAPP.
BANCO_APP = Path(os.getenv("PRISMA_APP_DB") or DATA_DIR / "app" / "prisma.db").expanduser()


def log(agente: str, msg: str) -> None:
    # Em MCP via stdio, o stdout é o canal do protocolo: logs vão sempre para o stderr.
    print(f"[{agente}] {msg}", file=sys.stderr, flush=True)


def carregar_chaves() -> dict:
    """Token dos serviços HTTP locais. MCP_TOKEN no ambiente tem prioridade; senão vem de
    ~/.prisma/chaves.json, gerado na 1ª vez com permissão 600."""
    if os.getenv("MCP_TOKEN"):
        return {"MCP_TOKEN": os.environ["MCP_TOKEN"]}
    arquivo = DATA_DIR / "chaves.json"
    if arquivo.exists():
        chaves = json.loads(arquivo.read_text())
        if chaves.get("MCP_TOKEN"):
            return {"MCP_TOKEN": chaves["MCP_TOKEN"]}
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    chaves = {"MCP_TOKEN": secrets.token_urlsafe(48)}
    arquivo.write_text(json.dumps(chaves, indent=2))
    try:
        arquivo.chmod(0o600)
    except OSError:
        pass  # o Windows ignora permissões POSIX
    log("prisma", f"Token novo dos serviços gerado em {arquivo}.")
    return chaves
