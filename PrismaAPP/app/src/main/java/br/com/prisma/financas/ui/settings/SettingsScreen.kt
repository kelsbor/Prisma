package br.com.prisma.financas.ui.settings

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Info
import androidx.compose.material.icons.outlined.Key
import androidx.compose.material.icons.outlined.Link
import androidx.compose.material.icons.outlined.Storage
import androidx.compose.material.icons.outlined.Sync
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.ListItem
import androidx.compose.material3.ListItemDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp
import androidx.hilt.lifecycle.viewmodel.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import br.com.prisma.financas.BuildConfig
import br.com.prisma.financas.domain.model.ConnectionStatus
import br.com.prisma.financas.ui.common.formatDate
import br.com.prisma.financas.ui.common.formatShortDateTime
import br.com.prisma.financas.ui.components.HealthPill
import br.com.prisma.financas.ui.components.SectionHeader
import br.com.prisma.financas.ui.components.dataFreshnessText
import br.com.prisma.financas.ui.components.lastCheckText

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(
    onOpenCredentials: () -> Unit,
    viewModel: SettingsViewModel = hiltViewModel(),
) {
    val connectionCount by viewModel.connectionCount.collectAsStateWithLifecycle()
    val sync by viewModel.sync.collectAsStateWithLifecycle()

    Column(Modifier.fillMaxSize()) {
        TopAppBar(title = { Text("Ajustes") })
        Column(Modifier.verticalScroll(rememberScrollState())) {
            SectionHeader("Conexão com a Pluggy")

            val s = sync
            val running = s?.running == true
            // Mostra quando a PLUGGY atualizou os dados com o banco (não quando o app consultou).
            val syncSubtitle = buildString {
                append(s?.dataFreshnessText() ?: "Ainda sem dados da Pluggy")
                s?.lastCheckText(viewModel.nowMillis())?.let { append("\n").append(it) }
                s?.error?.let { append("\n").append(it) }
                append("\nO Meu Pluggy atualiza os bancos 1x por dia.")
            }
            ListItem(
                headlineContent = { Text(if (running) "Sincronizando…" else "Sincronizar agora") },
                supportingContent = { Text(syncSubtitle) },
                leadingContent = { Icon(Icons.Outlined.Sync, contentDescription = null, tint = MaterialTheme.colorScheme.primary) },
                trailingContent = if (running) {
                    { CircularProgressIndicator(Modifier.size(22.dp), strokeWidth = 2.dp) }
                } else null,
                colors = ListItemDefaults.colors(containerColor = MaterialTheme.colorScheme.surface),
                modifier = Modifier.clickable(enabled = !running && connectionCount != null, onClick = viewModel::syncNow),
            )

            s?.connections?.forEach { ConnectionRow(it) }

            SettingsRow(
                icon = Icons.Outlined.Key,
                title = "Credenciais e conexões",
                subtitle = when (val n = connectionCount) {
                    null -> "Não configurado"
                    1 -> "1 conexão configurada · toque para editar"
                    else -> "$n conexões configuradas · toque para editar"
                },
                onClick = onOpenCredentials,
            )

            HorizontalDivider()
            SectionHeader("Dados")
            SettingsRow(
                icon = Icons.Outlined.Storage,
                title = "Banco de dados",
                subtitle = "SQLite local neste aparelho",
            )

            HorizontalDivider()
            SectionHeader("Sobre")
            SettingsRow(
                icon = Icons.Outlined.Info,
                title = "Prisma Finanças",
                subtitle = "Versão ${BuildConfig.VERSION_NAME}",
            )
        }
    }
}

@Composable
private fun ConnectionRow(c: ConnectionStatus) {
    val lines = buildList {
        add(c.dataUpdatedAt?.let { "Dados de ${it.formatShortDateTime()}" } ?: "Sem data de atualização")
        c.nextAutoSyncAt?.let { add("Próxima atualização na Pluggy: ${it.formatShortDateTime()}") }
        c.consentExpiresAt?.let { add("Autorização válida até ${it.formatDate()}") }
    }
    ListItem(
        headlineContent = { Text(c.connectorName) },
        supportingContent = { Text(lines.joinToString("\n")) },
        leadingContent = { Icon(Icons.Outlined.Link, contentDescription = null, tint = MaterialTheme.colorScheme.primary) },
        trailingContent = { HealthPill(c.health) },
        colors = ListItemDefaults.colors(containerColor = MaterialTheme.colorScheme.surface),
    )
}

@Composable
private fun SettingsRow(
    icon: ImageVector,
    title: String,
    subtitle: String,
    onClick: (() -> Unit)? = null,
) {
    ListItem(
        headlineContent = { Text(title) },
        supportingContent = { Text(subtitle) },
        leadingContent = { Icon(icon, contentDescription = null, tint = MaterialTheme.colorScheme.primary) },
        colors = ListItemDefaults.colors(containerColor = MaterialTheme.colorScheme.surface),
        modifier = if (onClick != null) Modifier.clickable(onClick = onClick) else Modifier,
    )
}
