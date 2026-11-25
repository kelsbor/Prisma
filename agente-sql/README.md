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
2. o SQL é executado sem validação (o banco é aberto como somente leitura);
3. o Gemini recebe a pergunta, o SQL e o resultado (mesmo se der erro ou vier vazio);
4. a resposta aparece na tela. Cada pergunta é independente: não há histórico.

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
