package br.com.prisma.financas.ui.home

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ReceiptLong
import androidx.compose.material.icons.outlined.AccountBalance
import androidx.compose.material.icons.outlined.CreditCard
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ListItem
import androidx.compose.material3.ListItemDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.hilt.lifecycle.viewmodel.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import br.com.prisma.financas.domain.model.Account
import br.com.prisma.financas.domain.model.TransactionView
import br.com.prisma.financas.ui.common.brl
import br.com.prisma.financas.ui.common.formatShortDate
import br.com.prisma.financas.ui.common.monthName
import br.com.prisma.financas.ui.components.EmptyState
import br.com.prisma.financas.ui.components.SyncStatusLine
import br.com.prisma.financas.ui.components.SyncWarnings
import br.com.prisma.financas.ui.components.TransactionRow
import br.com.prisma.financas.ui.theme.MoneyHeroStyle
import br.com.prisma.financas.ui.theme.MoneyTextStyle
import br.com.prisma.financas.ui.theme.PrismaThemeExt
import br.com.prisma.financas.ui.transactions.TransactionDetailSheet
import java.time.YearMonth
import kotlin.math.abs
import kotlin.math.roundToInt

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(
    onOpenTransactions: () -> Unit,
    viewModel: HomeViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val running = state.sync?.running == true
    var selected by remember { mutableStateOf<TransactionView?>(null) }

    Column(Modifier.fillMaxSize()) {
        TopAppBar(
            title = { Text("Prisma Finanças") },
            actions = {
                if (running) {
                    CircularProgressIndicator(Modifier.padding(end = 16.dp).size(22.dp), strokeWidth = 2.dp)
                } else {
                    IconButton(onClick = viewModel::refresh) { Icon(Icons.Outlined.Refresh, contentDescription = "Buscar dados na Pluggy") }
                }
            },
        )
        PullToRefreshBox(isRefreshing = running, onRefresh = viewModel::refresh, modifier = Modifier.fillMaxSize()) {
            LazyColumn(Modifier.fillMaxSize()) {
                item {
                    SyncStatusLine(state.sync, viewModel.nowMillis())
                    Spacer(Modifier.height(12.dp))
                    SyncWarnings(state.sync, viewModel.nowMillis(), Modifier.padding(bottom = 12.dp))
                    HeroCard(state)
                }

                if (state.loaded && !state.hasData) {
                    item {
                        EmptyState(
                            icon = Icons.AutoMirrored.Outlined.ReceiptLong,
                            title = if (running) "Buscando seu histórico" else "Ainda sem dados",
                            message = if (running) "Na primeira vez a Pluggy envia todo o histórico. Pode levar um minuto."
                            else "Puxe para baixo ou toque em ↻ para buscar seus dados na Pluggy.",
                        )
                    }
                }

                if (state.accounts.isNotEmpty()) {
                    item { SectionTitle("Contas e cartões") }
                    items(state.accounts, key = { "acc-" + it.id }) { AccountRow(it) }
                }

                if (state.recent.isNotEmpty()) {
                    item {
                        Row(
                            Modifier.fillMaxWidth().padding(start = 20.dp, end = 8.dp, top = 16.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text("Últimas transações", style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                            TextButton(onClick = onOpenTransactions) { Text("Ver todas") }
                        }
                    }
                    items(state.recent, key = { "tx-" + it.id }) { tx -> TransactionRow(tx, onClick = { selected = tx }) }
                }
                item { Spacer(Modifier.height(24.dp)) }
            }
        }
    }

    selected?.let { TransactionDetailSheet(it, onDismiss = { selected = null }) }
}

@Composable
private fun HeroCard(state: HomeUiState) {
    Box(
        Modifier
            .padding(horizontal = 20.dp)
            .fillMaxWidth()
            .clip(MaterialTheme.shapes.large)
            .background(PrismaThemeExt.finance.heroGradient)
            .padding(24.dp),
    ) {
        Column {
            Text("Saldo em contas", style = MaterialTheme.typography.labelLarge, color = Color.White.copy(alpha = 0.8f))
            Spacer(Modifier.height(6.dp))
            Text(if (state.hasData) state.bankBalance.brl() else "R$ —", style = MoneyHeroStyle, color = Color.White)
            Spacer(Modifier.height(18.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(28.dp)) {
                HeroStat("Gasto no mês", if (state.hasData) state.monthToDate.current.brl() else "—")
                HeroStat("Faturas dos cartões", if (state.hasData) state.cardBills.brl() else "—")
            }
            val change = state.monthToDate.changePercent
            if (state.hasData && change != null) {
                Spacer(Modifier.height(12.dp))
                val prevMonth = YearMonth.from(state.today).minusMonths(1).monthName()
                val pct = abs(change).roundToInt()
                val text = when {
                    pct == 0 -> "Igual ao mesmo período de $prevMonth"
                    change > 0 -> "▲ $pct% a mais que no mesmo período de $prevMonth"
                    else -> "▼ $pct% a menos que no mesmo período de $prevMonth"
                }
                Text(text, style = MaterialTheme.typography.bodySmall, color = Color.White.copy(alpha = 0.85f))
            }
        }
    }
}

@Composable
private fun HeroStat(label: String, value: String) {
    Column {
        Text(label, style = MaterialTheme.typography.labelMedium, color = Color.White.copy(alpha = 0.75f))
        Text(value, style = MaterialTheme.typography.titleMedium.merge(MoneyTextStyle), color = Color.White)
    }
}

@Composable
private fun SectionTitle(text: String) {
    Text(text, style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(start = 20.dp, end = 20.dp, top = 20.dp, bottom = 4.dp))
}

@Composable
private fun AccountRow(account: Account) {
    ListItem(
        leadingContent = {
            Box(
                Modifier.size(40.dp).clip(MaterialTheme.shapes.medium).background(MaterialTheme.colorScheme.primaryContainer),
                contentAlignment = Alignment.Center,
            ) {
                Icon(
                    if (account.isCreditCard) Icons.Outlined.CreditCard else Icons.Outlined.AccountBalance,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.onPrimaryContainer,
                )
            }
        },
        headlineContent = { Text(account.displayName, maxLines = 1, overflow = TextOverflow.Ellipsis) },
        supportingContent = {
            val due = account.dueDate?.let { " · vence ${it.formatShortDate()}" }.orEmpty()
            Text(account.subtitle + due, maxLines = 1, overflow = TextOverflow.Ellipsis)
        },
        trailingContent = {
            Column(horizontalAlignment = Alignment.End) {
                Text(account.balance.brl(), style = MaterialTheme.typography.titleSmall.merge(MoneyTextStyle))
                if (account.isCreditCard) {
                    Text(
                        account.availableLimit?.let { "Disponível ${it.brl()}" } ?: "Fatura atual",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        },
        colors = ListItemDefaults.colors(containerColor = MaterialTheme.colorScheme.surface),
        modifier = Modifier.padding(horizontal = 4.dp),
    )
}
