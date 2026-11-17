package br.com.prisma.financas.assistant

import br.com.prisma.financas.core.time.Clock

/**
 * Limites locais (o servidor também limita por minuto e por dia).
 * Evitam gasto à toa e cliques repetidos.
 */
class AssistantLimits(
    private val clock: Clock,
    private val maxPerHour: Int = MAX_PER_HOUR,
) {
    private val sent = ArrayDeque<Long>()
    private var lastAt = 0L

    /** Mensagem de bloqueio, ou nulo se a pergunta pode seguir. */
    @Synchronized
    fun check(question: String): String? {
        val text = question.trim()
        if (text.length < MIN_CHARS) return "Escreva uma pergunta um pouco mais completa."
        if (text.length > MAX_CHARS) return "A pergunta pode ter no máximo $MAX_CHARS caracteres."
        val now = clock.nowMillis()
        if (now - lastAt < COOLDOWN_MS) return "Aguarde um instante antes de perguntar de novo."
        while (sent.isNotEmpty() && now - sent.first() >= HOUR_MS) sent.removeFirst()
        if (sent.size >= maxPerHour) return "Você fez muitas perguntas na última hora. Tente mais tarde."
        sent.addLast(now)
        lastAt = now
        return null
    }

    companion object {
        const val MIN_CHARS = 3
        const val MAX_CHARS = 300
        const val COOLDOWN_MS = 3_000L
        const val MAX_PER_HOUR = 30
        private const val HOUR_MS = 3_600_000L
    }
}
