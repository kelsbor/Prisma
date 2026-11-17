package br.com.prisma.financas.data.local

import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import br.com.prisma.financas.data.local.entity.AccountEntity
import br.com.prisma.financas.data.local.entity.CategoryOverrideEntity
import br.com.prisma.financas.data.local.entity.ItemEntity
import br.com.prisma.financas.data.local.entity.PluggyCategoryEntity
import br.com.prisma.financas.data.local.entity.TransactionEntity
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.time.LocalDate

/** Roda a vw_registers num banco em memória com dados fictícios e confere as regras. */
@RunWith(AndroidJUnit4::class)
class RegisterViewTest {
    private lateinit var db: AppDatabase
    private val day = LocalDate.of(2026, 10, 5).toEpochDay()

    @Before fun setUp() = runBlocking {
        db = Room.inMemoryDatabaseBuilder(ApplicationProvider.getApplicationContext(), AppDatabase::class.java).build()
        db.itemDao().upsert(ItemEntity("it", "MeuPluggy", null, "UPDATED", "SUCCESS", null, null, null, null, null, bankName = "Banco Teste S.A."))
        db.accountDao().upsertAll(
            listOf(
                AccountEntity("bank", "it", "BANK", "CHECKING_ACCOUNT", "Banco Teste S.A. - IP", null, 0, "BRL", null, null, null),
                AccountEntity("card", "it", "CREDIT", "CREDIT_CARD", "platinum", null, 0, "BRL", null, null, null),
            ),
        )
        db.pluggyCategoryDao().upsertAll(
            listOf(
                cat("10000000", "Supermercado"), cat("11000000", "Alimentos e bebidas"), cat("11020000", "Delivery de alimentos"),
                cat("05000000", "Transferências"), cat("05100000", "Pagamento de cartão de crédito"),
                cat("01000000", "Renda"), cat("01010000", "Salário"), cat("08000000", "Compras"),
            ),
        )
        db.transactionDao().upsertAll(
            listOf(
                tx("t1", "bank", -10_000, "10000000"),               // gasto 100,00
                tx("t2", "card", -5_000, "11020000"),                // gasto 50,00
                tx("t3", "card", 2_000, "08000000"),                 // estorno -20,00
                tx("t4", "bank", -30_000, "05100000"),               // pagou fatura: transferência
                tx("t5", "card", 30_000, "05100000"),                // crédito da fatura: transferência
                tx("t6", "bank", 500_000, "01010000"),               // entrada 5.000,00
                tx("t7", "bank", -1_500, "10000000"),                // trocada manualmente para Delivery: gasto 15,00
                tx("t8", "bank", -700, null, raw = "Something"),     // sem categoria: gasto 7,00
            ),
        )
        db.categoryOverrideDao().upsertAll(listOf(CategoryOverrideEntity("t7", "11020000", 0)))
    }

    @After fun tearDown() = db.close()

    private fun cat(id: String, name: String) = PluggyCategoryEntity(id, name, null)

    private fun tx(id: String, account: String, cents: Long, categoryId: String?, raw: String? = "Raw EN") = TransactionEntity(
        id = id, accountId = account, dateEpochDay = day, dateTimeMillis = 0, description = "desc $id", descriptionRaw = null,
        amountCents = cents, rawAmountCents = cents, currencyCode = "BRL", type = if (cents < 0) "DEBIT" else "CREDIT",
        status = "POSTED", pluggyCategoryId = categoryId, pluggyCategory = raw, merchantName = null,
        installmentNumber = null, totalInstallments = null, updatedAtMillis = null,
    )

    @Test fun regras_iguais_as_telas() = runBlocking {
        val rows = db.registerDao().all().associateBy { it.transacaoId }
        assertEquals(8, rows.size)

        assertEquals("gasto", rows.getValue("t1").tipo)
        assertEquals("estorno", rows.getValue("t3").tipo)
        assertEquals("transferencia", rows.getValue("t4").tipo)
        assertEquals("transferencia", rows.getValue("t5").tipo)
        assertEquals("entrada", rows.getValue("t6").tipo)

        val t7 = rows.getValue("t7")
        assertEquals("Delivery de alimentos", t7.categoria)
        assertEquals(true, t7.categoriaManual)
        assertEquals("Alimentos e bebidas", t7.grupoCategoria)

        assertEquals("Sem categoria", rows.getValue("t8").categoria)

        val t2 = rows.getValue("t2")
        assertEquals("2026-10-05", t2.data)
        assertEquals(2026, t2.ano)
        assertEquals(10, t2.mes)
        assertEquals("cartao", t2.tipoConta)
        assertEquals("Banco Teste S.A.", t2.banco)
        assertEquals(-5_000L, t2.valorCentavos)

        // Mesmos totais que o app calcula: 100 + 50 - 20 + 15 + 7 = 152; entradas = 5.000
        assertEquals(152.0, rows.values.sumOf { it.valorGasto }, 0.001)
        assertEquals(5_000.0, rows.values.sumOf { it.valorEntrada }, 0.001)
    }
}
