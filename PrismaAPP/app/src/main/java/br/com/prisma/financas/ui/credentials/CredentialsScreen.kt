package br.com.prisma.financas.ui.credentials

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.outlined.HelpOutline
import androidx.compose.material.icons.outlined.AccountBalance
import androidx.compose.material.icons.outlined.Add
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.CreditCard
import androidx.compose.material.icons.outlined.Visibility
import androidx.compose.material.icons.outlined.VisibilityOff
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.hilt.lifecycle.viewmodel.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import br.com.prisma.financas.domain.model.ItemCheck
import br.com.prisma.financas.domain.model.ItemHealth
import br.com.prisma.financas.ui.common.formatDate
import br.com.prisma.financas.ui.common.formatDateTime
import br.com.prisma.financas.domain.model.userMessage
import br.com.prisma.financas.ui.components.HealthPill
import br.com.prisma.financas.ui.components.SectionHeader
import br.com.prisma.financas.ui.components.WarningBanner

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CredentialsScreen(
    onBack: () -> Unit,
    onOpenGuide: () -> Unit,
    onSaved: () -> Unit,
    viewModel: CredentialsViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()

    val scrollState = rememberScrollState()

    LaunchedEffect(state.saved) { if (state.saved) onSaved() }

    // Leva o usuário até o resultado do teste.
    val testFinished = state.test is TestState.Done || state.test is TestState.Failed
    LaunchedEffect(state.test) { if (testFinished) scrollState.animateScrollTo(scrollState.maxValue) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(if (state.isOnboarding) "Conectar Pluggy" else "Credenciais e conexões") },
                navigationIcon = {
                    IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Voltar") }
                },
                actions = {
                    IconButton(onClick = onOpenGuide) {
                        Icon(Icons.AutoMirrored.Outlined.HelpOutline, contentDescription = "Como obter as credenciais")
                    }
                },
            )
        },
        bottomBar = { BottomActions(state, viewModel::testConnection, viewModel::save) },
    ) { padding ->
        if (state.loading) {
            Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
            return@Scaffold
        }
        Column(
            Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(scrollState),
        ) {
            Text(
                "Cole os dados da sua aplicação no Dashboard da Pluggy. Vamos testar a conexão antes de salvar.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(horizontal = 20.dp),
            )
            Spacer(Modifier.height(12.dp))

            SectionHeader("Aplicação")
            Column(Modifier.padding(horizontal = 20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                OutlinedTextField(
                    value = state.clientId,
                    onValueChange = viewModel::onClientIdChange,
                    label = { Text("Client ID") },
                    singleLine = true,
                    isError = state.validation.clientIdError != null,
                    supportingText = state.validation.clientIdError?.let { { Text(it) } },
                    keyboardOptions = KeyboardOptions(autoCorrectEnabled = false, keyboardType = KeyboardType.Ascii, imeAction = ImeAction.Next),
                    modifier = Modifier.fillMaxWidth(),
                )
                SecretField(
                    value = state.clientSecret,
                    onValueChange = viewModel::onClientSecretChange,
                    error = state.validation.clientSecretError,
                )
            }

            Spacer(Modifier.height(16.dp))
            SectionHeader("Conexões (itemId)")
            Text(
                "Até 5. Encontre em Demo → Connected Items no Dashboard.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(horizontal = 20.dp),
            )
            Spacer(Modifier.height(8.dp))
            Column(Modifier.padding(horizontal = 20.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                state.itemIds.forEachIndexed { index, id ->
                    val error = state.validation.itemErrors[index]
                    OutlinedTextField(
                        value = id,
                        onValueChange = { viewModel.onItemIdChange(index, it) },
                        label = { Text("Conexão ${index + 1}") },
                        placeholder = { Text("00000000-0000-0000-0000-000000000000") },
                        singleLine = true,
                        isError = error != null,
                        supportingText = error?.let { { Text(it) } },
                        keyboardOptions = KeyboardOptions(autoCorrectEnabled = false, keyboardType = KeyboardType.Ascii),
                        trailingIcon = if (state.itemIds.size > 1 || id.isNotEmpty()) {
                            {
                                IconButton(onClick = { viewModel.removeItem(index) }) {
                                    Icon(Icons.Outlined.Close, contentDescription = "Remover conexão ${index + 1}")
                                }
                            }
                        } else null,
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
                if (state.canAddItem) {
                    TextButton(onClick = viewModel::addItem) {
                        Icon(Icons.Outlined.Add, contentDescription = null, modifier = Modifier.size(18.dp))
                        Spacer(Modifier.width(6.dp))
                        Text("Adicionar conexão")
                    }
                }
                state.validation.formError?.let {
                    Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
                }
            }

            Spacer(Modifier.height(16.dp))
            TestResultSection(state.test)
            Spacer(Modifier.height(24.dp))
        }
    }
}

@Composable
private fun SecretField(value: String, onValueChange: (String) -> Unit, error: String?) {
    var visible by remember { mutableStateOf(false) }
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        label = { Text("Client Secret") },
        singleLine = true,
        isError = error != null,
        supportingText = error?.let { { Text(it) } },
        visualTransformation = if (visible) VisualTransformation.None else PasswordVisualTransformation(),
        keyboardOptions = KeyboardOptions(autoCorrectEnabled = false, keyboardType = KeyboardType.Password, imeAction = ImeAction.Next),
        trailingIcon = {
            IconButton(onClick = { visible = !visible }) {
                Icon(
                    if (visible) Icons.Outlined.VisibilityOff else Icons.Outlined.Visibility,
                    contentDescription = if (visible) "Ocultar" else "Mostrar",
                )
            }
        },
        modifier = Modifier.fillMaxWidth(),
    )
}

@Composable
private fun BottomActions(state: CredentialsUiState, onTest: () -> Unit, onSave: () -> Unit) {
    Surface(tonalElevation = 3.dp) {
        Column(
            Modifier
                .fillMaxWidth()
                .navigationBarsPadding()
                .imePadding()
                .padding(horizontal = 20.dp, vertical = 12.dp),
        ) {
            val running = state.test is TestState.Running
            if (state.canSave) {
                Button(
                    onClick = onSave,
                    enabled = !state.saving,
                    modifier = Modifier.fillMaxWidth().height(52.dp),
                ) { Text(if (state.isOnboarding) "Salvar e continuar" else "Salvar alterações") }
                TextButton(onClick = onTest, modifier = Modifier.fillMaxWidth()) { Text("Testar novamente") }
            } else {
                Button(
                    onClick = onTest,
                    enabled = !running && !state.loading,
                    modifier = Modifier.fillMaxWidth().height(52.dp),
                ) {
                    if (running) {
                        CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp, color = MaterialTheme.colorScheme.onPrimary)
                        Spacer(Modifier.width(10.dp))
                        Text("Testando conexão…")
                    } else {
                        Text("Testar conexão")
                    }
                }
            }
        }
    }
}

@Composable
private fun TestResultSection(test: TestState) {
    when (test) {
        TestState.Idle, TestState.Running -> Unit
        is TestState.Failed -> WarningBanner(test.message, Modifier.padding(horizontal = 20.dp))
        is TestState.Done -> {
            SectionHeader("Resultado do teste")
            Column(Modifier.padding(horizontal = 20.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                test.items.forEach { ItemResultCard(it) }
                Text(
                    if (test.allOk) "Tudo certo. Os dados dos bancos são atualizados pela Pluggy uma vez por dia."
                    else "Corrija as conexões com erro (ou remova-as) e teste novamente.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@Composable
private fun ItemResultCard(check: ItemCheck) {
    Card(
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(16.dp)) {
            when (check) {
                is ItemCheck.Ok -> {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(check.connectorName ?: "Conexão", style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                        HealthPill(check.health)
                    }
                    check.lastUpdatedAt?.let {
                        Text(
                            "Dados do banco atualizados em ${it.formatDateTime()}",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    if (check.consentExpiresSoon && check.consentExpiresAt != null) {
                        Text(
                            "A autorização vence em ${check.consentExpiresAt.formatDate()}. Renove na aplicação Demo.",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.tertiary,
                        )
                    }
                    if (check.accounts.isNotEmpty()) {
                        HorizontalDivider(Modifier.padding(vertical = 10.dp))
                        check.accounts.forEach { acc ->
                            Row(Modifier.padding(vertical = 3.dp), verticalAlignment = Alignment.CenterVertically) {
                                Icon(
                                    if (acc.isCreditCard) Icons.Outlined.CreditCard else Icons.Outlined.AccountBalance,
                                    contentDescription = null,
                                    tint = MaterialTheme.colorScheme.primary,
                                    modifier = Modifier.size(18.dp),
                                )
                                Spacer(Modifier.width(10.dp))
                                Text(acc.name, style = MaterialTheme.typography.bodyMedium)
                            }
                        }
                    } else {
                        Text("Nenhuma conta encontrada nesta conexão.", style = MaterialTheme.typography.bodySmall)
                    }
                }
                is ItemCheck.Failed -> {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("Conexão ${check.itemId.take(8)}…", style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                        HealthPill(ItemHealth.ERROR)
                    }
                    Spacer(Modifier.height(4.dp))
                    Text(check.error.userMessage(), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.error)
                }
            }
        }
    }
}
