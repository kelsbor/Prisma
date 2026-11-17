package br.com.prisma.financas.core.time

/** Relógio de parede (epoch millis). Injetável para testes. */
fun interface Clock {
    fun nowMillis(): Long
}
