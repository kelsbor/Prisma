"""Séries do Banco Central usadas pelo Agente de Indicadores (API pública SGS, sem chave).

Códigos conferidos no portal de dados abertos do BCB (dadosabertos.bcb.gov.br). Para acrescentar uma
série, basta uma nova entrada aqui.
"""

SERIES = {
    "selic": {"codigo": 432, "nome": "Taxa Selic (meta do Copom)", "unidade": "% ao ano", "grupo": "economia",
              "explicacao": "juro básico da economia; serve de referência para os outros juros"},
    "ipca_mes": {"codigo": 433, "nome": "Inflação (IPCA) no mês", "unidade": "% no mês", "grupo": "economia",
                 "explicacao": "quanto os preços subiram no mês"},
    "ipca_12m": {"codigo": 13522, "nome": "Inflação (IPCA) em 12 meses", "unidade": "% em 12 meses",
                 "grupo": "economia", "explicacao": "quanto os preços subiram no último ano"},
    "rotativo": {"codigo": 22022, "nome": "Juros do cartão de crédito rotativo", "unidade": "% ao ano",
                 "grupo": "credito", "par_mensal": "rotativo_mes",
                 "explicacao": "taxa média para pessoas físicas quando a fatura não é paga inteira"},
    "rotativo_mes": {"codigo": 25477, "nome": "Juros do cartão de crédito rotativo", "unidade": "% ao mês",
                     "grupo": "mensal", "explicacao": "a mesma taxa, ao mês"},
    "cheque_especial": {"codigo": 20741, "nome": "Juros do cheque especial", "unidade": "% ao ano",
                        "grupo": "credito", "par_mensal": "cheque_especial_mes",
                        "explicacao": "taxa média para pessoas físicas quando a conta fica no vermelho"},
    "cheque_especial_mes": {"codigo": 25463, "nome": "Juros do cheque especial", "unidade": "% ao mês",
                            "grupo": "mensal", "explicacao": "a mesma taxa, ao mês"},
    "credito_pessoal": {"codigo": 20748, "nome": "Juros do crédito pessoal", "unidade": "% ao ano",
                        "grupo": "credito", "explicacao": "taxa média do empréstimo pessoal (consignado e não consignado)"},
    "credito_pf_total": {"codigo": 20740, "nome": "Juros médios do crédito para pessoas físicas",
                         "unidade": "% ao ano", "grupo": "credito",
                         "explicacao": "média de todas as modalidades de crédito livre para pessoas físicas"},
}


def url_da_serie(codigo: int) -> str:
    return f"https://www3.bcb.gov.br/sgspub/consultarvalores/consultarValoresSeries.do?method=consultarGraficoPorId&hdOidSeriesSelecionadas={codigo}"
