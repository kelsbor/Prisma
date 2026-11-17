package br.com.prisma.financas.ui.navigation

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ReceiptLong
import androidx.compose.material.icons.automirrored.outlined.ReceiptLong
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.PieChart
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.outlined.AutoAwesome
import androidx.compose.material.icons.outlined.Home
import androidx.compose.material.icons.outlined.PieChart
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.ui.graphics.vector.ImageVector
import kotlinx.serialization.Serializable

// Grafo raiz
@Serializable data object WelcomeRoute
@Serializable data class GuideRoute(val showContinue: Boolean)
@Serializable data class CredentialsRoute(val isOnboarding: Boolean)
@Serializable data object MainRoute

// Abas do app
@Serializable data object HomeRoute
@Serializable data object TransactionsRoute
@Serializable data object SummariesRoute
@Serializable data object AssistantRoute
@Serializable data object SettingsRoute

enum class TopLevelDestination(
    val route: Any,
    val label: String,
    val selectedIcon: ImageVector,
    val icon: ImageVector,
) {
    HOME(HomeRoute, "Início", Icons.Filled.Home, Icons.Outlined.Home),
    TRANSACTIONS(TransactionsRoute, "Transações", Icons.AutoMirrored.Filled.ReceiptLong, Icons.AutoMirrored.Outlined.ReceiptLong),
    SUMMARIES(SummariesRoute, "Resumos", Icons.Filled.PieChart, Icons.Outlined.PieChart),
    ASSISTANT(AssistantRoute, "Assistente", Icons.Filled.AutoAwesome, Icons.Outlined.AutoAwesome),
    SETTINGS(SettingsRoute, "Ajustes", Icons.Filled.Settings, Icons.Outlined.Settings),
}
