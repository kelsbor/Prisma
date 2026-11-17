package br.com.prisma.financas.data.source

import br.com.prisma.financas.core.time.Clock
import br.com.prisma.financas.data.remote.PluggyClient
import br.com.prisma.financas.domain.model.AccountBrief
import br.com.prisma.financas.domain.model.ConnectionTestResult
import br.com.prisma.financas.domain.model.ItemCheck
import br.com.prisma.financas.domain.model.ItemHealthRules
import br.com.prisma.financas.domain.model.PluggyCredentials
import br.com.prisma.financas.domain.model.SourceAccount
import br.com.prisma.financas.domain.model.SourceCategory
import br.com.prisma.financas.domain.model.SourceException
import br.com.prisma.financas.domain.model.SourceItem
import br.com.prisma.financas.domain.model.SourceTransaction
import br.com.prisma.financas.domain.source.TransactionSource
import java.time.Instant
import java.time.LocalDate
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class PluggyTransactionSource @Inject constructor(
    private val client: PluggyClient,
    private val clock: Clock,
) : TransactionSource {

    override suspend fun testConnection(credentials: PluggyCredentials): ConnectionTestResult = try {
        client.apiKey(credentials, forceRefresh = true) // valida Client ID/Secret de verdade
        ConnectionTestResult.Success(credentials.itemIds.map { checkItem(credentials, it) })
    } catch (e: SourceException) {
        ConnectionTestResult.Failure(e.error)
    }

    override suspend fun fetchCategories(credentials: PluggyCredentials): List<SourceCategory> =
        client.allCategories(credentials).map {
            SourceCategory(
                id = it.id,
                name = it.descriptionTranslated?.takeIf(String::isNotBlank) ?: it.description.orEmpty(),
                originalName = it.description,
            )
        }

    override suspend fun fetchItem(credentials: PluggyCredentials, itemId: String): SourceItem =
        PluggyMappers.item(client.item(credentials, itemId))

    override suspend fun fetchAccounts(credentials: PluggyCredentials, itemId: String): List<SourceAccount> =
        client.accounts(credentials, itemId).results.map(PluggyMappers::account)

    override suspend fun fetchTransactions(
        credentials: PluggyCredentials,
        accountId: String,
        from: LocalDate?,
    ): List<SourceTransaction> =
        client.allTransactions(credentials, accountId, from?.toString())
            .map { PluggyMappers.transaction(it, accountId) }
            .distinctBy { it.id }

    private suspend fun checkItem(credentials: PluggyCredentials, itemId: String): ItemCheck = try {
        val item = fetchItem(credentials, itemId)
        val accounts = fetchAccounts(credentials, itemId)
        val now = Instant.ofEpochMilli(clock.nowMillis())
        ItemCheck.Ok(
            itemId = itemId,
            connectorName = item.connectorName,
            health = ItemHealthRules.of(item.status, item.executionStatus, item.errorCode, item.consentExpiresAt, now),
            rawStatus = item.status,
            lastUpdatedAt = item.lastUpdatedAt,
            consentExpiresAt = item.consentExpiresAt,
            consentExpiresSoon = ItemHealthRules.consentExpiresSoon(item.consentExpiresAt, now),
            accounts = accounts.map { AccountBrief(name = it.name, isCreditCard = it.type.name == "CREDIT") },
        )
    } catch (e: SourceException) {
        if (e.error.isGlobal) throw e // credenciais/rede/limite: aborta o teste inteiro
        ItemCheck.Failed(itemId, e.error)
    }
}
