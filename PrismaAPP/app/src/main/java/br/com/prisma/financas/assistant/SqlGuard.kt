package br.com.prisma.financas.assistant

/**
 * Segunda barreira (a primeira é o servidor): o app só executa SQL que passe aqui.
 * - um único comando, começando com SELECT ou WITH, sem comentários;
 * - nenhuma palavra de escrita/administração (INSERT, DELETE, PRAGMA, ATTACH…);
 * - nenhuma tabela do banco além da view vw_registers (nem sqlite_master, nem pragma_*).
 * Além disso, o executor abre o banco em modo SOMENTE LEITURA.
 */
object SqlGuard {
    const val VIEW = "vw_registers"
    const val MAX_LENGTH = 4000

    private val FORBIDDEN = setOf(
        "insert", "update", "delete", "drop", "create", "alter", "attach", "detach", "pragma",
        "vacuum", "reindex", "analyze", "begin", "commit", "rollback", "savepoint", "release",
        "trigger", "returning", "upsert", "load_extension", "readfile", "writefile", "fts3_tokenizer",
    )

    sealed interface Result {
        data class Ok(val sql: String) : Result
        data class Rejected(val reason: String) : Result
    }

    /** [knownObjects]: nomes de tabelas/views/índices do banco (de sqlite_master), em minúsculas. */
    fun check(sql: String, knownObjects: Set<String>): Result {
        val text = sql.trim().trimEnd(';', ' ', '\n', '\t', '\r')
        if (text.isEmpty()) return Result.Rejected("SQL vazio")
        if (text.length > MAX_LENGTH) return Result.Rejected("SQL longo demais")

        val tokens = tokenize(text) ?: return Result.Rejected("SQL inválido")
        if (tokens.statementBreak) return Result.Rejected("apenas uma instrução é permitida")
        if (tokens.comment) return Result.Rejected("comentários não são permitidos")

        val words = tokens.words
        if (words.firstOrNull() !in setOf("select", "with")) return Result.Rejected("apenas SELECT é permitido")
        if (words.any { it in FORBIDDEN }) return Result.Rejected("apenas SELECT é permitido")
        if (words.any { it.startsWith("sqlite_") || it.startsWith("pragma_") }) {
            return Result.Rejected("objeto do sistema não permitido")
        }
        val otherObjects = knownObjects - VIEW
        if (words.any { it in otherObjects }) return Result.Rejected("apenas a view $VIEW pode ser consultada")
        if (VIEW !in words) return Result.Rejected("a consulta precisa usar a view $VIEW")
        return Result.Ok(text)
    }

    private class Tokens(val words: List<String>, val statementBreak: Boolean, val comment: Boolean)

    /** Separa palavras e identificadores, ignorando o conteúdo de strings '…'. Nulo se uma aspa não fechar. */
    private fun tokenize(sql: String): Tokens? {
        val words = mutableListOf<String>()
        var statementBreak = false
        var comment = false
        var i = 0
        while (i < sql.length) {
            val c = sql[i]
            when {
                c == '\'' -> { // string literal: pula ('' é aspa escapada)
                    i++
                    while (true) {
                        if (i >= sql.length) return null
                        if (sql[i] == '\'') {
                            if (i + 1 < sql.length && sql[i + 1] == '\'') i += 2 else break
                        } else {
                            i++
                        }
                    }
                    i++
                }
                c == '"' || c == '`' || c == '[' -> { // identificador entre aspas: vira palavra
                    val close = if (c == '[') ']' else c
                    val end = sql.indexOf(close, i + 1)
                    if (end < 0) return null
                    words += sql.substring(i + 1, end).lowercase()
                    i = end + 1
                }
                c == '-' && sql.startsWith("--", i) -> { comment = true; i += 2 }
                c == '/' && sql.startsWith("/*", i) -> { comment = true; i += 2 }
                c == ';' -> { statementBreak = true; i++ }
                c.isLetter() || c == '_' -> {
                    val start = i
                    while (i < sql.length && (sql[i].isLetterOrDigit() || sql[i] == '_' || sql[i] == '$')) i++
                    words += sql.substring(start, i).lowercase()
                }
                else -> i++
            }
        }
        return Tokens(words, statementBreak, comment)
    }
}
