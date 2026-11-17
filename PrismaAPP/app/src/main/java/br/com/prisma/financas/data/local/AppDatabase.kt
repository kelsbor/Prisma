package br.com.prisma.financas.data.local

import androidx.room.Database
import androidx.room.RoomDatabase
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase
import br.com.prisma.financas.data.local.dao.AccountDao
import br.com.prisma.financas.data.local.dao.CategoryOverrideDao
import br.com.prisma.financas.data.local.dao.ItemDao
import br.com.prisma.financas.data.local.dao.PluggyCategoryDao
import br.com.prisma.financas.data.local.dao.SyncStateDao
import br.com.prisma.financas.data.local.dao.TransactionDao
import br.com.prisma.financas.data.local.entity.AccountEntity
import br.com.prisma.financas.data.local.entity.CategoryOverrideEntity
import br.com.prisma.financas.data.local.entity.ItemEntity
import br.com.prisma.financas.data.local.entity.PluggyCategoryEntity
import br.com.prisma.financas.data.local.entity.SyncStateEntity
import br.com.prisma.financas.data.local.entity.TransactionEntity
import br.com.prisma.financas.data.local.view.RegisterDao
import br.com.prisma.financas.data.local.view.RegisterView

@Database(
    entities = [
        ItemEntity::class,
        AccountEntity::class,
        TransactionEntity::class,
        PluggyCategoryEntity::class,
        CategoryOverrideEntity::class,
        SyncStateEntity::class,
    ],
    views = [RegisterView::class],
    version = 4,
    exportSchema = true,
)
abstract class AppDatabase : RoomDatabase() {
    abstract fun registerDao(): RegisterDao
    abstract fun itemDao(): ItemDao
    abstract fun accountDao(): AccountDao
    abstract fun transactionDao(): TransactionDao
    abstract fun pluggyCategoryDao(): PluggyCategoryDao
    abstract fun categoryOverrideDao(): CategoryOverrideDao
    abstract fun syncStateDao(): SyncStateDao

    companion object {
        const val NAME = "prisma.db"

        /**
         * v1 → v2: categorias passam a ser as da Pluggy.
         * Remove as tabelas de categorias/regras próprias e cria o catálogo da Pluggy.
         * Escolhas manuais antigas apontavam para categorias próprias que deixaram de existir.
         */
        val MIGRATION_1_2 = object : Migration(1, 2) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("DROP TABLE IF EXISTS `category`")
                db.execSQL("DROP TABLE IF EXISTS `category_rule`")
                db.execSQL("DROP TABLE IF EXISTS `pluggy_category_map`")
                db.execSQL(
                    "CREATE TABLE IF NOT EXISTS `pluggy_category` (" +
                        "`id` TEXT NOT NULL, `name` TEXT NOT NULL, `originalName` TEXT, PRIMARY KEY(`id`))",
                )
                db.execSQL("DELETE FROM `category_override`")
            }
        }

        /**
         * v2 → v3: nomes no padrão fato/dimensão.
         * transactions → transaction_fact, account → account_dim, item → item_dim, pluggy_category → category_dim.
         * O SQLite não renomeia índices junto com a tabela, então eles são recriados com o nome que o Room espera.
         */
        val MIGRATION_2_3 = object : Migration(2, 3) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("ALTER TABLE `transactions` RENAME TO `transaction_fact`")
                db.execSQL("DROP INDEX IF EXISTS `index_transactions_accountId_dateEpochDay`")
                db.execSQL("DROP INDEX IF EXISTS `index_transactions_dateEpochDay`")
                db.execSQL("CREATE INDEX IF NOT EXISTS `index_transaction_fact_accountId_dateEpochDay` ON `transaction_fact` (`accountId`, `dateEpochDay`)")
                db.execSQL("CREATE INDEX IF NOT EXISTS `index_transaction_fact_dateEpochDay` ON `transaction_fact` (`dateEpochDay`)")

                db.execSQL("ALTER TABLE `account` RENAME TO `account_dim`")
                db.execSQL("DROP INDEX IF EXISTS `index_account_itemId`")
                db.execSQL("CREATE INDEX IF NOT EXISTS `index_account_dim_itemId` ON `account_dim` (`itemId`)")

                db.execSQL("ALTER TABLE `item` RENAME TO `item_dim`")
                db.execSQL("ALTER TABLE `pluggy_category` RENAME TO `category_dim`")
            }
        }

        /** v3 → v4: nome do banco em item_dim e a view vw_registers. */
        val MIGRATION_3_4 = object : Migration(3, 4) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("ALTER TABLE `item_dim` ADD COLUMN `bankName` TEXT")
                db.execSQL("CREATE VIEW `${RegisterView.NAME}` AS ${RegisterView.SQL}")
            }
        }
    }
}
