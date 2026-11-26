"""Barreiras do orquestrador.

1. Entrada (sem LLM): normaliza a pergunta, bloqueia tentativas óbvias de manipulação e detecta
   sinais de sofrimento intenso, que recebem o contato do CVV antes de qualquer outra coisa.
2. Escopo (com LLM, no grafo): só finanças. As mensagens fixas de recusa ficam aqui.
3. Saída (o guardião, único para todos os agentes): todo valor em R$ e todo percentual de cada resposta
   precisa estar nas evidências (linhas do SQL, dados do Banco Central, trechos da base, resumo do mês)
   ou na pergunta. Senão, o texto é descartado e a pessoa recebe os dados.
"""

import re
import unicodedata
from decimal import ROUND_HALF_UP, Decimal

MAX_PERGUNTA = 500

MSG_BLOQUEADO = ("Não posso atender esse pedido. Posso ajudar com os seus gastos e entradas, saldo e cartões, "
                 "conceitos de educação financeira e indicadores como Selic, inflação e juros.")
MSG_LONGA = f"A mensagem é longa demais (máximo de {MAX_PERGUNTA} caracteres). Tente resumir a pergunta."
MSG_FORA_DO_ESCOPO = ("Eu sou o assistente financeiro do Prisma e só consigo ajudar com finanças: os seus gastos "
                      "e entradas, saldo, fatura e limite dos cartões, conceitos de educação financeira e "
                      "indicadores do Banco Central, como Selic, inflação e juros. Quer perguntar algo sobre isso?")
MSG_CONVERSA = ("Estou por aqui! Posso responder sobre os seus gastos e entradas, saldo, fatura e limite dos "
                "cartões, explicar conceitos de finanças ou trazer juros, Selic e inflação do Banco Central.")
MSG_APOIO = ("Sinto muito que você esteja passando por isso. Você não precisa enfrentar esse momento sem apoio: "
             "o CVV (Centro de Valorização da Vida) atende de graça, 24 horas, pelo telefone 188 ou pelo chat em "
             "cvv.org.br. Em emergência, ligue 192 (SAMU). Quando quiser, também posso ajudar a olhar as suas "
             "finanças com calma, um passo de cada vez.")

_TENTATIVAS = [re.compile(p, re.IGNORECASE | re.DOTALL) for p in (
    r"\bignor[ea]\b.{0,40}\b(instru|regra|anterior|acima)",
    r"\b(esque[cç]a|desconsidere)\b.{0,40}\b(instru|regra|anterior|acima)",
    r"\b(prompt|instru[cç][oõ]es)\s+(do\s+)?(sistema|system)\b",
    r"\bsystem\s+prompt\b",
    r"\bjailbreak\b",
    r"\bmodo\s+(desenvolvedor|developer|dan)\b",
    r"\b(drop|delete|insert|update|alter|attach|pragma|truncate)\s+(table|from|into|database|\w+\s+set)\b",
    r";\s*(select|drop|delete|insert|update|with)\b",
)]

# Sinais claros de risco: resposta fixa com o CVV, sem depender do LLM.
_SOFRIMENTO = [re.compile(p, re.IGNORECASE) for p in (
    r"\bsuic[ií]d",
    r"\bme\s+matar\b",
    r"\btirar\s+(a\s+)?minha\s+(pr[oó]pria\s+)?vida\b",
    r"\b(quero|vou)\s+morrer\b",
    r"\bn[aã]o\s+(aguento|quero)\s+mais\s+viver\b",
    r"\bacabar\s+com\s+(a\s+)?minha\s+vida\b",
)]


def normalizar(pergunta: str) -> str:
    texto = unicodedata.normalize("NFKC", pergunta or "")
    return "".join(c for c in re.sub(r"\s+", " ", texto) if c.isprintable()).strip()


def verificar_entrada(pergunta: str) -> tuple[str, str | None, str | None]:
    """Devolve (texto, rota, mensagem). rota None = pode seguir para o classificador;
    "bloqueado" ou "apoio" = responder já com a mensagem."""
    texto = normalizar(pergunta)
    if any(r.search(texto) for r in _SOFRIMENTO):
        return texto, "apoio", MSG_APOIO
    if not texto:
        return texto, "bloqueado", MSG_BLOQUEADO
    if len(texto) > MAX_PERGUNTA:
        return texto, "bloqueado", MSG_LONGA
    if any(r.search(texto) for r in _TENTATIVAS):
        return texto, "bloqueado", MSG_BLOQUEADO
    return texto, None, None


# ------------------------------------------------------------------ saída: o guardião
# Todo valor em R$ e todo percentual de uma resposta precisa estar nas evidências (os dados de onde
# a resposta deveria ter saído) ou na pergunta. Arredondar vale; inventar ou calcular não.
_DINHEIRO = re.compile(r"R\$\s?-?\s?(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{1,2}))?")
_PERCENTUAL = re.compile(r"(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d+))?\s?%")


def _citados(texto: str) -> list[tuple[Decimal, int]]:
    """(valor, casas decimais escritas) de cada R$ e % do texto."""
    saida = []
    for padrao in (_DINHEIRO, _PERCENTUAL):
        for m in padrao.finditer(texto or ""):
            casas = len(m[2] or "")
            saida.append((Decimal(f"{m[1].replace('.', '')}.{m[2] or '0'}"), casas))
    return saida


def coletar_evidencias(*fontes) -> set[Decimal]:
    """Todos os números das evidências: valores soltos (inteiros também como centavos), e os R$ e %
    escritos em textos (trechos da base, respostas do Banco Central)."""
    numeros: set[Decimal] = set()

    def visitar(x):
        if isinstance(x, bool) or x is None:
            return
        if isinstance(x, (int, float)):
            v = Decimal(str(x)).copy_abs()
            numeros.add(v)
            if isinstance(x, int):
                numeros.add(v / 100)
        elif isinstance(x, str):
            numeros.update(v for v, _ in _citados(x))
        elif isinstance(x, dict):
            for valor in x.values():
                visitar(valor)
        elif isinstance(x, (list, tuple, set)):
            for item in x:
                visitar(item)

    for f in fontes:
        visitar(f)
    return numeros


def fundamentado(texto: str, evidencias: set[Decimal]) -> bool:
    arredondados: dict[int, set[Decimal]] = {}
    for valor, casas in _citados(texto):
        if casas not in arredondados:
            passo = Decimal(1).scaleb(-casas)
            arredondados[casas] = {e.quantize(passo, ROUND_HALF_UP) for e in evidencias}
        if valor.quantize(Decimal(1).scaleb(-casas)) not in arredondados[casas]:
            return False
    return True
