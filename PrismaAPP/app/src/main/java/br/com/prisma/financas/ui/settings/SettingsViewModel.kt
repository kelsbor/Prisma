package br.com.prisma.financas.ui.settings

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import br.com.prisma.financas.core.time.Clock
import br.com.prisma.financas.data.prefs.SecureSettingsStore
import br.com.prisma.financas.data.sync.SyncInfo
import br.com.prisma.financas.data.sync.SyncManager
import br.com.prisma.financas.data.sync.SyncStatusProvider
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import javax.inject.Inject

@HiltViewModel
class SettingsViewModel @Inject constructor(
    store: SecureSettingsStore,
    private val syncManager: SyncManager,
    syncStatus: SyncStatusProvider,
    private val clock: Clock,
) : ViewModel() {

    val sync: StateFlow<SyncInfo?> = syncStatus.info
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), null)

    /** Quantidade de conexões configuradas (nulo = sem credenciais). */
    val connectionCount: StateFlow<Int?> = store.credentials
        .map { it?.itemIds?.size }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), null)

    fun syncNow() = syncManager.requestSync()

    fun nowMillis(): Long = clock.nowMillis()
}
