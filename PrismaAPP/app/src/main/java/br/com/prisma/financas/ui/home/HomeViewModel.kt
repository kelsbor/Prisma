package br.com.prisma.financas.ui.home

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import br.com.prisma.financas.core.money.Money
import br.com.prisma.financas.core.money.sum
import br.com.prisma.financas.core.time.BrazilTime
import br.com.prisma.financas.core.time.Clock
import br.com.prisma.financas.data.repository.FinanceRepository
import br.com.prisma.financas.data.sync.SyncInfo
import br.com.prisma.financas.data.sync.SyncManager
import br.com.prisma.financas.data.sync.SyncStatusProvider
import br.com.prisma.financas.domain.model.Account
import br.com.prisma.financas.domain.model.AccountType
import br.com.prisma.financas.domain.model.TransactionView
import br.com.prisma.financas.domain.summary.MonthToDate
import br.com.prisma.financas.domain.summary.SummaryCalculator
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import java.time.LocalDate
import javax.inject.Inject

data class HomeUiState(
    val loaded: Boolean = false,
    val today: LocalDate = LocalDate.now(),
    val bankBalance: Money = Money.ZERO,
    val cardBills: Money = Money.ZERO,
    val monthToDate: MonthToDate = MonthToDate(Money.ZERO, Money.ZERO),
    val accounts: List<Account> = emptyList(),
    val recent: List<TransactionView> = emptyList(),
    val sync: SyncInfo? = null,
) {
    val hasData: Boolean get() = accounts.isNotEmpty() || recent.isNotEmpty()
}

@HiltViewModel
class HomeViewModel @Inject constructor(
    repository: FinanceRepository,
    private val syncManager: SyncManager,
    syncStatus: SyncStatusProvider,
    private val clock: Clock,
) : ViewModel() {

    val state: StateFlow<HomeUiState> = combine(
        repository.accounts,
        repository.transactions,
        syncStatus.info,
    ) { accounts, txs, sync ->
        val today = BrazilTime.today(clock)
        HomeUiState(
            loaded = true,
            today = today,
            bankBalance = accounts.filter { it.type == AccountType.BANK }.map { it.balance }.sum(),
            cardBills = accounts.filter { it.isCreditCard }.map { it.balance }.sum(),
            monthToDate = SummaryCalculator.monthToDate(txs, today),
            accounts = accounts,
            recent = txs.take(RECENT_COUNT),
            sync = sync,
        )
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), HomeUiState())

    init {
        viewModelScope.launch { syncManager.syncIfStale() }
    }

    fun refresh() = syncManager.requestSync()

    fun nowMillis(): Long = clock.nowMillis()

    private companion object {
        const val RECENT_COUNT = 8
    }
}
