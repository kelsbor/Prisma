"""Dados da pessoa, lidos do banco da Pluggy (o mesmo do PrismaAPP), somente leitura.

O banco é gerado pelo agente-sql (./prisma.sh pluggy) e tem a view vw_registers, a mesma que as telas
do app usam: valor_gasto já exclui transferências (fatura, mesma titularidade, investimentos) e
desconta estornos; valor_entrada só conta entradas em conta. As contas são feitas em SQL/Python,
nunca pelo Gemini.
"""

import sqlite3
from datetime import date

from comum.cliente_mcp import conectar
from comum.config import BANCO_APP


class SemDados(RuntimeError):
    pass


def _conectar() -> sqlite3.Connection:
    if not BANCO_APP.exists():
        raise SemDados(f"Banco da Pluggy não encontrado em {BANCO_APP}. Rode ./prisma.sh pluggy.")
    con = sqlite3.connect(f"file:{BANCO_APP}?mode=ro", uri=True)
    con.execute("PRAGMA query_only = 1")
    return con


def resumo(periodo: str | None = None, hoje: date | None = None) -> dict:
    """Resumo de um mês (AAAA-MM): entradas, gastos, saldo do mês, maiores categorias e contas.
    Sem período, usa o mês atual (até hoje). Parcelas futuras ficam de fora."""
    hoje = (hoje or date.today()).isoformat()
    periodo = periodo or hoje[:7]
    with _conectar() as con:
        meses = [r[0] for r in con.execute(
            "SELECT DISTINCT substr(data, 1, 7) FROM vw_registers WHERE data <= ? ORDER BY 1", (hoje,))]
        if not meses:
            raise SemDados("O banco da Pluggy não tem transações.")
        filtro = "substr(data, 1, 7) = ? AND data <= ?"
        entradas, gastos = con.execute(
            f"SELECT COALESCE(SUM(valor_entrada), 0), COALESCE(SUM(valor_gasto), 0) FROM vw_registers WHERE {filtro}",
            (periodo, hoje)).fetchone()
        categorias = con.execute(
            f"SELECT categoria, ROUND(SUM(valor_gasto), 2) AS total FROM vw_registers WHERE {filtro} "
            "GROUP BY categoria HAVING total > 0 ORDER BY total DESC LIMIT 8", (periodo, hoje)).fetchall()
        try:
            contas = con.execute(
                "SELECT trim(name), CASE type WHEN 'CREDIT' THEN 'cartão' ELSE 'conta' END, "
                "ROUND(balanceCents / 100.0, 2), ROUND(availableLimitCents / 100.0, 2) FROM account_dim").fetchall()
        except sqlite3.OperationalError:                  # banco copiado do celular, sem account_dim
            contas = []
    return {
        "periodo": periodo,
        "meses_com_dados": meses,
        "entradas": round(entradas, 2),
        "gastos": round(gastos, 2),
        "saldo_do_mes": round(entradas - gastos, 2),
        "maiores_gastos_por_categoria": [{"categoria": c, "total": t} for c, t in categorias],
        "contas": [{"conta": n, "tipo": tp, "saldo_ou_fatura": s, "limite_disponivel": lim}
                   for n, tp, s, lim in contas],
    }


async def indicadores() -> list[str]:
    """Taxas oficiais do Banco Central, pedidas ao Agente de Indicadores por MCP. Vazio se não der."""
    try:
        async with conectar("indicadores") as cliente:
            return (await cliente.chamar("juros_do_credito", {})).get("resumo", [])
    except Exception:
        return []
