"""Traduz as transações do Prisma (data, descrição, valor) para o formato da rede neural.

A rede (NeuralNetwork/) foi treinada com as categorias do gerador sintético. Aqui cada descrição do
extrato vira uma dessas categorias, com regras fixas em Python. Lançamentos que não existem no gerador
(fatura do cartão, saque, tarifa, juros) recebem categorias próprias: a rede não os pontua, mas eles
entram nos indicadores de risco.
"""

import re

# Categorias que a rede conhece (as do gerador sintético)
CATEGORIAS_DA_REDE = {
    "Assinaturas", "Combustível", "Compras", "Contas", "Educação", "Impostos", "Lazer", "Mercado",
    "Moradia", "Restaurantes e Delivery", "Saúde", "Telecom", "Transferências", "Transporte", "Viagem",
}
# Fora do modelo: não existem no sintético (lá as compras aparecem direto, sem a fatura do cartão)
FORA_DA_REDE = {"Fatura do cartão", "Saque", "Tarifas", "Juros e encargos", "Outros"}
# Dinheiro que só muda de lugar: não é renda nem gasto
INTERNAS = {"Investimentos"}

REGRAS = [  # (padrão na descrição, categoria se for saída, categoria se for entrada). Primeira que casar vence.
    (r"\bESTORNO\b", "Estorno", "Estorno"),
    (r"APLICACAO|RESGATE|\bCDB\b|POUPANCA|MESMA TITULARIDADE", "Investimentos", "Investimentos"),
    (r"\bJUROS\b|\bIOF\b|ENCARGO|CHEQUE ESPECIAL|ROTATIVO", "Juros e encargos", "Juros e encargos"),
    (r"\bTARIFA\b|ANUIDADE|PACOTE SERVICOS", "Tarifas", "Tarifas"),
    (r"PAGTO FATURA|PAGAMENTO FATURA|FATURA CARTAO", "Fatura do cartão", "Fatura do cartão"),
    (r"\bSAQUE\b", "Saque", "Saque"),
    (r"SALARIO|PROVENTOS|PIX RECEBIDO.*CLIENTE|TED RECEBIDA.*CLIENTE|FREELA", "Transferências", "Renda"),
    (r"PIX RECEBIDO|TED RECEBIDA|TRANSF RECEBIDA", "Transferências", "Transferências"),
    (r"IFOOD|IFOD|RAPPI|DELIVERY|RESTAURANTE|LANCHONETE|PADARIA|BURGER|MCDONALDS|STARBUCKS", "Restaurantes e Delivery", "Estorno"),
    (r"SUPERMERC|MERCADO(?! LIVRE)|HORTIFRUTI|ATACAD|ACOUGUE|FEIRA", "Mercado", "Estorno"),
    (r"POSTO|COMBUST", "Combustível", "Estorno"),
    (r"\bUBER|\b99\b|CABIFY|METRO|BILHETE|ESTACIONAMENTO|PEDAGIO|RIOCARD", "Transporte", "Estorno"),
    (r"DROGARIA|DROGA |FARMACIA|CLINICA|LABORATORIO|DENTISTA|HOSPITAL|ACADEMIA", "Saúde", "Estorno"),
    (r"NETFLIX|SPOTIFY|PRIME|DISNEY|HBO|GLOBOPLAY|YOUTUBE|ICLOUD|DEEZER", "Assinaturas", "Estorno"),
    (r"ENERGIA|ENEL|\bAGUA\b|SANEAMENTO|SABESP|\bGAS\b|\bLUZ\b", "Contas", "Estorno"),
    (r"RECARGA|CELULAR|TELEFON|INTERNET|\bVIVO\b|\bTIM\b|\bCLARO\b|\bOI\b", "Telecom", "Estorno"),
    (r"IMOBILIARIA|ALUGUEL|CONDOMINIO|FINANCIAMENTO IMOB", "Moradia", "Estorno"),
    (r"\bIPVA\b|\bIPTU\b|\bDARF\b|IMPOSTO|DETRAN", "Impostos", "Estorno"),
    (r"FACULDADE|ESCOLA|CURSO|MENSALIDADE", "Educação", "Estorno"),
    (r"HOTEL|POUSADA|AIRBNB|PASSAGEM|LATAM|\bGOL\b|\bAZUL\b|DECOLAR", "Viagem", "Estorno"),
    (r"CINEMA|CINEMARK|INGRESSO|SHOW|STEAM|PLAYSTATION|\bBAR\b|LIVRARIA", "Lazer", "Estorno"),
    (r"\bLOJA\b|AMAZON|AMZN|MERCADO LIVRE|\bMP\*|SHOPEE|MAGAZINE|AMERICANAS|SHEIN|KABUM|RENNER", "Compras", "Estorno"),
    (r"PIX ENVIADO|TED ENVIADA|TRANSF", "Transferências", "Transferências"),
]
_REGRAS = [(re.compile(p), saida, entrada) for p, saida, entrada in REGRAS]

_PREFIXOS = re.compile(r"^(COMPRA CARTAO DEB|COMPRA CARTAO|COMPRA DEB|DEB AUT|PIX ENVIADO -|PIX RECEBIDO -|"
                       r"TED ENVIADA -|PAG\*|DL\*|MP\*)\s*")


def categorizar(descricao: str, valor: float) -> str:
    d = (descricao or "").upper()
    for padrao, saida, entrada in _REGRAS:
        if padrao.search(d):
            return saida if valor < 0 else entrada
    return "Outros" if valor < 0 else "Transferências"


def estabelecimento(descricao: str) -> str:
    """Nome do estabelecimento sem prefixos do banco nem códigos ("SPOTIFY P1A2B3C4" -> "SPOTIFY")."""
    d = _PREFIXOS.sub("", (descricao or "").upper().strip())
    d = re.sub(r"\s+(?=[A-Z0-9]*\d)[A-Z0-9]{6,}$", "", d)        # código no fim, com dígitos
    return re.sub(r"\s+", " ", d).strip() or "DESCONHECIDO"
