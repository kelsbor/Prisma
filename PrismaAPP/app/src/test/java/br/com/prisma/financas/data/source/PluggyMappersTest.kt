package br.com.prisma.financas.data.source

import br.com.prisma.financas.data.remote.PluggyJson
import br.com.prisma.financas.data.remote.dto.TransactionDto
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.time.LocalDate

class PluggyMappersTest {
    private fun dto(json: String) = PluggyJson.instance.decodeFromString(TransactionDto.serializer(), json)

    @Test fun `compra no cartao vem DEBIT positiva e vira saida negativa`() {
        val t = PluggyMappers.transaction(dto("""{"id":"1","date":"2026-11-03T15:00:00.000Z","description":"Loja","amount":89.9,"type":"DEBIT","status":"POSTED"}"""), "acc")
        assertEquals(-8990L, t.amount.cents)
        assertEquals(8990L, t.rawAmount.cents)
    }

    @Test fun `debito em conta vem negativo e continua negativo`() {
        val t = PluggyMappers.transaction(dto("""{"id":"2","date":"2026-11-03T15:00:00.000Z","description":"Pix","amount":-50,"type":"DEBIT"}"""), "acc")
        assertEquals(-5000L, t.amount.cents)
    }

    @Test fun `estorno no cartao vem CREDIT negativo e vira entrada positiva`() {
        val t = PluggyMappers.transaction(dto("""{"id":"3","date":"2026-11-03T15:00:00.000Z","description":"Estorno","amount":-20.5,"type":"CREDIT"}"""), "acc")
        assertEquals(2050L, t.amount.cents)
    }

    @Test fun `data UTC vira data de Brasilia`() {
        // 02:00 UTC do dia 5 = 23:00 do dia 4 em Brasília
        val t = PluggyMappers.transaction(dto("""{"id":"4","date":"2026-11-05T02:00:00.000Z","description":"x","amount":1,"type":"DEBIT"}"""), "acc")
        assertEquals(LocalDate.of(2026, 11, 4), t.date)
    }

    @Test fun `moeda estrangeira usa o valor convertido da conta`() {
        val t = PluggyMappers.transaction(
            dto("""{"id":"5","date":"2026-11-03T12:00:00.000Z","description":"Steam","amount":10,"amountInAccountCurrency":55.37,"currencyCode":"USD","type":"DEBIT"}"""),
            "acc",
        )
        assertEquals(-5537L, t.amount.cents)
    }

    @Test fun `campos opcionais, parcelas e estabelecimento`() {
        val t = PluggyMappers.transaction(
            dto(
                """{"id":"6","date":"2026-11-03T12:00:00.000Z","description":"  ","descriptionRaw":"MAGALU 03/10","amount":100,"type":"DEBIT",
                "categoryId":"08000000","category":"Shopping","merchant":{"name":"","businessName":"Magazine Luiza SA"},
                "creditCardMetadata":{"installmentNumber":3,"totalInstallments":10}}""",
            ),
            "acc",
        )
        assertEquals("MAGALU 03/10", t.description)
        assertEquals("Magazine Luiza SA", t.merchantName)
        assertEquals(3, t.installmentNumber)
        assertEquals(10, t.totalInstallments)
        assertEquals("POSTED", t.status)
        assertEquals("acc", t.accountId)
        assertNull(t.updatedAt)
    }
}
