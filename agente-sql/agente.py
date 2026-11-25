import json
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from contextlib import nullcontext
from datetime import date
from pathlib import Path

from metricas import MetricasExecucao

PASTA = Path(__file__).parent
CONFIG = json.loads((PASTA / "config.json").read_text(encoding="utf-8"))

TABELAS = """
Use SOMENTE estas fontes:
- vw_registers para tudo sobre transações (gastos, entradas, categorias, parcelas)
- account_dim (+ item_dim) só para saldo, fatura atual, limite e vencimento
Não use transaction_fact, category_dim nem category_override.

vw_registers
- transacao_id
- data: texto 'AAAA-MM-DD'. Filtre direto: data BETWEEN '2026-10-01' AND '2026-10-31'
- ano, mes: inteiros (ex.: ano = 2026 AND mes = 11)
- descricao, estabelecimento (pode ser nulo)
- valor: em reais, com sinal. Negativo = saída, positivo = entrada/estorno
- valor_centavos: o mesmo valor em centavos
- tipo: 'gasto', 'entrada', 'estorno' (crédito no cartão), 'transferencia' ou 'neutro'
  'transferencia' = pagamento de fatura, investimentos e transferências entre contas próprias;
  NUNCA conte como gasto nem como entrada
- valor_gasto: em reais, POSITIVO. Já exclui transferências e já desconta estornos do cartão
  (estorno aparece negativo). Total gasto = SUM(valor_gasto)
- valor_entrada: em reais, positivo, só entradas em conta (não transferências). Total recebido = SUM(valor_entrada)
- categoria_id, categoria (nome em português; 'Sem categoria' quando não há)
- grupo_categoria: categoria-mãe (ex.: 'Alimentação' para 'Delivery de alimentos')
- categoria_manual: 1 se o usuário recategorizou
- conta (nome da conta/cartão, igual a account_dim.name), tipo_conta: 'conta' ou 'cartao', banco
- pendente: 1 = ainda não lançada. Inclui PARCELAS FUTURAS do cartão (datas depois de hoje).
  Para "quanto gastei" use só datas até hoje; para "quanto vou pagar"/"parcelas futuras" use pendente = 1
- parcela, total_parcelas: número da parcela (podem ser nulos)

account_dim (uma linha por conta/cartão; situação ATUAL, não histórica)
- id, itemId (-> item_dim.id), name (pode ter espaços no fim: use trim(name))
- type: 'BANK' = conta, 'CREDIT' = cartão
- balanceCents: em CENTAVOS. Conta = saldo; cartão = valor da fatura atual. Em reais: balanceCents / 100.0
- creditLimitCents, availableLimitCents: limite total e disponível do cartão, em centavos (nulo em conta)
- balanceDueDateEpochDay: vencimento da fatura em dias desde 1970-01-01 (pode ser nulo);
  converta com date(balanceDueDateEpochDay * 86400, 'unixepoch')

item_dim (banco de cada conta): id, bankName. Nome do banco: JOIN item_dim i ON i.id = a.itemId
"""

EXEMPLOS = """
Exemplos (considerando hoje = 2026-11-25; use a data de hoje informada na pergunta):

Pergunta: quanto gastei esse mês?
SELECT '2026-11-01 a 2026-11-25' AS periodo, ROUND(SUM(valor_gasto), 2) AS total_gasto
FROM vw_registers WHERE data BETWEEN '2026-11-01' AND '2026-11-25'

Pergunta: onde mais gastei no mês passado?
SELECT categoria, ROUND(SUM(valor_gasto), 2) AS total_gasto FROM vw_registers
WHERE ano = 2026 AND mes = 10 GROUP BY categoria HAVING total_gasto > 0
ORDER BY total_gasto DESC LIMIT 10

Pergunta: quanto gastei com ifood em 2026?
SELECT ROUND(SUM(valor_gasto), 2) AS total_gasto, COUNT(*) AS compras FROM vw_registers
WHERE (descricao LIKE '%ifood%' OR estabelecimento LIKE '%ifood%')
AND data BETWEEN '2026-01-01' AND '2026-11-25'

Pergunta: quanto recebi por mês este ano?
SELECT ano, mes, ROUND(SUM(valor_entrada), 2) AS total_recebido FROM vw_registers
WHERE ano = 2026 AND data <= '2026-11-25' GROUP BY ano, mes ORDER BY ano, mes

Pergunta: quais parcelas ainda vou pagar?
SELECT data, descricao, parcela, total_parcelas, ROUND(-valor, 2) AS valor FROM vw_registers
WHERE data > '2026-11-25' AND tipo = 'gasto' ORDER BY data LIMIT 50

Pergunta: qual meu saldo e quanto tenho de limite?
SELECT trim(a.name) AS conta, CASE a.type WHEN 'CREDIT' THEN 'cartão' ELSE 'conta' END AS tipo,
ROUND(a.balanceCents / 100.0, 2) AS saldo_ou_fatura, ROUND(a.availableLimitCents / 100.0, 2) AS limite_disponivel
FROM account_dim a ORDER BY a.type

Pergunta: últimas compras no cartão platinum
SELECT data, descricao, ROUND(valor_gasto, 2) AS valor FROM vw_registers
WHERE conta = 'platinum' AND tipo = 'gasto' AND data <= '2026-11-25' ORDER BY data DESC LIMIT 50
"""

PROMPT_SQL = f"""Você escreve consultas SQLite para um app de finanças pessoais.
Responda SOMENTE com a consulta SQL. Sem explicação, sem markdown.

Fontes:
{TABELAS}
{EXEMPLOS}"""

PROMPT_RESPOSTA = """Você é o assistente de um app de finanças pessoais.
O usuário fez uma pergunta, uma consulta SQL foi executada no banco dele e o resultado está abaixo.

Como responder:
- Em português, curto e direto (1 a 3 frases; use lista só se houver vários itens).
- Use SOMENTE o resultado. Não invente valores nem faça contas que o resultado não sustenta.
- Valores em reais no formato R$ 1.234,56. Datas no formato DD/MM/AAAA.
- Diga o período considerado quando ele não estiver claro na pergunta.
- Resultado vazio ou total nulo: diga que não encontrou registros para aquilo.
- Resultado com ERRO: diga que não conseguiu consultar e sugira reformular a pergunta.
- Se "cortado_em_200" for true, avise que mostrou só parte."""


def log(mensagem):
    # Vai para o stderr: no servidor MCP (stdio) o stdout é reservado para o protocolo.
    print(mensagem, file=sys.stderr, flush=True)


def perguntar_ao_llm(sistema, mensagem, metricas=None):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{CONFIG['gemini_model']}:generateContent"
    corpo = {
        "systemInstruction": {"parts": [{"text": sistema}]},
        "contents": [{"role": "user", "parts": [{"text": mensagem}]}],
    }
    pedido = urllib.request.Request(
        url, data=json.dumps(corpo).encode(), method="POST",
        headers={"Content-Type": "application/json", "x-goog-api-key": CONFIG["gemini_api_key"]},
    )
    for tentativa in range(4):
        if metricas:
            metricas.registrar_tentativa_llm()
        try:
            with urllib.request.urlopen(pedido, timeout=90) as resposta:
                dados = json.load(resposta)
            if metricas:
                metricas.registrar_chamada_llm(dados.get("usageMetadata"))
            break
        except urllib.error.HTTPError as e:
            # 429/500/503 = Gemini sobrecarregado ou limite por minuto: espera e tenta de novo.
            if e.code in (429, 500, 503) and tentativa < 3:
                if metricas:
                    metricas.registrar_chamada_llm(None)
                log(f"(Gemini ocupado, erro {e.code}; tentando de novo em {5 * (tentativa + 1)} s...)")
                time.sleep(5 * (tentativa + 1))
                continue
            raise RuntimeError(f"Erro {e.code} do Gemini: {e.read().decode(errors='replace')[:300]}")
    partes = dados["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in partes if not p.get("thought")).strip()


def limpar_sql(texto):
    # O modelo às vezes devolve o SQL dentro de ```sql ... ```
    return texto.replace("```sql", "").replace("```", "").strip()


def executar_sql(sql, metricas=None):
    caminho = (PASTA / CONFIG["banco"]).resolve()
    with (metricas.etapa("execucao_sql_ms") if metricas else nullcontext()):
        try:
            banco = sqlite3.connect(caminho.as_uri() + "?mode=ro", uri=True)
            try:
                cursor = banco.execute(sql)
                colunas = [c[0] for c in cursor.description or []]
                linhas = cursor.fetchmany(201)
            finally:
                banco.close()
            resultado = {"colunas": colunas, "linhas": linhas[:200], "cortado_em_200": len(linhas) > 200}
            if metricas:
                metricas.registrar_resultado_sql(len(resultado["linhas"]), resultado["cortado_em_200"])
            return json.dumps(resultado, ensure_ascii=False, default=str)
        except sqlite3.Error as e:
            return f"ERRO ao executar: {e}"


def responder_detalhado(pergunta, hoje=None, log_detalhes=True):
    """Faz o fluxo completo e devolve resposta, SQL e dados (é o que o servidor MCP usa)."""
    hoje = hoje or date.today()
    metricas = MetricasExecucao()
    try:
        with metricas.etapa("geracao_sql_ms"):
            sql = limpar_sql(perguntar_ao_llm(
                PROMPT_SQL, f"Data de hoje: {hoje}\nPergunta: {pergunta}", metricas,
            ))
        if log_detalhes:
            log(f"\n[SQL] {sql}")

        resultado = executar_sql(sql, metricas)
        if log_detalhes:
            log(f"[Resultado] {resultado[:500]}")

        with metricas.etapa("geracao_resposta_ms"):
            resposta = perguntar_ao_llm(
                PROMPT_RESPOSTA,
                f"Data de hoje: {hoje:%d/%m/%Y}\nPergunta: {pergunta}\n\n"
                f"SQL executado:\n{sql}\n\nResultado:\n{resultado}",
                metricas,
            )
        dados = json.loads(resultado) if not resultado.startswith("ERRO") else {"erro": resultado}
    except Exception as erro:
        metricas.finalizar("falha", type(erro).__name__)
        raise
    metricas.finalizar("erro_sql" if resultado.startswith("ERRO") else "sucesso")
    return {"resposta": resposta, "sql": sql, "dados": dados}


def responder(pergunta):
    return responder_detalhado(pergunta)["resposta"]


def main():
    print("Pergunte sobre suas finanças (ENTER vazio para sair).")
    while pergunta := input("\nPergunta: ").strip():
        try:
            print(f"\n{responder(pergunta)}")
        except Exception as e:
            print(f"\nFalhou: {e}")


if __name__ == "__main__":
    main()
