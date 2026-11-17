"""Prisma · Orientador financeiro com CrewAI.

Um agente do CrewAI (com o Gemini) que usa os agentes do Prisma como ferramentas, via MCP:
  - Perfil Financeiro: perfil_financeiro, transacoes_atipicas, classificar_endividamento
  - Especialista:      buscar_conhecimento, consultar_transacoes
  - Indicadores:       juros_do_credito, indicador, simular_custo (API do Banco Central)

O CrewAI decide quais ferramentas chamar; os números continuam vindo dos agentes do Prisma.

Roda num ambiente separado (veja crew/requirements.txt), a partir da raiz do projeto:
    .venv-crew/bin/python crew/orientador.py --titular 000.000.000-00 --pergunta "Como saio do rotativo?"
    .venv-crew/bin/python crew/orientador.py --listar-ferramentas
"""

import argparse
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
os.environ.setdefault("OTEL_SDK_DISABLED", "true")           # sem telemetria do CrewAI
os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")

from crewai import Agent, Crew, Process, Task  # noqa: E402
from crewai.mcp import MCPServerStdio  # noqa: E402

# Python do projeto (onde estão os agentes do Prisma), não o do CrewAI
PY_PRISMA = RAIZ / (".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python")
FERRAMENTAS = {
    "perfil": {"perfil_financeiro", "transacoes_atipicas", "classificar_endividamento"},
    "especialista": {"buscar_conhecimento", "consultar_transacoes"},   # sem "perguntar": o CrewAI já escreve
    "indicadores": {"juros_do_credito", "indicador", "simular_custo"},
}


def _carregar_env():
    arquivo = RAIZ / ".env"
    if arquivo.exists():
        for linha in arquivo.read_text(encoding="utf-8").splitlines():
            if "=" in linha and not linha.strip().startswith("#"):
                k, v = linha.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def servidor(agente: str) -> MCPServerStdio:
    permitidas = FERRAMENTAS[agente]
    return MCPServerStdio(
        command=str(PY_PRISMA) if PY_PRISMA.exists() else sys.executable,
        args=["-m", agente],
        env={**os.environ, "PYTHONPATH": str(RAIZ)},
        tool_filter=lambda ferramenta: ferramenta.get("name") in permitidas,
    )


def montar(titular: str, pergunta: str) -> Crew:
    modelo = "gemini/" + os.getenv("PRISMA_MODELO_LLM", "gemini-2.5-flash")
    orientador = Agent(
        role="Orientador financeiro do Prisma",
        goal="Ajudar a pessoa a entender a própria situação financeira e a planejar o próximo passo.",
        backstory=("Você trabalha num app de bem-estar financeiro. Usa as ferramentas do Prisma para obter "
                   "números e conteúdos revisados, e explica com calma, sem julgar."),
        llm=modelo,
        mcps=[servidor("perfil"), servidor("especialista"), servidor("indicadores")],
        allow_delegation=False,
        verbose=True,
    )
    tarefa = Task(
        description=(
            f"Titular: {titular}. Pergunta da pessoa: {pergunta}\n\n"
            "Passos: 1) chame perfil_financeiro com o titular; 2) se ajudar, chame consultar_transacoes; "
            "3) busque o conceito com buscar_conhecimento; 4) para juros e inflação, use juros_do_credito ou "
            "simular_custo (dados do Banco Central); 5) responda.\n\n"
            "Regras: use SOMENTE números devolvidos pelas ferramentas; explique conceitos SOMENTE com os trechos "
            "de buscar_conhecimento, citando fonte e página; não recomende produtos financeiros; não julgue gastos; "
            "o score serve para o tom, não para ser repetido como nota; transações atípicas são perguntas, nunca "
            "acusações; a classificação de endividamento é uma estimativa, nunca diga à pessoa que ela está "
            "endividada com base nela."
        ),
        expected_output="Resposta curta em português do Brasil, com valores como R$ 1.234,56 e as fontes citadas.",
        agent=orientador,
    )
    return Crew(agents=[orientador], tasks=[tarefa], process=Process.sequential, memory=False, verbose=True)


def main():
    _carregar_env()
    ap = argparse.ArgumentParser(description="Orientador financeiro do Prisma com CrewAI")
    ap.add_argument("--titular", default="000.000.000-00")
    ap.add_argument("--pergunta", default="Como está minha situação financeira e por onde começo?")
    ap.add_argument("--listar-ferramentas", action="store_true", help="só mostra as ferramentas, sem chamar o LLM")
    args = ap.parse_args()

    if args.listar_ferramentas:
        a = Agent(role="teste", goal="teste", backstory="teste", llm="gemini/gemini-2.5-flash",
                  mcps=[servidor("perfil"), servidor("especialista"), servidor("indicadores")])
        for t in a.get_mcp_tools(a.mcps):
            print("-", t.name)
        return
    if not (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")):
        sys.exit("Defina GOOGLE_API_KEY no .env: o CrewAI precisa de um LLM para decidir as ferramentas.")
    resultado = montar(args.titular, args.pergunta).kickoff()
    print("\n" + "=" * 70 + "\n" + str(resultado))


if __name__ == "__main__":
    main()
