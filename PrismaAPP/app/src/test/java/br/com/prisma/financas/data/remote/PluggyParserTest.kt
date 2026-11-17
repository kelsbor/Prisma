package br.com.prisma.financas.data.remote

import br.com.prisma.financas.data.remote.dto.AccountsResponse
import br.com.prisma.financas.data.remote.dto.ItemDto
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.math.BigDecimal

class PluggyParserTest {
    private val json = PluggyJson.instance

    @Test fun `contas com valores exatos em BigDecimal`() {
        val res = json.decodeFromString(AccountsResponse.serializer(), PluggyFixtures.ACCOUNTS)
        assertEquals(2, res.results.size)
        val card = res.results[0]
        assertEquals(BigDecimal("1234.56"), card.balance)
        assertEquals("CREDIT", card.type)
        assertEquals(BigDecimal("5000"), card.creditData?.creditLimit)
        assertEquals(BigDecimal("3765.44"), card.creditData?.availableCreditLimit)
        assertEquals(BigDecimal("0.1"), res.results[1].balance)
        assertNull(res.results[1].creditData)
    }

    @Test fun `item ignora campos desconhecidos e aceita nulos`() {
        val item = json.decodeFromString(ItemDto.serializer(), PluggyFixtures.ITEM)
        assertEquals("Banco Teste", item.connector?.name)
        assertEquals("UPDATED", item.status)
        assertNull(item.error)
    }

    @Test fun `campos opcionais ausentes`() {
        val item = json.decodeFromString(ItemDto.serializer(), """{"id":"x"}""")
        assertNull(item.status)
        assertNull(item.connector)
    }
}
