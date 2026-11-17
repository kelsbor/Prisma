package br.com.prisma.financas.assistant

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class AnswerGuardianTest {
    private val result = QueryResult(
        columns = listOf("categoria", "total_gasto", "centavos"),
        rows = listOf(listOf("Supermercado", 1234.5, 99_990L), listOf("Delivery", -342.0, null)),
        truncated = false,
    )

    @Test fun `aceita valores que existem no resultado`() {
        val text = "Você gastou R$ 1.234,50 com Supermercado e R$ 342,00 com Delivery."
        assertEquals(AnswerGuardian.Verdict.Grounded, AnswerGuardian.check(text, result))
    }

    @Test fun `aceita coluna em centavos e texto sem valores`() {
        assertEquals(AnswerGuardian.Verdict.Grounded, AnswerGuardian.check("Foram R$ 999,90.", result))
        assertEquals(AnswerGuardian.Verdict.Grounded, AnswerGuardian.check("Supermercado foi a maior categoria.", result))
    }

    @Test fun `rejeita valor inventado ou calculado`() {
        assertTrue(AnswerGuardian.check("No total foram R$ 1.576,50.", result) is AnswerGuardian.Verdict.Ungrounded)
        assertTrue(AnswerGuardian.check("Cerca de R$ 1.200,00.", result) is AnswerGuardian.Verdict.Ungrounded)
    }

    @Test fun `rejeita resposta vazia ou longa demais`() {
        assertTrue(AnswerGuardian.check(" ", result) is AnswerGuardian.Verdict.Ungrounded)
        assertTrue(AnswerGuardian.check("a".repeat(2000), result) is AnswerGuardian.Verdict.Ungrounded)
    }
}
