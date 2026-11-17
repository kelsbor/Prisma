package br.com.prisma.financas.core.money

import org.junit.Assert.assertEquals
import org.junit.Test

class BrlFormatterTest {
    private fun fmt(cents: Long, plus: Boolean = false) =
        BrlFormatter.format(Money(cents), plus).replace(' ', ' ')

    @Test fun formatos() {
        assertEquals("R$ 0,00", fmt(0))
        assertEquals("R$ 0,05", fmt(5))
        assertEquals("R$ 12,34", fmt(1234))
        assertEquals("R$ 1.234,56", fmt(123456))
        assertEquals("R$ 1.000.000,00", fmt(100000000))
        assertEquals("-R$ 1.234,56", fmt(-123456))
        assertEquals("+R$ 10,00", fmt(1000, plus = true))
    }
}
