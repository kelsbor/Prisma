"""Cliente da API SGS do Banco Central, com cache local.

    https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados/ultimos/{n}?formato=json

Só os códigos das séries saem da máquina: nenhum dado da pessoa vai para o Banco Central.
As respostas ficam em ~/.prisma/indicadores/cache.json por 12 horas. Se a API falhar, o agente usa o
último valor guardado e avisa de quando ele é.
"""

import json
import time
import urllib.request
from datetime import datetime

from comum.config import DATA_DIR, log

URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados/ultimos/{n}?formato=json"
CACHE = DATA_DIR / "indicadores" / "cache.json"
VALIDADE_S = 12 * 3600


class ErroBCB(Exception):
    pass


def _baixar(codigo: int, n: int) -> list:
    req = urllib.request.Request(URL.format(codigo=codigo, n=n),
                                 headers={"User-Agent": "Prisma/1.0 (projeto educacional)", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def _ler_cache() -> dict:
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _gravar_cache(cache: dict) -> None:
    try:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _normalizar(bruto: list) -> list[dict]:
    pontos = []
    for p in bruto:
        try:
            data = datetime.strptime(p["data"], "%d/%m/%Y").date().isoformat()
            pontos.append({"data": data, "valor": float(str(p["valor"]).replace(",", "."))})
        except (KeyError, ValueError):
            continue
    return pontos


def ultimos(codigo: int, n: int = 1) -> dict:
    """Últimos n valores da série: {"pontos": [...], "origem": "api"|"cache", "consultado_em": ..., "aviso"?}."""
    chave = f"{codigo}:{n}"
    cache = _ler_cache()
    item = cache.get(chave)
    if item and time.time() - item["ts"] < VALIDADE_S:
        return {"pontos": item["pontos"], "origem": "cache", "consultado_em": item["consultado_em"]}
    try:
        pontos = _normalizar(_baixar(codigo, n))
        if not pontos:
            raise ErroBCB("resposta vazia")
        agora = datetime.now().astimezone().isoformat(timespec="seconds")
        cache[chave] = {"ts": time.time(), "pontos": pontos, "consultado_em": agora}
        _gravar_cache(cache)
        return {"pontos": pontos, "origem": "api", "consultado_em": agora}
    except Exception as e:
        log("agente-indicadores", f"API do Banco Central indisponível para a série {codigo}: {e}")
        if item:
            return {"pontos": item["pontos"], "origem": "cache antigo", "consultado_em": item["consultado_em"],
                    "aviso": f"API indisponível; valor guardado em {item['consultado_em']}"}
        raise ErroBCB(f"série {codigo}: API do Banco Central indisponível e sem cache ({e})") from e
