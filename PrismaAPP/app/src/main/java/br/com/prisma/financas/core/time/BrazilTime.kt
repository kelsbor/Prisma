package br.com.prisma.financas.core.time

import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId

/** Datas das transações são interpretadas no fuso de Brasília (o app é em BRL). */
object BrazilTime {
    val ZONE: ZoneId = ZoneId.of("America/Sao_Paulo")

    fun today(clock: Clock): LocalDate = Instant.ofEpochMilli(clock.nowMillis()).atZone(ZONE).toLocalDate()

    fun dateOf(instant: Instant): LocalDate = instant.atZone(ZONE).toLocalDate()
}
