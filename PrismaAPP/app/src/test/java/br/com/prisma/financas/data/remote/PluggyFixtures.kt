package br.com.prisma.financas.data.remote

import br.com.prisma.financas.domain.model.PluggyCredentials

/** Dados 100% fictícios para testes. */
object PluggyFixtures {
    const val ITEM_ID = "11111111-2222-3333-4444-555555555555"
    val CREDENTIALS = PluggyCredentials(
        clientId = "00000000-0000-0000-0000-000000000000",
        clientSecret = "fake-secret",
        itemIds = listOf(ITEM_ID),
    )

    fun auth(key: String) = """{"apiKey":"$key"}"""

    val ITEM = """
        {
          "id": "$ITEM_ID",
          "connector": {"id": 200, "name": "Banco Teste", "imageUrl": "https://example.com/x.svg", "hasMFA": false},
          "status": "UPDATED",
          "executionStatus": "SUCCESS",
          "lastUpdatedAt": "2026-11-06T09:30:00.000Z",
          "nextAutoSyncAt": "2026-11-07T09:30:00.000Z",
          "consentExpiresAt": "2027-10-01T00:00:00.000Z",
          "error": null,
          "statusDetail": null,
          "campoNovoQualquer": {"a": 1}
        }
    """.trimIndent()

    val ACCOUNTS = """
        {
          "total": 2, "totalPages": 1, "page": 1,
          "results": [
            {
              "id": "aaaaaaaa-0000-0000-0000-000000000001", "itemId": "$ITEM_ID",
              "type": "CREDIT", "subtype": "CREDIT_CARD", "name": "Cartão Teste", "number": "xxxx1234",
              "balance": 1234.56, "currencyCode": "BRL", "marketingName": null, "bankData": null,
              "creditData": {"brand": "VISA", "creditLimit": 5000, "availableCreditLimit": 3765.44, "balanceDueDate": "2026-11-15T00:00:00.000Z"}
            },
            {
              "id": "aaaaaaaa-0000-0000-0000-000000000002", "itemId": "$ITEM_ID",
              "type": "BANK", "subtype": "CHECKING_ACCOUNT", "name": "Conta Corrente", "number": "0001/12345-6",
              "balance": 0.1, "currencyCode": "BRL", "creditData": null
            }
          ]
        }
    """.trimIndent()

    fun error(code: Int, description: String? = null) =
        """{"code":$code,"codeDescription":${description?.let { "\"$it\"" } ?: "null"},"message":"erro de teste"}"""
}
