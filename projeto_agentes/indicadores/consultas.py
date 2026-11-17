"""O que o Agente de Indicadores responde. Todas as contas são feitas aqui, em Python."""

from datetime import date

from indicadores import bcb
from indicadores.series import SERIES, url_da_serie

MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
TETO_ROTATIVO = 1.0      # Lei 14.690/2023: juros e encargos do rotativo limitados a 100% do valor original


def _pct(v: float) -> str:
    return f"{v:,.2f}%".replace(",", "X").replace(".", ",").replace("X", ".")


def _brl(v: float) -> str:
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _referencia(nome: str, data_iso: str) -> str:
    d = date.fromisoformat(data_iso)
    return d.strftime("%d/%m/%Y") if nome == "selic" else f"{MESES[d.month - 1]}/{d.year}"


def indicador(nome: str) -> dict:
    if nome not in SERIES:
        raise ValueError(f"Indicador desconhecido: {nome}. Opções: {', '.join(SERIES)}")
    s = SERIES[nome]
    r = bcb.ultimos(s["codigo"], 1)
    p = r["pontos"][-1]
    saida = {"indicador": nome, "nome": s["nome"], "valor": p["valor"], "unidade": s["unidade"],
             "texto": f"{s['nome']}: {_pct(p['valor'])} {s['unidade'].removeprefix('% ')}",
             "referencia": _referencia(nome, p["data"]), "explicacao": s["explicacao"],
             "fonte": f"Banco Central do Brasil, série SGS {s['codigo']}", "url": url_da_serie(s["codigo"]),
             "origem": r["origem"], "consultado_em": r["consultado_em"]}
    if "aviso" in r:
        saida["aviso"] = r["aviso"]
    return saida


def _seguro(nome):
    try:
        return indicador(nome)
    except Exception as e:
        return {"indicador": nome, "erro": str(e)}


def juros_do_credito() -> dict:
    """Juros médios das modalidades de crédito para pessoas físicas, comparados com a Selic."""
    selic = _seguro("selic")
    modalidades = []
    for nome, s in SERIES.items():
        if s["grupo"] != "credito":
            continue
        a = _seguro(nome)
        if "erro" in a:
            modalidades.append(a)
            continue
        item = {"modalidade": s["nome"].removeprefix("Juros do ").removeprefix("Juros médios do "),
                "ao_ano": a["valor"], "referencia": a["referencia"], "fonte": a["fonte"]}
        if s.get("par_mensal"):
            m = _seguro(s["par_mensal"])
            if "erro" not in m:
                item["ao_mes"] = m["valor"]
        if "erro" not in selic and selic["valor"] > 0:
            item["vezes_a_selic"] = round(a["valor"] / selic["valor"], 1)
        modalidades.append(item)
    linhas = [f"{m['modalidade']}: {_pct(m['ao_ano'])} ao ano" + (f" ({_pct(m['ao_mes'])} ao mês)" if "ao_mes" in m else "")
              + f", {m['referencia']}" for m in modalidades if "ao_ano" in m]
    if "erro" not in selic:
        linhas.append(f"Selic: {_pct(selic['valor'])} ao ano, {selic['referencia']}")
    return {"modalidades": modalidades, "selic": selic, "resumo": linhas,
            "fonte": "Banco Central do Brasil (estatísticas de crédito, taxas médias de novas operações)"}


def simular(valor: float, modalidade: str, meses: int) -> dict:
    """Quanto custaria deixar `valor` numa modalidade por `meses`, com a taxa média do mercado."""
    if modalidade not in ("rotativo", "cheque_especial", "credito_pessoal"):
        raise ValueError("modalidade deve ser rotativo, cheque_especial ou credito_pessoal")
    if valor <= 0 or not 1 <= meses <= 60:
        raise ValueError("valor deve ser positivo e meses entre 1 e 60")
    s = SERIES[modalidade]
    if s.get("par_mensal"):
        base = indicador(s["par_mensal"])
        taxa_mes = base["valor"] / 100
    else:
        base = indicador(modalidade)
        taxa_mes = (1 + base["valor"] / 100) ** (1 / 12) - 1
    juros = valor * ((1 + taxa_mes) ** meses - 1)
    teto_aplicado = False
    if modalidade == "rotativo" and juros > valor * TETO_ROTATIVO:
        juros, teto_aplicado = valor * TETO_ROTATIVO, True
    total = valor + juros
    texto = (f"{_brl(valor)} no {s['nome'].removeprefix('Juros do ').lower()} por {meses} "
             f"{'mês' if meses == 1 else 'meses'} viram cerca de {_brl(total)} ({_brl(juros)} de juros), "
             f"com a taxa média de {_pct(taxa_mes * 100)} ao mês ({base['referencia']}).")
    if teto_aplicado:
        texto += " Os juros pararam em 100% do valor original por causa do teto legal do rotativo."
    return {"valor": valor, "modalidade": modalidade, "meses": meses, "taxa_mensal": round(taxa_mes * 100, 2),
            "juros": round(juros, 2), "total": round(total, 2), "teto_aplicado": teto_aplicado, "texto": texto,
            "fonte": base["fonte"], "referencia": base["referencia"],
            "observacao": "Estimativa com a taxa média do mercado; a taxa real está no contrato ou na fatura e "
                          "pode ser diferente. Não inclui IOF nem tarifas."}


def historico(nome: str, n: int = 12) -> dict:
    if nome not in SERIES:
        raise ValueError(f"Indicador desconhecido: {nome}. Opções: {', '.join(SERIES)}")
    s = SERIES[nome]
    r = bcb.ultimos(s["codigo"], max(1, min(n, 60)))
    return {"indicador": nome, "nome": s["nome"], "unidade": s["unidade"], "fonte": f"Banco Central do Brasil, série SGS {s['codigo']}",
            "pontos": [{"referencia": _referencia(nome, p["data"]), "valor": p["valor"]} for p in r["pontos"]],
            "origem": r["origem"]}

