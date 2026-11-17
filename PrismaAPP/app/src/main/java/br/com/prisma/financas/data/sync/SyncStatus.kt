package br.com.prisma.financas.data.sync

import br.com.prisma.financas.data.prefs.SecureSettingsStore
import br.com.prisma.financas.data.repository.FinanceRepository
import br.com.prisma.financas.domain.model.ConnectionStatus
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.combine
import java.time.Instant
import javax.inject.Inject
import javax.inject.Singleton

data class SyncInfo(
    val running: Boolean,
    /** Quando o app consultou a Pluggy pela última vez. */
    val lastCheckAt: Long?,
    val error: String?,
    /**
     * Quando a Pluggy atualizou os dados com o banco (lastUpdatedAt do item).
     * Com várias conexões, a mais antiga — é a informação honesta sobre o quão recentes são os dados.
     */
    val dataUpdatedAt: Instant?,
    val connections: List<ConnectionStatus>,
)

@Singleton
class SyncStatusProvider @Inject constructor(
    syncManager: SyncManager,
    store: SecureSettingsStore,
    repository: FinanceRepository,
) {
    val info: Flow<SyncInfo> = combine(
        syncManager.isRunning,
        store.lastSyncAt,
        store.lastSyncError,
        repository.connections,
    ) { running, lastCheck, error, connections ->
        SyncInfo(
            running = running,
            lastCheckAt = lastCheck,
            error = error,
            dataUpdatedAt = connections.mapNotNull { it.dataUpdatedAt }.minOrNull(),
            connections = connections,
        )
    }
}
