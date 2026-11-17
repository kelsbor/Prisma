package br.com.prisma.financas.assistant

import android.content.Context
import android.database.Cursor
import android.database.sqlite.SQLiteDatabase
import android.os.CancellationSignal
import android.os.OperationCanceledException
import br.com.prisma.financas.data.local.AppDatabase
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import javax.inject.Inject
import javax.inject.Singleton

data class QueryResult(
    val columns: List<String>,
    val rows: List<List<Any?>>,
    /** true se havia mais linhas do que o limite pedido. */
    val truncated: Boolean,
) {
    val isEmpty: Boolean get() = rows.isEmpty() || rows.all { row -> row.all { it == null } }
}

class QueryException(message: String) : Exception(message)

interface QueryRunner {
    /** Nomes de tabelas/views/índices do banco, para o [SqlGuard]. */
    suspend fun knownObjects(): Set<String>

    /** Categorias, contas e bancos existentes: ajuda o modelo a usar nomes exatos. */
    suspend fun context(): Contexto

    /** Executa um SQL já validado, em conexão somente leitura, com limite de linhas e de tempo. */
    suspend fun run(sql: String, maxRows: Int, timeoutMs: Long): QueryResult
}

@Singleton
class SqliteReadOnlyRunner @Inject constructor(
    @ApplicationContext private val context: Context,
) : QueryRunner {

    override suspend fun knownObjects(): Set<String> = withContext(Dispatchers.IO) {
        useDb { db ->
            db.rawQuery("SELECT name FROM sqlite_master", null).use { c ->
                buildSet { while (c.moveToNext()) add(c.getString(0).lowercase()) }
            }
        }
    }

    override suspend fun context(): Contexto = withContext(Dispatchers.IO) {
        useDb { db ->
            fun distinct(column: String, limit: Int): List<String> =
                db.rawQuery(
                    "SELECT DISTINCT $column FROM ${SqlGuard.VIEW} WHERE $column IS NOT NULL ORDER BY 1 LIMIT $limit",
                    null,
                ).use { c -> buildList { while (c.moveToNext()) add(c.getString(0).take(120)) } }
            Contexto(categorias = distinct("categoria", 300), contas = distinct("conta", 30), bancos = distinct("banco", 10))
        }
    }

    override suspend fun run(sql: String, maxRows: Int, timeoutMs: Long): QueryResult = withContext(Dispatchers.IO) {
        coroutineScope {
            val signal = CancellationSignal()
            val watchdog = launch { delay(timeoutMs); signal.cancel() }
            try {
                useDb { db ->
                    // A consulta vira subconsulta: o LIMIT externo vale mesmo que o SQL não tenha LIMIT.
                    db.rawQueryWithFactory(null, "SELECT * FROM ($sql) LIMIT ${maxRows + 1}", null, "", signal)
                        .use { c -> read(c, maxRows) }
                }
            } catch (_: OperationCanceledException) {
                throw QueryException("A consulta demorou demais.")
            } catch (e: android.database.SQLException) {
                // A mensagem do SQLite (ex.: "no such column") ajuda o modelo a corrigir; não contém dados.
                throw QueryException(e.message?.substringBefore(" (code")?.take(200) ?: "erro de SQL")
            } finally {
                watchdog.cancel()
            }
        }
    }

    private fun read(c: Cursor, maxRows: Int): QueryResult {
        if (c.columnCount > MAX_COLUMNS) throw QueryException("Colunas demais no resultado.")
        val columns = c.columnNames.map { it.take(64) }
        val rows = mutableListOf<List<Any?>>()
        var truncated = false
        while (c.moveToNext()) {
            if (rows.size == maxRows) { truncated = true; break }
            rows += (0 until c.columnCount).map { i ->
                when (c.getType(i)) {
                    Cursor.FIELD_TYPE_NULL -> null
                    Cursor.FIELD_TYPE_INTEGER -> c.getLong(i)
                    Cursor.FIELD_TYPE_FLOAT -> c.getDouble(i)
                    Cursor.FIELD_TYPE_BLOB -> "[binário]"
                    else -> c.getString(i).take(MAX_CELL)
                }
            }
        }
        return QueryResult(columns, rows, truncated)
    }

    private inline fun <T> useDb(block: (SQLiteDatabase) -> T): T {
        val file = context.getDatabasePath(AppDatabase.NAME)
        if (!file.exists()) throw QueryException("Ainda não há dados no aparelho.")
        val db = SQLiteDatabase.openDatabase(file.path, null, SQLiteDatabase.OPEN_READONLY)
        return try { block(db) } finally { db.close() }
    }

    private companion object {
        const val MAX_COLUMNS = 20
        const val MAX_CELL = 200
    }
}
