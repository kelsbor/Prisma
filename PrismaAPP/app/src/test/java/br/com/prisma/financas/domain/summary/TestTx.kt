package br.com.prisma.financas.domain.summary

import br.com.prisma.financas.core.money.Money
import br.com.prisma.financas.domain.model.Category
import br.com.prisma.financas.domain.model.CategorySource
import br.com.prisma.financas.domain.model.PluggyCategories
import br.com.prisma.financas.domain.model.TransactionView
import java.time.LocalDate

/** Categorias da Pluggy usadas nos testes (ids e nomes reais do catálogo). */
object Cat {
    val MERCADO = PluggyCategories.build("10000000", "Supermercado")
    val TRANSPORTE = PluggyCategories.build("19000000", "Transporte")
    val COMPRAS = PluggyCategories.build("08000000", "Compras")
    val ASSINATURAS = PluggyCategories.build("09020000", "Streaming de vídeo")
    val FATURA = PluggyCategories.build("05100000", "Pagamento de cartão de crédito")
    val INVESTIMENTOS = PluggyCategories.build("03020000", "Renda fixa")
    val RENDA = PluggyCategories.build("01010000", "Salário")
}

private var seq = 0

/** Transação fictícia para testes. [cents] já normalizado (saída < 0). */
fun tx(
    date: String,
    cents: Long,
    category: Category = Cat.MERCADO,
    card: Boolean = false,
    description: String = "Compra ${++seq}",
    installments: Int? = null,
) = TransactionView(
    id = "t${++seq}",
    accountId = if (card) "card" else "bank",
    accountName = if (card) "Cartão" else "Conta",
    isCreditCard = card,
    date = LocalDate.parse(date),
    description = description,
    merchantName = null,
    amount = Money(cents),
    isPending = false,
    category = category,
    categorySource = CategorySource.PLUGGY,
    installmentNumber = installments?.let { 1 },
    totalInstallments = installments,
)
