package br.com.prisma.financas.domain.model

import kotlinx.serialization.Serializable

/** Credenciais da Pluggy. toString nunca expõe os valores. */
@Serializable
data class PluggyCredentials(
    val clientId: String,
    val clientSecret: String,
    val itemIds: List<String>,
) {
    override fun toString(): String = "PluggyCredentials(itens=${itemIds.size}, ***)"
}
