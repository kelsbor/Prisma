package br.com.prisma.financas.data.remote

import br.com.prisma.financas.data.remote.dto.AccountsResponse
import br.com.prisma.financas.data.remote.dto.AuthRequest
import br.com.prisma.financas.data.remote.dto.AuthResponse
import br.com.prisma.financas.data.remote.dto.CategoriesResponse
import br.com.prisma.financas.data.remote.dto.ItemDto
import br.com.prisma.financas.data.remote.dto.TransactionsPage
import kotlinx.serialization.json.Json
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query

/** Endpoints da Pluggy (base https://api.pluggy.ai/). */
interface PluggyApi {
    @POST("auth")
    suspend fun auth(@Body body: AuthRequest): AuthResponse

    @GET("items/{id}")
    suspend fun item(@Header(API_KEY_HEADER) apiKey: String, @Path("id") itemId: String): ItemDto

    @GET("accounts")
    suspend fun accounts(@Header(API_KEY_HEADER) apiKey: String, @Query("itemId") itemId: String): AccountsResponse

    /** v2 com cursor. A v1 (GET /transactions) já responde 410 Gone. Parâmetros nulos são omitidos. */
    @GET("v2/transactions")
    suspend fun transactions(
        @Header(API_KEY_HEADER) apiKey: String,
        @Query("accountId") accountId: String,
        @Query("dateFrom") dateFrom: String?,
        @Query("after") after: String?,
    ): TransactionsPage

    @GET("categories")
    suspend fun categories(@Header(API_KEY_HEADER) apiKey: String, @Query("page") page: Int): CategoriesResponse

    companion object {
        const val BASE_URL = "https://api.pluggy.ai/"
        const val API_KEY_HEADER = "X-API-KEY"
    }
}

object PluggyJson {
    val instance: Json = Json {
        ignoreUnknownKeys = true
        coerceInputValues = true
        explicitNulls = false
    }
}
