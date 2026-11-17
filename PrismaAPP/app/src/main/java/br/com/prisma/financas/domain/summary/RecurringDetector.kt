package br.com.prisma.financas.domain.summary

import br.com.prisma.financas.core.money.Money
import br.com.prisma.financas.domain.model.Category
import br.com.prisma.financas.domain.model.CategoryKind
import br.com.prisma.financas.domain.model.TransactionView
import java.text.Normalizer
import java.time.LocalDate
import java.time.YearMonth
import kotlin.math.abs

data class RecurringExpense(
    val name: String,
    val typicalAmount: Money,
    val monthsCount: Int,
    val lastDate: LocalDate,
    val category: Category,
)

/**
 * Detecta gastos recorrentes/assinaturas: mesmo estabelecimento em ≥ 3 meses diferentes
 * dos últimos 6, ainda ativo (último mês ou o anterior), com valor estável (±25% da mediana).
 * Compras parceladas ficam de fora (são parcelas, não assinaturas).
 */
object RecurringDetector {
    private const val WINDOW_MONTHS = 6L
    private const val MIN_MONTHS = 3
    private const val TOLERANCE = 0.25
    private const val MIN_CONSISTENT_SHARE = 0.75

    fun detect(txs: List<TransactionView>, referenceMonth: YearMonth): List<RecurringExpense> {
        val windowStart = referenceMonth.minusMonths(WINDOW_MONTHS - 1).atDay(1)
        val windowEnd = referenceMonth.atEndOfMonth()

        return txs.asSequence()
            .filter { it.amount.isNegative && it.category.kind != CategoryKind.TRANSFER }
            .filter { (it.totalInstallments ?: 1) <= 1 }
            .filter { !it.date.isBefore(windowStart) && !it.date.isAfter(windowEnd) }
            .groupBy { normalizeKey(it.merchantName ?: it.description) }
            .filterKeys { it.length >= 3 }
            .mapNotNull { (_, list) -> evaluate(list, referenceMonth) }
            .sortedByDescending { it.typicalAmount }
            .toList()
    }

    private fun evaluate(list: List<TransactionView>, referenceMonth: YearMonth): RecurringExpense? {
        val months = list.map { YearMonth.from(it.date) }.toSet()
        if (months.size < MIN_MONTHS) return null
        if (months.max() < referenceMonth.minusMonths(1)) return null // parou de cobrar

        val amounts = list.map { -it.amount.cents }.sorted()
        val median = amounts[amounts.size / 2]
        if (median <= 0) return null
        val consistent = amounts.count { abs(it - median) <= median * TOLERANCE }
        if (consistent < amounts.size * MIN_CONSISTENT_SHARE) return null

        val latest = list.maxBy { it.date }
        return RecurringExpense(
            name = latest.merchantName ?: latest.description,
            typicalAmount = Money(median),
            monthsCount = months.size,
            lastDate = latest.date,
            category = latest.category,
        )
    }

    /** "Netflix.com 12/03" → "NETFLIX COM": sem acentos, números e pontuação. */
    internal fun normalizeKey(text: String): String {
        val noAccents = Normalizer.normalize(text, Normalizer.Form.NFD).replace(Regex("\\p{M}+"), "")
        return noAccents.uppercase()
            .replace(Regex("[^A-Z]+"), " ")
            .trim()
            .split(" ")
            .filter { it.length > 1 }
            .take(3)
            .joinToString(" ")
    }
}
