package br.com.prisma.financas.data.remote

import br.com.prisma.financas.data.source.PluggyTransactionSource
import br.com.prisma.financas.domain.model.ConnectionTestResult
import br.com.prisma.financas.domain.model.ItemCheck
import br.com.prisma.financas.domain.model.ItemHealth
import br.com.prisma.financas.domain.model.SourceError
import kotlinx.coroutines.test.runTest
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import java.time.Instant

class PluggyConnectionTest {
    private lateinit var server: MockWebServer
    private lateinit var client: PluggyClient
    private lateinit var source: PluggyTransactionSource
    private val now = Instant.parse("2026-11-07T12:00:00Z").toEpochMilli()

    @Before fun setUp() {
        server = MockWebServer()
        server.start()
        val api = Retrofit.Builder()
            .baseUrl(server.url("/"))
            .client(OkHttpClient())
            .addConverterFactory(PluggyJson.instance.asConverterFactory("application/json".toMediaType()))
            .build()
            .create(PluggyApi::class.java)
        client = PluggyClient(api) { now }
        source = PluggyTransactionSource(client) { now }
    }

    @After fun tearDown() {
        server.close()
    }

    private fun enqueue(code: Int, body: String, vararg headers: Pair<String, String>) {
        val builder = MockResponse.Builder().code(code).body(body).addHeader("Content-Type", "application/json")
        headers.forEach { (k, v) -> builder.addHeader(k, v) }
        server.enqueue(builder.build())
    }

    @Test fun `conexao ok traz banco, status e contas`() = runTest {
        enqueue(200, PluggyFixtures.auth("key-1"))
        enqueue(200, PluggyFixtures.ITEM)
        enqueue(200, PluggyFixtures.ACCOUNTS)

        val result = source.testConnection(PluggyFixtures.CREDENTIALS) as ConnectionTestResult.Success
        val item = result.items.single() as ItemCheck.Ok
        assertEquals("Banco Teste", item.connectorName)
        assertEquals(ItemHealth.OK, item.health)
        assertEquals(2, item.accounts.size)
        assertTrue(item.accounts[0].isCreditCard)

        assertEquals("/auth", server.takeRequest().url.encodedPath)
        val itemReq = server.takeRequest()
        assertEquals("/items/${PluggyFixtures.ITEM_ID}", itemReq.url.encodedPath)
        assertEquals("key-1", itemReq.headers[PluggyApi.API_KEY_HEADER])
        val accReq = server.takeRequest()
        assertEquals(PluggyFixtures.ITEM_ID, accReq.url.queryParameter("itemId"))
    }

    @Test fun `credenciais invalidas`() = runTest {
        enqueue(401, PluggyFixtures.error(401))
        val result = source.testConnection(PluggyFixtures.CREDENTIALS)
        assertEquals(ConnectionTestResult.Failure(SourceError.InvalidCredentials), result)
    }

    @Test fun `item inexistente falha so aquela conexao`() = runTest {
        enqueue(200, PluggyFixtures.auth("key-1"))
        enqueue(404, PluggyFixtures.error(404))
        val result = source.testConnection(PluggyFixtures.CREDENTIALS) as ConnectionTestResult.Success
        assertEquals(ItemCheck.Failed(PluggyFixtures.ITEM_ID, SourceError.ItemNotFound), result.items.single())
    }

    @Test fun `401 em chamada autenticada renova a apiKey uma vez`() = runTest {
        enqueue(200, PluggyFixtures.auth("key-1"))
        enqueue(401, PluggyFixtures.error(401))
        enqueue(200, PluggyFixtures.auth("key-2"))
        enqueue(200, PluggyFixtures.ITEM)
        enqueue(200, PluggyFixtures.ACCOUNTS)

        val result = source.testConnection(PluggyFixtures.CREDENTIALS) as ConnectionTestResult.Success
        assertTrue(result.allOk)
        assertEquals(5, server.requestCount)
        server.takeRequest(); server.takeRequest(); server.takeRequest()
        assertEquals("key-2", server.takeRequest().headers[PluggyApi.API_KEY_HEADER])
    }

    @Test fun `401 repetido nao entra em loop`() = runTest {
        enqueue(200, PluggyFixtures.auth("key-1"))
        enqueue(401, PluggyFixtures.error(401))
        enqueue(200, PluggyFixtures.auth("key-2"))
        enqueue(401, PluggyFixtures.error(401))

        val result = source.testConnection(PluggyFixtures.CREDENTIALS)
        assertEquals(ConnectionTestResult.Failure(SourceError.InvalidCredentials), result)
        assertEquals(4, server.requestCount)
    }

    @Test fun `rate limit usa RateLimit-Reset`() = runTest {
        enqueue(429, "Too many requests", "RateLimit-Reset" to "42", "Retry-After" to "60")
        val result = source.testConnection(PluggyFixtures.CREDENTIALS)
        assertEquals(ConnectionTestResult.Failure(SourceError.RateLimited(42)), result)
    }

    @Test fun `autorizacao expirada pelo codeDescription`() = runTest {
        enqueue(200, PluggyFixtures.auth("key-1"))
        enqueue(400, PluggyFixtures.error(400, "USER_AUTHORIZATION_EXPIRED"))
        val result = source.testConnection(PluggyFixtures.CREDENTIALS) as ConnectionTestResult.Success
        assertEquals(ItemCheck.Failed(PluggyFixtures.ITEM_ID, SourceError.AuthorizationExpired), result.items.single())
    }

    @Test fun `erro 503 nas contas`() = runTest {
        enqueue(200, PluggyFixtures.auth("key-1"))
        enqueue(200, PluggyFixtures.ITEM)
        enqueue(503, PluggyFixtures.error(503))
        val result = source.testConnection(PluggyFixtures.CREDENTIALS) as ConnectionTestResult.Success
        assertEquals(ItemCheck.Failed(PluggyFixtures.ITEM_ID, SourceError.Server(503)), result.items.single())
    }

    @Test fun `resposta invalida`() = runTest {
        enqueue(200, """{"semApiKey": true}""")
        val result = source.testConnection(PluggyFixtures.CREDENTIALS)
        assertEquals(ConnectionTestResult.Failure(SourceError.UnexpectedResponse), result)
    }

    @Test fun `sem rede`() = runTest {
        server.close()
        val result = source.testConnection(PluggyFixtures.CREDENTIALS)
        assertEquals(ConnectionTestResult.Failure(SourceError.Network), result)
    }

    @Test fun `transacoes seguem o cursor next ate acabar`() = runTest {
        val tx = { id: String -> """{"id":"$id","date":"2026-11-01T12:00:00.000Z","description":"t","amount":1,"type":"DEBIT"}""" }
        enqueue(200, PluggyFixtures.auth("key-1"))
        enqueue(200, """{"results":[${tx("a")},${tx("b")}],"next":"?accountId=acc-1&after=abc%3D%3D"}""")
        enqueue(200, """{"results":[${tx("c")}],"next":null}""")

        val list = source.fetchTransactions(PluggyFixtures.CREDENTIALS, "acc-1", java.time.LocalDate.of(2026, 10, 1))
        assertEquals(listOf("a", "b", "c"), list.map { it.id })

        server.takeRequest() // auth
        val first = server.takeRequest()
        assertEquals("/v2/transactions", first.url.encodedPath)
        assertEquals("2026-10-01", first.url.queryParameter("dateFrom"))
        assertEquals(null, first.url.queryParameter("after"))
        val second = server.takeRequest()
        assertEquals("abc==", second.url.queryParameter("after"))
    }

    @Test fun `extrai o cursor da query string`() {
        assertEquals("x/y=", PluggyClient.extractAfter("?accountId=1&after=x%2Fy%3D"))
        assertEquals(null, PluggyClient.extractAfter("?accountId=1"))
    }

    @Test fun `apiKey e reaproveitada dentro da validade`() = runTest {
        enqueue(200, PluggyFixtures.auth("key-1"))
        val a = client.apiKey(PluggyFixtures.CREDENTIALS)
        val b = client.apiKey(PluggyFixtures.CREDENTIALS)
        assertEquals("key-1", a)
        assertEquals(a, b)
        assertEquals(1, server.requestCount)
    }
}
