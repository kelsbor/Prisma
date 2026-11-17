package br.com.prisma.financas.domain.model

/** Validação do formulário de credenciais (sem chamadas de rede). */
object CredentialsInput {
    const val MAX_ITEMS = 5

    private val UUID = Regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
    private val SEPARATORS = Regex("[\\s,;]+")

    fun isUuid(value: String): Boolean = UUID.matches(value)

    /** Divide um texto colado em vários itemIds (vírgula, ponto e vírgula, espaço ou quebra de linha). */
    fun splitIds(raw: String): List<String> = raw.split(SEPARATORS).map { it.trim() }.filter { it.isNotEmpty() }

    data class Result(
        val clientIdError: String? = null,
        val clientSecretError: String? = null,
        val itemErrors: Map<Int, String> = emptyMap(),
        val formError: String? = null,
    ) {
        val isValid: Boolean
            get() = clientIdError == null && clientSecretError == null && itemErrors.isEmpty() && formError == null
    }

    fun validate(clientId: String, clientSecret: String, itemIds: List<String>): Result {
        val ids = itemIds.map { it.trim() }
        val itemErrors = mutableMapOf<Int, String>()
        val seen = mutableSetOf<String>()
        ids.forEachIndexed { i, id ->
            when {
                id.isEmpty() -> if (ids.size > 1) itemErrors[i] = "Preencha ou remova esta conexão"
                !isUuid(id) -> itemErrors[i] = "Formato inválido (esperado um ID como 4f4f3b48-…)"
                !seen.add(id.lowercase()) -> itemErrors[i] = "Conexão repetida"
            }
        }
        val nonEmpty = ids.count { it.isNotEmpty() }
        return Result(
            clientIdError = if (clientId.isBlank()) "Informe o Client ID" else null,
            clientSecretError = if (clientSecret.isBlank()) "Informe o Client Secret" else null,
            itemErrors = itemErrors,
            formError = when {
                nonEmpty == 0 -> "Informe pelo menos uma conexão (itemId)"
                nonEmpty > MAX_ITEMS -> "O Meu Pluggy permite no máximo $MAX_ITEMS conexões"
                else -> null
            },
        )
    }
}
