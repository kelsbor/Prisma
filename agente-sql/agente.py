
import json
import sqlite3
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

PASTA = Path(__file__).parent
CONFIG = json.loads((PASTA / "config.json").read_text(encoding="utf-8"))

TABELAS = """
transaction_fact (uma linha por transação)
- id, accountId (-> account_dim.id)
- dateEpochDay: dias desde 1970-01-01. NUNCA calcule esse número; filtre com as funções de data, ex.:
  strftime('%Y-%m', dateEpochDay * 86400, 'unixepoch') = '2026-11'
  date(dateEpochDay * 86400, 'unixepoch') BETWEEN '2026-10-01' AND '2026-10-15'
- description, merchantName (estabelecimento, pode ser nulo)
- amountCents: valor em CENTAVOS. Negativo = gasto/saída, positivo = entrada/estorno. Em reais: amountCents / 100.0
- status: 'POSTED' ou 'PENDING'
- pluggyCategoryId (-> category_dim.id), pluggyCategory (nome em inglês)
- installmentNumber, totalInstallments (parcelas, podem ser nulos)

account_dim (contas e cartões)
- id, itemId (-> item_dim.id), name, type ('BANK' = conta, 'CREDIT' = cartão)
- balanceCents: saldo da conta ou fatura do cartão, em centavos

item_dim (conexões/bancos): id, bankName, connectorName

category_dim (categorias): id, name (em português)
- ids hierárquicos: os 2 primeiros dígitos são o grupo ('11020000' pertence a '11000000')
- '05100000' = pagamento de fatura; ids começando com '03' (investimentos) ou '04'
  (transferência entre contas próprias) não são gastos nem entradas
"""

PROMPT_SQL = f"""Você escreve consultas SQLite para um app de finanças pessoais.
Responda SOMENTE com a consulta SQL. Sem explicação, sem markdown.

Tabelas do banco:
{TABELAS}"""

PROMPT_RESPOSTA = f"""Você é o assistente de um app de finanças pessoais.
O usuário fez uma pergunta, uma consulta SQL foi executada no banco dele e o resultado está abaixo.
Responda em português, de forma curta, usando só o resultado. Valores em reais no formato R$ 1.234,56.

Tabelas do banco:
{TABELAS}"""


def perguntar_ao_llm(sistema, mensagem):
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
        try:
            with urllib.request.urlopen(pedido, timeout=90) as resposta:
                dados = json.load(resposta)
            break
        except urllib.error.HTTPError as e:
            # 429/500/503 = Gemini sobrecarregado ou limite por minuto: espera e tenta de novo.
            if e.code in (429, 500, 503) and tentativa < 3:
                print(f"(Gemini ocupado, erro {e.code}; tentando de novo em {5 * (tentativa + 1)} s...)")
                time.sleep(5 * (tentativa + 1))
                continue
            raise RuntimeError(f"Erro {e.code} do Gemini: {e.read().decode(errors='replace')[:300]}")
    partes = dados["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in partes if not p.get("thought")).strip()


def limpar_sql(texto):
    # O modelo às vezes devolve o SQL dentro de ```sql ... ```
    return texto.replace("```sql", "").replace("```", "").strip()


def executar_sql(sql):
    caminho = (PASTA / CONFIG["banco"]).resolve()
    try:
        with sqlite3.connect(caminho.as_uri() + "?mode=ro", uri=True) as banco:
            cursor = banco.execute(sql)
            colunas = [c[0] for c in cursor.description or []]
            linhas = cursor.fetchmany(200)
        return json.dumps({"colunas": colunas, "linhas": linhas}, ensure_ascii=False, default=str)
    except sqlite3.Error as e:
        return f"ERRO ao executar: {e}"


def responder(pergunta):
    hoje = date.today().isoformat()

    sql = limpar_sql(perguntar_ao_llm(PROMPT_SQL, f"Data de hoje: {hoje}\nPergunta: {pergunta}"))
    print(f"\n[SQL] {sql}")

    resultado = executar_sql(sql)
    print(f"[Resultado] {resultado[:500]}")

    return perguntar_ao_llm(
        PROMPT_RESPOSTA,
        f"Data de hoje: {hoje}\nPergunta: {pergunta}\n\nSQL executado:\n{sql}\n\nResultado:\n{resultado}",
    )


def main():
    print("Pergunte sobre suas finanças (ENTER vazio para sair).")
    while pergunta := input("\nPergunta: ").strip():
        try:
            print(f"\n{responder(pergunta)}")
        except Exception as e:
            print(f"\nFalhou: {e}")


if __name__ == "__main__":
    main()
