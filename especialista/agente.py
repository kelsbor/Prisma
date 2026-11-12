"""Responde perguntas juntando a RAG (conceitos) e o resumo do mês (números), com o Gemini escrevendo o texto.

Regra de ouro: os números vêm do Armazenamento e do Python; o Gemini só escreve.
"""

import os

from especialista import rag

MODELO_LLM = os.getenv("PRISMA_MODELO_LLM", "gemini-3.5-flash-lite")
NOTA_MINIMA = float(os.getenv("PRISMA_NOTA_MINIMA", "0.5"))

PROMPT = """Você é o especialista financeiro do Prisma, um app de bem-estar financeiro. Ajude a pessoa a planejar; a decisão é sempre dela.

Regras:
- Use SOMENTE os números de DADOS DO USUÁRIO. Nunca invente valores.
- Para explicar conceitos, use SOMENTE os TRECHOS DE REFERÊNCIA. Se eles não cobrirem a pergunta, diga que ainda não tem um conteúdo revisado sobre isso.
- Cite a fonte e a página dos trechos que usar, como (fonte, p. N).
- Se dois trechos se contradizem, siga as "Atualizações da equipe" do Prisma, que corrigem materiais antigos, e não repita a informação desatualizada.
- Materiais antigos podem estar desatualizados: se um trecho falar de regra ou lei com data, avise que vale conferir se ainda está em vigor.
- Não recomende produtos financeiros específicos (ações, fundos, bancos). Não julgue gastos.
- O perfil_de_risco (0 a 100) serve para escolher o tom, não para ser repetido como nota. Se a faixa for "alto", comece acolhendo, sem tom de alarme, e priorize um passo pequeno e possível.
- Transações atípicas são perguntas, nunca acusações ("essa compra repetida foi você mesmo?").
- Responda em português do Brasil, curto, com valores como R$ 1.234,56.

## DADOS DO USUÁRIO
{dados}

## TRECHOS DE REFERÊNCIA
{trechos}

## PERGUNTA
{pergunta}
"""


def perguntar(pergunta: str, resumo_mes: dict | None = None) -> dict:
    try:
        todos = rag.buscar(pergunta)
        trechos = [t for t in todos if t["nota"] >= NOTA_MINIMA]
    except Exception as e:
        return {"resposta": f"A base de conhecimento não está disponível: {e}", "fontes": [], "gerado_por": "erro"}

    texto_trechos = "\n\n".join(f"[{t['fonte']}, p. {t['pagina']}] {t['texto']}" for t in trechos) or "(nenhum trecho relevante)"
    fontes = sorted({f"{t['fonte']}, p. {t['pagina']}" for t in trechos})
    try:
        if not os.getenv("GOOGLE_API_KEY"):
            raise RuntimeError("GOOGLE_API_KEY não definida")
        from langchain_google_genai import ChatGoogleGenerativeAI
        llm = ChatGoogleGenerativeAI(model=MODELO_LLM)
        resposta = llm.invoke(PROMPT.format(dados=resumo_mes or "(não informados)",
                                            trechos=texto_trechos, pergunta=pergunta))
        return {"resposta": str(resposta.text), "fontes": fontes, "gerado_por": "gemini"}
    except Exception as e:  # sem chave, sem internet, cota esgotada: devolve os trechos para a pessoa ler
        return {"resposta": "Não consegui gerar a resposta agora. Estes são os trechos mais próximos da sua pergunta.",
                "trechos": trechos or todos,   # sem Gemini, mostra os mais próximos mesmo abaixo da nota mínima
                "fontes": fontes or sorted({f"{t['fonte']}, p. {t['pagina']}" for t in todos}),
                "gerado_por": f"sem Gemini ({e})"}
