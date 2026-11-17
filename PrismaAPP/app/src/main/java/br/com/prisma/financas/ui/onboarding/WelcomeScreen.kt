package br.com.prisma.financas.ui.onboarding

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.AccountBalance
import androidx.compose.material.icons.outlined.AutoAwesome
import androidx.compose.material.icons.outlined.PieChart
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp
import br.com.prisma.financas.ui.components.PrismaLogo
import br.com.prisma.financas.ui.theme.PrismaThemeExt

@Composable
fun WelcomeScreen(onStart: () -> Unit) {
    Box(
        Modifier
            .fillMaxSize()
            .background(PrismaThemeExt.finance.heroGradient)
            .safeDrawingPadding(),
    ) {
        Column(
            Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 28.dp, vertical = 24.dp),
        ) {
            Spacer(Modifier.weight(1f))
            PrismaLogo(size = 80.dp)
            Spacer(Modifier.height(28.dp))
            Text("Prisma Finanças", style = MaterialTheme.typography.headlineLarge, color = Color.White)
            Spacer(Modifier.height(8.dp))
            Text(
                "Entenda para onde vai o seu dinheiro.",
                style = MaterialTheme.typography.titleMedium,
                color = Color.White.copy(alpha = 0.85f),
            )
            Spacer(Modifier.height(36.dp))
            Feature(Icons.Outlined.AccountBalance, "Seus bancos em um lugar", "Contas e cartões conectados pelo Open Finance via Meu Pluggy.")
            Feature(Icons.Outlined.PieChart, "Gastos organizados", "Por categoria, por mês e com as assinaturas recorrentes.")
            Feature(Icons.Outlined.AutoAwesome, "Dicas sobre seus gastos", "Alertas quando uma categoria sobe em relação ao mês anterior.")
            Spacer(Modifier.weight(1f))
            Spacer(Modifier.height(24.dp))
            Button(
                onClick = onStart,
                colors = ButtonDefaults.buttonColors(containerColor = Color.White, contentColor = MaterialTheme.colorScheme.primary),
                modifier = Modifier.fillMaxWidth().height(52.dp),
            ) { Text("Começar") }
        }
    }
}

@Composable
private fun Feature(icon: ImageVector, title: String, text: String) {
    Row(Modifier.padding(vertical = 10.dp), verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.Start) {
        Box(
            Modifier.size(40.dp).clip(CircleShape).background(Color.White.copy(alpha = 0.14f)),
            contentAlignment = Alignment.Center,
        ) { Icon(icon, contentDescription = null, tint = Color.White, modifier = Modifier.size(22.dp)) }
        Spacer(Modifier.width(14.dp))
        Column {
            Text(title, style = MaterialTheme.typography.titleSmall, color = Color.White)
            Text(text, style = MaterialTheme.typography.bodyMedium, color = Color.White.copy(alpha = 0.75f))
        }
    }
}
