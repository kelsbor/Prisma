package br.com.prisma.financas.ui.onboarding

import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.outlined.OpenInNew
import androidx.compose.material.icons.outlined.Schedule
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp

private data class Step(val title: String, val text: String)

private val STEPS = listOf(
    Step("Crie sua conta no Meu Pluggy", "Acesse meu.pluggy.ai, crie a conta e conecte seus bancos."),
    Step("Crie uma conta no Dashboard da Pluggy", "Em dashboard.pluggy.ai. É o painel para desenvolvedores, gratuito para uso pessoal."),
    Step("Crie a aplicação", "No Dashboard, adicione o conector MeuPluggy e crie uma aplicação de desenvolvimento. Ela mostra o Client ID e o Client Secret."),
    Step("Autorize seus bancos", "Abra a aplicação Demo e autorize sua conta Meu Pluggy (uma vez para cada banco)."),
    Step("Copie o itemId", "Ainda na Demo, em Connected Items, toque em cada conexão e copie o id. São até 5 conexões."),
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun GuideScreen(
    showContinue: Boolean,
    onBack: () -> Unit,
    onContinue: () -> Unit,
) {
    val context = LocalContext.current
    fun open(url: String) {
        try {
            context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
        } catch (_: ActivityNotFoundException) { }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Como conectar") },
                navigationIcon = {
                    IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Voltar") }
                },
            )
        },
        bottomBar = {
            if (showContinue) {
                Column(Modifier.navigationBarsPadding().padding(20.dp)) {
                    Button(onClick = onContinue, modifier = Modifier.fillMaxWidth().height(52.dp)) {
                        Text("Já tenho minhas credenciais")
                    }
                }
            }
        },
    ) { padding ->
        Column(
            Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp),
        ) {
            Text(
                "Você vai precisar de 3 informações: Client ID, Client Secret e o itemId de cada banco.",
                style = MaterialTheme.typography.bodyLarge,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.height(20.dp))
            STEPS.forEachIndexed { i, step -> StepRow(i + 1, step) }

            Spacer(Modifier.height(8.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                OutlinedButton(onClick = { open("https://meu.pluggy.ai") }, modifier = Modifier.weight(1f)) {
                    Text("Meu Pluggy")
                    Spacer(Modifier.width(6.dp))
                    Icon(Icons.AutoMirrored.Outlined.OpenInNew, contentDescription = null, modifier = Modifier.size(16.dp))
                }
                OutlinedButton(onClick = { open("https://dashboard.pluggy.ai") }, modifier = Modifier.weight(1f)) {
                    Text("Dashboard")
                    Spacer(Modifier.width(6.dp))
                    Icon(Icons.AutoMirrored.Outlined.OpenInNew, contentDescription = null, modifier = Modifier.size(16.dp))
                }
            }

            Spacer(Modifier.height(20.dp))
            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.secondaryContainer)) {
                Row(Modifier.padding(16.dp), verticalAlignment = Alignment.Top) {
                    Icon(Icons.Outlined.Schedule, contentDescription = null, tint = MaterialTheme.colorScheme.onSecondaryContainer)
                    Spacer(Modifier.width(12.dp))
                    Text(
                        "O Meu Pluggy atualiza os dados dos bancos uma vez por dia. Lançamentos de hoje podem aparecer só amanhã.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSecondaryContainer,
                    )
                }
            }
            Spacer(Modifier.height(24.dp))
        }
    }
}

@Composable
private fun StepRow(number: Int, step: Step) {
    Row(Modifier.fillMaxWidth().padding(bottom = 18.dp), verticalAlignment = Alignment.Top) {
        Box(
            Modifier.size(32.dp).clip(CircleShape).background(MaterialTheme.colorScheme.primaryContainer),
            contentAlignment = Alignment.Center,
        ) {
            Text("$number", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onPrimaryContainer)
        }
        Spacer(Modifier.width(14.dp))
        Column(Modifier.weight(1f)) {
            Text(step.title, style = MaterialTheme.typography.titleSmall)
            Spacer(Modifier.height(2.dp))
            Text(step.text, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}
