package br.com.prisma.financas.ui.transactions

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import br.com.prisma.financas.data.repository.FinanceRepository
import br.com.prisma.financas.domain.model.Category
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import javax.inject.Inject

/** Usado pelo [TransactionDetailSheet] em qualquer tela: catálogo de categorias e troca manual. */
@HiltViewModel
class TransactionDetailViewModel @Inject constructor(
    private val repository: FinanceRepository,
) : ViewModel() {

    /** Catálogo completo da Pluggy, em português. */
    val categories: StateFlow<List<Category>> = repository.categories
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    /** Nulo volta à categoria automática da Pluggy. */
    fun setCategory(txId: String, categoryId: String?) {
        viewModelScope.launch { repository.setCategory(txId, categoryId) }
    }
}
