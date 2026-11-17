package br.com.prisma.financas.core.money

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.math.BigDecimal

class MoneyTest {

    @Test fun `parse decimal para centavos`() {
        assertEquals(12345L, Money.parse("123.45").cents)
        assertEquals(-10L, Money.parse("-0.1").cents)
        assertEquals(12095000L, Money.parse("120950").cents)
        assertEquals(15000L, Money.parse("1.5E2").cents)
    }

    @Test fun `arredondamento bancario`() {
        assertEquals(100L, Money.parse("1.005").cents)
        assertEquals(102L, Money.parse("1.015").cents)
    }

    @Test fun `valor que seria impreciso em double fica exato`() {
        val total = listOf("0.1", "0.2").map(Money::parse).sum()
        assertEquals(Money(30), total)
        assertEquals(BigDecimal("0.30"), total.toBigDecimal())
    }

    @Test fun `operacoes basicas`() {
        val a = Money(1000)
        val b = Money(250)
        assertEquals(Money(1250), a + b)
        assertEquals(Money(750), a - b)
        assertEquals(Money(-1000), -a)
        assertEquals(Money(1000), Money(-1000).abs())
        assertTrue(Money(-1).isNegative)
    }

    @Test(expected = ArithmeticException::class)
    fun `overflow lanca excecao em vez de corromper o valor`() {
        Money(Long.MAX_VALUE) + Money(1)
    }
}
