package br.com.prisma.financas.domain.summary

import br.com.prisma.financas.core.money.Money
import br.com.prisma.financas.domain.model.Category
import br.com.prisma.financas.domain.model.CategoryKind
import br.com.prisma.financas.domain.model.TransactionView
import java.time.LocalDate
import java.time.YearMonth

data class Totals(val expense: Money, val income: Money) {
    val net: Money get() = income - expense
}

data class CategoryTotal(val category: Category, val amount: Money, val share: Double)

data class MonthPoint(val month: YearMonth, val expense: Money, val income: Money)

/** Gasto do mês até hoje vs. o mesmo período do mês anterior. */
data class MonthToDate(val current: Money, val previous: Money) {
    /** Variação percentual; nulo se não há base de comparação. */
    val changePercent: Double?
        get() = if (previous.cents <= 0) null else (current.cents - previous.cents) * 100.0 / previous.cents
}

/** Cálculos de resumo. Funções puras, sem Android, testadas em SummaryCalculatorTest. */
object SummaryCalculator {

    fun inRange(txs: List<TransactionView>, from: LocalDate, to: LocalDate): List<TransactionView> =
        txs.filter { !it.date.isBefore(from) && !it.date.isAfter(to) }

    fun inMonth(txs: List<TransactionView>, month: YearMonth) = inRange(txs, month.atDay(1), month.atEndOfMonth())

    fun totals(txs: List<TransactionView>): Totals {
        val expense = txs.sumOf { it.expenseCents }.coerceAtLeast(0)
        val income = txs.sumOf { it.incomeCents }
        return Totals(Money(expense), Money(income))
    }

    /** Gastos por categoria (estornos abatem; categorias zeradas somem). Ordenado do maior para o menor. */
    fun byCategory(txs: List<TransactionView>): List<CategoryTotal> {
        val sums = txs.filter { it.category.kind != CategoryKind.TRANSFER }
            .groupBy { it.category }
            .mapValues { (_, list) -> list.sumOf { it.expenseCents } }
            .filterValues { it > 0 }
        val total = sums.values.sum()
        if (total <= 0) return emptyList()
        return sums.map { (cat, cents) -> CategoryTotal(cat, Money(cents), cents.toDouble() / total) }
            .sortedByDescending { it.amount }
    }

    fun monthlySeries(txs: List<TransactionView>, endMonth: YearMonth, count: Int): List<MonthPoint> {
        val byMonth = txs.groupBy { YearMonth.from(it.date) }
        return (count - 1 downTo 0).map { back ->
            val month = endMonth.minusMonths(back.toLong())
            val t = totals(byMonth[month].orEmpty())
            MonthPoint(month, t.expense, t.income)
        }
    }

    fun topExpenses(txs: List<TransactionView>, limit: Int): List<TransactionView> =
        txs.filter { it.category.kind != CategoryKind.TRANSFER && it.amount.isNegative }
            .sortedBy { it.amount }
            .take(limit)

    fun monthToDate(txs: List<TransactionView>, today: LocalDate): MonthToDate {
        val current = totals(inRange(txs, today.withDayOfMonth(1), today)).expense
        val prevMonth = YearMonth.from(today).minusMonths(1)
        val prevEnd = prevMonth.atDay(minOf(today.dayOfMonth, prevMonth.lengthOfMonth()))
        val previous = totals(inRange(txs, prevMonth.atDay(1), prevEnd)).expense
        return MonthToDate(current, previous)
    }
}
