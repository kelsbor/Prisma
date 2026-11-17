package br.com.prisma.financas.domain.summary

import br.com.prisma.financas.core.money.Money
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.time.LocalDate
import java.time.YearMonth

class SummaryCalculatorTest {

    @Test fun `gastos e entradas ignoram transferencias e pagamento de fatura`() {
        val txs = listOf(
            tx("2026-11-02", -10_000),                                       // mercado na conta
            tx("2026-11-03", -5_000, card = true),                           // compra no cartão
            tx("2026-11-05", -15_000, Cat.FATURA),                    // pagou a fatura: não é gasto de novo
            tx("2026-11-05", 15_000, Cat.FATURA, card = true),        // crédito da fatura no cartão
            tx("2026-11-06", -20_000, Cat.INVESTIMENTOS),             // aplicação
            tx("2026-11-07", 300_000, Cat.RENDA),                     // salário
        )
        val t = SummaryCalculator.totals(txs)
        assertEquals(Money(15_000), t.expense)
        assertEquals(Money(300_000), t.income)
        assertEquals(Money(285_000), t.net)
    }

    @Test fun `estorno no cartao abate o gasto e nao vira renda`() {
        val txs = listOf(
            tx("2026-11-02", -8_000, Cat.COMPRAS, card = true),
            tx("2026-11-04", 3_000, Cat.COMPRAS, card = true),
        )
        val t = SummaryCalculator.totals(txs)
        assertEquals(Money(5_000), t.expense)
        assertEquals(Money.ZERO, t.income)
    }

    @Test fun `gastos por categoria ordenados com participacao`() {
        val txs = listOf(
            tx("2026-11-02", -3_000, Cat.TRANSPORTE),
            tx("2026-11-02", -6_000, Cat.MERCADO),
            tx("2026-11-03", -1_000, Cat.MERCADO),
            tx("2026-11-03", 50_000, Cat.RENDA),
        )
        val list = SummaryCalculator.byCategory(txs)
        assertEquals(listOf(Cat.MERCADO, Cat.TRANSPORTE), list.map { it.category })
        assertEquals(Money(7_000), list[0].amount)
        assertEquals(0.7, list[0].share, 1e-9)
    }

    @Test fun `evolucao mensal inclui meses sem gasto`() {
        val txs = listOf(tx("2026-09-10", -1_000), tx("2026-11-01", -2_000))
        val series = SummaryCalculator.monthlySeries(txs, YearMonth.of(2026, 11), 3)
        assertEquals(listOf(YearMonth.of(2026, 9), YearMonth.of(2026, 10), YearMonth.of(2026, 11)), series.map { it.month })
        assertEquals(listOf(1_000L, 0L, 2_000L), series.map { it.expense.cents })
    }

    @Test fun `comparacao com o mesmo periodo do mes anterior`() {
        val txs = listOf(
            tx("2026-10-03", -10_000),
            tx("2026-10-20", -99_000), // depois do dia 8: fora da comparação
            tx("2026-11-02", -15_000),
        )
        val mtd = SummaryCalculator.monthToDate(txs, LocalDate.of(2026, 11, 8))
        assertEquals(Money(15_000), mtd.current)
        assertEquals(Money(10_000), mtd.previous)
        assertEquals(50.0, mtd.changePercent!!, 1e-9)
    }

    @Test fun `sem base de comparacao`() {
        assertNull(SummaryCalculator.monthToDate(listOf(tx("2026-11-02", -1)), LocalDate.of(2026, 11, 8)).changePercent)
    }

    @Test fun `dia 31 compara com o ultimo dia de um mes mais curto`() {
        val txs = listOf(tx("2026-02-28", -1_000), tx("2026-03-31", -1_000))
        assertEquals(Money(1_000), SummaryCalculator.monthToDate(txs, LocalDate.of(2026, 3, 31)).previous)
    }

    @Test fun `maiores gastos`() {
        val txs = listOf(tx("2026-11-01", -100), tx("2026-11-01", -900), tx("2026-11-01", -500), tx("2026-11-01", 10_000, Cat.RENDA))
        assertEquals(listOf(-900L, -500L), SummaryCalculator.topExpenses(txs, 2).map { it.amount.cents })
    }
}
