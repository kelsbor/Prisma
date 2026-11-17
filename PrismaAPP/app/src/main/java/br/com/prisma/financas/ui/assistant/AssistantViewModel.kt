package br.com.prisma.financas.ui.assistant

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import br.com.prisma.financas.assistant.AssistantLimits
import br.com.prisma.financas.assistant.AssistantOrchestrator
import br.com.prisma.financas.assistant.QueryResult
import br.com.prisma.financas.assistant.ReplyKind
import br.com.prisma.financas.assistant.Turno
import br.com.prisma.financas.data.prefs.SecureSettingsStore
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

data class ChatMessage(
    val id: Long,
    val fromUser: Boolean,
    val text: String,
    val kind: ReplyKind? = null,
    val sql: String? = null,
    val table: QueryResult? = null,
)

data class AssistantUiState(
    val messages: List<ChatMessage> = emptyList(),
    val input: String = "",
    val loading: Boolean = false,
)

@HiltViewModel
class AssistantViewModel @Inject constructor(
    private val orchestrator: AssistantOrchestrator,
    private val settings: SecureSettingsStore,
) : ViewModel() {

    private val _state = MutableStateFlow(AssistantUiState())
    val state: StateFlow<AssistantUiState> = _state.asStateFlow()

    /** null = carregando a preferência. */
    val consent: StateFlow<Boolean?> = settings.assistantConsent.map<Boolean, Boolean?> { it }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), null)

    val isConfigured: Boolean get() = orchestrator.isConfigured
    val maxChars: Int = AssistantLimits.MAX_CHARS

    /** Últimas perguntas respondidas com SQL: dão contexto a perguntas como "e em setembro?". */
    private val history = ArrayDeque<Turno>()
    private var nextId = 0L

    fun onInput(text: String) {
        _state.update { it.copy(input = text.take(maxChars)) }
    }

    fun acceptConsent() {
        viewModelScope.launch { settings.setAssistantConsent(true) }
    }

    fun clear() {
        history.clear()
        _state.update { AssistantUiState(input = it.input) }
    }

    fun send(text: String = _state.value.input) {
        val question = text.trim()
        if (question.isEmpty() || _state.value.loading) return
        _state.update {
            it.copy(input = "", loading = true, messages = it.messages + ChatMessage(nextId++, fromUser = true, text = question))
        }
        viewModelScope.launch {
            val reply = orchestrator.ask(question, history.toList())
            if (reply.kind == ReplyKind.ANSWER && reply.sql != null) {
                history.addLast(Turno(question, reply.sql))
                while (history.size > 3) history.removeFirst()
            }
            _state.update {
                it.copy(
                    loading = false,
                    messages = it.messages + ChatMessage(nextId++, false, reply.text, reply.kind, reply.sql, reply.table),
                )
            }
        }
    }
}
