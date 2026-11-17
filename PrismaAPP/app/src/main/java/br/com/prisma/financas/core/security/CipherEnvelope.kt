package br.com.prisma.financas.core.security

/**
 * Formato binário de um dado cifrado: [versão][tamanho do IV][IV][ciphertext+tag].
 * Separado do Keystore para poder ser testado na JVM.
 */
object CipherEnvelope {
    const val VERSION: Byte = 1

    fun pack(iv: ByteArray, cipherText: ByteArray): ByteArray {
        require(iv.isNotEmpty() && iv.size <= 32) { "IV inválido" }
        return byteArrayOf(VERSION, iv.size.toByte()) + iv + cipherText
    }

    fun unpack(blob: ByteArray): Pair<ByteArray, ByteArray> {
        require(blob.size > 2) { "Dado cifrado inválido" }
        require(blob[0] == VERSION) { "Versão de cifra não suportada" }
        val ivSize = blob[1].toInt()
        require(ivSize in 1..32 && blob.size > 2 + ivSize) { "Dado cifrado inválido" }
        val iv = blob.copyOfRange(2, 2 + ivSize)
        val cipherText = blob.copyOfRange(2 + ivSize, blob.size)
        return iv to cipherText
    }
}
