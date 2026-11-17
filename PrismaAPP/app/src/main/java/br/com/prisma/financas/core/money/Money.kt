package br.com.prisma.financas.core.money

import java.math.BigDecimal
import java.math.RoundingMode

/**
 * Valor monetário em centavos. Nunca usar Float/Double para dinheiro.
 */
@JvmInline
value class Money(val cents: Long) : Comparable<Money> {

    operator fun plus(other: Money): Money = Money(Math.addExact(cents, other.cents))
    operator fun minus(other: Money): Money = Money(Math.subtractExact(cents, other.cents))
    operator fun unaryMinus(): Money = Money(Math.negateExact(cents))

    val isNegative: Boolean get() = cents < 0
    val isPositive: Boolean get() = cents > 0
    val isZero: Boolean get() = cents == 0L

    fun abs(): Money = if (cents < 0) -this else this

    fun toBigDecimal(): BigDecimal = BigDecimal.valueOf(cents, 2)

    override fun compareTo(other: Money): Int = cents.compareTo(other.cents)

    override fun toString(): String = toBigDecimal().toPlainString()

    companion object {
        val ZERO = Money(0)

        /** Converte para centavos com arredondamento bancário (HALF_EVEN). */
        fun of(value: BigDecimal): Money =
            Money(value.setScale(2, RoundingMode.HALF_EVEN).unscaledValue().longValueExact())

        /** Lê um número decimal em texto (ex.: "-1234.56", "120950", "1.5E2"). */
        fun parse(text: String): Money = of(BigDecimal(text.trim()))
    }
}

fun Iterable<Money>.sum(): Money = fold(Money.ZERO) { acc, m -> acc + m }
