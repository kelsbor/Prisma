# Agente SQL (Python, local)

O agente e o gerador do banco só usam a biblioteca padrão do Python (3.11+).
O servidor MCP precisa do pacote `mcp` (veja `requirements.txt`).

## Configurar

1. Copie `config.example.json` para `config.json`.
2. Preencha as 3 credenciais da Pluggy (Client ID, Client Secret e o itemId de cada banco)
   e a chave do Gemini.

## Gerar o banco

```
python gerar_banco.py
```

Cria o `financas.db` com as mesmas tabelas do app. Se preferir usar o banco do celular,
coloque o `prisma.db` nesta pasta (junto com o `prisma.db-wal`, se existir) e troque
`"banco"` no `config.json`.

## Rodar o agente

```
python agente.py
```

Fluxo (o "Agente Simples"):

1. o Gemini recebe a descrição das tabelas e a pergunta, e devolve só o SQL;
2. o SQL é executado com a proteção abaixo; se o banco recusar, o Gemini tem 1 chance de corrigir;
3. o Gemini recebe a pergunta, o SQL e o resultado e redige a resposta;
4. a resposta aparece na tela. Cada pergunta é independente: não há histórico.

### Proteção do SQL (`guardas.py`, só biblioteca padrão)

Fica aqui porque o SQL só existe dentro deste agente: quem executa é quem consegue barrar.

| Proteção | Como |
|---|---|
| Validação do SQL | o próprio SQLite confere cada leitura (`set_authorizer`): só `SELECT`/`WITH`, só `vw_registers`, `account_dim` e `item_dim` (a view pode ler as tabelas dela por dentro), sem `PRAGMA`, `ATTACH`, escrita, `sqlite_master` nem funções como `load_extension`; uma instrução por vez |
| Execução | banco somente leitura (`mode=ro` e `query_only`), até 5 s e 200 linhas |
| Correção | se o SQL for recusado ou falhar, o Gemini recebe o erro e tenta mais uma vez |

O **filtro de entrada** (manipulação, "só finanças") e o **guardião** dos valores da resposta ficam no
**orquestrador** (`projeto_agentes/orquestrador/guardas.py`), que é o ponto de entrada único. O guardião
confere cada R$ da resposta contra as linhas que este agente devolve em `dados`.

A ferramenta MCP devolve também `status`: `sucesso` ou `erro_sql` (o mesmo valor fica em `metricas.db`).
No benchmark (`avaliar.py --hoje 2026-11-25`), a proteção manteve o acerto de fatos (21/46 antes e depois)
e zerou os erros de SQL (2 → 0) com a segunda tentativa.

## Rodar como servidor MCP

O mesmo agente, exposto como a ferramenta `consultar_financas(pergunta)` para um orquestrador
(CrewAI, LangGraph), o Claude Desktop/Code ou o VS Code:

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt      (Linux/Mac: .venv/bin/pip)
.venv\Scripts\python servidor_mcp.py
```

A ferramenta devolve `resposta` (texto), `sql` (consulta executada) e `dados` (linhas do banco).
Em caso de falha do Gemini, devolve `erro`. Os logs (`[SQL]`, `[Resultado]`) vão para o stderr,
porque no modo stdio o stdout é usado pelo protocolo.

Exemplo de configuração num cliente MCP (ajuste os caminhos):

```json
{
  "mcpServers": {
    "agente-sql": {
      "command": "C:/caminho/agente-sql/.venv/Scripts/python.exe",
      "args": ["C:/caminho/agente-sql/servidor_mcp.py"]
    }
  }
}
```

## Métricas e avaliação

### Preparar o benchmark

Execute os comandos a partir de `agente-sql/`. O Python precisa ser 3.11 ou superior, e `config.json`
deve conter a chave Gemini, o modelo e o nome do banco em `banco`. Não compartilhe esse arquivo.

O benchmark usa `../projeto_agentes/perguntas_respostas_prisma(in).csv`. Para resultados comparáveis,
aponte `banco` para uma cópia local do banco que originou esse CSV, incluindo `-wal` e `-shm` se
existirem. Um banco Pluggy recém-gerado pode conter dados diferentes e invalidar a comparação; não
use a cópia ativa do celular como referência sem confirmar que é o mesmo snapshot.

### Executar a avaliação

Rode todos os casos com a data de referência fixa do conjunto:

```
python avaliar.py --hoje 2026-11-25
```

O script lê pergunta/resposta do CSV, chama o agente para cada pergunta e compara fatos extraídos da
resposta produzida com o gabarito. Os IDs `q-...` são derivados das perguntas e permanecem estáveis
se a ordem das linhas mudar. Também é possível informar outro arquivo de casos ou outra data:

```
python avaliar.py --csv caminho/para/casos.csv --hoje AAAA-MM-DD
```

Cada caso mostra um destes resultados:

| Resultado | Significado |
|---|---|
| `FATOS_OK` | Valores em reais, datas e contagens extraídos coincidem com o gabarito. |
| `FATOS_DIVERGEM` | Os fatos extraídos não coincidem. |
| `REVISÃO` | O gabarito não tem valores, datas ou contagens que o comparador consiga verificar. |
| `FALHA_<tipo>` | O agente falhou antes de produzir uma resposta avaliável. |

No final, `Acerto de fatos` mostra acertos/casos comparáveis; falhas do agente contam como erros.
Código de saída `0` significa que todos os casos comparáveis passaram; `1` indica divergência,
falha ou ausência de casos comparáveis. O script **não** compara o texto inteiro: nomes de
estabelecimentos/categorias, contexto e qualidade da explicação não são cobertos integralmente.
No CSV atual, 46 de 50 casos têm fatos comparáveis automaticamente; os demais exigem revisão textual.
Trate essa nota como um indicador, não como uma garantia completa de correção.

Opcionalmente, acrescente um juiz LLM para relevância, clareza e fundamentação:

```
python avaliar.py --hoje 2026-11-25 --juiz-llm
```

O juiz faz chamadas adicionais ao Gemini e envia a pergunta, o gabarito e a resposta gerada ao
provedor. Use essa opção apenas se estiver de acordo com esse envio e com o custo/limite de chamadas.
O resultado `JUIZ_OK`/`JUIZ_DIVERGE` é complementar e não substitui a comparação determinística nem
a revisão humana.

### Observar as métricas

Cada operação do CLI/MCP e cada resposta gerada durante a avaliação grava uma linha em
`metricas.db`, separado do banco financeiro e ignorado pelo Git. Veja um resumo acumulado:

```
python metricas.py
```

O resumo apresenta taxa de sucesso operacional, contagem por resultado, latência p50/p95, tokens
reportados e operações do juiz LLM. A taxa operacional não mede se a resposta está correta: uma
consulta sem erro SQL pode ainda responder incorretamente. `sucesso` significa que o fluxo terminou
sem erro de execução SQL; `erro_sql` indica falha ao executar a consulta e `falha` indica erro não
recuperado no fluxo.

Para inspecionar as últimas operações e as latências por etapa, abra `metricas.db` com um visualizador
SQLite ou execute esta consulta:

```sql
SELECT iniciado_em, componente, resultado, tipo_erro,
       ROUND(duracao_ms) AS duracao_ms, etapas_ms,
       chamadas_llm, tentativas_llm, tokens_entrada, tokens_saida, tokens_total,
       tokens_completos, linhas_sql, cortado
FROM operacoes
ORDER BY iniciado_em DESC
LIMIT 20;
```

`etapas_ms` é um objeto JSON com tempos de `geracao_sql_ms`, `execucao_sql_ms` e
`geracao_resposta_ms`. `tokens_*` só vêm do `usageMetadata` devolvido pelo Gemini; `NULL` significa
que o provedor não informou o uso. `tokens_completos = 0` indica que pelo menos uma chamada daquela
operação não teve uso de tokens disponível. As chamadas do juiz são marcadas com `componente =
'juiz_llm'` e não entram na taxa de sucesso do agente.

As métricas não persistem pergunta, SQL, resposta, linhas do banco ou credenciais. O banco cresce
localmente conforme as operações são executadas; remova ou arquive `metricas.db` se quiser começar
um período de medição novo.
