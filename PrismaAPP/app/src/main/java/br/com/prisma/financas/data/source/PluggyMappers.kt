package br.com.prisma.financas.data.source

import br.com.prisma.financas.core.money.Money
import br.com.prisma.financas.core.time.BrazilTime
import br.com.prisma.financas.data.remote.dto.AccountDto
import br.com.prisma.financas.data.remote.dto.ItemDto
import br.com.prisma.financas.data.remote.dto.TransactionDto
import br.com.prisma.financas.domain.model.AccountType
import br.com.prisma.financas.domain.model.SourceAccount
import br.com.prisma.financas.domain.model.SourceItem
import br.com.prisma.financas.domain.model.SourceTransaction
import java.time.Instant
import java.time.LocalDate

/** Converte o modelo da Pluggy para o modelo do app. Testado em PluggyMappersTest. */
object PluggyMappers {

    fun item(dto: ItemDto) = SourceItem(
        id = dto.id,
        connectorName = dto.connector?.name,
        connectorImageUrl = dto.connector?.imageUrl,
        status = dto.status,
        executionStatus = dto.executionStatus,
        errorCode = dto.error?.code,
        lastUpdatedAt = dto.lastUpdatedAt.toInstantOrNull(),
        nextAutoSyncAt = dto.nextAutoSyncAt.toInstantOrNull(),
        consentExpiresAt = dto.consentExpiresAt.toInstantOrNull(),
    )

    fun account(dto: AccountDto) = SourceAccount(
        id = dto.id,
        itemId = dto.itemId,
        type = if (dto.type == "CREDIT") AccountType.CREDIT else AccountType.BANK,
        subtype = dto.subtype,
        name = dto.marketingName ?: dto.name,
        number = dto.number,
        balance = Money.of(dto.balance),
        currencyCode = dto.currencyCode,
        creditLimit = dto.creditData?.creditLimit?.let(Money::of),
        availableLimit = dto.creditData?.availableCreditLimit?.let(Money::of),
        dueDate = dto.creditData?.balanceDueDate.toInstantOrNull()?.let(BrazilTime::dateOf),
    )

    /**
     * Sinal normalizado pelo campo type (DEBIT = saída, CREDIT = entrada), porque a Pluggy usa
     * convenções diferentes: no cartão a compra é DEBIT positiva; na conta o débito vem negativo.
     * Para compras em moeda estrangeira usamos o valor convertido para a moeda da conta.
     */
    fun transaction(dto: TransactionDto, accountId: String): SourceTransaction {
        val raw = Money.of(dto.amount)
        val inAccountCurrency = dto.amountInAccountCurrency?.let(Money::of) ?: raw
        val abs = inAccountCurrency.abs()
        val normalized = if (dto.type.equals("DEBIT", ignoreCase = true)) -abs else abs
        val instant = dto.date.toInstantOrNull()
            ?: LocalDate.parse(dto.date.take(10)).atStartOfDay(BrazilTime.ZONE).toInstant()
        val description = dto.description?.trim().takeUnless { it.isNullOrEmpty() }
            ?: dto.descriptionRaw?.trim().takeUnless { it.isNullOrEmpty() }
            ?: "Sem descrição"
        return SourceTransaction(
            id = dto.id,
            accountId = dto.accountId ?: accountId,
            date = BrazilTime.dateOf(instant),
            dateTime = instant,
            description = description,
            descriptionRaw = dto.descriptionRaw,
            amount = normalized,
            rawAmount = raw,
            currencyCode = dto.currencyCode ?: "BRL",
            type = dto.type.uppercase(),
            status = dto.status?.uppercase() ?: "POSTED",
            pluggyCategoryId = dto.categoryId,
            pluggyCategory = dto.category,
            merchantName = dto.merchant?.name?.takeIf { it.isNotBlank() } ?: dto.merchant?.businessName?.takeIf { it.isNotBlank() },
            installmentNumber = dto.creditCardMetadata?.installmentNumber,
            totalInstallments = dto.creditCardMetadata?.totalInstallments,
            updatedAt = dto.updatedAt.toInstantOrNull(),
        )
    }

    private fun String?.toInstantOrNull(): Instant? = this?.let { runCatching { Instant.parse(it) }.getOrNull() }
}
