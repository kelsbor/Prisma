package br.com.prisma.financas.ui.navigation

import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.lifecycle.Lifecycle
import androidx.navigation.NavBackStackEntry
import androidx.navigation.NavDestination.Companion.hasRoute
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.toRoute
import br.com.prisma.financas.ui.credentials.CredentialsScreen
import br.com.prisma.financas.ui.onboarding.GuideScreen
import br.com.prisma.financas.ui.onboarding.WelcomeScreen
import br.com.prisma.financas.ui.home.HomeScreen
import br.com.prisma.financas.ui.assistant.AssistantScreen
import br.com.prisma.financas.ui.settings.SettingsScreen
import br.com.prisma.financas.ui.summaries.SummariesScreen
import br.com.prisma.financas.ui.transactions.TransactionsScreen

/** Grafo raiz: onboarding (boas-vindas → guia → credenciais) e o app principal. */
@Composable
fun PrismaRootNavHost(navController: NavHostController, onboardingCompleted: Boolean) {
    NavHost(
        navController = navController,
        startDestination = if (onboardingCompleted) MainRoute else WelcomeRoute,
    ) {
        composable<WelcomeRoute> { entry ->
            WelcomeScreen(onStart = entry.ifResumed { navController.navigate(GuideRoute(showContinue = true)) })
        }
        composable<GuideRoute> { entry ->
            GuideScreen(
                showContinue = entry.toRoute<GuideRoute>().showContinue,
                onBack = entry.ifResumed { navController.popBackStack() },
                onContinue = entry.ifResumed { navController.navigate(CredentialsRoute(isOnboarding = true)) },
            )
        }
        composable<CredentialsRoute> { entry ->
            val route = entry.toRoute<CredentialsRoute>()
            CredentialsScreen(
                onBack = entry.ifResumed { navController.popBackStack() },
                onOpenGuide = entry.ifResumed { navController.navigate(GuideRoute(showContinue = false)) },
                onSaved = {
                    if (route.isOnboarding) {
                        navController.navigate(MainRoute) {
                            popUpTo(navController.graph.id) { inclusive = true }
                        }
                    } else {
                        navController.popBackStack()
                    }
                },
            )
        }
        composable<MainRoute> { entry ->
            MainScaffold(onOpenCredentials = entry.ifResumed { navController.navigate(CredentialsRoute(isOnboarding = false)) })
        }
    }
}

/** Ignora toques enquanto a tela está em transição (evita pular telas com toque duplo). */
private fun NavBackStackEntry.ifResumed(action: () -> Unit): () -> Unit = {
    if (lifecycle.currentState == Lifecycle.State.RESUMED) action()
}

/** App principal com navegação inferior. */
@Composable
private fun MainScaffold(onOpenCredentials: () -> Unit) {
    val navController = rememberNavController()
    val backStackEntry by navController.currentBackStackEntryAsState()
    val currentDestination = backStackEntry?.destination
    fun goToTab(route: Any) = navController.navigate(route) {
        popUpTo(navController.graph.findStartDestination().id) { saveState = true }
        launchSingleTop = true
        restoreState = true
    }

    Scaffold(
        bottomBar = {
            NavigationBar {
                TopLevelDestination.entries.forEach { dest ->
                    val selected = currentDestination?.hierarchy?.any { it.hasRoute(dest.route::class) } == true
                    NavigationBarItem(
                        selected = selected,
                        onClick = { goToTab(dest.route) },
                        icon = { Icon(if (selected) dest.selectedIcon else dest.icon, contentDescription = null) },
                        label = { Text(dest.label) },
                    )
                }
            }
        },
    ) { innerPadding ->
        NavHost(
            navController = navController,
            startDestination = HomeRoute,
            // Só o inset inferior: cada tela tem sua TopAppBar, que já trata a status bar.
            modifier = Modifier.padding(bottom = innerPadding.calculateBottomPadding()),
        ) {
            composable<HomeRoute> { HomeScreen(onOpenTransactions = { goToTab(TransactionsRoute) }) }
            composable<TransactionsRoute> { TransactionsScreen() }
            composable<SummariesRoute> { SummariesScreen() }
            composable<AssistantRoute> { AssistantScreen() }
            composable<SettingsRoute> { SettingsScreen(onOpenCredentials = onOpenCredentials) }
        }
    }
}
