package br.com.prisma.financas.data.local

import br.com.prisma.financas.data.local.entity.AccountEntity
import br.com.prisma.financas.data.local.entity.ItemEntity
import br.com.prisma.financas.data.local.entity.TransactionEntity
import br.com.prisma.financas.domain.model.SourceAccount
import br.com.prisma.financas.domain.model.SourceItem
import br.com.prisma.financas.domain.model.SourceTransaction

fun SourceItem.toEntity(lastSyncAt: Long, bankName: String?) = ItemEntity(
    id = id,
    connectorName = connectorName,
    connectorImageUrl = connectorImageUrl,
    status = status,
    executionStatus = executionStatus,
    lastUpdatedAt = lastUpdatedAt?.toEpochMilli(),
    nextAutoSyncAt = nextAutoSyncAt?.toEpochMilli(),
    consentExpiresAt = consentExpiresAt?.toEpochMilli(),
    errorCode = errorCode,
    lastSyncAt = lastSyncAt,
    bankName = bankName,
)

fun SourceAccount.toEntity() = AccountEntity(
    id = id,
    itemId = itemId,
    type = type.name,
    subtype = subtype,
    name = name,
    numberMasked = number,
    balanceCents = balance.cents,
    currencyCode = currencyCode,
    creditLimitCents = creditLimit?.cents,
    availableLimitCents = availableLimit?.cents,
    balanceDueDateEpochDay = dueDate?.toEpochDay(),
)

fun SourceTransaction.toEntity() = TransactionEntity(
    id = id,
    accountId = accountId,
    dateEpochDay = date.toEpochDay(),
    dateTimeMillis = dateTime.toEpochMilli(),
    description = description,
    descriptionRaw = descriptionRaw,
    amountCents = amount.cents,
    rawAmountCents = rawAmount.cents,
    currencyCode = currencyCode,
    type = type,
    status = status,
    pluggyCategoryId = pluggyCategoryId,
    pluggyCategory = pluggyCategory,
    merchantName = merchantName,
    installmentNumber = installmentNumber,
    totalInstallments = totalInstallments,
    updatedAtMillis = updatedAt?.toEpochMilli(),
)
