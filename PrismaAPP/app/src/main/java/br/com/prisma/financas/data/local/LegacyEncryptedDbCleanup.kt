package br.com.prisma.financas.data.local

import android.content.Context
import br.com.prisma.financas.core.security.KeystoreCipher
import java.io.File

/**
 * Versões anteriores usavam SQLCipher. Um banco criptografado não abre com o SQLite comum,
 * então, se ainda existir a chave antiga, o banco antigo é apagado (os dados voltam na
 * próxima sincronização com a Pluggy) e a chave é descartada.
 */
object LegacyEncryptedDbCleanup {
    private const val LEGACY_KEY_FILE = "db.key.enc"
    private const val LEGACY_KEY_ALIAS = "prisma_db_key"

    fun run(context: Context) {
        val keyFile = File(context.noBackupFilesDir, LEGACY_KEY_FILE)
        if (!keyFile.exists()) return
        context.deleteDatabase(AppDatabase.NAME) // remove também -wal, -shm e -journal
        keyFile.delete()
        runCatching { KeystoreCipher(LEGACY_KEY_ALIAS).deleteKey() }
    }
}
