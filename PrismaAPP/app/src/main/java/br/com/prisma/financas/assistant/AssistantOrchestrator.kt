package br.com.prisma.financas.assistant

import br.com.prisma.financas.core.time.BrazilTime
import br.com.prisma.financas.core.time.Clock
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import retrofit2.HttpException
import java.io.IOException
import javax.inject.Inject
import kotlin.coroutines.cancellation.CancellationException

data class AssistantConfig(val url: String, val token: String) {
    val isConfigured: Boolean get() = url.isNotBlank() && token.isNotBlank()
}

enum class ReplyKind { ANSWER, DONT_KNOW, OUT_OF_SCOPE, BLOCKED, LIMIT, ERROR }

data class AssistantReply(
    val kind: ReplyKind,
    val text: String,
    /** SQL executado (para "Ver consulta"). */
    val sql: String? = null,
    /** Dados reais da consulta (mostrados na tela; também quando o guardião descarta a resposta). */
    val table: QueryResult? = null,
)

/**
 * O "script" do assistente. Para cada pergunta:
 * 1. limites locais → 2. servidor gera o SQL (Chamada 1) → 3. SqlGuard valida →
 * 4. executa no SQLite somente leitura (1 correção se der erro) → 5. resultado vazio = "não encontrei" →
 * 6. servidor redige a resposta (Chamada 2) → 7. AnswerGuardian confere os valores.
 */
class AssistantOrchestrator @Inject constructor(
    private val api: AssistantApi,
    private val runner: QueryRunner,
    private val config: AssistantConfig,
    private val clock: Clock,
    private val limits: AssistantLimits,
) {
    val isConfigured: Boolean get() = config.isConfigured

    suspend fun ask(question: String, history: List<Turno>): AssistantReply {
        if (!config.isConfigured) return AssistantReply(ReplyKind.ERROR, NOT_CONFIGURED)
        limits.check(question)?.let { return AssistantReply(ReplyKind.LIMIT, it) }
        val pergunta = question.trim()
        val hoje = BrazilTime.today(clock).toString()

        return try {
            val contexto = runner.context()
            val known = runner.knownObjects()
            var request = GerarSqlRequest(pergunta = pergunta, hoje = hoje, historico = history.takeLast(3), contexto = contexto)

            // O servidor já corrige sozinho um SQL fora das regras. Aqui só pedimos UMA correção
            // quando o SQL falha ao EXECUTAR no aparelho (erro que só o banco local conhece).
            var executed: Pair<String, QueryResult>? = null
            for (attempt in 0..1) {
                val generated = api.gerarSql(request)
                when (generated.status) {
                    "ok" -> Unit
                    "fora_do_escopo" -> return AssistantReply(ReplyKind.OUT_OF_SCOPE, generated.mensagem ?: OUT_OF_SCOPE)
                    "bloqueado" -> return AssistantReply(ReplyKind.BLOCKED, generated.mensagem ?: BLOCKED)
                    else -> return AssistantReply(ReplyKind.DONT_KNOW, generated.mensagem ?: DONT_KNOW)
                }
                // Reprovado aqui = o servidor deixou passar algo indevido: não executa nem insiste.
                val sql = (SqlGuard.check(generated.sql.orEmpty(), known) as? SqlGuard.Result.Ok)?.sql
                    ?: return AssistantReply(ReplyKind.DONT_KNOW, DONT_KNOW)
                try {
                    executed = sql to runner.run(sql, MAX_ROWS, QUERY_TIMEOUT_MS)
                    break
                } catch (e: QueryException) {
                    request = request.copy(erroAnterior = ErroAnterior(sql, e.message.orEmpty().take(300)))
                }
            }
            val (sql, result) = executed ?: return AssistantReply(ReplyKind.DONT_KNOW, DONT_KNOW)
            if (result.isEmpty) return AssistantReply(ReplyKind.DONT_KNOW, NOT_FOUND, sql = sql, table = result)

            val sentRows = result.rows.take(MAX_ROWS_TO_MODEL)
            val answer = api.responder(
                ResponderRequest(
                    pergunta = pergunta,
                    hoje = hoje,
                    sql = sql,
                    colunas = result.columns,
                    linhas = sentRows.map { row -> row.map(::toJson) },
                    totalLinhas = result.rows.size,
                ),
            )
            if (answer.status != "ok") return AssistantReply(ReplyKind.DONT_KNOW, answer.resposta, sql, result)
            when (AnswerGuardian.check(answer.resposta, QueryResult(result.columns, sentRows, false))) {
                AnswerGuardian.Verdict.Grounded -> AssistantReply(ReplyKind.ANSWER, answer.resposta.trim(), sql, result)
                is AnswerGuardian.Verdict.Ungrounded -> AssistantReply(ReplyKind.DONT_KNOW, UNGROUNDED, sql, result)
            }
        } catch (e: CancellationException) {
            throw e
        } catch (e: QueryException) {
            AssistantReply(ReplyKind.ERROR, e.message ?: DONT_KNOW)
        } catch (e: HttpException) {
            httpError(e)
        } catch (_: IOException) {
            AssistantReply(ReplyKind.ERROR, OFFLINE)
        } catch (_: kotlinx.serialization.SerializationException) {
            AssistantReply(ReplyKind.ERROR, UNAVAILABLE)
        }
    }

    private fun httpError(e: HttpException): AssistantReply = when (e.code()) {
        401, 403 -> AssistantReply(ReplyKind.ERROR, UNAUTHORIZED)
        429 -> AssistantReply(ReplyKind.LIMIT, detail(e) ?: RATE_LIMITED)
        400, 413, 422 -> AssistantReply(ReplyKind.DONT_KNOW, DONT_KNOW)
        else -> AssistantReply(ReplyKind.ERROR, UNAVAILABLE)
    }

    /** Mensagem amigável que o servidor manda em {"detail": "..."} (só para 429). */
    private fun detail(e: HttpException): String? = runCatching {
        val body = e.response()?.errorBody()?.string()?.take(1000) ?: return null
        Json.parseToJsonElement(body).jsonObject["detail"]?.jsonPrimitive?.content?.take(200)
    }.getOrNull()

    private fun toJson(cell: Any?): JsonElement = when (cell) {
        null -> JsonNull
        is Long -> JsonPrimitive(cell)
        is Double -> if (cell.isFinite()) JsonPrimitive(cell) else JsonNull
        is Number -> JsonPrimitive(cell)
        else -> JsonPrimitive(cell.toString())
    }

    companion object {
        const val MAX_ROWS = 200
        const val MAX_ROWS_TO_MODEL = 50
        const val QUERY_TIMEOUT_MS = 3_000L

        const val NOT_CONFIGURED = "O assistente não está configurado neste aparelho."
        const val OUT_OF_SCOPE = "Só consigo responder perguntas sobre as suas transações no app."
        const val BLOCKED = "Não posso atender esse pedido."
        const val DONT_KNOW = "Não sei responder isso com segurança. Tente perguntar de outro jeito."
        const val NOT_FOUND = "Não encontrei registros para essa pergunta."
        const val UNGROUNDED = "Não consegui confirmar a resposta com segurança. Veja abaixo os dados que encontrei."
        const val UNAUTHORIZED = "Este app não está autorizado no servidor do assistente."
        const val RATE_LIMITED = "Muitas perguntas em pouco tempo. Aguarde um instante."
        const val OFFLINE = "Não consegui falar com o servidor do assistente. Verifique a conexão."
        const val UNAVAILABLE = "O assistente está indisponível no momento. Tente mais tarde."
    }
}
