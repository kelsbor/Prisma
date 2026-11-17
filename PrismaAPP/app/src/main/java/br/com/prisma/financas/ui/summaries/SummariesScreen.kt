package br.com.prisma.financas.ui.summaries

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.KeyboardArrowLeft
import androidx.compose.material.icons.automirrored.outlined.KeyboardArrowRight
import androidx.compose.material.icons.outlined.PieChart
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.hilt.lifecycle.viewmodel.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import br.com.prisma.financas.domain.model.TransactionView
import br.com.prisma.financas.domain.summary.CategoryTotal
import br.com.prisma.financas.domain.summary.MonthPoint
import br.com.prisma.financas.domain.summary.RecurringExpense
import br.com.prisma.financas.ui.common.brl
import br.com.prisma.financas.ui.common.formatShortDate
import br.com.prisma.financas.ui.common.label
import br.com.prisma.financas.ui.common.shortLabel
import br.com.prisma.financas.ui.components.CategoryIcon
import br.com.prisma.financas.ui.components.EmptyState
import br.com.prisma.financas.ui.components.TransactionRow
import br.com.prisma.financas.ui.theme.MoneyTextStyle
import br.com.prisma.financas.ui.transactions.TransactionDetailSheet
import java.time.YearMonth
import kotlin.math.roundToInt

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SummariesScreen(viewModel: SummariesViewModel = hiltViewModel()) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    var selected by remember { mutableStateOf<TransactionView?>(null) }

    Column(Modifier.fillMaxSize()) {
        TopAppBar(title = { Text("Resumos") })

        if (state.loaded && !state.hasAnyTransaction) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                EmptyState(
                    icon = Icons.Outlined.PieChart,
                    title = "Resumos a caminho",
                    message = "Depois da primeira sincronização com a Pluggy, seus gastos aparecem organizados aqui.",
                )
            }
            return@Column
        }

        MonthSelector(state, viewModel::previousMonth, viewModel::nextMonth)

        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            TotalsCard(state)
            SectionCard("Evolução mensal dos gastos") { EvolutionChart(state.evolution, state.month, viewModel::selectMonth) }
            SectionCard("Gastos por categoria") {
                if (state.byCategory.isEmpty()) Muted("Nenhum gasto neste mês.")
                else state.byCategory.forEach { CategoryBar(it) }
            }
            SectionCard("Maiores gastos do mês", padded = false) {
                if (state.topExpenses.isEmpty()) Muted("Nenhum gasto neste mês.", Modifier.padding(horizontal = 16.dp))
                else state.topExpenses.forEach { tx -> TransactionRow(tx, onClick = { selected = tx }) }
            }
            SectionCard("Gastos recorrentes e assinaturas") {
                if (state.recurring.isEmpty()) {
                    Muted("Nenhum gasto recorrente identificado. Precisamos de pelo menos 3 meses de histórico com o mesmo estabelecimento.")
                } else {
                    val monthly = state.recurring.sumOf { it.typicalAmount.cents }
                    Muted("Cerca de ${br.com.prisma.financas.core.money.Money(monthly).brl()} por mês")
                    Spacer(Modifier.height(8.dp))
                    state.recurring.forEach { RecurringRow(it) }
                }
            }
        }
    }

    selected?.let { TransactionDetailSheet(it, onDismiss = { selected = null }) }
}

@Composable
private fun MonthSelector(state: SummariesUiState, onPrev: () -> Unit, onNext: () -> Unit) {
    Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp), verticalAlignment = Alignment.CenterVertically) {
        IconButton(onClick = onPrev, enabled = state.canGoBack) {
            Icon(Icons.AutoMirrored.Outlined.KeyboardArrowLeft, contentDescription = "Mês anterior")
        }
        Text(state.month.label(), style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f), textAlign = androidx.compose.ui.text.style.TextAlign.Center)
        IconButton(onClick = onNext, enabled = state.canGoForward) {
            Icon(Icons.AutoMirrored.Outlined.KeyboardArrowRight, contentDescription = "Próximo mês")
        }
    }
}

@Composable
private fun TotalsCard(state: SummariesUiState) {
    Row(Modifier.padding(horizontal = 16.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        StatTile("Gastos", state.totals.expense.brl(), Modifier.weight(1f))
        StatTile("Entradas", state.totals.income.brl(), Modifier.weight(1f))
        StatTile("Saldo do mês", state.totals.net.brl(showPlus = state.totals.net.isPositive), Modifier.weight(1f))
    }
}

@Composable
private fun StatTile(label: String, value: String, modifier: Modifier) {
    Card(modifier, colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow)) {
        Column(Modifier.padding(12.dp)) {
            Text(label, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text(value, style = MaterialTheme.typography.titleSmall.merge(MoneyTextStyle), maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
    }
}

@Composable
private fun SectionCard(title: String, padded: Boolean = true, content: @Composable () -> Unit) {
    Card(
        Modifier.padding(horizontal = 16.dp).fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow),
    ) {
        Column(Modifier.padding(vertical = 16.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(horizontal = 16.dp))
            Spacer(Modifier.height(12.dp))
            Column(if (padded) Modifier.padding(horizontal = 16.dp) else Modifier) { content() }
        }
    }
}

@Composable
private fun Muted(text: String, modifier: Modifier = Modifier) {
    Text(text, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = modifier)
}

/**
 * Barras verticais de uma série (gasto por mês), uma só cor; o mês selecionado fica destacado
 * e é o único com valor rotulado. Tocar numa barra seleciona o mês.
 */
@Composable
private fun EvolutionChart(points: List<MonthPoint>, selected: YearMonth, onSelect: (YearMonth) -> Unit) {
    val max = points.maxOfOrNull { it.expense.cents }?.takeIf { it > 0 } ?: 1L
    val selectedPoint = points.firstOrNull { it.month == selected }
    Text(
        selectedPoint?.let { "${it.month.label()}: ${it.expense.brl()}" }.orEmpty(),
        style = MaterialTheme.typography.bodyMedium.merge(MoneyTextStyle),
    )
    Spacer(Modifier.height(12.dp))
    Row(Modifier.fillMaxWidth().height(140.dp), horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.Bottom) {
        points.forEach { p ->
            val isSelected = p.month == selected
            val fraction = (p.expense.cents.toFloat() / max).coerceIn(0.02f, 1f)
            Column(
                Modifier
                    .weight(1f)
                    .fillMaxHeight()
                    .clickable { onSelect(p.month) }
                    .semantics { contentDescription = "${p.month.label()}: gastos de ${p.expense.brl()}" },
                verticalArrangement = Arrangement.Bottom,
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Box(
                    Modifier
                        .fillMaxWidth(0.62f)
                        .fillMaxHeight(fraction)
                        .background(
                            if (isSelected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.primary.copy(alpha = 0.32f),
                            RoundedCornerShape(topStart = 4.dp, topEnd = 4.dp),
                        ),
                )
            }
        }
    }
    Spacer(Modifier.height(6.dp))
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        points.forEach { p ->
            Text(
                p.month.shortLabel(),
                style = MaterialTheme.typography.labelSmall,
                color = if (p.month == selected) MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.weight(1f),
                textAlign = androidx.compose.ui.text.style.TextAlign.Center,
            )
        }
    }
}

/** Linha de categoria: ícone (identidade), nome, valor, % e barra de proporção em cor única. */
@Composable
private fun CategoryBar(item: CategoryTotal) {
    Row(Modifier.fillMaxWidth().padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
        CategoryIcon(item.category, size = 34.dp)
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(item.category.name, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(item.amount.brl(), style = MaterialTheme.typography.bodyMedium.merge(MoneyTextStyle))
            }
            Spacer(Modifier.height(4.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    Modifier.weight(1f).height(6.dp)
                        .background(MaterialTheme.colorScheme.surfaceContainerHighest, RoundedCornerShape(3.dp)),
                ) {
                    Box(
                        Modifier.fillMaxWidth(item.share.toFloat().coerceIn(0.01f, 1f)).fillMaxHeight()
                            .background(MaterialTheme.colorScheme.primary, RoundedCornerShape(3.dp)),
                    )
                }
                Spacer(Modifier.width(8.dp))
                Text(
                    "${(item.share * 100).roundToInt()}%",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.width(36.dp),
                    textAlign = androidx.compose.ui.text.style.TextAlign.End,
                )
            }
        }
    }
}

@Composable
private fun RecurringRow(item: RecurringExpense) {
    Row(Modifier.fillMaxWidth().padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
        CategoryIcon(item.category, size = 34.dp)
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(item.name, style = MaterialTheme.typography.bodyMedium, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(
                "Em ${item.monthsCount} meses · última em ${item.lastDate.formatShortDate()}",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        Text("~${item.typicalAmount.brl()}", style = MaterialTheme.typography.bodyMedium.merge(MoneyTextStyle))
    }
}
