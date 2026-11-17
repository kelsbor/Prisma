package br.com.prisma.financas.assistant

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement
import retrofit2.http.Body
import retrofit2.http.POST

/** Servidor do assistente (pasta agent/). Só recebe a pergunta, o contexto e o resultado da consulta. */
interface AssistantApi {
    @POST("v1/gerar-sql")
    suspend fun gerarSql(@Body body: GerarSqlRequest): GerarSqlResponse

    @POST("v1/responder")
    suspend fun responder(@Body body: ResponderRequest): ResponderResponse
}

@Serializable
data class Turno(val pergunta: String, val sql: String? = null)

@Serializable
data class ErroAnterior(val sql: String, val erro: String)

@Serializable
data class Contexto(
    val categorias: List<String> = emptyList(),
    val contas: List<String> = emptyList(),
    val bancos: List<String> = emptyList(),
)

@Serializable
data class GerarSqlRequest(
    val pergunta: String,
    val hoje: String,
    val historico: List<Turno> = emptyList(),
    val contexto: Contexto = Contexto(),
    @SerialName("erro_anterior") val erroAnterior: ErroAnterior? = null,
)

@Serializable
data class GerarSqlResponse(val status: String, val sql: String? = null, val mensagem: String? = null)

@Serializable
data class ResponderRequest(
    val pergunta: String,
    val hoje: String,
    val sql: String,
    val colunas: List<String>,
    val linhas: List<List<JsonElement>>,
    @SerialName("total_linhas") val totalLinhas: Int,
)

@Serializable
data class ResponderResponse(val status: String, val resposta: String)
