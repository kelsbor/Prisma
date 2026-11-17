package br.com.prisma.financas.data.sync

import br.com.prisma.financas.data.local.dao.ExistingTransaction
import br.com.prisma.financas.data.local.entity.CategoryOverrideEntity
import br.com.prisma.financas.data.local.entity.TransactionEntity
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class TransactionReconcilerTest {
    private fun entity(id: String, day: Long = 100, cents: Long = -1000, status: String = "POSTED") = TransactionEntity(
        id = id, accountId = "acc", dateEpochDay = day, dateTimeMillis = day * 86_400_000, description = "d",
        descriptionRaw = null, amountCents = cents, rawAmountCents = -cents, currencyCode = "BRL", type = "DEBIT",
        status = status, pluggyCategoryId = null, pluggyCategory = null, merchantName = null,
        installmentNumber = null, totalInstallments = null, updatedAtMillis = null,
    )

    private fun existing(id: String, day: Long = 100, cents: Long = -1000, status: String = "POSTED") =
        ExistingTransaction(id, "acc", day, cents, status)

    @Test fun `sincronizar duas vezes nao duplica`() {
        val fetched = listOf(entity("a"), entity("b"))
        val plan = TransactionReconciler.plan(listOf(existing("a"), existing("b")), fetched, emptyList(), 0)
        assertEquals(setOf("a", "b"), plan.upserts.map { it.id }.toSet())
        assertTrue(plan.deleteIds.isEmpty())
    }

    @Test fun `ids repetidos na resposta viram um so`() {
        val plan = TransactionReconciler.plan(emptyList(), listOf(entity("a"), entity("a")), emptyList(), 0)
        assertEquals(1, plan.upserts.size)
    }

    @Test fun `pendente que sumiu da janela e removida`() {
        val plan = TransactionReconciler.plan(
            listOf(existing("pend", status = "PENDING"), existing("ok")),
            listOf(entity("ok"), entity("posted")),
            emptyList(),
            0,
        )
        assertEquals(listOf("pend"), plan.deleteIds)
    }

    @Test fun `categoria manual da pendente passa para a confirmada equivalente`() {
        val plan = TransactionReconciler.plan(
            existingInWindow = listOf(existing("pend", day = 100, cents = -2590, status = "PENDING")),
            fetched = listOf(entity("posted", day = 102, cents = -2590), entity("outra", day = 101, cents = -999)),
            overridesOfExisting = listOf(CategoryOverrideEntity("pend", "lazer", 1)),
            nowMillis = 5,
        )
        assertEquals(listOf("pend"), plan.deleteIds)
        assertEquals(listOf(CategoryOverrideEntity("posted", "lazer", 5)), plan.movedOverrides)
    }

    @Test fun `sem equivalente a categoria manual nao e movida`() {
        val plan = TransactionReconciler.plan(
            listOf(existing("pend", day = 100, cents = -2590)),
            listOf(entity("posted", day = 110, cents = -2590)), // 10 dias depois: não é a mesma
            listOf(CategoryOverrideEntity("pend", "lazer", 1)),
            5,
        )
        assertTrue(plan.movedOverrides.isEmpty())
    }
}
