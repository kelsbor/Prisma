package br.com.prisma.financas.domain.model

import java.time.Duration
import java.time.Instant

object ItemHealthRules {
    /** Com quantos dias de antecedência avisamos que a autorização vai vencer. */
    const val CONSENT_WARNING_DAYS = 30L

    /** A autorização ainda vale, mas vence nos próximos [CONSENT_WARNING_DAYS] dias. */
    fun consentExpiresSoon(consentExpiresAt: Instant?, now: Instant): Boolean =
        consentExpiresAt != null && Duration.between(now, consentExpiresAt).toDays() in 0..CONSENT_WARNING_DAYS

    fun of(
        status: String?,
        executionStatus: String?,
        errorCode: String?,
        consentExpiresAt: Instant?,
        now: Instant,
    ): ItemHealth {
        val marker = "${errorCode.orEmpty()} ${executionStatus.orEmpty()}".uppercase()
        return when {
            "AUTHORIZATION_EXPIRED" in marker || (consentExpiresAt != null && consentExpiresAt.isBefore(now)) -> ItemHealth.EXPIRED
            status == "LOGIN_ERROR" || executionStatus == "ERROR" -> ItemHealth.ERROR
            status == "UPDATED" -> ItemHealth.OK
            status == "UPDATING" -> ItemHealth.UPDATING
            else -> ItemHealth.WARNING
        }
    }
}
