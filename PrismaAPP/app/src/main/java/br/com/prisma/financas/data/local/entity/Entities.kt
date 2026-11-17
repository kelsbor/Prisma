package br.com.prisma.financas.data.local.entity

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

/** Dimensão: conexão (item) da Pluggy. Datas em epoch millis (UTC). */
@Entity(tableName = "item_dim")
data class ItemEntity(
    @PrimaryKey val id: String,
    val connectorName: String?,
    val connectorImageUrl: String?,
    val status: String?,
    val executionStatus: String?,
    val lastUpdatedAt: Long?,
    val nextAutoSyncAt: Long?,
    val consentExpiresAt: Long?,
    val errorCode: String?,
    val lastSyncAt: Long?,
    /** Nome do banco. No Meu Pluggy o conector é sempre "MeuPluggy", então é deduzido das contas (ver BankNames). */
    val bankName: String? = null,
)

/** Dimensão: conta bancária ou cartão. Valores em centavos. */
@Entity(tableName = "account_dim", indices = [Index("itemId")])
data class AccountEntity(
    @PrimaryKey val id: String,
    val itemId: String,
    val type: String,          // BANK | CREDIT
    val subtype: String?,      // CHECKING_ACCOUNT | SAVINGS_ACCOUNT | CREDIT_CARD ...
    val name: String,
    val numberMasked: String?,
    val balanceCents: Long,
    val currencyCode: String,
    val creditLimitCents: Long?,
    val availableLimitCents: Long?,
    val balanceDueDateEpochDay: Long?,
)

/**
 * Transação. PK = id da Pluggy (garante deduplicação/idempotência).
 * [amountCents] é normalizado: gasto < 0, entrada > 0, independente do tipo de conta.
 * [rawAmountCents] guarda o valor exatamente como veio da API.
 */
@Entity(
    tableName = "transaction_fact",
    indices = [Index(value = ["accountId", "dateEpochDay"]), Index("dateEpochDay")],
)
data class TransactionEntity(
    @PrimaryKey val id: String,
    val accountId: String,
    val dateEpochDay: Long,
    val dateTimeMillis: Long,
    val description: String,
    val descriptionRaw: String?,
    val amountCents: Long,
    val rawAmountCents: Long,
    val currencyCode: String,
    val type: String,          // DEBIT | CREDIT
    val status: String,        // POSTED | PENDING
    val pluggyCategoryId: String?,
    val pluggyCategory: String?,
    val merchantName: String?,
    val installmentNumber: Int?,
    val totalInstallments: Int?,
    val updatedAtMillis: Long?,
)

/** Dimensão: catálogo de categorias da Pluggy (GET /categories). name = português; originalName = inglês. */
@Entity(tableName = "category_dim")
data class PluggyCategoryEntity(
    @PrimaryKey val id: String,
    val name: String,
    val originalName: String?,
)

/** Categoria (id da Pluggy) escolhida manualmente. Tabela separada: a sincronização nunca a toca. */
@Entity(tableName = "category_override")
data class CategoryOverrideEntity(
    @PrimaryKey val transactionId: String,
    val categoryId: String,
    val updatedAtMillis: Long,
)

/** Estado de sincronização por conta. */
@Entity(tableName = "sync_state")
data class SyncStateEntity(
    @PrimaryKey val accountId: String,
    val lastSuccessfulSyncAt: Long,
    val fullHistoryLoaded: Boolean,
)
