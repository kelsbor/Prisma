"""
main.py  -  Junta tudo: 2 agentes + armazenamento compartilhado + orquestrador.

    Coletor  (determinístico, sem LLM)  ->  grava transações no armazenamento
    Analista (com LLM + ferramentas)    ->  lê do armazenamento e explica os gastos

Os agentes NÃO conversam diretamente: o ponto de encontro é o armazenamento (o agente-simples
do Prisma). O orquestrador só decide a ordem. É o jeito mais simples de "2 agentes trabalhando juntos".

Rodar:   python main.py
Sem chave de API configurada, usa o LLM falso (modo aula) e mostra o laço funcionando.
"""

import os

from agente import Agente
from ferramentas import criar_armazenamento, ferramentas_do_analista
from llm import LLM, LLMFalso
from memoria import MemoriaCurtoPrazo, MemoriaLongoPrazo

TITULAR_ID = "000.000.000-00"      # sempre fictício em testes

# Dados FICTÍCIOS. No projeto real, viriam do notebook coletor (extratos CSV/PDF/imagem).
EXTRATO_FICTICIO = [
    {"data": "2026-08-01", "descricao": "SALARIO", "valor": 3000.00},
    {"data": "2026-08-02", "descricao": "MERCADO BOM PRECO", "valor": -150.75},
    {"data": "2026-08-03", "descricao": "PAG*IFOOD", "valor": -48.70},
    {"data": "2026-08-04", "descricao": "UBER* TRIP", "valor": -23.90},
    {"data": "2026-08-05", "descricao": "NETFLIX.COM", "valor": -39.90},
    {"data": "2026-08-06", "descricao": "FARMACIA SAO JOAO", "valor": -62.30},   # sem regra
    {"data": "2026-08-07", "descricao": "MERCADO BOM PRECO", "valor": -210.10},
    {"data": "2026-08-08", "descricao": "PIX TESTE", "valor": -0.01},            # sem regra
]

# Base de conhecimento (aqui, só texto). Cresceu demais? Aí vale buscar só o trecho relevante (RAG).
CONHECIMENTO = """Categorias permitidas: alimentacao, transporte, lazer, saude, renda, outros.
Regra 50/30/20: 50% necessidades, 30% desejos, 20% poupança/dívidas (referência didática, não é regra fixa).
Valores abaixo de R$ 1,00 podem ser testes e devem ser mencionados, nunca descartados."""

INSTRUCOES_ANALISTA = """Você é o Analista do Prisma, um assistente de educação financeira.
Regras:
1. NUNCA faça contas de cabeça. Para qualquer soma ou total, use a ferramenta totais_por_categoria.
2. Explique de forma simples para onde o dinheiro foi, citando os números que as ferramentas devolveram.
3. Quem decide o que cortar é o usuário: você sugere e explica o porquê, sem ordenar.
4. Se uma ferramenta devolver erro, diga isso com clareza em vez de inventar números.
Responda em português do Brasil."""


# ---------------------------------------------------------------- Agente 1: Coletor
REGRAS_DE_CATEGORIA = {          # regras simples: palavra-chave -> categoria
    "mercado": "alimentacao", "ifood": "alimentacao",
    "uber": "transporte", "netflix": "lazer", "salario": "renda",
}


def coletor(armazenamento, titular_id, extrato):
    """Agente reativo simples: percebe uma transação, aplica regra fixa, grava. Sem LLM."""
    for t in extrato:
        categoria = next((c for palavra, c in REGRAS_DE_CATEGORIA.items()
                          if palavra in t["descricao"].lower()), None)
        armazenamento.chamar("salvar_transacao", {
            "titular_id": titular_id,
            "dados": {**t, "moeda": "BRL", "categoria": categoria},
        })
    print(f"[Coletor] {len(extrato)} transações gravadas.")


# ---------------------------------------------------------------- LLM: real ou falso
def escolher_llm():
    provedor = os.getenv("LLM_PROVIDER", "groq")
    chave_env = "GROQ_API_KEY" if provedor == "groq" else "GEMINI_API_KEY"
    if os.getenv(chave_env):
        print(f"[LLM] usando {provedor}")
        return LLM(provedor)
    print("[LLM] nenhuma chave encontrada: usando LLM FALSO (modo aula)")
    return LLMFalso()


# ---------------------------------------------------------------- Orquestrador
def main():
    armazenamento = criar_armazenamento()
    contexto = {"titular_id": TITULAR_ID}          # controlado pelo código, não pelo modelo

    # 1) Coletor trabalha
    coletor(armazenamento, TITULAR_ID, EXTRATO_FICTICIO)

    # 2) Analista trabalha, lendo o que o Coletor gravou
    analista = Agente(
        nome="Analista",
        instrucoes=INSTRUCOES_ANALISTA,
        conhecimento=CONHECIMENTO,
        llm=escolher_llm(),
        ferramentas=ferramentas_do_analista(armazenamento, contexto),
        memoria=MemoriaCurtoPrazo(max_mensagens=30),
        memoria_longa=MemoriaLongoPrazo("memoria_longo_prazo.json"),
    )

    print("\n--- Pergunta 1 ---")
    print(analista.executar("Para onde foi meu dinheiro neste período?"))

    # A memória de curto prazo continua: o modelo "lembra" da pergunta anterior porque
    # o histórico foi reenviado junto.
    print("\n--- Pergunta 2 (usa o histórico da primeira) ---")
    print(analista.executar("E quais lançamentos ficaram sem categoria?"))

    print(f"\n[Trilha de auditoria] {len(analista.trilha)} eventos registrados em analista.trilha")


if __name__ == "__main__":
    main()