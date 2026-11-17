package br.com.prisma.financas.assistant

import java.math.BigDecimal
import java.math.RoundingMode

/**
 * Guardião da resposta: confere que todo valor em reais citado no texto existe no resultado da consulta.
 * Se o modelo citar um valor que não está nos dados (inventou ou calculou), a resposta é descartada
 * e o usuário recebe "não sei" + a tabela com os dados reais.
 */
object AnswerGuardian {
    const val MAX_LENGTH = 1200

    private val MONEY = Regex("""R\$\s?-?\s?(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{1,2}))?""")

    sealed interface Verdict {
        data object Grounded : Verdict
        data class Ungrounded(val reason: String) : Verdict
    }

    fun check(answer: String, result: QueryResult): Verdict {
        if (answer.isBlank()) return Verdict.Ungrounded("resposta vazia")
        if (answer.length > MAX_LENGTH) return Verdict.Ungrounded("resposta longa demais")

        val cited = MONEY.findAll(answer).map { m ->
            val inteiro = m.groupValues[1].replace(".", "")
            val centavos = m.groupValues[2].padEnd(2, '0').ifEmpty { "00" }
            BigDecimal("$inteiro.$centavos").setScale(2)
        }.toList()
        if (cited.isEmpty()) return Verdict.Grounded

        val allowed = allowedValues(result)
        val missing = cited.filterNot { it in allowed }
        return if (missing.isEmpty()) Verdict.Grounded else Verdict.Ungrounded("valor não encontrado nos dados")
    }

    /** Valores numéricos do resultado em reais (absoluto, 2 casas), aceitando também colunas em centavos. */
    private fun allowedValues(result: QueryResult): Set<BigDecimal> = buildSet {
        for (row in result.rows) for (cell in row) {
            val value = when (cell) {
                is Long -> BigDecimal.valueOf(cell)
                is Int -> BigDecimal.valueOf(cell.toLong())
                is Double -> if (cell.isFinite()) BigDecimal.valueOf(cell) else null
                else -> null
            } ?: continue
            add(value.abs().setScale(2, RoundingMode.HALF_UP))
            if (cell is Long) add(value.abs().movePointLeft(2).setScale(2, RoundingMode.HALF_UP))
        }
    }
}
