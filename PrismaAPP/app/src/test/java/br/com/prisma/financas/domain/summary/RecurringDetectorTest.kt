package br.com.prisma.financas.domain.summary

import br.com.prisma.financas.core.money.Money
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.YearMonth

class RecurringDetectorTest {
    private val nov = YearMonth.of(2026, 11)

    @Test fun `assinatura mensal e detectada`() {
        val txs = listOf("2026-08-10", "2026-09-10", "2026-10-10", "2026-11-10").map {
            tx(it, -5_590, Cat.ASSINATURAS, card = true, description = "NETFLIX.COM ${it.takeLast(2)}")
        }
        val found = RecurringDetector.detect(txs, nov)
        assertEquals(1, found.size)
        assertEquals(Money(5_590), found[0].typicalAmount)
        assertEquals(4, found[0].monthsCount)
    }

    @Test fun `pequena variacao de valor ainda conta`() {
        val txs = listOf(tx("2026-09-05", -10_000, description = "Academia X"), tx("2026-10-05", -11_000, description = "ACADEMIA X"), tx("2026-11-05", -10_500, description = "academia x"))
        assertEquals(1, RecurringDetector.detect(txs, nov).size)
    }

    @Test fun `menos de 3 meses nao conta`() {
        val txs = listOf(tx("2026-10-10", -5_000, description = "Spotify"), tx("2026-11-10", -5_000, description = "Spotify"))
        assertTrue(RecurringDetector.detect(txs, nov).isEmpty())
    }

    @Test fun `valores muito diferentes nao sao assinatura`() {
        val txs = listOf(tx("2026-09-01", -1_000, description = "Mercado Bom"), tx("2026-10-01", -40_000, description = "Mercado Bom"), tx("2026-11-01", -9_000, description = "Mercado Bom"), tx("2026-11-15", -25_000, description = "Mercado Bom"))
        assertTrue(RecurringDetector.detect(txs, nov).isEmpty())
    }

    @Test fun `assinatura cancelada ha meses nao aparece`() {
        val txs = listOf("2026-05-10", "2026-06-10", "2026-07-10").map { tx(it, -3_000, description = "Disney Plus") }
        assertTrue(RecurringDetector.detect(txs, nov).isEmpty())
    }

    @Test fun `compras parceladas ficam de fora`() {
        val txs = listOf("2026-09-10", "2026-10-10", "2026-11-10").map { tx(it, -20_000, description = "Loja Y", installments = 10) }
        assertTrue(RecurringDetector.detect(txs, nov).isEmpty())
    }

    @Test fun `normalizacao de descricao`() {
        assertEquals("NETFLIX COM", RecurringDetector.normalizeKey("Netflix.com 12/03"))
        assertEquals("ACAI DA ESQUINA", RecurringDetector.normalizeKey("Açaí da Esquina 123"))
    }
}
