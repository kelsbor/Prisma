package br.com.prisma.financas.domain.model

/** Mensagens claras para o usuário, sem detalhes técnicos sensíveis. */
fun SourceError.userMessage(): String = when (this) {
    SourceError.InvalidCredentials ->
        "Client ID ou Client Secret inválidos. Confira os dados da sua aplicação no Dashboard da Pluggy."
    SourceError.Forbidden ->
        "Sem permissão para acessar esta conexão. Verifique se ela foi autorizada para esta aplicação."
    SourceError.ItemNotFound ->
        "Conexão não encontrada. Confira o itemId copiado em Demo → Connected Items."
    SourceError.AuthorizationExpired ->
        "A autorização do Meu Pluggy expirou. Autorize de novo na aplicação Demo do Dashboard."
    is SourceError.RateLimited ->
        "Muitas tentativas seguidas. Tente novamente em ${retryAfterSeconds ?: 60} segundos."
    SourceError.Network ->
        "Sem conexão com a internet. Verifique sua rede e tente novamente."
    SourceError.Timeout ->
        "A Pluggy demorou para responder. Tente novamente em instantes."
    is SourceError.Server ->
        "A Pluggy está instável no momento (erro $httpCode). Tente mais tarde."
    is SourceError.Http ->
        "A Pluggy recusou a solicitação (erro $httpCode)."
    SourceError.UnexpectedResponse ->
        "A Pluggy respondeu em um formato inesperado. Tente novamente mais tarde."
}

/** Erros temporários: vale tentar de novo mais tarde. */
val SourceError.isRetryable: Boolean
    get() = this is SourceError.Network || this is SourceError.Timeout ||
        this is SourceError.Server || this is SourceError.RateLimited
