"""Avalia o gerador de SQL contra uma CÓPIA do prisma.db (com -wal e -shm na mesma pasta).

Uso (a partir de agent/):
    uv run python evals/run_evals.py --db caminho/para/prisma.db [--hoje 2026-11-15] [--detalhes]

Chama o Gemini de verdade (só a etapa 1: envia pergunta, esquema e nomes de categorias/contas,
nunca linhas do banco). Por padrão mostra só ACERTOU/ERROU; --detalhes mostra o motivo e o SQL gerado.
Os valores do banco nunca são impressos.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from prisma_agent.api import limite_do_provedor  # noqa: E402
from prisma_agent.chains import criar_gerador  # noqa: E402
from prisma_agent.config import load_settings  # noqa: E402
from prisma_agent.guard import SqlRejeitado, validar_sql, verificar_pergunta  # noqa: E402
from prisma_agent.knowledge import aplicar_datas  # noqa: E402
from prisma_agent.schemas import Contexto, GerarSqlRequest, Turno  # noqa: E402


def abrir(db: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)


def contexto(con: sqlite3.Connection) -> Contexto:
    def distintos(col: str, limite: int) -> list[str]:
        sql = f"SELECT DISTINCT {col} FROM vw_registers WHERE {col} IS NOT NULL ORDER BY 1 LIMIT {limite}"
        return [r[0] for r in con.execute(sql)]
    return Contexto(categorias=distintos("categoria", 300), contas=distintos("conta", 30), bancos=distintos("banco", 10))


def assinatura(linhas: list[tuple]) -> list[tuple]:
    """Só os números de cada linha, arredondados; ordem das linhas ignorada."""
    out = []
    for linha in linhas:
        nums = sorted(round(float(v), 2) for v in linha if isinstance(v, (int, float)))
        out.append(tuple(nums))
    return sorted(out)


def mesmos_numeros(ref: list[tuple], gerado: list[tuple]) -> bool:
    a, b = assinatura(ref), assinatura(gerado)
    if len(a) != len(b):
        return False
    restantes = list(b)
    for nums in a:  # cada linha de referência precisa caber em alguma linha gerada (colunas extras são ok)
        for i, cand in enumerate(restantes):
            if not (Counter(nums) - Counter(cand)):
                restantes.pop(i)
                break
        else:
            return False
    return True


_ultima_chamada = 0.0


def chamar_com_ritmo(gerador, req, pergunta, intervalo: float):
    global _ultima_chamada
    for tentativa in range(3):
        espera = intervalo - (time.monotonic() - _ultima_chamada)
        if espera > 0:
            time.sleep(espera)
        _ultima_chamada = time.monotonic()
        try:
            return gerador(req, pergunta)
        except Exception as e:
            por_dia = "PerDay" in str(e)  # cota diária: esperar não adianta
            if tentativa == 2 or por_dia or not limite_do_provedor(e):
                raise
            time.sleep(30)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True, type=Path)
    p.add_argument("--hoje", type=date.fromisoformat, default=date.today())
    p.add_argument("--detalhes", action="store_true")
    p.add_argument("--so", help="rodar só este id")
    p.add_argument("--intervalo", type=float, default=13.0,
                   help="segundos entre chamadas (plano gratuito do Gemini: 5 por minuto)")
    args = p.parse_args()

    hoje: date = args.hoje
    casos = yaml.safe_load((Path(__file__).parent / "perguntas.yaml").read_text(encoding="utf-8"))
    if args.so:
        casos = [c for c in casos if c["id"] == args.so]
    con = abrir(args.db)
    ctx = contexto(con)
    gerador = criar_gerador(load_settings())

    acertos = feitos = 0
    for caso in casos:
        esperado = caso["esperado"]
        entrada = verificar_pergunta(caso["pergunta"])
        motivo = None
        if entrada.bloqueada:
            obtido, sql, ok = "bloqueado", None, esperado in ("recusa", "fora_do_escopo")
        else:
            historico = [Turno(**t) for t in caso.get("historico", [])]
            req = GerarSqlRequest(pergunta=entrada.texto, hoje=hoje, contexto=ctx, historico=historico)
            try:
                decisao = chamar_com_ritmo(gerador, req, entrada.texto, args.intervalo)
            except Exception as e:
                motivo = "cota do Gemini esgotada" if limite_do_provedor(e) else type(e).__name__
                print(f"\nParou em '{caso['id']}': {motivo}. {acertos}/{feitos} corretas até aqui.", flush=True)
                return 2
            obtido, sql, motivo = decisao.classificacao, decisao.sql, decisao.motivo
            if obtido == "consulta":
                try:
                    sql = validar_sql(sql or "")
                except SqlRejeitado as e:
                    obtido = f"rejeitado ({e})"
            if esperado == "consulta" and obtido == "consulta":
                ref_sql = aplicar_datas(caso["sql_referencia"], hoje)
                try:
                    ok = mesmos_numeros(con.execute(ref_sql).fetchall(), con.execute(sql).fetchall())
                except sqlite3.Error as e:
                    ok, obtido = False, f"erro ao executar ({type(e).__name__})"
            elif esperado == "recusa":
                ok = obtido != "consulta"
            else:
                ok = obtido == esperado
        acertos += ok
        feitos += 1
        print(f"{'ACERTOU' if ok else 'ERROU  '}  {caso['id']:<22} esperado={esperado:<15} obtido={obtido}", flush=True)
        if args.detalhes:
            if motivo:
                print(f"         motivo: {motivo}", flush=True)
            if sql:
                print(f"         sql: {sql}", flush=True)

    print(f"\n{acertos}/{len(casos)} corretas")
    return 0 if acertos == len(casos) else 1


if __name__ == "__main__":
    raise SystemExit(main())
