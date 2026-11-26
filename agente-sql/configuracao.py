"""Configuração do agente-sql.

Ordem: 1) config.json nesta pasta (o jeito original); 2) o .env ÚNICO do projeto
(../projeto_agentes/.env, ou o arquivo em PRISMA_ENV_FILE) e as variáveis de ambiente.
Assim o agente-sql usa a mesma chave do Gemini e o mesmo banco do app que o resto do Prisma.

Variáveis do .env usadas:
  GOOGLE_API_KEY, GEMINI_MODEL                     -> gemini_api_key, gemini_model
  PLUGGY_CLIENT_ID, PLUGGY_CLIENT_SECRET            -> credenciais da Pluggy
  PLUGGY_ITEM_IDS (separados por vírgula)           -> pluggy_item_ids
  PRISMA_APP_DB (padrão ~/.prisma/app/prisma.db)    -> banco
"""

import json
import os
from pathlib import Path

PASTA = Path(__file__).parent


def _ler_env(arquivo: Path) -> dict:
    valores = {}
    if arquivo.exists():
        for linha in arquivo.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if linha and not linha.startswith("#") and "=" in linha:
                k, v = linha.split("=", 1)
                valores[k.strip()] = v.strip().strip('"').strip("'")
    return valores


def carregar() -> dict:
    arquivo_json = PASTA / "config.json"
    if arquivo_json.exists():
        return json.loads(arquivo_json.read_text(encoding="utf-8"))
    env_file = Path(os.getenv("PRISMA_ENV_FILE") or PASTA.parent / "projeto_agentes" / ".env").expanduser()
    env = {**_ler_env(env_file), **{k: v for k, v in os.environ.items() if v}}   # o ambiente tem prioridade
    banco = env.get("PRISMA_APP_DB") or str(Path.home() / ".prisma" / "app" / "prisma.db")
    return {
        "gemini_api_key": env.get("GOOGLE_API_KEY", ""),
        "gemini_model": env.get("GEMINI_MODEL") or "gemini-flash-lite-latest",
        "pluggy_client_id": env.get("PLUGGY_CLIENT_ID", ""),
        "pluggy_client_secret": env.get("PLUGGY_CLIENT_SECRET", ""),
        "pluggy_item_ids": [i.strip() for i in env.get("PLUGGY_ITEM_IDS", "").split(",") if i.strip()],
        "banco": str(Path(banco).expanduser()),
    }
