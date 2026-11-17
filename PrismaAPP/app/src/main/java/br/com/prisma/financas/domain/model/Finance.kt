package br.com.prisma.financas.domain.model

import br.com.prisma.financas.core.money.Money
import java.time.Instant
import java.time.LocalDate

enum class AccountType { BANK, CREDIT }

// ---- Dados vindos da fonte (já normalizados, independentes da Pluggy) ----

data class SourceItem(
    val id: String,
    val connectorName: String?,
    val connectorImageUrl: String?,
    val status: String?,
    val executionStatus: String?,
    val errorCode: String?,
    val lastUpdatedAt: Instant?,
    val nextAutoSyncAt: Instant?,
    val consentExpiresAt: Instant?,
)

data class SourceAccount(
    val id: String,
    val itemId: String,
    val type: AccountType,
    val subtype: String?,
    val name: String,
    val number: String?,
    val balance: Money,
    val currencyCode: String,
    val creditLimit: Money?,
    val availableLimit: Money?,
    val dueDate: LocalDate?,
)

/**
 * [amount] normalizado: saída < 0 e entrada > 0, para qualquer tipo de conta.
 * (Na Pluggy, compra no cartão vem positiva e débito em conta vem negativo; decidimos pelo campo type.)
 */
data class SourceTransaction(
    val id: String,
    val accountId: String,
    val date: LocalDate,
    val dateTime: Instant,
    val description: String,
    val descriptionRaw: String?,
    val amount: Money,
    val rawAmount: Money,
    val currencyCode: String,
    val type: String,
    val status: String,
    val pluggyCategoryId: String?,
    val pluggyCategory: String?,
    val merchantName: String?,
    val installmentNumber: Int?,
    val totalInstallments: Int?,
    val updatedAt: Instant?,
)

// ---- Modelos para a interface ----

data class Account(
    val id: String,
    val itemId: String,
    val type: AccountType,
    val displayName: String,
    val subtitle: String,
    /** Conta: saldo. Cartão: fatura atual (valor devido, positivo). */
    val balance: Money,
    val availableLimit: Money?,
    val dueDate: LocalDate?,
) {
    val isCreditCard: Boolean get() = type == AccountType.CREDIT
}

data class ConnectionStatus(
    val itemId: String,
    val connectorName: String,
    val health: ItemHealth,
    /** Última vez que a Pluggy atualizou os dados com o banco. */
    val dataUpdatedAt: Instant?,
    val nextAutoSyncAt: Instant?,
    val consentExpiresAt: Instant?,
)

enum class CategorySource { MANUAL, PLUGGY, DEFAULT }

data class TransactionView(
    val id: String,
    val accountId: String,
    val accountName: String,
    val isCreditCard: Boolean,
    val date: LocalDate,
    val description: String,
    val merchantName: String?,
    val amount: Money,
    val isPending: Boolean,
    val category: Category,
    val categorySource: CategorySource,
    val installmentNumber: Int?,
    val totalInstallments: Int?,
) {
    /** Quanto conta como gasto (centavos > 0); estorno no cartão abate (< 0). Transferências não contam. */
    val expenseCents: Long
        get() = when {
            category.kind == CategoryKind.TRANSFER -> 0
            amount.isNegative -> -amount.cents
            amount.isPositive && isCreditCard -> -amount.cents
            else -> 0
        }

    /** Quanto conta como entrada (centavos ≥ 0). Créditos no cartão são estornos, não renda. */
    val incomeCents: Long
        get() = if (category.kind != CategoryKind.TRANSFER && amount.isPositive && !isCreditCard) amount.cents else 0
}
