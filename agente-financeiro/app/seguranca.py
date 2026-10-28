import hashlib
import hmac
import json

from cryptography.fernet import Fernet

from app.config import ENCRYPTION_KEY, HASH_KEY

_fernet = Fernet(ENCRYPTION_KEY.encode())


def cifrar(dados) -> str:
    """Criptografa qualquer JSON (AES + HMAC via Fernet)."""
    return _fernet.encrypt(json.dumps(dados, ensure_ascii=False, default=str).encode()).decode()


def decifrar(token: str):
    return json.loads(_fernet.decrypt(token.encode()))


def pseudonimizar(titular_id: str) -> str:
    """Transforma CPF/ID do titular em um hash irreversível sem a HASH_KEY."""
    return hmac.new(HASH_KEY.encode(), titular_id.strip().encode(), hashlib.sha256).hexdigest()
