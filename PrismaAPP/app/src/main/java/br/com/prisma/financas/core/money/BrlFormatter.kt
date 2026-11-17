package br.com.prisma.financas.core.money

/**
 * Formata em Real brasileiro de forma determinística (independe do ICU do aparelho).
 * Ex.: 123456 centavos -> "R$ 1.234,56" (com espaço não separável).
 */
object BrlFormatter {
    private const val NBSP = ' '

    fun format(money: Money, showPlusSign: Boolean = false): String {
        val cents = money.cents
        val absCents = if (cents == Long.MIN_VALUE) Long.MAX_VALUE else kotlin.math.abs(cents)
        val reais = absCents / 100
        val centavos = absCents % 100
        val grouped = reais.toString().reversed().chunked(3).joinToString(".").reversed()
        val sign = when {
            cents < 0 -> "-"
            showPlusSign && cents > 0 -> "+"
            else -> ""
        }
        return "${sign}R$$NBSP$grouped,${centavos.toString().padStart(2, '0')}"
    }
}
