package br.com.prisma.financas.ui.credentials

import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.navigation.toRoute
import br.com.prisma.financas.data.prefs.SecureSettingsStore
import br.com.prisma.financas.data.sync.SyncManager
import br.com.prisma.financas.domain.model.ConnectionTestResult
import br.com.prisma.financas.domain.model.CredentialsInput
import br.com.prisma.financas.domain.model.ItemCheck
import br.com.prisma.financas.domain.model.PluggyCredentials
import br.com.prisma.financas.domain.source.TransactionSource
import br.com.prisma.financas.domain.model.userMessage
import br.com.prisma.financas.ui.navigation.CredentialsRoute
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

sealed interface TestState {
    data object Idle : TestState
    data object Running : TestState
    data class Done(val items: List<ItemCheck>, val tested: PluggyCredentials) : TestState {
        val allOk: Boolean get() = items.all { it is ItemCheck.Ok }
    }
    data class Failed(val message: String) : TestState
}

data class CredentialsUiState(
    val isOnboarding: Boolean,
    val loading: Boolean = true,
    val clientId: String = "",
    val clientSecret: String = "",
    val itemIds: List<String> = listOf(""),
    val validation: CredentialsInput.Result = CredentialsInput.Result(),
    val test: TestState = TestState.Idle,
    val saving: Boolean = false,
    val saved: Boolean = false,
) {
    val canAddItem: Boolean get() = itemIds.size < CredentialsInput.MAX_ITEMS

    fun toCredentials() = PluggyCredentials(
        clientId = clientId.trim(),
        clientSecret = clientSecret.trim(),
        itemIds = itemIds.map { it.trim() }.filter { it.isNotEmpty() },
    )

    /** Só pode salvar se o teste passou para exatamente as credenciais que estão na tela. */
    val canSave: Boolean
        get() = (test as? TestState.Done)?.let { it.allOk && it.tested == toCredentials() } == true
}

/**
 * Atenção: o segredo fica só em memória (StateFlow), nunca em SavedStateHandle,
 * que pode ser gravado em disco pelo sistema.
 */
@HiltViewModel
class CredentialsViewModel @Inject constructor(
    savedStateHandle: SavedStateHandle,
    private val source: TransactionSource,
    private val store: SecureSettingsStore,
    private val syncManager: SyncManager,
) : ViewModel() {

    private val route = savedStateHandle.toRoute<CredentialsRoute>()
    private val _state = MutableStateFlow(CredentialsUiState(isOnboarding = route.isOnboarding))
    val state: StateFlow<CredentialsUiState> = _state.asStateFlow()

    init {
        viewModelScope.launch {
            val existing = store.currentCredentials()
            _state.update {
                if (existing == null) it.copy(loading = false)
                else it.copy(
                    loading = false,
                    clientId = existing.clientId,
                    clientSecret = existing.clientSecret,
                    itemIds = existing.itemIds.ifEmpty { listOf("") },
                )
            }
        }
    }

    fun onClientIdChange(value: String) = edit { it.copy(clientId = value.trim()) }
    fun onClientSecretChange(value: String) = edit { it.copy(clientSecret = value.trim()) }

    /** Se o usuário colar vários IDs de uma vez, viram várias conexões. */
    fun onItemIdChange(index: Int, value: String) = edit { s ->
        val parts = CredentialsInput.splitIds(value)
        val ids = s.itemIds.toMutableList()
        if (parts.size > 1) {
            ids.removeAt(index)
            ids.addAll(index, parts)
        } else {
            ids[index] = value.trim()
        }
        s.copy(itemIds = ids.take(CredentialsInput.MAX_ITEMS))
    }

    fun addItem() = edit { if (it.canAddItem) it.copy(itemIds = it.itemIds + "") else it }

    fun removeItem(index: Int) = edit { s ->
        if (s.itemIds.size <= 1) s.copy(itemIds = listOf("")) else s.copy(itemIds = s.itemIds.filterIndexed { i, _ -> i != index })
    }

    fun testConnection() {
        val s = _state.value
        val validation = CredentialsInput.validate(s.clientId, s.clientSecret, s.itemIds)
        _state.update { it.copy(validation = validation) }
        if (!validation.isValid || s.test is TestState.Running) return

        val credentials = s.toCredentials()
        _state.update { it.copy(test = TestState.Running) }
        viewModelScope.launch {
            val result = when (val r = source.testConnection(credentials)) {
                is ConnectionTestResult.Success -> TestState.Done(r.items, credentials)
                is ConnectionTestResult.Failure -> TestState.Failed(r.error.userMessage())
            }
            _state.update { it.copy(test = result) }
        }
    }

    fun save() {
        val s = _state.value
        if (!s.canSave || s.saving) return
        _state.update { it.copy(saving = true) }
        viewModelScope.launch {
            store.saveCredentials(s.toCredentials())
            if (s.isOnboarding) store.setOnboardingCompleted(true)
            syncManager.requestSync() // busca os dados (e remove os de conexões retiradas)
            _state.update { it.copy(saving = false, saved = true) }
        }
    }

    /**
     * Uma edição real invalida o último teste e limpa os erros de validação.
     * O campo de texto às vezes reenvia o mesmo valor (ex.: ao fechar o teclado): isso é ignorado.
     */
    private fun edit(transform: (CredentialsUiState) -> CredentialsUiState) {
        _state.update { current ->
            val next = transform(current)
            val changed = next.clientId != current.clientId ||
                next.clientSecret != current.clientSecret ||
                next.itemIds != current.itemIds
            when {
                !changed -> current
                current.test is TestState.Running -> next.copy(validation = CredentialsInput.Result())
                else -> next.copy(validation = CredentialsInput.Result(), test = TestState.Idle)
            }
        }
    }
}
