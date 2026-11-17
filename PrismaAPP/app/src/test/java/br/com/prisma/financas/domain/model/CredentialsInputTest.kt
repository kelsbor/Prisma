package br.com.prisma.financas.domain.model

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

class CredentialsInputTest {
    private val a = "11111111-2222-3333-4444-555555555555"
    private val b = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    @Test fun `entrada valida`() {
        assertTrue(CredentialsInput.validate("id", "secret", listOf(a, b)).isValid)
    }

    @Test fun `campos obrigatorios`() {
        val r = CredentialsInput.validate(" ", "", listOf(""))
        assertNotNull(r.clientIdError)
        assertNotNull(r.clientSecretError)
        assertNotNull(r.formError)
    }

    @Test fun `itemId com formato invalido e repetido`() {
        val r = CredentialsInput.validate("id", "s", listOf(a, "abc", a.uppercase()))
        assertFalse(r.isValid)
        assertEquals(setOf(1, 2), r.itemErrors.keys)
    }

    @Test fun `no maximo 5 conexoes`() {
        val ids = (1..6).map { "1111111$it-2222-3333-4444-555555555555" }
        assertNotNull(CredentialsInput.validate("id", "s", ids).formError)
    }

    @Test fun `colar varios ids separados`() {
        assertEquals(listOf(a, b), CredentialsInput.splitIds(" $a,\n$b ; "))
    }
}
