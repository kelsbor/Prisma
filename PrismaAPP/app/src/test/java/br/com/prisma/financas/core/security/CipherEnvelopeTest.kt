package br.com.prisma.financas.core.security

import org.junit.Assert.assertArrayEquals
import org.junit.Test

class CipherEnvelopeTest {

    @Test fun `pack e unpack preservam iv e ciphertext`() {
        val iv = ByteArray(12) { it.toByte() }
        val ct = ByteArray(40) { (it * 3).toByte() }
        val (iv2, ct2) = CipherEnvelope.unpack(CipherEnvelope.pack(iv, ct))
        assertArrayEquals(iv, iv2)
        assertArrayEquals(ct, ct2)
    }

    @Test(expected = IllegalArgumentException::class)
    fun `versao desconhecida e rejeitada`() {
        CipherEnvelope.unpack(byteArrayOf(9, 12) + ByteArray(30))
    }

    @Test(expected = IllegalArgumentException::class)
    fun `dado truncado e rejeitado`() {
        CipherEnvelope.unpack(byteArrayOf(CipherEnvelope.VERSION, 12, 1, 2))
    }
}
