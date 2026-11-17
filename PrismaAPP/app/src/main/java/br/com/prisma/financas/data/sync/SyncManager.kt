package br.com.prisma.financas.data.sync

import androidx.room.withTransaction
import br.com.prisma.financas.core.time.BrazilTime
import br.com.prisma.financas.core.time.Clock
import br.com.prisma.financas.data.local.AppDatabase
import br.com.prisma.financas.data.local.entity.PluggyCategoryEntity
import br.com.prisma.financas.data.local.entity.SyncStateEntity
import br.com.prisma.financas.data.local.toEntity
import br.com.prisma.financas.data.prefs.SecureSettingsStore
import br.com.prisma.financas.di.ApplicationScope
import br.com.prisma.financas.domain.model.BankNames
import br.com.prisma.financas.domain.model.PluggyCredentials
import br.com.prisma.financas.domain.model.SourceAccount
import br.com.prisma.financas.domain.model.SourceError
import br.com.prisma.financas.domain.model.SourceException
import br.com.prisma.financas.domain.model.userMessage
import br.com.prisma.financas.domain.source.TransactionSource
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import java.time.Instant
import javax.inject.Inject
import javax.inject.Singleton

sealed interface SyncOutcome {
    data object NotConfigured : SyncOutcome
    data object AlreadyRunning : SyncOutcome
    data class Success(val failedItems: Map<String, SourceError>) : SyncOutcome
    data class Failure(val error: SourceError) : SyncOutcome
}

/**
 * Sincronização idempotente: Pluggy → banco local.
 * - 1ª vez por conta: todo o histórico disponível. Depois: a partir da última sync menos [OVERLAP_DAYS].
 * - Upsert pelo ID da Pluggy (nunca duplica) + conciliação de pendentes ([TransactionReconciler]).
 * - Categorias manuais ficam em outra tabela e nunca são sobrescritas.
 * - Conexões removidas das credenciais têm seus dados apagados.
 */
@Singleton
class SyncManager @Inject constructor(
    private val source: TransactionSource,
    private val store: SecureSettingsStore,
    private val db: AppDatabase,
    private val clock: Clock,
    @ApplicationScope private val appScope: CoroutineScope,
) {
    private val mutex = Mutex()
    private val _isRunning = MutableStateFlow(false)
    val isRunning: StateFlow<Boolean> = _isRunning.asStateFlow()

    /** Dispara uma sincronização em segundo plano (ignora se já houver uma rodando). */
    fun requestSync() {
        if (_isRunning.value) return
        appScope.launch { sync() }
    }

    /**
     * Sincroniza se o banco está vazio, se ainda não há catálogo de categorias,
     * se nunca sincronizou ou se a última consulta tem mais de [STALE_AFTER_MS].
     */
    suspend fun syncIfStale() {
        val last = store.lastSyncAt.first()
        val missingData = db.accountDao().count() == 0 || db.pluggyCategoryDao().count() == 0
        if (missingData || last == null || clock.nowMillis() - last > STALE_AFTER_MS) requestSync()
    }

    suspend fun sync(): SyncOutcome {
        if (!mutex.tryLock()) return SyncOutcome.AlreadyRunning
        _isRunning.value = true
        try {
            val credentials = store.currentCredentials() ?: return SyncOutcome.NotConfigured
            refreshCategories(credentials)
            removeDataOfDeletedConnections(credentials.itemIds)

            val failed = linkedMapOf<String, SourceError>()
            for (itemId in credentials.itemIds) {
                try {
                    syncItem(credentials, itemId)
                } catch (e: SourceException) {
                    if (e.error.isGlobal) throw e
                    failed[itemId] = e.error
                }
            }
            val partial = failed.values.firstOrNull()?.let {
                if (failed.size == credentials.itemIds.size) it.userMessage()
                else "Não foi possível atualizar ${failed.size} conexão(ões): ${it.userMessage()}"
            }
            store.recordSyncSuccess(clock.nowMillis(), partial)
            return SyncOutcome.Success(failed)
        } catch (e: SourceException) {
            store.recordSyncFailure(e.error.userMessage())
            return SyncOutcome.Failure(e.error)
        } finally {
            _isRunning.value = false
            mutex.unlock()
        }
    }

    private suspend fun syncItem(credentials: PluggyCredentials, itemId: String) {
        val now = clock.nowMillis()
        val item = source.fetchItem(credentials, itemId)
        val accounts = source.fetchAccounts(credentials, itemId)

        db.withTransaction {
            db.itemDao().upsert(item.toEntity(lastSyncAt = now, bankName = BankNames.infer(item.connectorName, accounts)))
            val goneAccounts = db.accountDao().idsForItem(itemId) - accounts.map { it.id }.toSet()
            if (goneAccounts.isNotEmpty()) db.accountDao().deleteByIds(goneAccounts)
            db.accountDao().upsertAll(accounts.map { it.toEntity() })
            db.transactionDao().deleteOrphans()
            db.syncStateDao().deleteOrphans()
        }
        for (account in accounts) syncAccount(credentials, account)
    }

    private suspend fun syncAccount(credentials: PluggyCredentials, account: SourceAccount) {
        val state = db.syncStateDao().get(account.id)
        val from = if (state?.fullHistoryLoaded == true) {
            BrazilTime.dateOf(Instant.ofEpochMilli(state.lastSuccessfulSyncAt)).minusDays(OVERLAP_DAYS)
        } else {
            null // primeira vez: todo o histórico que a Pluggy oferecer
        }

        val fetched = source.fetchTransactions(credentials, account.id, from).map { it.toEntity() }
        val now = clock.nowMillis()

        db.withTransaction {
            val txDao = db.transactionDao()
            val overrideDao = db.categoryOverrideDao()
            val existing = txDao.existingSince(account.id, from?.toEpochDay() ?: Long.MIN_VALUE)
            val overrides = existing.map { it.id }.chunked(CHUNK).flatMap { overrideDao.forIds(it) }
            val plan = TransactionReconciler.plan(existing, fetched, overrides, now)

            plan.upserts.chunked(CHUNK).forEach { txDao.upsertAll(it) }
            plan.deleteIds.chunked(CHUNK).forEach {
                overrideDao.deleteIds(it)
                txDao.deleteByIds(it)
            }
            if (plan.movedOverrides.isNotEmpty()) overrideDao.upsertAll(plan.movedOverrides)
            db.syncStateDao().upsert(SyncStateEntity(account.id, now, fullHistoryLoaded = true))
        }
    }

    private suspend fun removeDataOfDeletedConnections(itemIds: List<String>) {
        db.withTransaction {
            db.itemDao().deleteNotIn(itemIds)
            db.accountDao().deleteNotInItems(itemIds)
            db.transactionDao().deleteOrphans()
            db.categoryOverrideDao().deleteOrphans()
            db.syncStateDao().deleteOrphans()
        }
    }

    /**
     * Atualiza o catálogo de categorias da Pluggy (nomes em português).
     * Se falhar por um motivo não global, segue a sincronização usando o catálogo já salvo.
     */
    private suspend fun refreshCategories(credentials: PluggyCredentials) {
        try {
            val categories = source.fetchCategories(credentials)
            if (categories.isNotEmpty()) {
                db.pluggyCategoryDao().upsertAll(categories.map { PluggyCategoryEntity(it.id, it.name, it.originalName) })
            }
        } catch (e: SourceException) {
            if (e.error.isGlobal) throw e
        }
    }

    companion object {
        /** Reconsulta os últimos dias para pegar lançamentos que a Pluggy ajustou/confirmou. */
        const val OVERLAP_DAYS = 10L
        const val STALE_AFTER_MS = 6 * 60 * 60 * 1000L
        private const val CHUNK = 500 // limite de parâmetros do SQLite
    }
}
