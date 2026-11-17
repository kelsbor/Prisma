package br.com.prisma.financas.ui.transactions

import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ReceiptLong
import androidx.compose.material.icons.outlined.ArrowDropDown
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material.icons.outlined.SearchOff
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.hilt.lifecycle.viewmodel.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import br.com.prisma.financas.domain.model.TransactionView
import br.com.prisma.financas.ui.common.brl
import br.com.prisma.financas.ui.common.dayHeader
import br.com.prisma.financas.ui.components.EmptyState
import br.com.prisma.financas.ui.components.TransactionRow

@OptIn(ExperimentalMaterial3Api::class, androidx.compose.foundation.ExperimentalFoundationApi::class)
@Composable
fun TransactionsScreen(viewModel: TransactionsViewModel = hiltViewModel()) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    var selected by remember { mutableStateOf<TransactionView?>(null) }
    val f = state.filters

    Column(Modifier.fillMaxSize()) {
        TopAppBar(title = { Text("Transações") })

        OutlinedTextField(
            value = f.query,
            onValueChange = viewModel::setQuery,
            placeholder = { Text("Buscar por descrição ou estabelecimento") },
            leadingIcon = { Icon(Icons.Outlined.Search, contentDescription = null) },
            trailingIcon = if (f.query.isNotEmpty()) {
                { IconButton(onClick = { viewModel.setQuery("") }) { Icon(Icons.Outlined.Close, contentDescription = "Limpar busca") } }
            } else null,
            singleLine = true,
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
            shape = MaterialTheme.shapes.extraLarge,
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp),
        )

        Row(
            Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal = 16.dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            DropdownChip(
                label = f.period.label,
                active = f.period != Period.ALL,
                options = Period.entries.map { it.label to it },
                onSelect = { viewModel.setPeriod(it ?: Period.ALL) },
            )
            DropdownChip(
                label = state.accounts.firstOrNull { it.id == f.accountId }?.displayName ?: "Todas as contas",
                active = f.accountId != null,
                options = listOf("Todas as contas" to null) + state.accounts.map { it.displayName to it.id },
                onSelect = viewModel::setAccount,
            )
            DropdownChip(
                label = state.categories.firstOrNull { it.id == f.categoryId }?.name ?: "Todas as categorias",
                active = f.categoryId != null,
                options = listOf("Todas as categorias" to null) + state.categories.map { it.name to it.id },
                onSelect = viewModel::setCategory,
            )
        }

        if (state.count > 0) {
            Text(
                "${state.count} transações · Saídas ${state.totals.expense.brl()} · Entradas ${state.totals.income.brl()}",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(horizontal = 20.dp, vertical = 4.dp),
            )
        }

        when {
            !state.loaded -> Unit
            !state.hasAnyTransaction -> Box(Modifier.fillMaxSize(), contentAlignment = androidx.compose.ui.Alignment.Center) {
                EmptyState(
                    icon = Icons.AutoMirrored.Outlined.ReceiptLong,
                    title = "Sem transações por enquanto",
                    message = "Depois da primeira sincronização com a Pluggy, suas transações aparecem aqui.",
                )
            }
            state.count == 0 -> Box(Modifier.fillMaxSize(), contentAlignment = androidx.compose.ui.Alignment.Center) {
                EmptyState(
                    icon = Icons.Outlined.SearchOff,
                    title = "Nada encontrado",
                    message = "Nenhuma transação com esses filtros.",
                    action = { TextButton(onClick = { viewModel.clearFilters(); viewModel.setQuery("") }) { Text("Limpar filtros") } },
                )
            }
            else -> LazyColumn(Modifier.fillMaxSize()) {
                state.groups.forEach { (date, txs) ->
                    stickyHeader(key = "h-$date") {
                        Text(
                            date.dayHeader(state.today),
                            style = MaterialTheme.typography.labelLarge,
                            color = MaterialTheme.colorScheme.primary,
                            modifier = Modifier
                                .fillMaxWidth()
                                .background(MaterialTheme.colorScheme.surface)
                                .padding(horizontal = 20.dp, vertical = 8.dp),
                        )
                    }
                    items(txs, key = { it.id }) { tx -> TransactionRow(tx, onClick = { selected = tx }) }
                }
            }
        }
    }

    selected?.let { TransactionDetailSheet(it, onDismiss = { selected = null }) }
}

@Composable
private fun <T> DropdownChip(label: String, active: Boolean, options: List<Pair<String, T?>>, onSelect: (T?) -> Unit) {
    var open by remember { mutableStateOf(false) }
    Box {
        FilterChip(
            selected = active,
            onClick = { open = true },
            label = { Text(label, maxLines = 1) },
            trailingIcon = { Icon(Icons.Outlined.ArrowDropDown, contentDescription = null) },
        )
        DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            options.forEach { (text, value) ->
                DropdownMenuItem(text = { Text(text) }, onClick = { onSelect(value); open = false })
            }
        }
    }
}
