package br.com.prisma.financas.di

import android.content.Context
import androidx.room.Room
import br.com.prisma.financas.data.local.AppDatabase
import br.com.prisma.financas.data.local.LegacyEncryptedDbCleanup
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import javax.inject.Qualifier
import javax.inject.Singleton

/** Escopo que vive enquanto o app vive (ex.: sincronização iniciada pela UI continua ao trocar de tela). */
@Qualifier
@Retention(AnnotationRetention.BINARY)
annotation class ApplicationScope

@Module
@InstallIn(SingletonComponent::class)
object AppModule {

    @Provides
    @Singleton
    @ApplicationScope
    fun provideApplicationScope(): CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    /** Banco SQLite comum (sem criptografia), em /data/data/<app>/databases/prisma.db. */
    @Provides
    @Singleton
    fun provideDatabase(@ApplicationContext context: Context): AppDatabase {
        LegacyEncryptedDbCleanup.run(context)
        return Room.databaseBuilder(context, AppDatabase::class.java, AppDatabase.NAME)
            .addMigrations(AppDatabase.MIGRATION_1_2, AppDatabase.MIGRATION_2_3, AppDatabase.MIGRATION_3_4)
            .build()
    }

    @Provides fun provideItemDao(db: AppDatabase) = db.itemDao()
    @Provides fun provideAccountDao(db: AppDatabase) = db.accountDao()
    @Provides fun provideTransactionDao(db: AppDatabase) = db.transactionDao()
    @Provides fun provideCategoryOverrideDao(db: AppDatabase) = db.categoryOverrideDao()
    @Provides fun providePluggyCategoryDao(db: AppDatabase) = db.pluggyCategoryDao()
    @Provides fun provideSyncStateDao(db: AppDatabase) = db.syncStateDao()
}
