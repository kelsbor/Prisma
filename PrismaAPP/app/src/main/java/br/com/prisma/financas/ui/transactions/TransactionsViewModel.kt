package br.com.prisma.financas.ui.transactions

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import br.com.prisma.financas.core.time.BrazilTime
import br.com.prisma.financas.core.time.Clock
import br.com.prisma.financas.data.repository.FinanceRepository
import br.com.prisma.financas.domain.model.Account
import br.com.prisma.financas.domain.model.Category
import br.com.prisma.financas.domain.model.TransactionView
import br.com.prisma.financas.domain.summary.SummaryCalculator
import br.com.prisma.financas.domain.summary.Totals
import br.com.prisma.financas.core.money.Money
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import java.text.Normalizer
import java.time.LocalDate
import java.time.YearMonth
import javax.inject.Inject

enum class Period(val label: String) {
    THIS_MONTH("Este mês"),
    LAST_MONTH("Mês passado"),
    LAST_3_MONTHS("Últimos 3 meses"),
    THIS_YEAR("Este ano"),
    ALL("Todo o período");

    /** Intervalo de datas (inclusive) do período, relativo a [today]. */
    fun range(today: LocalDate): Pair<LocalDate, LocalDate> = when (this) {
        THIS_MONTH -> today.withDayOfMonth(1) to today
        LAST_MONTH -> YearMonth.from(today).minusMonths(1).let { it.atDay(1) to it.atEndOfMonth() }
        LAST_3_MONTHS -> YearMonth.from(today).minusMonths(2).atDay(1) to today
        THIS_YEAR -> today.withDayOfYear(1) to today
        ALL -> LocalDate.MIN to LocalDate.MAX
    }
}

data class TransactionFilters(
    val query: String = "",
    val period: Period = Period.ALL,
    val accountId: String? = null,
    val categoryId: String? = null,
)

data class TransactionsUiState(
    val loaded: Boolean = false,
    val today: LocalDate = LocalDate.now(),
    val filters: TransactionFilters = TransactionFilters(),
    val accounts: List<Account> = emptyList(),
    val categories: List<Category> = emptyList(),
    /** Agrupado por dia, mais recente primeiro. */
    val groups: List<Pair<LocalDate, List<TransactionView>>> = emptyList(),
    val count: Int = 0,
    val totals: Totals = Totals(Money.ZERO, Money.ZERO),
    val hasAnyTransaction: Boolean = false,
)

@HiltViewModel
class TransactionsViewModel @Inject constructor(
    repository: FinanceRepository,
    private val clock: Clock,
) : ViewModel() {

    private val filters = MutableStateFlow(TransactionFilters())

    val state: StateFlow<TransactionsUiState> = combine(
        repository.transactions,
        repository.accounts,
        filters,
    ) { txs, accounts, f ->
        val today = BrazilTime.today(clock)
        val filtered = applyFilters(txs, f, today)
        TransactionsUiState(
            loaded = true,
            today = today,
            filters = f,
            accounts = accounts,
            categories = txs.map { it.category }.distinct().sortedBy { it.name },
            groups = filtered.groupBy { it.date }.toList(),
            count = filtered.size,
            totals = SummaryCalculator.totals(filtered),
            hasAnyTransaction = txs.isNotEmpty(),
        )
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), TransactionsUiState())

    fun setQuery(q: String) = filters.update { it.copy(query = q) }
    fun setPeriod(p: Period) = filters.update { it.copy(period = p) }
    fun setAccount(id: String?) = filters.update { it.copy(accountId = id) }
    fun setCategory(id: String?) = filters.update { it.copy(categoryId = id) }
    fun clearFilters() = filters.update { TransactionFilters(query = it.query) }

    private fun applyFilters(txs: List<TransactionView>, f: TransactionFilters, today: LocalDate): List<TransactionView> {
        val (from, to) = f.period.range(today)
        val q = normalize(f.query)
        return SummaryCalculator.inRange(txs, from, to).filter { t ->
            (f.accountId == null || t.accountId == f.accountId) &&
                (f.categoryId == null || t.category.id == f.categoryId) &&
                (q.isEmpty() || normalize(t.description).contains(q) || normalize(t.merchantName.orEmpty()).contains(q))
        }
    }

    private fun normalize(s: String): String =
        Normalizer.normalize(s, Normalizer.Form.NFD).replace(Regex("\\p{M}+"), "").lowercase().trim()
}
