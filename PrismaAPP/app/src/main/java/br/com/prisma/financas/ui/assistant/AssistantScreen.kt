package br.com.prisma.financas.ui.assistant

import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.outlined.AutoAwesome
import androidx.compose.material.icons.outlined.CloudOff
import androidx.compose.material.icons.outlined.DeleteSweep
import androidx.compose.material.icons.outlined.ErrorOutline
import androidx.compose.material.icons.outlined.Info
import androidx.compose.material.icons.outlined.Lock
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SuggestionChip
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.hilt.lifecycle.viewmodel.compose.hiltViewModel
import br.com.prisma.financas.assistant.QueryResult
import br.com.prisma.financas.assistant.ReplyKind
import br.com.prisma.financas.ui.components.EmptyState
import java.text.NumberFormat
import java.util.Locale

private val SUGGESTIONS = listOf(
    "Quanto gastei este mês?",
    "Gastos por categoria no mês passado",
    "Meus 5 maiores gastos deste mês",
    "Quanto recebi este mês?",
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AssistantScreen(viewModel: AssistantViewModel = hiltViewModel()) {
    val state by viewModel.state.collectAsState()
    val consent by viewModel.consent.collectAsState()

    Column(Modifier.fillMaxSize()) {
        TopAppBar(
            title = { Text("Assistente") },
            actions = {
                if (state.messages.isNotEmpty()) {
                    IconButton(onClick = viewModel::clear) {
                        Icon(Icons.Outlined.DeleteSweep, contentDescription = "Limpar conversa")
                    }
                }
            },
        )
        when {
            !viewModel.isConfigured -> CenteredState {
                EmptyState(
                    icon = Icons.Outlined.CloudOff,
                    title = "Assistente não configurado",
                    message = "Defina assistant.url e assistant.token no local.properties e gere o app de novo.",
                )
            }
            consent == null -> Unit
            consent == false -> CenteredState { ConsentCard(onAccept = viewModel::acceptConsent) }
            else -> Chat(
                state = state,
                maxChars = viewModel.maxChars,
                onInput = viewModel::onInput,
                onSend = { viewModel.send() },
                onSuggestion = viewModel::send,
            )
        }
    }
}

@Composable
private fun CenteredState(content: @Composable () -> Unit) {
    Box(Modifier.fillMaxSize().padding(bottom = 48.dp), contentAlignment = Alignment.Center) { content() }
}

@Composable
private fun ConsentCard(onAccept: () -> Unit) {
    Card(Modifier.padding(20.dp)) {
        Column(Modifier.padding(20.dp)) {
            Icon(Icons.Outlined.Lock, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
            Spacer(Modifier.height(12.dp))
            Text("Antes de começar", style = MaterialTheme.typography.titleMedium)
            Spacer(Modifier.height(8.dp))
            Text(
                "Para responder, o app envia ao Gemini (Google), pelo servidor do assistente: sua pergunta, " +
                    "os nomes das suas categorias e contas, e o resultado da consulta (por exemplo, um total ou " +
                    "algumas transações). O banco de dados completo não é enviado.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.height(8.dp))
            Text(
                "O assistente só responde sobre as suas transações e diz \"não sei\" quando não tem certeza.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.height(16.dp))
            Button(onClick = onAccept, modifier = Modifier.fillMaxWidth()) { Text("Concordo") }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun Chat(
    state: AssistantUiState,
    maxChars: Int,
    onInput: (String) -> Unit,
    onSend: () -> Unit,
    onSuggestion: (String) -> Unit,
) {
    val listState = rememberLazyListState()
    LaunchedEffect(state.messages.size, state.loading) {
        val last = state.messages.size + (if (state.loading) 1 else 0) - 1
        if (last >= 0) listState.animateScrollToItem(last)
    }

    Column(Modifier.fillMaxSize()) {
        if (state.messages.isEmpty() && !state.loading) {
            Column(Modifier.weight(1f).fillMaxWidth(), verticalArrangement = Arrangement.Center) {
                EmptyState(
                    icon = Icons.Outlined.AutoAwesome,
                    title = "Pergunte sobre seus gastos",
                    message = "Respondo com base nas suas transações: totais, categorias, maiores compras e entradas.",
                )
                FlowRow(
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 20.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp, Alignment.CenterHorizontally),
                ) {
                    SUGGESTIONS.forEach { s -> SuggestionChip(onClick = { onSuggestion(s) }, label = { Text(s) }) }
                }
            }
        } else {
            LazyColumn(
                state = listState,
                modifier = Modifier.weight(1f).fillMaxWidth(),
                contentPadding = PaddingValues(horizontal = 16.dp, vertical = 12.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                items(state.messages, key = { it.id }) { m ->
                    if (m.fromUser) UserBubble(m.text) else AssistantBubble(m)
                }
                if (state.loading) item(key = "loading") { ThinkingBubble() }
            }
        }

        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            OutlinedTextField(
                value = state.input,
                onValueChange = onInput,
                modifier = Modifier.weight(1f),
                placeholder = { Text("Ex.: quanto gastei com mercado?") },
                supportingText = { Text("${state.input.length}/$maxChars") },
                maxLines = 4,
                enabled = !state.loading,
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                keyboardActions = KeyboardActions(onSend = { onSend() }),
            )
            Spacer(Modifier.width(8.dp))
            IconButton(onClick = onSend, enabled = !state.loading && state.input.isNotBlank()) {
                Icon(Icons.AutoMirrored.Filled.Send, contentDescription = "Enviar")
            }
        }
    }
}

@Composable
private fun UserBubble(text: String) {
    Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.CenterEnd) {
        Text(
            text,
            modifier = Modifier
                .widthIn(max = 300.dp)
                .clip(RoundedCornerShape(16.dp, 16.dp, 4.dp, 16.dp))
                .background(MaterialTheme.colorScheme.primary)
                .padding(horizontal = 14.dp, vertical = 10.dp),
            color = MaterialTheme.colorScheme.onPrimary,
            style = MaterialTheme.typography.bodyMedium,
        )
    }
}

@Composable
private fun AssistantBubble(m: ChatMessage) {
    val (container, content, icon) = when (m.kind) {
        ReplyKind.ERROR -> Triple(MaterialTheme.colorScheme.errorContainer, MaterialTheme.colorScheme.onErrorContainer, Icons.Outlined.ErrorOutline)
        ReplyKind.ANSWER, null -> Triple(MaterialTheme.colorScheme.surfaceVariant, MaterialTheme.colorScheme.onSurfaceVariant, null)
        else -> Triple(MaterialTheme.colorScheme.secondaryContainer, MaterialTheme.colorScheme.onSecondaryContainer, Icons.Outlined.Info)
    }
    var showDetails by rememberSaveable(m.id) { mutableStateOf(false) }

    Column(
        Modifier
            .fillMaxWidth(0.92f)
            .clip(RoundedCornerShape(16.dp, 16.dp, 16.dp, 4.dp))
            .background(container)
            .padding(horizontal = 14.dp, vertical = 10.dp),
    ) {
        Row(verticalAlignment = Alignment.Top) {
            if (icon != null) {
                Icon(icon, contentDescription = null, tint = content, modifier = Modifier.size(18.dp).padding(top = 2.dp))
                Spacer(Modifier.width(8.dp))
            }
            Text(m.text, color = content, style = MaterialTheme.typography.bodyMedium)
        }
        val alwaysShowTable = m.kind == ReplyKind.DONT_KNOW && m.table != null && !m.table.isEmpty
        if (alwaysShowTable) {
            Spacer(Modifier.height(8.dp))
            ResultTable(m.table!!, content)
        }
        if (m.sql != null) {
            TextButton(onClick = { showDetails = !showDetails }, contentPadding = PaddingValues(0.dp)) {
                Text(if (showDetails) "Ocultar consulta" else "Ver consulta")
            }
            if (showDetails) {
                Text(
                    m.sql,
                    fontFamily = FontFamily.Monospace,
                    style = MaterialTheme.typography.bodySmall,
                    color = content,
                )
                if (!alwaysShowTable && m.table != null && !m.table.isEmpty) {
                    Spacer(Modifier.height(8.dp))
                    ResultTable(m.table, content)
                }
            }
        }
    }
}

@Composable
private fun ThinkingBubble() {
    Row(
        Modifier
            .clip(RoundedCornerShape(16.dp))
            .background(MaterialTheme.colorScheme.surfaceVariant)
            .padding(horizontal = 14.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp)
        Spacer(Modifier.width(10.dp))
        Text("Consultando seus dados…", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

private const val TABLE_ROWS = 20

@Composable
private fun ResultTable(table: QueryResult, color: Color) {
    val format = remember { NumberFormat.getNumberInstance(Locale.forLanguageTag("pt-BR")).apply { maximumFractionDigits = 2; minimumFractionDigits = 2 } }
    fun cell(v: Any?): String = when (v) {
        null -> "—"
        is Double -> format.format(v)
        else -> v.toString()
    }
    Column(Modifier.horizontalScroll(rememberScrollState())) {
        Row {
            table.columns.forEach { c ->
                Text(c, modifier = Modifier.width(120.dp).padding(end = 8.dp), fontWeight = FontWeight.SemiBold,
                    style = MaterialTheme.typography.labelMedium, color = color, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
        }
        table.rows.take(TABLE_ROWS).forEach { row ->
            Row(Modifier.padding(top = 4.dp)) {
                row.forEach { v ->
                    Text(cell(v), modifier = Modifier.width(120.dp).padding(end = 8.dp),
                        style = MaterialTheme.typography.bodySmall, color = color, maxLines = 2, overflow = TextOverflow.Ellipsis)
                }
            }
        }
        if (table.rows.size > TABLE_ROWS || table.truncated) {
            Text("Mostrando as primeiras $TABLE_ROWS linhas.", style = MaterialTheme.typography.labelSmall, color = color,
                modifier = Modifier.padding(top = 4.dp))
        }
    }
}
