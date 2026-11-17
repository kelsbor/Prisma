package br.com.prisma.financas.data.repository

import br.com.prisma.financas.core.money.Money
import br.com.prisma.financas.core.time.Clock
import br.com.prisma.financas.data.local.dao.AccountDao
import br.com.prisma.financas.data.local.dao.CategoryOverrideDao
import br.com.prisma.financas.data.local.dao.ItemDao
import br.com.prisma.financas.data.local.dao.PluggyCategoryDao
import br.com.prisma.financas.data.local.dao.TransactionDao
import br.com.prisma.financas.data.local.entity.AccountEntity
import br.com.prisma.financas.data.local.entity.CategoryOverrideEntity
import br.com.prisma.financas.di.ApplicationScope
import br.com.prisma.financas.domain.category.CategoryResolver
import br.com.prisma.financas.domain.model.Account
import br.com.prisma.financas.domain.model.AccountType
import br.com.prisma.financas.domain.model.Category
import br.com.prisma.financas.domain.model.ConnectionStatus
import br.com.prisma.financas.domain.model.ItemHealthRules
import br.com.prisma.financas.domain.model.TransactionView
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.shareIn
import java.time.Instant
import java.time.LocalDate
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class FinanceRepository @Inject constructor(
    itemDao: ItemDao,
    accountDao: AccountDao,
    transactionDao: TransactionDao,
    private val overrideDao: CategoryOverrideDao,
    categoryDao: PluggyCategoryDao,
    private val clock: Clock,
    @ApplicationScope scope: CoroutineScope,
) {
    val accounts: Flow<List<Account>> = accountDao.observeAll()
        .map { list -> list.map(::toAccount) }
        .shareIn(scope, SharingStarted.WhileSubscribed(5_000), replay = 1)

    val connections: Flow<List<ConnectionStatus>> = itemDao.observeAll().map { items ->
        val now = Instant.ofEpochMilli(clock.nowMillis())
        items.map { e ->
            val consent = e.consentExpiresAt?.let(Instant::ofEpochMilli)
            ConnectionStatus(
                itemId = e.id,
                connectorName = e.connectorName ?: "Conexão",
                health = ItemHealthRules.of(e.status, e.executionStatus, e.errorCode, consent, now),
                dataUpdatedAt = e.lastUpdatedAt?.let(Instant::ofEpochMilli),
                nextAutoSyncAt = e.nextAutoSyncAt?.let(Instant::ofEpochMilli),
                consentExpiresAt = consent,
            )
        }
    }

    /** Catálogo da Pluggy: id → nome em português. */
    private val catalog: Flow<Map<String, String>> = categoryDao.observeAll()
        .map { list -> list.associate { it.id to it.name } }

    /** Todas as categorias da Pluggy (para escolher manualmente), em português. */
    val categories: Flow<List<Category>> = catalog.map { map ->
        val resolver = CategoryResolver(map)
        map.keys.sorted().map { resolver.category(it) }
    }

    /** Todas as transações com conta e categoria resolvidas (ordem: mais recente primeiro). */
    val transactions: Flow<List<TransactionView>> = combine(
        transactionDao.observeAll(),
        accountDao.observeAll(),
        overrideDao.observeAll(),
        catalog,
    ) { txs, accounts, overrides, catalogMap ->
        val accountById = accounts.associateBy { it.id }
        val overrideById = overrides.associate { it.transactionId to it.categoryId }
        val resolver = CategoryResolver(catalogMap)
        txs.map { t ->
            val account = accountById[t.accountId]
            val resolved = resolver.resolve(t.pluggyCategoryId, t.pluggyCategory, overrideById[t.id])
            TransactionView(
                id = t.id,
                accountId = t.accountId,
                accountName = account?.let { toAccount(it).displayName } ?: "Conta",
                isCreditCard = account?.type == AccountType.CREDIT.name,
                date = LocalDate.ofEpochDay(t.dateEpochDay),
                description = t.description,
                merchantName = t.merchantName,
                amount = Money(t.amountCents),
                isPending = t.status == "PENDING",
                category = resolved.category,
                categorySource = resolved.source,
                installmentNumber = t.installmentNumber,
                totalInstallments = t.totalInstallments,
            )
        }
    }
        .flowOn(Dispatchers.Default)
        .shareIn(scope, SharingStarted.WhileSubscribed(5_000), replay = 1)

    /** Define a categoria manual (persistida em tabela própria; a sincronização não sobrescreve). Nulo volta à automática. */
    suspend fun setCategory(transactionId: String, categoryId: String?) {
        if (categoryId == null) {
            overrideDao.deleteIds(listOf(transactionId))
        } else {
            overrideDao.upsertAll(listOf(CategoryOverrideEntity(transactionId, categoryId, clock.nowMillis())))
        }
    }

    private fun toAccount(e: AccountEntity): Account {
        val type = if (e.type == AccountType.CREDIT.name) AccountType.CREDIT else AccountType.BANK
        return Account(
            id = e.id,
            itemId = e.itemId,
            type = type,
            displayName = AccountNames.display(type, e.name),
            subtitle = AccountNames.subtitle(type, e.subtype, e.numberMasked),
            balance = Money(e.balanceCents),
            availableLimit = e.availableLimitCents?.let(::Money),
            dueDate = e.balanceDueDateEpochDay?.let(LocalDate::ofEpochDay),
        )
    }
}

/** Nomes amigáveis: a Pluggy às vezes devolve só "platinum" ou a razão social completa. */
object AccountNames {
    fun display(type: AccountType, rawName: String): String {
        val name = rawName.trim()
        return when (type) {
            AccountType.CREDIT ->
                if (name.contains("cart", ignoreCase = true)) name else "Cartão ${name.replaceFirstChar { it.uppercase() }}"
            AccountType.BANK -> name.substringBefore(" - ").trim().ifEmpty { name }
        }
    }

    fun subtitle(type: AccountType, subtype: String?, number: String?): String {
        val kind = when (subtype) {
            "CHECKING_ACCOUNT" -> "Conta corrente"
            "SAVINGS_ACCOUNT" -> "Poupança"
            "CREDIT_CARD" -> "Cartão de crédito"
            else -> if (type == AccountType.CREDIT) "Cartão de crédito" else "Conta"
        }
        val last4 = number?.filter { it.isDigit() }?.takeLast(4)?.takeIf { it.length == 4 }
        return if (last4 != null) "$kind · final $last4" else kind
    }
}
