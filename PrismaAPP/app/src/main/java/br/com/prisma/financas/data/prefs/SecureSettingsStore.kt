package br.com.prisma.financas.data.prefs

import android.content.Context
import android.util.Base64
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.longPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import br.com.prisma.financas.core.security.KeystoreCipher
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import br.com.prisma.financas.domain.model.PluggyCredentials
import kotlinx.serialization.json.Json
import javax.inject.Inject
import javax.inject.Singleton

private val Context.settingsDataStore: DataStore<Preferences> by preferencesDataStore(name = "prisma_settings")

/**
 * Preferências do app. Dados sensíveis (credenciais/itemIds) são gravados
 * cifrados com AES-GCM via Android Keystore; nada sensível fica em texto puro.
 */
@Singleton
class SecureSettingsStore @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    private val cipher = KeystoreCipher(KEY_ALIAS)
    private val json = Json { ignoreUnknownKeys = true }
    private val store get() = context.settingsDataStore

    val credentials: Flow<PluggyCredentials?> = store.data.map { prefs ->
        prefs[CREDENTIALS]?.let(::decryptCredentials)
    }

    val onboardingCompleted: Flow<Boolean> = store.data.map { it[ONBOARDING_DONE] ?: false }

    /** Quando o app consultou a Pluggy pela última vez com sucesso (epoch millis). */
    val lastSyncAt: Flow<Long?> = store.data.map { it[LAST_SYNC_AT] }

    /** Mensagem do último erro de sincronização (já amigável, sem dados sensíveis), ou nulo. */
    val lastSyncError: Flow<String?> = store.data.map { it[LAST_SYNC_ERROR] }

    /** O usuário aceitou que a pergunta e o resultado da consulta sejam enviados ao Gemini. */
    val assistantConsent: Flow<Boolean> = store.data.map { it[ASSISTANT_CONSENT] ?: false }

    suspend fun setAssistantConsent(accepted: Boolean) {
        store.edit { it[ASSISTANT_CONSENT] = accepted }
    }

    suspend fun recordSyncSuccess(atMillis: Long, partialError: String?) {
        store.edit {
            it[LAST_SYNC_AT] = atMillis
            if (partialError == null) it.remove(LAST_SYNC_ERROR) else it[LAST_SYNC_ERROR] = partialError
        }
    }

    suspend fun recordSyncFailure(message: String) {
        store.edit { it[LAST_SYNC_ERROR] = message }
    }

    suspend fun currentCredentials(): PluggyCredentials? = credentials.first()

    suspend fun saveCredentials(credentials: PluggyCredentials) {
        val plain = json.encodeToString(PluggyCredentials.serializer(), credentials).encodeToByteArray()
        val encrypted = Base64.encodeToString(cipher.encrypt(plain), Base64.NO_WRAP)
        plain.fill(0)
        store.edit { it[CREDENTIALS] = encrypted }
    }

    suspend fun setOnboardingCompleted(done: Boolean) {
        store.edit { it[ONBOARDING_DONE] = done }
    }

    suspend fun clearAll() {
        store.edit { it.clear() }
        cipher.deleteKey()
    }

    private fun decryptCredentials(encoded: String): PluggyCredentials? = runCatching {
        val plain = cipher.decrypt(Base64.decode(encoded, Base64.NO_WRAP))
        try {
            json.decodeFromString(PluggyCredentials.serializer(), plain.decodeToString())
        } finally {
            plain.fill(0)
        }
    }.getOrNull() // chave perdida/corrompida: trata como "sem credenciais"

    private companion object {
        const val KEY_ALIAS = "prisma_settings_key"
        val CREDENTIALS = stringPreferencesKey("pluggy_credentials_enc")
        val ONBOARDING_DONE = booleanPreferencesKey("onboarding_completed")
        val LAST_SYNC_AT = longPreferencesKey("last_sync_at")
        val LAST_SYNC_ERROR = stringPreferencesKey("last_sync_error")
        val ASSISTANT_CONSENT = booleanPreferencesKey("assistant_consent")
    }
}
