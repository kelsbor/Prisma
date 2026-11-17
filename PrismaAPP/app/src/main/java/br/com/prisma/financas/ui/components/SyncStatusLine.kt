package br.com.prisma.financas.ui.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import br.com.prisma.financas.data.sync.SyncInfo
import br.com.prisma.financas.domain.model.ItemHealth
import br.com.prisma.financas.domain.model.ItemHealthRules
import br.com.prisma.financas.ui.common.formatDate
import br.com.prisma.financas.ui.common.formatShortDateTime
import br.com.prisma.financas.ui.common.relativeTime
import java.time.Instant

/** Texto principal sobre a atualidade dos dados: quando a PLUGGY atualizou com o banco. */
fun SyncInfo.dataFreshnessText(): String = when {
    running && dataUpdatedAt == null -> "Buscando seus dados na Pluggy…"
    running -> "Atualizando… dados da Pluggy de ${dataUpdatedAt!!.formatShortDateTime()}"
    dataUpdatedAt != null -> "Dados atualizados pela Pluggy em ${dataUpdatedAt.formatShortDateTime()}"
    else -> "Ainda sem dados da Pluggy"
}

/** Texto secundário: quando o app conferiu a Pluggy pela última vez. */
fun SyncInfo.lastCheckText(nowMillis: Long): String? =
    lastCheckAt?.let { "Verificado ${relativeTime(it, nowMillis)}" }

/** Avisos importantes de conexão (autorização expirada/vencendo, erro). */
fun SyncInfo.connectionWarnings(now: Instant): List<Pair<String, Boolean>> {
    val list = mutableListOf<Pair<String, Boolean>>()
    error?.let { list += it to true }
    connections.forEach { c ->
        when (c.health) {
            ItemHealth.EXPIRED -> list += "A autorização de ${c.connectorName} expirou. Renove na aplicação Demo do Dashboard da Pluggy." to true
            ItemHealth.ERROR -> list += "A conexão ${c.connectorName} está com erro na Pluggy. Os dados podem estar desatualizados." to true
            else -> if (ItemHealthRules.consentExpiresSoon(c.consentExpiresAt, now)) {
                list += "A autorização de ${c.connectorName} vence em ${c.consentExpiresAt!!.formatDate()}." to false
            }
        }
    }
    return list
}

/** Avisos de conexão. Não ocupa espaço quando não há avisos. */
@Composable
fun SyncWarnings(info: SyncInfo?, nowMillis: Long, modifier: Modifier = Modifier) {
    val warnings = info?.connectionWarnings(Instant.ofEpochMilli(nowMillis)).orEmpty()
    if (warnings.isEmpty()) return
    Column(modifier.fillMaxWidth().padding(horizontal = 20.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        warnings.forEach { (msg, isError) -> WarningBanner(msg, isError = isError) }
    }
}

@Composable
fun SyncStatusLine(info: SyncInfo?, nowMillis: Long, modifier: Modifier = Modifier) {
    if (info == null) return
    Column(modifier.padding(horizontal = 20.dp)) {
        Text(info.dataFreshnessText(), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        info.lastCheckText(nowMillis)?.let {
            Text(it, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.outline)
        }
    }
}
