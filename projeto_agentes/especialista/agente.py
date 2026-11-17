"""Responde perguntas juntando a RAG (conceitos) e o resumo do mês (números), com o Gemini escrevendo o texto.

Regra de ouro: os números vêm do Armazenamento e do Python; o Gemini só escreve.
"""

import os
import time

from especialista import log_prompts, rag

MODELO_LLM = os.getenv("PRISMA_MODELO_LLM", "gemini-3.5-flash-lite")
NOTA_MINIMA = float(os.getenv("PRISMA_NOTA_MINIMA", "0.5"))

PROMPT = """Você é o especialista financeiro do Prisma, um app de bem-estar financeiro. Ajude a pessoa a planejar; a decisão é sempre dela.

Regras:
- Use SOMENTE os números de DADOS DO USUÁRIO e de INDICADORES DO BANCO CENTRAL. Nunca invente valores.
- Para taxas de mercado (juros médios, Selic, inflação), use os INDICADORES DO BANCO CENTRAL, diga que são médias e cite "Banco Central" com o mês de referência.
- Para explicar conceitos, use SOMENTE os TRECHOS DE REFERÊNCIA. Se eles não cobrirem a pergunta, diga que ainda não tem um conteúdo revisado sobre isso.
- Cite a fonte e a página dos trechos que usar, como (fonte, p. N).
- Se dois trechos se contradizem, siga as "Atualizações da equipe" do Prisma, que corrigem materiais antigos, e não repita a informação desatualizada.
- Materiais antigos podem estar desatualizados: se um trecho falar de regra ou lei com data, avise que vale conferir se ainda está em vigor.
- Não recomende produtos financeiros específicos (ações, fundos, bancos). Não julgue gastos.
- O score do perfil_financeiro (risco de endividamento, de 0 a 100) serve para escolher o tom, não para ser repetido como nota. Se a faixa for "alto", comece acolhendo, sem tom de alarme, e priorize um passo pequeno e possível.
- Transações atípicas são perguntas, nunca acusações ("essa compra repetida foi você mesmo?").
- Responda em português do Brasil, curto, com valores como R$ 1.234,56.

## DADOS DO USUÁRIO
{dados}

## INDICADORES DO BANCO CENTRAL
{indicadores}

## TRECHOS DE REFERÊNCIA
{trechos}

## PERGUNTA
{pergunta}
"""


def perguntar(pergunta: str, resumo_mes: dict | None = None, indicadores: list[str] | None = None) -> dict:
    inicio = time.monotonic()
    try:
        todos = rag.buscar(pergunta)
        trechos = [t for t in todos if t["nota"] >= NOTA_MINIMA]
    except Exception as e:
        saida = {"resposta": f"A base de conhecimento não está disponível: {e}", "fontes": [], "gerado_por": "erro"}
        log_prompts.registrar({"pergunta": pergunta, "prompt": None, "gerado_por": "erro", "erro": str(e)})
        return saida

    texto_trechos = "\n\n".join(f"[{t['fonte']}, p. {t['pagina']}] {t['texto']}" for t in trechos) or "(nenhum trecho relevante)"
    fontes = sorted({f"{t['fonte']}, p. {t['pagina']}" for t in trechos})
    prompt = PROMPT.format(dados=resumo_mes or "(não informados)", trechos=texto_trechos, pergunta=pergunta,
                           indicadores="\n".join(indicadores or []) or "(indisponíveis)")
    try:
        if not os.getenv("GOOGLE_API_KEY"):
            raise RuntimeError("GOOGLE_API_KEY não definida")
        from langchain_google_genai import ChatGoogleGenerativeAI
        llm = ChatGoogleGenerativeAI(model=MODELO_LLM)
        resposta = llm.invoke(prompt)
        saida = {"resposta": str(resposta.text), "fontes": fontes, "gerado_por": "gemini"}
    except Exception as e:  # sem chave, sem internet, cota esgotada: devolve os trechos para a pessoa ler
        saida = {"resposta": "Não consegui gerar a resposta agora. Estes são os trechos mais próximos da sua pergunta.",
                 "trechos": trechos or todos,   # sem Gemini, mostra os mais próximos mesmo abaixo da nota mínima
                 "fontes": fontes or sorted({f"{t['fonte']}, p. {t['pagina']}" for t in todos}),
                 "gerado_por": f"sem Gemini ({e})"}

    log_prompts.registrar({
        "pergunta": pergunta,
        "modelo": MODELO_LLM,
        "enviado_ao_gemini": saida["gerado_por"] == "gemini",
        "nota_minima": NOTA_MINIMA,
        "trechos": [{"fonte": t["fonte"], "pagina": t["pagina"], "nota": t["nota"],
                     "usado": t["nota"] >= NOTA_MINIMA} for t in todos],
        "prompt": prompt,
        "resposta": saida["resposta"],
        "gerado_por": saida["gerado_por"],
        "segundos": round(time.monotonic() - inicio, 2),
    })
    return saida
