package br.com.prisma.financas.domain.model

/**
 * Nome do banco de uma conexão.
 * - Conexão direta (conector ≠ MeuPluggy): o nome do conector já é o banco.
 * - Meu Pluggy: o conector é sempre "MeuPluggy" e a API não informa o banco; como o Meu Pluggy
 *   cria uma conexão por banco, usa o nome da conta bancária da conexão até o " - "
 *   (ex.: "Nu Pagamentos S.A. - Instituição de Pagamento" → "Nu Pagamentos S.A.").
 *   O cartão da mesma conexão herda esse nome.
 */
object BankNames {
    private const val MEU_PLUGGY = "MeuPluggy"

    fun infer(connectorName: String?, accounts: List<SourceAccount>): String? {
        val connector = connectorName?.trim().orEmpty()
        if (connector.isNotEmpty() && !connector.equals(MEU_PLUGGY, ignoreCase = true)) return connector
        return accounts.firstOrNull { it.type == AccountType.BANK }?.name?.let(::shortName)
    }

    fun shortName(accountName: String): String? =
        accountName.substringBefore(" - ").trim().ifEmpty { null }
}
