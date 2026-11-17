# Prisma Finanças — App Android + Assistente

App Android de finanças pessoais que reúne as contas e cartões do usuário via **Pluggy** (Open Finance)
e tem um **assistente** que responde perguntas em português sobre as transações
("Quanto gastei com mercado em outubro?").

O projeto tem duas partes:

| Pasta | O que é | Tecnologia |
|---|---|---|
| `app/` | O aplicativo Android | Kotlin, Jetpack Compose, Room (SQLite), Hilt, Retrofit |
| `agent/` | O servidor do assistente (text-to-SQL) | Python, FastAPI, LangChain, Gemini |

> **Princípio central:** os dados financeiros ficam **no celular**. O servidor do assistente nunca
> acessa o banco: ele só escreve a consulta SQL e redige a resposta. Quem executa a consulta é o app.

---

## 1. O produto (app)

### Telas

| Aba | O que mostra |
|---|---|
| **Início** | Saldo das contas, faturas dos cartões, gasto do mês comparado ao mesmo período do mês anterior e últimas transações |
| **Transações** | Lista completa agrupada por dia, com busca e filtros por período, conta e categoria |
| **Resumos** | Totais do mês, gastos por categoria, evolução de 6 meses, maiores gastos e gastos recorrentes/assinaturas |
| **Assistente** | Perguntas em linguagem natural sobre as transações |
| **Ajustes** | Status das conexões, sincronização manual e credenciais da Pluggy |

Na primeira abertura, um passo a passo guia o usuário a obter as credenciais no Dashboard da Pluggy
(Client ID, Client Secret e os `itemId` das conexões). O app **testa a conexão antes de salvar**.

### Como os dados fluem

```
Pluggy (API) ──► PluggyClient ──► SyncManager ──► Room/SQLite (no aparelho) ──► FinanceRepository ──► Telas
```

- **Sincronização** (`data/sync/SyncManager.kt`): na primeira vez busca todo o histórico; depois, só
  os últimos dias (com 10 dias de sobreposição para pegar ajustes). É idempotente: atualiza pelo ID da
  Pluggy e nunca duplica. Roda ao abrir o app se os dados tiverem mais de 6 h, ou ao puxar a tela.
- **Categorias**: vêm da Pluggy em português. O usuário pode trocar manualmente; a escolha fica numa
  tabela própria e a sincronização nunca a sobrescreve.
- **Regras de gasto/entrada**: transferências entre contas, pagamento de fatura e investimentos não
  contam como gasto. Crédito no cartão é estorno (abate o gasto), não renda.
- **Segurança**: as credenciais da Pluggy são gravadas cifradas (AES-GCM com chave no Android Keystore).

### Organização do código (`app/src/main/java/br/com/prisma/financas/`)

| Pasta | Conteúdo |
|---|---|
| `data/remote` | Cliente da API da Pluggy (autenticação, paginação, tratamento de erros) |
| `data/sync` | Sincronização e conciliação de transações |
| `data/local` | Banco Room: tabelas, DAOs e a view `vw_registers` usada pelo assistente |
| `data/repository` | Junta os dados do banco no formato usado pelas telas |
| `domain` | Modelos e regras puras (resumos, recorrências, categorias), sem Android |
| `assistant` | Lado do app do assistente: orquestração, validação de SQL e execução somente leitura |
| `ui` | Telas em Compose e seus ViewModels |

---

## 2. O assistente (agente text-to-SQL)

O assistente transforma a pergunta em uma consulta SQL sobre a view `vw_registers` (uma linha por
transação, já com categoria, tipo e os valores que contam como gasto ou entrada).

### Fluxo de uma pergunta

```
 APP (Android)                                   SERVIDOR (agent/)
 ─────────────                                   ─────────────────
 1. Limites locais (tamanho, intervalo)
 2. Lê categorias/contas/bancos existentes ────► 3. POST /v1/gerar-sql
                                                    - confere token e limites
                                                    - bloqueia tentativas de manipulação
                                                    - Gemini (chamada 1) classifica e escreve o SQL
                                                    - valida o SQL (1 correção se falhar)
 4. Valida o SQL de novo                    ◄─────── devolve o SQL
 5. Executa no SQLite SOMENTE LEITURA
    (se der erro no banco, pede 1 correção)
 6. Resultado vazio? → "não encontrei"
 7. Envia pergunta + SQL + resultado ──────────► 8. POST /v1/responder
                                                    - Gemini (chamada 2) redige o texto
 9. Confere se todo "R$" citado existe     ◄─────── devolve o texto
    no resultado (senão, descarta)
10. Mostra a resposta, o SQL e a tabela
```

O modelo **nunca faz contas**: somas, médias e comparações são feitas no SQL. A view já traz
`valor_gasto` e `valor_entrada` prontos, o que evita a maior parte das alucinações com números.

### Arquivos do servidor (`agent/src/prisma_agent/`)

| Arquivo | Função |
|---|---|
| `api.py` | Endpoints, autenticação por token, prazo total por requisição e mensagens fixas |
| `guard.py` | Filtro de manipulação na pergunta e validação do SQL (`sqlglot`): um único `SELECT`, só na `vw_registers` |
| `chains.py` | As duas chamadas ao Gemini com saída estruturada |
| `knowledge.py` + `prompts/` | Monta o prompt a partir de arquivos de texto: esquema, regras de negócio, glossário e exemplos |
| `ratelimit.py` | Limites por token (por minuto e por dia) |
| `config.py` | Lê a configuração do `agent/.env` |

Para ajustar o comportamento do assistente, normalmente basta editar os arquivos em `prompts/`.

### Camadas de segurança

| Camada | Onde | O que faz |
|---|---|---|
| Token | servidor | `Authorization: Bearer`; sem token válido → 401 |
| Limites | app e servidor | por minuto, por dia e por hora; corpo até 64 KB; pergunta até 300 caracteres |
| Manipulação | servidor | "ignore as instruções", SQL na pergunta etc. → bloqueado sem chamar o modelo |
| SQL | servidor **e** app | um único SELECT, só a `vw_registers`, sem comentários, sem PRAGMA/ATTACH/escrita |
| Execução | app | banco aberto somente leitura, no máximo 200 linhas e 3 s |
| Anti-alucinação | app | todo valor em R$ citado precisa existir no resultado |
| Privacidade | servidor | nada do conteúdo vai para log; documentação/OpenAPI desligadas |

---

## 3. Como rodar

### Pré-requisitos

- **Android Studio** (já inclui o Java 17 e o SDK). No SDK Manager, instale a **API 37** e o
  **Android SDK Platform-Tools**.
- **uv** (gerenciador de Python): `winget install astral-sh.uv`
- Uma conta na **Pluggy** com uma aplicação criada (Client ID e Client Secret) e conexões de teste.
- Uma **chave da API do Gemini** (Google AI Studio).

### 3.1 Servidor do assistente

```powershell
cd agent
copy .env.example .env      # preencha GOOGLE_API_KEY e APP_TOKENS
uv sync                     # usa o Python 3.12 (fixado em .python-version)
uv run uvicorn prisma_agent.api:app --app-dir src --host 127.0.0.1 --port 8000
```

- `APP_TOKENS`: um texto aleatório longo (mínimo 24 caracteres). Para gerar:
  `uv run python -c "import secrets; print(secrets.token_urlsafe(32))"`
- Para conferir: abra `http://127.0.0.1:8000/health` → `{"status":"ok"}`.

### 3.2 App Android

1. Crie o arquivo `local.properties` na raiz desta pasta (ele **não** vai para o git):
   ```properties
   sdk.dir=C\:\\Users\\SEU_USUARIO\\AppData\\Local\\Android\\Sdk
   assistant.url=http\://127.0.0.1\:8000/
   assistant.token=<o mesmo valor de APP_TOKENS>
   ```
2. Abra esta pasta no Android Studio e espere o Gradle sincronizar.
3. Inicie um emulador (ou conecte um celular com depuração USB).
4. Redirecione a porta do servidor para o aparelho. **Repita sempre que o emulador/celular reiniciar**:
   ```powershell
   adb reverse tcp:8000 tcp:8000
   ```
   (Se `adb` não for reconhecido, use o caminho completo:
   `%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe`.)
5. Clique em ▶ **Run 'app'** (ou rode `.\gradlew.bat installDebug`).
6. No app, siga o passo a passo e informe as credenciais da Pluggy.

> **Por que `127.0.0.1` e `adb reverse`?** O Android 17 bloqueia apps de acessar a rede local
> (inclusive o `10.0.2.2` do emulador). Com o `adb reverse`, o `127.0.0.1:8000` do aparelho aponta
> para o PC. Assim o servidor também não fica exposto na rede.

O app funciona sem o servidor; só a aba **Assistente** depende dele.

### 3.3 Testes

```powershell
# App (testes unitários)
.\gradlew.bat test

# Servidor (sem rede, com modelos falsos)
cd agent
uv run pytest
```

### 3.4 Avaliação do assistente (evals)

Mede a qualidade do gerador de SQL contra uma **cópia** do banco do app. Chama o Gemini de verdade e
consome cota; envia só a pergunta e os nomes de categorias/contas, nunca as transações.

```powershell
cd agent
uv run python evals/run_evals.py --db C:\caminho\copia\prisma.db --detalhes
```

As perguntas ficam em `agent/evals/perguntas.yaml`. Elas **não podem repetir** os exemplos do prompt
(`prompts/exemplos.yaml`); um teste automático garante isso.

---

## 4. Problemas comuns

| Sintoma | Causa provável | Solução |
|---|---|---|
| `uv sync` falha compilando `zstandard`/`pyyaml` | Python novo demais, sem pacotes prontos | `uv sync --python 3.12` |
| "Não consegui falar com o servidor do assistente" | servidor parado ou porta não redirecionada | suba o servidor e rode `adb reverse tcp:8000 tcp:8000` |
| "Este app não está autorizado no servidor" | `assistant.token` diferente de `APP_TOKENS` | iguale os valores e reinstale o app |
| "O limite de uso do Gemini foi atingido" | cota do plano gratuito | aguarde um minuto (ou o dia seguinte) |

> **Privacidade:** na chamada 2, descrições e valores das transações consultadas são enviados ao
> Gemini. No plano gratuito da API, o Google pode usar esses dados para melhorar seus produtos;
> para uso real, prefira o plano pago. O app pede o consentimento do usuário antes de usar o assistente.
