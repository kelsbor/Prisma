package br.com.prisma.financas.ui.root

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import br.com.prisma.financas.data.prefs.SecureSettingsStore
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import javax.inject.Inject

sealed interface RootState {
    data object Loading : RootState
    data class Ready(val onboardingCompleted: Boolean) : RootState
}

/** Decide a tela inicial uma única vez (o destino inicial do NavHost não pode mudar depois). */
@HiltViewModel
class RootViewModel @Inject constructor(
    private val store: SecureSettingsStore,
) : ViewModel() {
    private val _state = MutableStateFlow<RootState>(RootState.Loading)
    val state: StateFlow<RootState> = _state.asStateFlow()

    init {
        viewModelScope.launch {
            val done = store.onboardingCompleted.first() && store.currentCredentials() != null
            _state.value = RootState.Ready(done)
        }
    }
}
