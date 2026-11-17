package br.com.prisma.financas.ui.summaries

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import br.com.prisma.financas.core.money.Money
import br.com.prisma.financas.core.time.BrazilTime
import br.com.prisma.financas.core.time.Clock
import br.com.prisma.financas.data.repository.FinanceRepository
import br.com.prisma.financas.domain.model.TransactionView
import br.com.prisma.financas.domain.summary.CategoryTotal
import br.com.prisma.financas.domain.summary.MonthPoint
import br.com.prisma.financas.domain.summary.RecurringDetector
import br.com.prisma.financas.domain.summary.RecurringExpense
import br.com.prisma.financas.domain.summary.SummaryCalculator
import br.com.prisma.financas.domain.summary.Totals
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import java.time.YearMonth
import javax.inject.Inject

data class SummariesUiState(
    val loaded: Boolean = false,
    val month: YearMonth = YearMonth.now(),
    val currentMonth: YearMonth = YearMonth.now(),
    val earliestMonth: YearMonth? = null,
    val totals: Totals = Totals(Money.ZERO, Money.ZERO),
    val byCategory: List<CategoryTotal> = emptyList(),
    val evolution: List<MonthPoint> = emptyList(),
    val topExpenses: List<TransactionView> = emptyList(),
    val recurring: List<RecurringExpense> = emptyList(),
    val hasAnyTransaction: Boolean = false,
) {
    val canGoBack: Boolean get() = earliestMonth != null && month > earliestMonth
    val canGoForward: Boolean get() = month < currentMonth
}

@HiltViewModel
class SummariesViewModel @Inject constructor(
    repository: FinanceRepository,
    private val clock: Clock,
) : ViewModel() {

    private val selectedMonth = MutableStateFlow(YearMonth.from(BrazilTime.today(clock)))

    val state: StateFlow<SummariesUiState> = combine(repository.transactions, selectedMonth) { txs, month ->
        val monthTxs = SummaryCalculator.inMonth(txs, month)
        SummariesUiState(
            loaded = true,
            month = month,
            currentMonth = YearMonth.from(BrazilTime.today(clock)),
            earliestMonth = txs.minOfOrNull { it.date }?.let(YearMonth::from),
            totals = SummaryCalculator.totals(monthTxs),
            byCategory = SummaryCalculator.byCategory(monthTxs),
            evolution = SummaryCalculator.monthlySeries(txs, month, EVOLUTION_MONTHS),
            topExpenses = SummaryCalculator.topExpenses(monthTxs, TOP_COUNT),
            recurring = RecurringDetector.detect(txs, month),
            hasAnyTransaction = txs.isNotEmpty(),
        )
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), SummariesUiState())

    fun previousMonth() = selectedMonth.value.minusMonths(1).let { selectedMonth.value = it }
    fun nextMonth() {
        val current = YearMonth.from(BrazilTime.today(clock))
        if (selectedMonth.value < current) selectedMonth.value = selectedMonth.value.plusMonths(1)
    }
    fun selectMonth(month: YearMonth) { selectedMonth.value = month }

    private companion object {
        const val EVOLUTION_MONTHS = 6
        const val TOP_COUNT = 5
    }
}
