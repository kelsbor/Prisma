package br.com.prisma.financas.domain.source

import br.com.prisma.financas.domain.model.ConnectionTestResult
import br.com.prisma.financas.domain.model.PluggyCredentials
import br.com.prisma.financas.domain.model.SourceAccount
import br.com.prisma.financas.domain.model.SourceCategory
import br.com.prisma.financas.domain.model.SourceItem
import br.com.prisma.financas.domain.model.SourceTransaction
import java.time.LocalDate

/**
 * Fonte de dados financeiros. Hoje: Pluggy direto do aparelho.
 * Pode ser trocada no futuro (ex.: Connect Widget + backend) sem mexer na UI nem na sincronização.
 * Os métodos fetch* lançam SourceException em caso de falha.
 */
interface TransactionSource {
    /** Valida as credenciais e cada conexão (item + contas). */
    suspend fun testConnection(credentials: PluggyCredentials): ConnectionTestResult

    /** Catálogo de categorias da fonte, com o nome em português. */
    suspend fun fetchCategories(credentials: PluggyCredentials): List<SourceCategory>

    suspend fun fetchItem(credentials: PluggyCredentials, itemId: String): SourceItem

    suspend fun fetchAccounts(credentials: PluggyCredentials, itemId: String): List<SourceAccount>

    /** Todas as transações da conta com data ≥ [from] (ou todo o histórico se nulo). */
    suspend fun fetchTransactions(
        credentials: PluggyCredentials,
        accountId: String,
        from: LocalDate?,
    ): List<SourceTransaction>
}
