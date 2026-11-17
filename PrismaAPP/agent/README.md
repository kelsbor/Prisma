# Prisma Agent

Servidor do assistente text-to-SQL do Prisma Finanças (Python + LangChain + Gemini).

O banco fica só no celular. O servidor faz duas coisas:

1. `POST /v1/gerar-sql`: recebe a pergunta, devolve **só** um SQL (ou `fora_do_escopo` / `nao_sei` / `bloqueado`).
2. `POST /v1/responder`: recebe a pergunta, o SQL e o resultado que o app executou, e devolve o texto da resposta.

## Configurar

```powershell
cd agent
copy .env.example .env    # e preencha GOOGLE_API_KEY e APP_TOKENS
uv sync
```

No app, o `local.properties` (raiz do projeto) precisa de:

```
assistant.url=http://127.0.0.1:8000/
assistant.token=<o mesmo valor de APP_TOKENS>
```

O Android 17 bloqueia apps de acessar a rede local (inclusive `10.0.2.2`, o PC visto pelo emulador).
Por isso o app usa `127.0.0.1` e o adb encaminha a porta para o PC. Rode **sempre que o emulador
ou o celular reiniciar**:

```powershell
adb reverse tcp:8000 tcp:8000
```

Funciona também num celular de verdade ligado por USB.

## Rodar

```powershell
cd agent
uv run uvicorn prisma_agent.api:app --app-dir src --host 127.0.0.1 --port 8000
```

O servidor escuta só em `127.0.0.1`, então não fica exposto na rede; o app chega nele pelo `adb reverse`.

## Testes e avaliação

```powershell
uv run pytest                                                           # sem rede
uv run python evals/run_evals.py --db C:\caminho\copia\prisma.db         # usa o Gemini de verdade
```

## Segurança

| Camada | Onde | O que faz |
|---|---|---|
| Token | servidor | `Authorization: Bearer`; sem token válido → 401 |
| Limites | servidor | por minuto e por dia (por token); corpo até 64 KB; pergunta até 300 caracteres |
| Bloqueio de manipulação | servidor | "ignore as instruções", SQL na pergunta etc. → `bloqueado`, sem chamar o modelo |
| Escopo | Gemini (chamada 1) | só perguntas sobre as transações; o resto → `fora_do_escopo` / `nao_sei` (mensagens fixas) |
| SQL | servidor **e** app | um único SELECT, só a `vw_registers`, sem comentários, sem PRAGMA/ATTACH/escrita |
| Execução | app | conexão SQLite **somente leitura**, LIMIT 200, 3 s no máximo |
| Guardião "não sei" | servidor + app | resultado vazio → "não encontrei"; o modelo marca quando não tem certeza; o app confere que todo R$ citado existe no resultado |
| Privacidade | servidor | nada de conteúdo em log; docs/OpenAPI desligados |
