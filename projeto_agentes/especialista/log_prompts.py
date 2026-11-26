"""Registro dos prompts do Especialista.

Cada chamada do `perguntar` vira uma linha JSON em ~/.prisma/logs/prompts.jsonl, com o prompt exato
(o mesmo texto que vai, ou iria, para o Gemini), os trechos usados, a resposta e quanto tempo levou.
O arquivo fica na máquina, fora do repositório. Com --com-dados, ele contém o resumo do mês da pessoa:
trate-o como dado pessoal.

    PRISMA_LOG_PROMPTS=0   desliga o registro
"""

import json
import os
from datetime import datetime, timezone

from comum.config import DATA_DIR

ARQUIVO = DATA_DIR / "logs" / "prompts.jsonl"
LIMITE_BYTES = 20 * 1024 * 1024        # acima disso, o arquivo atual vira prompts.jsonl.1


def ativo() -> bool:
    return os.getenv("PRISMA_LOG_PROMPTS", "1") != "0"


def registrar(registro: dict) -> None:
    if not ativo():
        return
    try:
        ARQUIVO.parent.mkdir(parents=True, exist_ok=True)
        if ARQUIVO.exists() and ARQUIVO.stat().st_size > LIMITE_BYTES:
            ARQUIVO.replace(ARQUIVO.with_suffix(".jsonl.1"))
        registro = {"quando": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"), **registro}
        with open(ARQUIVO, "a", encoding="utf-8") as f:
            f.write(json.dumps(registro, ensure_ascii=False, default=str) + "\n")
        try:
            ARQUIVO.chmod(0o600)        # só o próprio usuário lê (ignorado no Windows)
        except OSError:
            pass
    except OSError:
        pass                            # o log nunca pode derrubar a resposta


def ultimos(n: int = 5) -> list[dict]:
    if not ARQUIVO.exists():
        return []
    linhas = ARQUIVO.read_text(encoding="utf-8").splitlines()[-n:]
    return [json.loads(linha) for linha in linhas if linha.strip()]
