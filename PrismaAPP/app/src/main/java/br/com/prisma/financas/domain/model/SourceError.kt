package br.com.prisma.financas.domain.model

/** Erros da fonte de dados, independentes de HTTP/Retrofit. */
sealed interface SourceError {
    data object InvalidCredentials : SourceError
    data object Forbidden : SourceError
    data object ItemNotFound : SourceError
    data object AuthorizationExpired : SourceError
    data class RateLimited(val retryAfterSeconds: Long?) : SourceError
    data object Network : SourceError
    data object Timeout : SourceError
    data class Server(val httpCode: Int) : SourceError
    data class Http(val httpCode: Int) : SourceError
    data object UnexpectedResponse : SourceError

    /** Erros que afetam todas as conexões (não só um item). */
    val isGlobal: Boolean
        get() = this is InvalidCredentials || this is RateLimited || this is Network || this is Timeout
}

class SourceException(val error: SourceError) : Exception(error.toString())
