package br.com.prisma.financas

import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.compose.rememberNavController
import br.com.prisma.financas.ui.navigation.PrismaRootNavHost
import br.com.prisma.financas.ui.root.RootState
import br.com.prisma.financas.ui.root.RootViewModel
import br.com.prisma.financas.ui.theme.PrismaTheme
import dagger.hilt.android.AndroidEntryPoint

@AndroidEntryPoint
class MainActivity : ComponentActivity() {

    private val rootViewModel: RootViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        // Bloqueia prints, gravação de tela e a miniatura em "Recentes".
        window.setFlags(WindowManager.LayoutParams.FLAG_SECURE, WindowManager.LayoutParams.FLAG_SECURE)

        setContent {
            PrismaTheme {
                val state by rootViewModel.state.collectAsStateWithLifecycle()
                val navController = rememberNavController()
                when (val s = state) {
                    RootState.Loading -> Box(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background))
                    is RootState.Ready -> PrismaRootNavHost(navController, s.onboardingCompleted)
                }
            }
        }
    }
}
