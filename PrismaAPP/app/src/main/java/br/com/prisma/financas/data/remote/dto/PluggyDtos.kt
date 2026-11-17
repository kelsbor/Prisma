package br.com.prisma.financas.data.remote.dto

import kotlinx.serialization.Serializable

// Modelos conferidos contra a API real (docs.pluggy.ai + chamada de teste em 11/2026).
// Campos não usados são ignorados (ignoreUnknownKeys).

@Serializable
data class AuthRequest(val clientId: String, val clientSecret: String) {
    override fun toString(): String = "AuthRequest(***)"
}

@Serializable
data class AuthResponse(val apiKey: String) {
    override fun toString(): String = "AuthResponse(***)"
}

/** GET /items/{id} */
@Serializable
data class ItemDto(
    val id: String,
    val status: String? = null,
    val executionStatus: String? = null,
    val lastUpdatedAt: String? = null,
    val nextAutoSyncAt: String? = null,
    val consentExpiresAt: String? = null,
    val error: ItemErrorDto? = null,
    val connector: ConnectorDto? = null,
)

@Serializable
data class ItemErrorDto(val code: String? = null, val message: String? = null)

@Serializable
data class ConnectorDto(val id: Long? = null, val name: String? = null, val imageUrl: String? = null)

/** GET /accounts?itemId= */
@Serializable
data class AccountsResponse(val results: List<AccountDto>)

@Serializable
data class AccountDto(
    val id: String,
    val itemId: String,
    val type: String,               // BANK | CREDIT
    val subtype: String? = null,    // CHECKING_ACCOUNT | SAVINGS_ACCOUNT | CREDIT_CARD
    val name: String,
    val marketingName: String? = null,
    val number: String? = null,
    val balance: Decimal,
    val currencyCode: String = "BRL",
    val creditData: CreditDataDto? = null,
)

@Serializable
data class CreditDataDto(
    val brand: String? = null,
    val creditLimit: Decimal? = null,
    val availableCreditLimit: Decimal? = null,
    val balanceDueDate: String? = null,
)

/** GET /v2/transactions (paginação por cursor: [next] é a query string da próxima página ou null). */
@Serializable
data class TransactionsPage(
    val results: List<TransactionDto>,
    val next: String? = null,
)

@Serializable
data class TransactionDto(
    val id: String,
    val accountId: String? = null,
    val date: String,
    val description: String? = null,
    val descriptionRaw: String? = null,
    val amount: Decimal,
    val amountInAccountCurrency: Decimal? = null,
    val currencyCode: String? = null,
    val type: String,               // DEBIT | CREDIT
    val status: String? = null,     // POSTED | PENDING
    val category: String? = null,
    val categoryId: String? = null,
    val merchant: MerchantDto? = null,
    val creditCardMetadata: CreditCardMetadataDto? = null,
    val updatedAt: String? = null,
)

@Serializable
data class MerchantDto(val name: String? = null, val businessName: String? = null)

@Serializable
data class CreditCardMetadataDto(
    val installmentNumber: Int? = null,
    val totalInstallments: Int? = null,
)

/** GET /categories — catálogo de categorias. description = inglês; descriptionTranslated = português. */
@Serializable
data class CategoriesResponse(
    val results: List<CategoryDto>,
    val page: Int = 1,
    val totalPages: Int = 1,
)

@Serializable
data class CategoryDto(
    val id: String,
    val description: String? = null,
    val descriptionTranslated: String? = null,
)

/** Corpo de erro padrão da Pluggy. */
@Serializable
data class PluggyErrorDto(
    val code: Int? = null,
    val codeDescription: String? = null,
    val message: String? = null,
)
