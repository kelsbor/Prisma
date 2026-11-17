package br.com.prisma.financas.assistant

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class SqlGuardTest {
    private val known = setOf(
        "vw_registers", "item_dim", "account_dim", "transaction_fact", "category_dim", "category_override",
        "sync_state", "room_master_table", "android_metadata", "index_account_dim_itemid",
    )

    private fun ok(sql: String) = assertTrue(sql, SqlGuard.check(sql, known) is SqlGuard.Result.Ok)
    private fun rejected(sql: String) = assertTrue(sql, SqlGuard.check(sql, known) is SqlGuard.Result.Rejected)

    @Test fun `aceita selects na view`() {
        ok("SELECT ROUND(SUM(valor_gasto), 2) AS total FROM vw_registers WHERE ano = 2026 AND mes = 10")
        ok("select categoria, sum(valor_gasto) from vw_registers group by categoria;")
        ok("WITH m AS (SELECT mes, SUM(valor_gasto) g FROM vw_registers GROUP BY mes) SELECT * FROM m")
        ok("SELECT descricao FROM vw_registers WHERE lower(descricao) LIKE '%delete from item_dim%'") // texto em string é ignorado
        ok("SELECT REPLACE(descricao, 'x', 'y') FROM vw_registers")
        ok("SELECT * FROM \"vw_registers\"")
    }

    @Test fun `remove ponto e virgula final`() {
        val r = SqlGuard.check("SELECT * FROM vw_registers ;  ", known)
        assertEquals(SqlGuard.Result.Ok("SELECT * FROM vw_registers"), r)
    }

    @Test fun `rejeita escrita, outras tabelas e truques`() {
        rejected("")
        rejected("DELETE FROM vw_registers")
        rejected("UPDATE transaction_fact SET amountCents = 0")
        rejected("SELECT * FROM transaction_fact")
        rejected("SELECT * FROM \"item_dim\"")
        rejected("SELECT * FROM [sync_state]")
        rejected("SELECT name FROM sqlite_master")
        rejected("SELECT * FROM pragma_table_info('vw_registers')")
        rejected("SELECT * FROM vw_registers; DROP TABLE item_dim")
        rejected("SELECT * FROM vw_registers -- x")
        rejected("SELECT * FROM vw_registers /* x */")
        rejected("PRAGMA table_info(vw_registers)")
        rejected("ATTACH DATABASE 'x' AS y")
        rejected("WITH x AS (SELECT 1) DELETE FROM transaction_fact")
        rejected("SELECT 1")
        rejected("SELECT * FROM vw_registers WHERE descricao = 'sem fim")
        rejected("SELECT load_extension('x') FROM vw_registers")
        rejected("SELECT " + "x".repeat(5000) + " FROM vw_registers")
    }
}
