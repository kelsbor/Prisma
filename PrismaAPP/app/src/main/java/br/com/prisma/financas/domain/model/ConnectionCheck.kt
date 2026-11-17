package br.com.prisma.financas.domain.model

import java.time.Instant

enum class ItemHealth { OK, UPDATING, WARNING, ERROR, EXPIRED }

data class AccountBrief(val name: String, val isCreditCard: Boolean)

sealed interface ItemCheck {
    val itemId: String

    data class Ok(
        override val itemId: String,
        val connectorName: String?,
        val health: ItemHealth,
        val rawStatus: String?,
        val lastUpdatedAt: Instant?,
        val consentExpiresAt: Instant?,
        /** A autorização vence em breve (ver [ItemHealthRules.consentExpiresSoon]). */
        val consentExpiresSoon: Boolean,
        val accounts: List<AccountBrief>,
    ) : ItemCheck

    data class Failed(override val itemId: String, val error: SourceError) : ItemCheck
}

sealed interface ConnectionTestResult {
    data class Success(val items: List<ItemCheck>) : ConnectionTestResult {
        val allOk: Boolean get() = items.all { it is ItemCheck.Ok }
    }
    data class Failure(val error: SourceError) : ConnectionTestResult
}
