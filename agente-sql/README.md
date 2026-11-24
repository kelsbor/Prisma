# Agente SQL (Python, local)

Só usa a biblioteca padrão do Python (3.11+). Não precisa de `pip install`.

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
