package br.com.prisma.financas.assistant

import br.com.prisma.financas.core.time.Clock
import kotlinx.coroutines.test.runTest
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import retrofit2.HttpException
import retrofit2.Response
import java.io.IOException

class AssistantOrchestratorTest {
    private val sqlOk = "SELECT ROUND(SUM(valor_gasto), 2) AS total FROM vw_registers WHERE ano = 2026 AND mes = 10"

    private class FakeApi : AssistantApi {
        val sqlReplies = ArrayDeque<Any>()
        var answer: Any = ResponderResponse("ok", "Você gastou R$ 123,40 em outubro.")
        val sqlRequests = mutableListOf<GerarSqlRequest>()
        var responderRequest: ResponderRequest? = null

        override suspend fun gerarSql(body: GerarSqlRequest): GerarSqlResponse {
            sqlRequests += body
            return when (val r = sqlReplies.removeFirst()) {
                is Exception -> throw r
                else -> r as GerarSqlResponse
            }
        }

        override suspend fun responder(body: ResponderRequest): ResponderResponse {
            responderRequest = body
            return when (val r = answer) {
                is Exception -> throw r
                else -> r as ResponderResponse
            }
        }
    }

    private class FakeRunner(var result: QueryResult) : QueryRunner {
        val executed = mutableListOf<String>()
        var failFirst: String? = null
        override suspend fun knownObjects() = setOf("vw_registers", "item_dim", "transaction_fact")
        override suspend fun context() = Contexto(categorias = listOf("Supermercado"))
        override suspend fun run(sql: String, maxRows: Int, timeoutMs: Long): QueryResult {
            executed += sql
            failFirst?.let { failFirst = null; throw QueryException(it) }
            return result
        }
    }

    private val api = FakeApi()
    private val runner = FakeRunner(QueryResult(listOf("total"), listOf(listOf(123.4)), false))
    private var now = 1_000_000L
    private val clock = Clock { now }

    private fun orchestrator(config: AssistantConfig = AssistantConfig("http://x/", "t".repeat(32))) =
        AssistantOrchestrator(api, runner, config, clock, AssistantLimits(clock))

    @Test fun `fluxo completo responde e guarda o sql`() = runTest {
        api.sqlReplies += GerarSqlResponse("ok", sqlOk)
        val reply = orchestrator().ask("Quanto gastei em outubro?", emptyList())
        assertEquals(ReplyKind.ANSWER, reply.kind)
        assertEquals("Você gastou R$ 123,40 em outubro.", reply.text)
        assertEquals(sqlOk, reply.sql)
        assertEquals(listOf("Supermercado"), api.sqlRequests.single().contexto.categorias)
        assertEquals(1, api.responderRequest!!.totalLinhas)
    }

    @Test fun `fora do escopo e bloqueado nao executam nada`() = runTest {
        api.sqlReplies += GerarSqlResponse("fora_do_escopo", mensagem = "Só sobre transações.")
        val reply = orchestrator().ask("Capital da França?", emptyList())
        assertEquals(ReplyKind.OUT_OF_SCOPE, reply.kind)
        assertTrue(runner.executed.isEmpty())
    }

    @Test fun `sql perigoso do servidor nunca e executado nem gera nova chamada`() = runTest {
        api.sqlReplies += GerarSqlResponse("ok", "SELECT * FROM item_dim")
        val reply = orchestrator().ask("Liste tudo", emptyList())
        assertEquals(ReplyKind.DONT_KNOW, reply.kind)
        assertTrue(runner.executed.isEmpty())
        assertEquals(1, api.sqlRequests.size) // a correção de SQL fora das regras é do servidor
    }

    @Test fun `erro ao executar pede uma correcao`() = runTest {
        runner.failFirst = "no such column: valorx"
        api.sqlReplies += GerarSqlResponse("ok", sqlOk.replace("valor_gasto", "valorx"))
        api.sqlReplies += GerarSqlResponse("ok", sqlOk)
        val reply = orchestrator().ask("Quanto gastei em outubro?", emptyList())
        assertEquals(ReplyKind.ANSWER, reply.kind)
        assertEquals("no such column: valorx", api.sqlRequests[1].erroAnterior!!.erro)
    }

    @Test fun `resultado vazio responde nao encontrei sem chamar o redator`() = runTest {
        runner.result = QueryResult(listOf("total"), listOf(listOf(null)), false)
        api.sqlReplies += GerarSqlResponse("ok", sqlOk)
        val reply = orchestrator().ask("Quanto gastei em 1990?", emptyList())
        assertEquals(AssistantOrchestrator.NOT_FOUND, reply.text)
        assertNull(api.responderRequest)
    }

    @Test fun `guardiao descarta valor inventado e mostra os dados`() = runTest {
        api.sqlReplies += GerarSqlResponse("ok", sqlOk)
        api.answer = ResponderResponse("ok", "Você gastou R$ 999,99.")
        val reply = orchestrator().ask("Quanto gastei em outubro?", emptyList())
        assertEquals(ReplyKind.DONT_KNOW, reply.kind)
        assertEquals(AssistantOrchestrator.UNGROUNDED, reply.text)
        assertEquals(runner.result, reply.table)
    }

    @Test fun `limites locais`() = runTest {
        val o = orchestrator()
        assertEquals(ReplyKind.LIMIT, o.ask("oi", emptyList()).kind)
        assertEquals(ReplyKind.LIMIT, o.ask("x".repeat(301), emptyList()).kind)
        api.sqlReplies += GerarSqlResponse("ok", sqlOk)
        assertEquals(ReplyKind.ANSWER, o.ask("Quanto gastei?", emptyList()).kind)
        assertEquals(ReplyKind.LIMIT, o.ask("Quanto gastei?", emptyList()).kind) // menos de 3 s depois
    }

    @Test fun `erros de rede e do servidor viram mensagens amigaveis`() = runTest {
        api.sqlReplies += IOException("offline")
        assertEquals(AssistantOrchestrator.OFFLINE, orchestrator().ask("Quanto gastei?", emptyList()).text)

        now += 10_000
        val body = """{"detail":"O limite de uso do Gemini foi atingido. Aguarde um minuto."}""".toResponseBody()
        api.sqlReplies += HttpException(Response.error<Any>(429, body))
        val limited = orchestrator().ask("Quanto gastei?", emptyList())
        assertEquals(ReplyKind.LIMIT, limited.kind)
        assertEquals("O limite de uso do Gemini foi atingido. Aguarde um minuto.", limited.text)

        api.sqlReplies += HttpException(Response.error<Any>(401, "".toResponseBody()))
        assertEquals(AssistantOrchestrator.UNAUTHORIZED, orchestrator().ask("Quanto gastei?", emptyList()).text)
    }

    @Test fun `sem configuracao nao chama nada`() = runTest {
        val reply = orchestrator(AssistantConfig("", "")).ask("Quanto gastei?", emptyList())
        assertEquals(AssistantOrchestrator.NOT_CONFIGURED, reply.text)
        assertTrue(api.sqlRequests.isEmpty())
    }
}
