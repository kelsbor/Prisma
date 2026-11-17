package br.com.prisma.financas.data.local.dao

import androidx.room.Dao
import androidx.room.Query
import androidx.room.Upsert
import br.com.prisma.financas.data.local.entity.AccountEntity
import br.com.prisma.financas.data.local.entity.CategoryOverrideEntity
import br.com.prisma.financas.data.local.entity.ItemEntity
import br.com.prisma.financas.data.local.entity.PluggyCategoryEntity
import br.com.prisma.financas.data.local.entity.SyncStateEntity
import br.com.prisma.financas.data.local.entity.TransactionEntity
import kotlinx.coroutines.flow.Flow

@Dao
interface ItemDao {
    @Upsert suspend fun upsert(item: ItemEntity)

    @Query("SELECT * FROM item_dim") fun observeAll(): Flow<List<ItemEntity>>

    @Query("DELETE FROM item_dim WHERE id NOT IN (:ids)") suspend fun deleteNotIn(ids: List<String>)
}

@Dao
interface AccountDao {
    @Upsert suspend fun upsertAll(accounts: List<AccountEntity>)

    @Query("SELECT * FROM account_dim ORDER BY type ASC, name ASC") fun observeAll(): Flow<List<AccountEntity>>

    @Query("SELECT id FROM account_dim WHERE itemId = :itemId") suspend fun idsForItem(itemId: String): List<String>

    @Query("SELECT COUNT(*) FROM account_dim") suspend fun count(): Int

    @Query("DELETE FROM account_dim WHERE itemId NOT IN (:itemIds)") suspend fun deleteNotInItems(itemIds: List<String>)

    @Query("DELETE FROM account_dim WHERE id IN (:ids)") suspend fun deleteByIds(ids: List<String>)
}

/** Projeção usada na conciliação (só o necessário). */
data class ExistingTransaction(
    val id: String,
    val accountId: String,
    val dateEpochDay: Long,
    val amountCents: Long,
    val status: String,
)

@Dao
interface TransactionDao {
    @Upsert suspend fun upsertAll(transactions: List<TransactionEntity>)

    @Query(
        "SELECT id, accountId, dateEpochDay, amountCents, status FROM transaction_fact " +
            "WHERE accountId = :accountId AND dateEpochDay >= :fromEpochDay",
    )
    suspend fun existingSince(accountId: String, fromEpochDay: Long): List<ExistingTransaction>

    @Query("DELETE FROM transaction_fact WHERE id IN (:ids)") suspend fun deleteByIds(ids: List<String>)

    @Query("DELETE FROM transaction_fact WHERE accountId NOT IN (SELECT id FROM account_dim)") suspend fun deleteOrphans()

    @Query("SELECT * FROM transaction_fact ORDER BY dateEpochDay DESC, dateTimeMillis DESC, id ASC")
    fun observeAll(): Flow<List<TransactionEntity>>
}

@Dao
interface CategoryOverrideDao {
    @Query("SELECT * FROM category_override") fun observeAll(): Flow<List<CategoryOverrideEntity>>

    @Query("SELECT * FROM category_override WHERE transactionId IN (:ids)")
    suspend fun forIds(ids: List<String>): List<CategoryOverrideEntity>

    @Upsert suspend fun upsertAll(overrides: List<CategoryOverrideEntity>)

    @Query("DELETE FROM category_override WHERE transactionId IN (:ids)") suspend fun deleteIds(ids: List<String>)

    @Query("DELETE FROM category_override WHERE transactionId NOT IN (SELECT id FROM transaction_fact)")
    suspend fun deleteOrphans()
}

@Dao
interface PluggyCategoryDao {
    @Query("SELECT * FROM category_dim ORDER BY id ASC") fun observeAll(): Flow<List<PluggyCategoryEntity>>

    @Upsert suspend fun upsertAll(categories: List<PluggyCategoryEntity>)

    @Query("SELECT COUNT(*) FROM category_dim") suspend fun count(): Int
}

@Dao
interface SyncStateDao {
    @Query("SELECT * FROM sync_state WHERE accountId = :accountId") suspend fun get(accountId: String): SyncStateEntity?

    @Upsert suspend fun upsert(state: SyncStateEntity)

    @Query("DELETE FROM sync_state WHERE accountId NOT IN (SELECT id FROM account_dim)") suspend fun deleteOrphans()
}
