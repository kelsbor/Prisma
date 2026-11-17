package br.com.prisma.financas.ui.transactions

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Check
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.lifecycle.viewmodel.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import br.com.prisma.financas.domain.model.CategorySource
import br.com.prisma.financas.domain.model.TransactionView
import br.com.prisma.financas.ui.common.formatDate
import br.com.prisma.financas.ui.components.AmountText
import br.com.prisma.financas.ui.components.CategoryIcon
import br.com.prisma.financas.ui.theme.MoneyHeroStyle

/**
 * Detalhes da transação + troca manual de categoria, entre as categorias da Pluggy.
 * A escolha é persistida e a sincronização não a sobrescreve.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TransactionDetailSheet(
    tx: TransactionView,
    onDismiss: () -> Unit,
    viewModel: TransactionDetailViewModel = hiltViewModel(),
) {
    val categories by viewModel.categories.collectAsStateWithLifecycle()
    val onSelectCategory: (String?) -> Unit = { viewModel.setCategory(tx.id, it); onDismiss() }
    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)) {
        Column(Modifier.padding(horizontal = 20.dp)) {
            Text(tx.description, style = MaterialTheme.typography.titleLarge)
            Spacer(Modifier.height(4.dp))
            AmountText(tx.amount, style = MoneyHeroStyle)
            Spacer(Modifier.height(12.dp))
            Detail("Data", tx.date.formatDate())
            Detail("Conta", tx.accountName)
            if (tx.isPending) Detail("Situação", "Pendente (ainda pode mudar)")
            if ((tx.totalInstallments ?: 0) > 1) Detail("Parcela", "${tx.installmentNumber} de ${tx.totalInstallments}")
            tx.merchantName?.let { Detail("Estabelecimento", it) }

            HorizontalDivider(Modifier.padding(vertical = 14.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("Categoria", style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                if (tx.categorySource == CategorySource.MANUAL) {
                    TextButton(onClick = { onSelectCategory(null) }) { Text("Usar a da Pluggy") }
                }
            }
            Text(
                when (tx.categorySource) {
                    CategorySource.MANUAL -> "Escolhida por você"
                    CategorySource.PLUGGY -> "Categoria da Pluggy"
                    CategorySource.DEFAULT -> "A Pluggy não informou categoria"
                },
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.height(8.dp))
            LazyColumn(Modifier.heightIn(max = 380.dp)) {
                items(categories, key = { it.id }) { cat ->
                    val selected = cat.id == tx.category.id
                    val isSub = !cat.id.endsWith("000000")
                    Row(
                        Modifier
                            .fillMaxWidth()
                            .clickable { if (!selected) onSelectCategory(cat.id) }
                            .padding(start = if (isSub) 28.dp else 0.dp, top = 6.dp, bottom = 6.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        CategoryIcon(cat, size = if (isSub) 28.dp else 34.dp)
                        Spacer(Modifier.width(12.dp))
                        Text(
                            cat.name,
                            style = if (isSub) MaterialTheme.typography.bodyMedium else MaterialTheme.typography.titleSmall,
                            modifier = Modifier.weight(1f),
                        )
                        if (selected) Icon(Icons.Outlined.Check, contentDescription = "Selecionada", tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(20.dp))
                    }
                }
            }
            Spacer(Modifier.height(24.dp))
        }
    }
}

@Composable
private fun Detail(label: String, value: String) {
    Row(Modifier.fillMaxWidth().padding(vertical = 3.dp)) {
        Text(label, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.weight(0.4f))
        Text(value, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.weight(0.6f))
    }
}
