package br.com.prisma.financas.ui.common

import br.com.prisma.financas.core.money.BrlFormatter
import br.com.prisma.financas.core.money.Money
import br.com.prisma.financas.core.time.BrazilTime
import br.com.prisma.financas.domain.model.ItemHealth
import java.time.Instant
import java.time.LocalDate
import java.time.YearMonth
import java.time.format.DateTimeFormatter
import java.time.temporal.ChronoUnit
import java.util.Locale

private val PT_BR: Locale = Locale.forLanguageTag("pt-BR")
private val DATE_TIME = DateTimeFormatter.ofPattern("dd/MM/yyyy 'às' HH:mm", PT_BR)
private val SHORT_DATE_TIME = DateTimeFormatter.ofPattern("dd/MM 'às' HH:mm", PT_BR)
private val DATE = DateTimeFormatter.ofPattern("dd/MM/yyyy", PT_BR)
private val SHORT_DATE = DateTimeFormatter.ofPattern("dd/MM", PT_BR)
private val DAY_HEADER = DateTimeFormatter.ofPattern("EEEE, d 'de' MMMM", PT_BR)
private val DAY_HEADER_YEAR = DateTimeFormatter.ofPattern("EEEE, d 'de' MMMM 'de' yyyy", PT_BR)
private val MONTH_YEAR = DateTimeFormatter.ofPattern("MMMM 'de' yyyy", PT_BR)
private val MONTH_SHORT = DateTimeFormatter.ofPattern("MMM", PT_BR)
private val MONTH_NAME = DateTimeFormatter.ofPattern("MMMM", PT_BR)

fun Money.brl(showPlus: Boolean = false): String = BrlFormatter.format(this, showPlus)

fun Instant.formatDateTime(): String = DATE_TIME.format(atZone(BrazilTime.ZONE))
fun Instant.formatShortDateTime(): String = SHORT_DATE_TIME.format(atZone(BrazilTime.ZONE))
fun Instant.formatDate(): String = DATE.format(atZone(BrazilTime.ZONE))
fun LocalDate.formatDate(): String = DATE.format(this)
fun LocalDate.formatShortDate(): String = SHORT_DATE.format(this)

fun String.capitalizeFirst(): String = replaceFirstChar { if (it.isLowerCase()) it.titlecase(PT_BR) else it.toString() }

/** "Hoje", "Ontem" ou "Sábado, 8 de novembro" (com ano se não for o ano atual). */
fun LocalDate.dayHeader(today: LocalDate): String = when (this) {
    today -> "Hoje"
    today.minusDays(1) -> "Ontem"
    else -> (if (year == today.year) DAY_HEADER else DAY_HEADER_YEAR).format(this).capitalizeFirst()
}

fun YearMonth.label(): String = MONTH_YEAR.format(atDay(1)).capitalizeFirst()
fun YearMonth.shortLabel(): String = MONTH_SHORT.format(atDay(1)).trimEnd('.').capitalizeFirst()
fun YearMonth.monthName(): String = MONTH_NAME.format(atDay(1))

/** "agora mesmo", "há 5 min", "há 3 h", "ontem", ou a data. */
fun relativeTime(epochMillis: Long, nowMillis: Long): String {
    val then = Instant.ofEpochMilli(epochMillis)
    val now = Instant.ofEpochMilli(nowMillis)
    val minutes = ChronoUnit.MINUTES.between(then, now)
    return when {
        minutes < 1 -> "agora mesmo"
        minutes < 60 -> "há $minutes min"
        minutes < 24 * 60 -> "há ${minutes / 60} h"
        BrazilTime.dateOf(then) == BrazilTime.dateOf(now).minusDays(1) -> "ontem"
        else -> "em ${then.formatDate()}"
    }
}

fun ItemHealth.label(): String = when (this) {
    ItemHealth.OK -> "Atualizada"
    ItemHealth.UPDATING -> "Atualizando"
    ItemHealth.WARNING -> "Atenção"
    ItemHealth.ERROR -> "Com erro"
    ItemHealth.EXPIRED -> "Autorização expirada"
}
