"""Configuração compartilhada pelos agentes do Prisma: pasta de dados, chaves e logs."""

import json
import os
import secrets
import sys
from pathlib import Path

from cryptography.fernet import Fernet

RAIZ = Path(__file__).resolve().parent.parent          # pasta do projeto


def _carregar_env(arquivo: Path) -> None:
    """Lê KEY=VALOR de um .env na raiz do projeto, sem sobrescrever o que já está no ambiente."""
    if not arquivo.exists():
        return
    for linha in arquivo.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#") and "=" in linha:
            chave, valor = linha.split("=", 1)
            os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))


_carregar_env(RAIZ / ".env")
DATA_DIR = Path(os.getenv("PRISMA_DIR", Path.home() / ".prisma"))
NOMES_CHAVES = ("MCP_TOKEN", "ENCRYPTION_KEY", "HASH_KEY")


def log(agente: str, msg: str) -> None:
    # Em MCP via stdio, o stdout é o canal do protocolo: logs vão sempre para o stderr.
    print(f"[{agente}] {msg}", file=sys.stderr, flush=True)


def carregar_chaves() -> dict:
    """Variáveis de ambiente têm prioridade; o que faltar vem de ~/.prisma/chaves.json (gerado na 1ª vez)."""
    do_ambiente = {k: os.environ[k] for k in NOMES_CHAVES if os.getenv(k)}
    if len(do_ambiente) == len(NOMES_CHAVES):
        return do_ambiente

    arquivo = DATA_DIR / "chaves.json"
    if arquivo.exists():
        chaves = json.loads(arquivo.read_text())
    else:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        chaves = {
            "MCP_TOKEN": secrets.token_urlsafe(48),
            "ENCRYPTION_KEY": Fernet.generate_key().decode(),
            "HASH_KEY": secrets.token_urlsafe(48),
        }
        arquivo.write_text(json.dumps(chaves, indent=2))
        try:
            arquivo.chmod(0o600)
        except OSError:
            pass  # o Windows ignora permissões POSIX
        log("prisma", f"Chaves novas geradas em {arquivo}. Faça backup: sem elas os dados não podem ser lidos.")
    return {**chaves, **do_ambiente}
