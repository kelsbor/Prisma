package br.com.prisma.financas.data.sync

import br.com.prisma.financas.data.local.dao.ExistingTransaction
import br.com.prisma.financas.data.local.entity.CategoryOverrideEntity
import br.com.prisma.financas.data.local.entity.TransactionEntity
import kotlin.math.abs

/**
 * Decide o que fazer com as transações de uma conta após buscar uma janela na Pluggy.
 *
 * - Upsert pelo ID da Pluggy: rodar a sincronização de novo nunca duplica nada.
 * - Transações locais dentro da janela que não vieram mais são removidas
 *   (caso típico: PENDING que virou POSTED com outro ID).
 * - Se a removida tinha categoria manual, ela é transferida para a nova transação
 *   equivalente (mesma conta e valor, até 3 dias de diferença).
 */
object TransactionReconciler {

    data class Plan(
        val upserts: List<TransactionEntity>,
        val deleteIds: List<String>,
        val movedOverrides: List<CategoryOverrideEntity>,
    )

    fun plan(
        existingInWindow: List<ExistingTransaction>,
        fetched: List<TransactionEntity>,
        overridesOfExisting: List<CategoryOverrideEntity>,
        nowMillis: Long,
    ): Plan {
        val fetchedById = fetched.associateBy { it.id }
        val existingIds = existingInWindow.mapTo(HashSet()) { it.id }
        val removed = existingInWindow.filter { it.id !in fetchedById }
        val brandNew = fetched.filter { it.id !in existingIds }.toMutableList()

        val overrideById = overridesOfExisting.associateBy { it.transactionId }
        val moved = mutableListOf<CategoryOverrideEntity>()
        for (old in removed) {
            val override = overrideById[old.id] ?: continue
            val match = brandNew.firstOrNull {
                it.accountId == old.accountId &&
                    it.amountCents == old.amountCents &&
                    abs(it.dateEpochDay - old.dateEpochDay) <= 3
            } ?: continue
            brandNew.remove(match)
            moved += CategoryOverrideEntity(match.id, override.categoryId, nowMillis)
        }

        return Plan(
            upserts = fetchedById.values.toList(),
            deleteIds = removed.map { it.id },
            movedOverrides = moved,
        )
    }
}
