# Cofre Financeiro (servidor MCP)

Guarda dados de transações financeiras em qualquer formato JSON, sem validação,
de forma criptografada, com medidas alinhadas à LGPD.

## Ferramentas MCP
| Tool | O que faz |
|---|---|
| `salvar_transacao(titular_id, dados, finalidade)` | Guarda qualquer JSON, criptografado |
| `consultar_titular(titular_id)` | Devolve tudo de um titular (LGPD art. 18, II: acesso) |
| `eliminar_titular(titular_id)` | Apaga tudo de um titular (LGPD art. 18, VI: eliminação) |

## Segurança
- Dados criptografados no banco (Fernet: AES-128-CBC + HMAC-SHA256).
- CPF/ID do titular nunca é gravado; só um hash HMAC-SHA256 (pseudonimização).
- Acesso só com `Authorization: Bearer <MCP_TOKEN>`; HTTPS no Render.
- Tabela `auditoria` registra ação, titular (hash) e horário, sem o conteúdo.
- Logs de acesso desligados (`--no-access-log`).

## Chaves
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"   # ENCRYPTION_KEY
```
Guarde a ENCRYPTION_KEY e a HASH_KEY fora do Render (ex.: gerenciador de senhas).
Se perder alguma delas, os dados não podem mais ser lidos nem localizados.

## Rodar localmente
```bash
pip install -r requirements.txt
cp .env.example .env    # preencha as 3 chaves
export $(grep -v '^#' .env | xargs)
uvicorn app.server:app --reload --no-access-log
```
Endpoint: `http://localhost:8000/mcp`

## Deploy no Render
Use New > Blueprint e escolha o repositório. Cole a ENCRYPTION_KEY quando pedir.
Endpoint: `https://<servico>.onrender.com/mcp`
