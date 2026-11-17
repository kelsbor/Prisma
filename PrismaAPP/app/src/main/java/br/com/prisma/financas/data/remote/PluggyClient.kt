package br.com.prisma.financas.data.remote

import br.com.prisma.financas.core.time.Clock
import br.com.prisma.financas.data.remote.dto.AccountsResponse
import br.com.prisma.financas.data.remote.dto.AuthRequest
import br.com.prisma.financas.data.remote.dto.CategoryDto
import br.com.prisma.financas.data.remote.dto.ItemDto
import br.com.prisma.financas.data.remote.dto.PluggyErrorDto
import br.com.prisma.financas.data.remote.dto.TransactionDto
import java.net.URLDecoder
import br.com.prisma.financas.domain.model.PluggyCredentials
import br.com.prisma.financas.domain.model.SourceError
import br.com.prisma.financas.domain.model.SourceException
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.serialization.SerializationException
import retrofit2.HttpException
import java.io.IOException
import java.io.InterruptedIOException
import java.security.MessageDigest
import javax.inject.Inject
import javax.inject.Singleton
import kotlin.coroutines.cancellation.CancellationException

/**
 * Cliente da Pluggy:
 * - mantém a apiKey só em memória e a renova antes de expirar (validade de 2h);
 * - em 401/403 renova a apiKey uma única vez e repete a chamada;
 * - converte falhas HTTP/rede em [SourceError] (nunca expõe corpo, chave ou segredo).
 */
@Singleton
class PluggyClient @Inject constructor(
    private val api: PluggyApi,
    private val clock: Clock,
) {
    enum class CallKind { AUTH, ITEM, ACCOUNTS, TRANSACTIONS, CATEGORIES }

    private class CachedKey(val fingerprint: String, val apiKey: String, val obtainedAt: Long)

    private val mutex = Mutex()
    private var cached: CachedKey? = null

    /** Autentica e devolve a apiKey (usa o cache se ainda for válida para essas credenciais). */
    suspend fun apiKey(credentials: PluggyCredentials, forceRefresh: Boolean = false): String = mutex.withLock {
        val fingerprint = fingerprint(credentials)
        val current = cached
        if (!forceRefresh && current != null && current.fingerprint == fingerprint &&
            clock.nowMillis() - current.obtainedAt < KEY_TTL_MS
        ) {
            return@withLock current.apiKey
        }
        val key = mapErrors(CallKind.AUTH) {
            api.auth(AuthRequest(credentials.clientId, credentials.clientSecret)).apiKey
        }
        if (key.isBlank()) throw SourceException(SourceError.UnexpectedResponse)
        cached = CachedKey(fingerprint, key, clock.nowMillis())
        key
    }

    fun clearCachedKey() {
        cached = null
    }

    suspend fun item(credentials: PluggyCredentials, itemId: String): ItemDto =
        authorized(credentials, CallKind.ITEM) { api.item(it, itemId) }

    suspend fun accounts(credentials: PluggyCredentials, itemId: String): AccountsResponse =
        authorized(credentials, CallKind.ACCOUNTS) { api.accounts(it, itemId) }

    /** Catálogo completo de categorias (segue as páginas, se houver mais de uma). */
    suspend fun allCategories(credentials: PluggyCredentials): List<CategoryDto> {
        val all = mutableListOf<CategoryDto>()
        var page = 1
        do {
            val current = page
            val res = authorized(credentials, CallKind.CATEGORIES) { api.categories(it, current) }
            all += res.results
            page++
        } while (current < res.totalPages && current < MAX_PAGES)
        return all
    }

    /** Busca todas as páginas de transações da conta, seguindo o cursor `next` até ele vir nulo. */
    suspend fun allTransactions(credentials: PluggyCredentials, accountId: String, dateFrom: String?): List<TransactionDto> {
        val all = mutableListOf<TransactionDto>()
        var after: String? = null
        var pages = 0
        do {
            val cursor = after
            val page = authorized(credentials, CallKind.TRANSACTIONS) { api.transactions(it, accountId, dateFrom, cursor) }
            all += page.results
            after = page.next?.let(::extractAfter)
            if (++pages > MAX_PAGES) throw SourceException(SourceError.UnexpectedResponse)
        } while (after != null && page.results.isNotEmpty())
        return all
    }

    /** Executa [block] com a apiKey; em 401/403 renova a chave uma vez e tenta de novo. */
    suspend fun <T> authorized(
        credentials: PluggyCredentials,
        kind: CallKind,
        block: suspend (apiKey: String) -> T,
    ): T {
        val first = apiKey(credentials)
        try {
            return block(first)
        } catch (e: HttpException) {
            if (e.code() != 401 && e.code() != 403) throw toSourceException(e, kind)
        } catch (e: Throwable) {
            throw toSourceException(e, kind)
        }
        val fresh = apiKey(credentials, forceRefresh = true)
        return mapErrors(kind) { block(fresh) }
    }

    private suspend fun <T> mapErrors(kind: CallKind, block: suspend () -> T): T =
        try {
            block()
        } catch (e: Throwable) {
            throw toSourceException(e, kind)
        }

    private fun toSourceException(t: Throwable, kind: CallKind): Throwable = when (t) {
        is CancellationException -> t
        is SourceException -> t
        else -> SourceException(classify(t, kind))
    }

    private fun classify(t: Throwable, kind: CallKind): SourceError = when (t) {
        is HttpException -> classifyHttp(t, kind)
        is InterruptedIOException -> SourceError.Timeout // inclui SocketTimeoutException
        is IOException -> SourceError.Network
        is SerializationException, is IllegalArgumentException -> SourceError.UnexpectedResponse
        else -> SourceError.UnexpectedResponse
    }

    private fun classifyHttp(e: HttpException, kind: CallKind): SourceError {
        val code = e.code()
        val body = readErrorBody(e)
        val marker = "${body?.codeDescription.orEmpty()} ${body?.message.orEmpty()}".uppercase()
        if ("AUTHORIZATION_EXPIRED" in marker) return SourceError.AuthorizationExpired
        return when {
            code == 401 -> SourceError.InvalidCredentials
            code == 403 -> SourceError.Forbidden
            code == 429 -> SourceError.RateLimited(retryAfterSeconds(e))
            (code == 404 || code == 400) && kind == CallKind.ITEM -> SourceError.ItemNotFound
            code >= 500 -> SourceError.Server(code)
            else -> SourceError.Http(code)
        }
    }

    private fun readErrorBody(e: HttpException): PluggyErrorDto? = runCatching {
        val text = e.response()?.errorBody()?.string() ?: return null
        PluggyJson.instance.decodeFromString(PluggyErrorDto.serializer(), text.take(4_000))
    }.getOrNull()

    private fun retryAfterSeconds(e: HttpException): Long? {
        val headers = e.response()?.headers() ?: return null
        return (headers["RateLimit-Reset"] ?: headers["Retry-After"])?.trim()?.toLongOrNull()
    }

    private fun fingerprint(c: PluggyCredentials): String {
        val digest = MessageDigest.getInstance("SHA-256").digest("${c.clientId}\u0000${c.clientSecret}".encodeToByteArray())
        return digest.joinToString("") { "%02x".format(it) }
    }

    companion object {
        /** A apiKey vale 2h; renovamos com 10 min de folga. */
        const val KEY_TTL_MS = 110 * 60 * 1000L

        /** Proteção contra cursor em loop (500 itens/página → 1 milhão de transações). */
        private const val MAX_PAGES = 2_000

        /** De "?accountId=x&after=abc%3D" extrai "abc=" (decodificado; o Retrofit codifica de novo). */
        internal fun extractAfter(next: String): String? =
            next.substringAfter('?', next).split('&')
                .firstOrNull { it.startsWith("after=") }
                ?.removePrefix("after=")
                ?.let { URLDecoder.decode(it, "UTF-8") }
                ?.takeIf { it.isNotEmpty() }
    }
}
