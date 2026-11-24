"""Baixa os dados da Pluggy e grava no banco SQLite (mesmas tabelas do app)."""
import json
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

PASTA = Path(__file__).parent
CONFIG = json.loads((PASTA / "config.json").read_text(encoding="utf-8"))
API = "https://api.pluggy.ai"
BRASILIA = timezone(timedelta(hours=-3))

TABELAS = """
CREATE TABLE IF NOT EXISTS item_dim (
    id TEXT PRIMARY KEY, connectorName TEXT, connectorImageUrl TEXT, status TEXT,
    executionStatus TEXT, lastUpdatedAt INTEGER, nextAutoSyncAt INTEGER, consentExpiresAt INTEGER,
    errorCode TEXT, lastSyncAt INTEGER, bankName TEXT);
CREATE TABLE IF NOT EXISTS account_dim (
    id TEXT PRIMARY KEY, itemId TEXT NOT NULL, type TEXT NOT NULL, subtype TEXT, name TEXT NOT NULL,
    numberMasked TEXT, balanceCents INTEGER NOT NULL, currencyCode TEXT NOT NULL,
    creditLimitCents INTEGER, availableLimitCents INTEGER, balanceDueDateEpochDay INTEGER);
CREATE TABLE IF NOT EXISTS transaction_fact (
    id TEXT PRIMARY KEY, accountId TEXT NOT NULL, dateEpochDay INTEGER NOT NULL, dateTimeMillis INTEGER NOT NULL,
    description TEXT NOT NULL, descriptionRaw TEXT, amountCents INTEGER NOT NULL, rawAmountCents INTEGER NOT NULL,
    currencyCode TEXT NOT NULL, type TEXT NOT NULL, status TEXT NOT NULL, pluggyCategoryId TEXT,
    pluggyCategory TEXT, merchantName TEXT, installmentNumber INTEGER, totalInstallments INTEGER,
    updatedAtMillis INTEGER);
CREATE TABLE IF NOT EXISTS category_dim (id TEXT PRIMARY KEY, name TEXT NOT NULL, originalName TEXT);
"""


def chamar(metodo, caminho, api_key=None, corpo=None):
    cabecalhos = {"Content-Type": "application/json", "Accept": "application/json"}
    if api_key:
        cabecalhos["X-API-KEY"] = api_key
    dados = json.dumps(corpo).encode() if corpo is not None else None
    pedido = urllib.request.Request(API + caminho, data=dados, headers=cabecalhos, method=metodo)
    try:
        with urllib.request.urlopen(pedido, timeout=60) as resposta:
            return json.load(resposta)
    except urllib.error.HTTPError as e:
        sys.exit(f"Erro {e.code} da Pluggy em {caminho}: {e.read().decode(errors='replace')[:300]}")


def centavos(valor):
    return int((Decimal(str(valor)) * 100).quantize(Decimal("1"))) if valor is not None else None


def data_hora(texto):
    return datetime.fromisoformat(texto.replace("Z", "+00:00")) if texto else None


def millis(texto):
    dt = data_hora(texto)
    return int(dt.timestamp() * 1000) if dt else None


def epoch_day(dt):
    return (dt.astimezone(BRASILIA).date() - date(1970, 1, 1)).days


def nome_do_banco(conector, contas):
    # No Meu Pluggy o conector é sempre "MeuPluggy": usa o nome da conta bancária até o " - ".
    if conector and conector.lower() != "meupluggy":
        return conector
    banco = next((c for c in contas if c["type"] == "BANK"), None)
    return banco["name"].split(" - ")[0].strip() if banco else None


def todas_as_transacoes(api_key, conta_id):
    transacoes, cursor = [], None
    while True:
        params = {"accountId": conta_id}
        if cursor:
            params["after"] = cursor
        pagina = chamar("GET", "/v2/transactions?" + urllib.parse.urlencode(params), api_key)
        transacoes += pagina["results"]
        proximo = pagina.get("next")
        if not proximo or not pagina["results"]:
            return transacoes
        cursor = urllib.parse.parse_qs(proximo.lstrip("?")).get("after", [None])[0]


def main():
    api_key = chamar("POST", "/auth", corpo={
        "clientId": CONFIG["pluggy_client_id"],
        "clientSecret": CONFIG["pluggy_client_secret"],
    })["apiKey"]

    banco = sqlite3.connect(PASTA / CONFIG["banco"])
    banco.executescript(TABELAS)

    pagina, total = 1, 1
    while pagina <= total:
        resposta = chamar("GET", f"/categories?page={pagina}", api_key)
        for c in resposta["results"]:
            nome = c.get("descriptionTranslated") or c.get("description") or ""
            banco.execute("INSERT OR REPLACE INTO category_dim VALUES (?,?,?)", (c["id"], nome, c.get("description")))
        total, pagina = resposta.get("totalPages", 1), pagina + 1

    for item_id in CONFIG["pluggy_item_ids"]:
        item = chamar("GET", f"/items/{item_id}", api_key)
        contas = chamar("GET", "/accounts?" + urllib.parse.urlencode({"itemId": item_id}), api_key)["results"]
        conector = (item.get("connector") or {})
        banco.execute("INSERT OR REPLACE INTO item_dim VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
            item["id"], conector.get("name"), conector.get("imageUrl"), item.get("status"),
            item.get("executionStatus"), millis(item.get("lastUpdatedAt")), millis(item.get("nextAutoSyncAt")),
            millis(item.get("consentExpiresAt")), (item.get("error") or {}).get("code"),
            int(datetime.now().timestamp() * 1000), nome_do_banco(conector.get("name"), contas),
        ))

        for conta in contas:
            credito = conta.get("creditData") or {}
            vencimento = data_hora(credito.get("balanceDueDate"))
            banco.execute("INSERT OR REPLACE INTO account_dim VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
                conta["id"], item_id, conta["type"], conta.get("subtype"),
                conta.get("marketingName") or conta["name"], conta.get("number"), centavos(conta["balance"]),
                conta.get("currencyCode") or "BRL", centavos(credito.get("creditLimit")),
                centavos(credito.get("availableCreditLimit")), epoch_day(vencimento) if vencimento else None,
            ))

            transacoes = todas_as_transacoes(api_key, conta["id"])
            for t in transacoes:
                # Sinal pelo campo type: DEBIT = saída (negativo), CREDIT = entrada (positivo).
                valor = abs(centavos(t.get("amountInAccountCurrency") or t["amount"]))
                if t["type"].upper() == "DEBIT":
                    valor = -valor
                quando = data_hora(t["date"])
                loja = t.get("merchant") or {}
                parcela = t.get("creditCardMetadata") or {}
                banco.execute("INSERT OR REPLACE INTO transaction_fact VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                    t["id"], conta["id"], epoch_day(quando), int(quando.timestamp() * 1000),
                    (t.get("description") or t.get("descriptionRaw") or "Sem descrição").strip(),
                    t.get("descriptionRaw"), valor, centavos(t["amount"]), t.get("currencyCode") or "BRL",
                    t["type"].upper(), (t.get("status") or "POSTED").upper(), t.get("categoryId"),
                    t.get("category"), loja.get("name") or loja.get("businessName"),
                    parcela.get("installmentNumber"), parcela.get("totalInstallments"), millis(t.get("updatedAt")),
                ))
            print(f"{conta['name']}: {len(transacoes)} transações")

    banco.commit()
    banco.close()
    print(f"Banco salvo em {PASTA / CONFIG['banco']}")


if __name__ == "__main__":
    main()
