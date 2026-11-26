#!/usr/bin/env bash
# Prisma · inicializa e controla os agentes locais.
#
#   ./prisma.sh iniciar     prepara o ambiente (venv, dependências, .env) e sobe os 3 agentes
#   ./prisma.sh parar       para todos
#   ./prisma.sh reiniciar   para e sobe de novo
#   ./prisma.sh status      mostra quem está no ar
#   ./prisma.sh logs [agente]  acompanha os logs (indicadores, especialista ou consultas)
#   ./prisma.sh env         mostra a configuração única (.env), sem expor segredos
#   ./prisma.sh pluggy      baixa contas e transações da Pluggy (Open Finance) para o banco local
#   ./prisma.sh indexar     atualiza o índice da base de conhecimento (Gemini ou modelo local)
#   ./prisma.sh especialista perguntar "pergunta" [--com-dados]
#   ./prisma.sh consultas perguntar "pergunta"     perguntas sobre os gastos, com SQL validado
#   ./prisma.sh sql "pergunta"                     agente-sql da equipe (inclui saldo, fatura e limite)
#   ./prisma.sh indicadores juros                  juros médios do Banco Central
#   ./prisma.sh orquestrador chat                  conversa com todos os agentes (só finanças)
#   ./prisma.sh app [parar] assistente do PrismaAPP (porta 8010), com o mesmo .env
#   ./prisma.sh testes      roda os testes
#   ./prisma.sh liberar     derruba agentes do Prisma que ocupam as portas (ex.: de outra pasta)
#
# Cada agente sobe como serviço HTTP em 127.0.0.1, com o token de ~/.prisma/chaves.json.
# O Especialista usa o Agente de Indicadores que está no ar (INDICADORES_URL).
set -euo pipefail
cd "$(dirname "$0")"

PORTA_ESPECIALISTA="${PORTA_ESPECIALISTA:-8002}"
PORTA_INDICADORES="${PORTA_INDICADORES:-8004}"
PORTA_CONSULTAS="${PORTA_CONSULTAS:-8006}"
AGENTES=(indicadores especialista consultas)
RUN=".run"                      # pids e logs (fora do Git)
APP_DIR="${PRISMA_APP_DIR:-../PrismaAPP}"   # o app Android e o servidor do assistente dele
SQL_DIR="${PRISMA_SQL_DIR:-../agente-sql}"  # agente-sql da equipe: download da Pluggy e text-to-SQL simples
PY=".venv/bin/python"
export PYTHONPATH="$PWD"
export INDICADORES_URL="http://127.0.0.1:${PORTA_INDICADORES}"

verde()    { printf '\033[32m%s\033[0m\n' "$*"; }
amarelo()  { printf '\033[33m%s\033[0m\n' "$*"; }
vermelho() { printf '\033[31m%s\033[0m\n' "$*" >&2; }

porta_de() {
  case "$1" in
    especialista)  echo "$PORTA_ESPECIALISTA" ;;
    indicadores)   echo "$PORTA_INDICADORES" ;;
    consultas)     echo "$PORTA_CONSULTAS" ;;
  esac
}

comando_de() { echo "$1 servidor --http --port $(porta_de "$1")"; }   # argumentos de "python -m"

# ---------------------------------------------------------------- preparação
achar_python() {
  for c in python3.12 python3.11 python3.10 python3; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
      echo "$c"; return
    fi
  done
  vermelho "Preciso de Python 3.10 ou mais novo (ex.: python3.11). Instale e rode de novo."
  exit 1
}

conferir_projeto() {
  local falta=()
  for d in especialista indicadores consultas comum; do [[ -d "$d" ]] || falta+=("$d/"); done
  [[ -f requirements.txt ]] || falta+=("requirements.txt")
  if (( ${#falta[@]} )); then
    vermelho "Esta pasta ($PWD) não parece ser a raiz do projeto Prisma. Faltando: ${falta[*]}"
    vermelho "Coloque o prisma.sh na pasta que tem especialista/, indicadores/ e consultas/."
    exit 1
  fi
}

criar_env() {
  if [[ -d .env.example ]]; then
    vermelho "'.env.example' é uma pasta (provavelmente um venv criado por engano). Apague com: rm -rf .env.example"
    exit 1
  fi
  if [[ -f .env.example ]]; then
    cp .env.example .env
  else                                   # o .env.example pode não ter sido copiado (arquivos com ponto ficam ocultos)
    printf 'PLUGGY_CLIENT_ID=\nPLUGGY_CLIENT_SECRET=\nPLUGGY_ITEM_IDS=\nGOOGLE_API_KEY=\nGEMINI_MODEL=gemini-3.5-flash-lite\nPRISMA_EMBEDDINGS=local\nAPP_TOKENS=\n' > .env
  fi
  chmod 600 .env
  amarelo "Criei o .env (configuração única do projeto). Coloque a GOOGLE_API_KEY nele."
}

valor_env() { grep -E "^$1=" .env 2>/dev/null | tail -1 | cut -d= -f2- || true; }

definir_env() {   # grava CHAVE=valor no .env (troca a linha se existir)
  if grep -qE "^$1=" .env; then
    "$PY" -c "import re,sys; p='.env'; s=open(p).read(); s=re.sub(r'(?m)^'+re.escape(sys.argv[1])+r'=.*$', sys.argv[1]+'='+sys.argv[2], s); open(p,'w').write(s)" "$1" "$2"
  else
    printf '%s=%s\n' "$1" "$2" >> .env
  fi
}

mostrar_env() {   # o que está configurado, sem mostrar segredos
  [[ -f .env ]] || criar_env
  echo "Configuração única: $PWD/.env"
  local k v
  for k in GOOGLE_API_KEY GEMINI_MODEL PRISMA_EMBEDDINGS APP_TOKENS PLUGGY_CLIENT_ID PLUGGY_CLIENT_SECRET \
           PLUGGY_ITEM_IDS LLM_TIMEOUT_S PRISMA_APP_DB; do
    v="$(valor_env "$k")"
    if [[ -z "$v" ]]; then printf '  %-22s (vazio)\n' "$k"
    elif [[ "$k" == GOOGLE_API_KEY || "$k" == APP_TOKENS || "$k" == PLUGGY_* ]]; then printf '  %-22s definido (%s caracteres)\n' "$k" "${#v}"
    else printf '  %-22s %s\n' "$k" "$v"; fi
  done
  if [[ -f "$APP_DIR/agent/.env" ]]; then
    amarelo "Existe também $APP_DIR/agent/.env (antigo). O ./prisma.sh app usa só o .env daqui; pode apagar o antigo."
  fi
}

app_servidor() {   # servidor do assistente do PrismaAPP, com o MESMO .env do Prisma
  local porta="${PORTA_APP:-8010}" pidf="$RUN/app.pid" dir="$APP_DIR/agent"
  mkdir -p "$RUN"
  if [[ "${1:-}" == parar ]]; then
    local p q cmd; p="$(cat "$pidf" 2>/dev/null || true)"
    if [[ -n "$p" ]] && kill -0 "$p" 2>/dev/null; then
      kill -- "-$p" 2>/dev/null || kill "$p"          # o grupo inteiro: uv e o uvicorn filho
      echo "  servidor do app parado"
    else
      echo "  servidor do app não estava rodando"
    fi
    rm -f "$pidf"
    sleep 1
    q="$(pid_da_porta "$porta")"                        # sobrou algum uvicorn do app na porta?
    if [[ -n "$q" ]]; then
      cmd="$(tr '\0' ' ' < "/proc/$q/cmdline" 2>/dev/null)"
      if [[ "$cmd" == *"prisma_agent.api"* ]]; then kill "$q" && echo "  uvicorn antigo do app encerrado (pid $q)"; fi
    fi
    return
  fi
  [[ -d "$dir/src/prisma_agent" ]] || { vermelho "Não encontrei o assistente do app em $dir (defina PRISMA_APP_DIR)."; return 1; }
  command -v uv >/dev/null || { vermelho "Falta o uv: sudo snap install --classic astral-uv"; return 1; }
  [[ -f .env ]] || criar_env
  # traz do .env antigo do app o que ainda não existe aqui (só uma vez: depois o .env daqui manda)
  local marca="${PRISMA_DIR:-$HOME/.prisma}/app/.env-do-app-migrado"
  if [[ -f "$dir/.env" && ! -f "$marca" ]]; then
    mkdir -p "$(dirname "$marca")"; touch "$marca"
    local k v
    for k in GOOGLE_API_KEY APP_TOKENS GEMINI_MODEL; do
      v="$(grep -E "^$k=" "$dir/.env" | tail -1 | cut -d= -f2- || true)"
      if [[ -n "$v" && -z "$(valor_env "$k")" ]]; then definir_env "$k" "$v"; echo "  $k copiado de $dir/.env"; fi
    done
    amarelo "Agora o .env único manda. Pode apagar o antigo: rm $dir/.env"
  fi
  [[ -n "$(valor_env GOOGLE_API_KEY)" ]] || { vermelho "Coloque a GOOGLE_API_KEY no .env antes de subir o assistente do app."; return 1; }
  if [[ "$(valor_env APP_TOKENS | cut -d, -f1 | tr -d ' ' | wc -c)" -lt 25 ]]; then
    definir_env APP_TOKENS "$("$PY" -c 'import secrets; print(secrets.token_urlsafe(32))')"
    amarelo "Gerei um APP_TOKENS novo no .env. Use o MESMO valor em assistant.token no local.properties do app."
  fi
  local p; p="$(cat "$pidf" 2>/dev/null || true)"
  if [[ -z "$p" ]] || ! kill -0 "$p" 2>/dev/null; then
    if porta_ocupada "$porta"; then
      local q cmd; q="$(pid_da_porta "$porta")"
      cmd="$(tr '\0' ' ' < "/proc/$q/cmdline" 2>/dev/null || true)"
      if [[ -n "$q" && "$cmd" == *"prisma_agent.api"* ]]; then
        kill "$q"; sleep 1; echo "  uvicorn antigo do app encerrado (pid $q)"
      else
        vermelho "A porta $porta está ocupada por outro programa${q:+ (pid $q)}. Pare-o ou mude PORTA_APP."; return 1
      fi
    fi
    (
      cd "$dir" || exit 1
      # o próprio uv vira líder de um grupo de processos: o "parar" encerra o uv e o uvicorn filho juntos
      setsid nohup uv run --env-file "$OLDPWD/.env" uvicorn prisma_agent.api:app --app-dir src \
        --host 127.0.0.1 --port "$porta" >> "$OLDPWD/$RUN/app.log" 2>&1 < /dev/null &
      echo $! > "$OLDPWD/$pidf"
    )
    echo "Subindo o assistente do PrismaAPP (na 1ª vez o uv instala as dependências)..."
  fi
  for _ in $(seq 1 90); do
    "$PY" -c "import sys,urllib.request; urllib.request.urlopen(sys.argv[1], timeout=2)" "http://127.0.0.1:$porta/health" >/dev/null 2>&1 && break
    sleep 2
  done
  if ! "$PY" -c "import sys,urllib.request; urllib.request.urlopen(sys.argv[1], timeout=2)" "http://127.0.0.1:$porta/health" >/dev/null 2>&1; then
    vermelho "O assistente do app não respondeu. Últimas linhas de $RUN/app.log:"; tail -n 15 "$RUN/app.log" >&2; return 1
  fi
  verde "Assistente do PrismaAPP no ar: http://127.0.0.1:$porta"
  local adb; adb="$(command -v adb || echo "$HOME/Android/Sdk/platform-tools/adb")"
  if [[ -x "$adb" ]] && "$adb" get-state >/dev/null 2>&1; then
    "$adb" reverse "tcp:$porta" "tcp:$porta" >/dev/null && verde "adb reverse tcp:$porta feito: o celular já alcança o assistente."
  else
    echo "Com o celular conectado, rode: adb reverse tcp:$porta tcp:$porta"
  fi
  echo "No local.properties do app: assistant.token=<APP_TOKENS do .env> e assistant.url=http\\://127.0.0.1\\:$porta/"
  echo "(no emulador, assistant.url=http\\://10.0.2.2\\:$porta/). Depois, Run 'app' de novo no Android Studio."
}

preparar() {
  conferir_projeto
  if [[ ! -x "$PY" ]]; then
    local base; base="$(achar_python)"
    amarelo "Criando o ambiente virtual com $base..."
    "$base" -m venv .venv || { vermelho "Falhou. No Ubuntu, instale: sudo apt install ${base}-venv"; exit 1; }
  fi

  local marca=".venv/.requirements.sha256" atual
  atual="$(sha256sum requirements.txt | cut -d' ' -f1)"
  if [[ ! -f "$marca" || "$(cat "$marca")" != "$atual" ]]; then
    amarelo "Instalando dependências (só quando o requirements.txt muda)..."
    "$PY" -m pip install -q --upgrade pip
    "$PY" -m pip install -q -r requirements.txt
    echo "$atual" > "$marca"
  fi

  [[ -f .env ]] || criar_env
  if ! grep -qE '^GOOGLE_API_KEY=.+' .env; then
    amarelo "Aviso: GOOGLE_API_KEY vazia no .env. Sem ela, o Especialista devolve só os trechos da base, e o Consultas, o agente-sql e o assistente do app não respondem."
  fi
  mkdir -p "$RUN"
}

# ---------------------------------------------------------------- serviços
pid_de()   { cat "$RUN/$1.pid" 2>/dev/null || true; }
rodando()  { local p; p="$(pid_de "$1")"; [[ -n "$p" ]] && kill -0 "$p" 2>/dev/null; }
saudavel() {   # o /health responde E é do agente certo (outro programa na porta não conta)
  "$PY" -c "import json,sys,urllib.request
d = json.load(urllib.request.urlopen(sys.argv[1], timeout=2))
sys.exit(0 if d.get('agente') == sys.argv[2] else 1)" \
    "http://127.0.0.1:$(porta_de "$1")/health" "agente-$1" >/dev/null 2>&1
}
porta_ocupada() { "$PY" -c "import socket,sys; s=socket.socket(); s.settimeout(1); sys.exit(0 if s.connect_ex(('127.0.0.1', int(sys.argv[1]))) == 0 else 1)" "$1"; }

pid_da_porta() {   # PID de quem escuta na porta (só processos do próprio usuário; lê o /proc, sem ss/lsof)
  python3 - "$1" <<'PY' 2>/dev/null
import os, sys
porta, inodes = int(sys.argv[1]), set()
for arq in ("/proc/net/tcp", "/proc/net/tcp6"):
    try:
        for linha in open(arq).readlines()[1:]:
            c = linha.split()
            if c[3] == "0A" and int(c[1].rsplit(":", 1)[1], 16) == porta:
                inodes.add(f"socket:[{c[9]}]")
    except OSError:
        pass
for pid in filter(str.isdigit, os.listdir("/proc")):
    try:
        if any(os.readlink(f"/proc/{pid}/fd/{fd}") in inodes for fd in os.listdir(f"/proc/{pid}/fd")):
            print(pid)
            break
    except OSError:
        pass
PY
}

liberar_porta() {   # derruba quem ocupa a porta do agente, mas só se for um agente do Prisma
  local nome="$1" porta pid cmd
  porta="$(porta_de "$nome")"
  pid="$(pid_da_porta "$porta")"
  if [[ -z "$pid" ]]; then
    porta_ocupada "$porta" || return 0
    vermelho "  A porta $porta está ocupada por um programa de outro usuário (talvez iniciado com sudo). Não mexi nele."
    vermelho "  Pare-o ou mude PORTA_${nome^^}."
    return 1
  fi
  cmd="$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null)"
  if [[ "$cmd" != *"-m $nome"* ]]; then
    vermelho "  A porta $porta está com outro programa (pid $pid: ${cmd:-desconhecido}). Não mexi nele."
    vermelho "  Pare-o ou mude PORTA_${nome^^}."
    return 1
  fi
  kill "$pid" 2>/dev/null || true
  for _ in $(seq 1 20); do kill -0 "$pid" 2>/dev/null || break; sleep 0.25; done
  kill -0 "$pid" 2>/dev/null && kill -9 "$pid"
  amarelo "  porta $porta liberada (havia um $nome antigo no ar, pid $pid)"
}

subir() {
  local nome="$1" porta; porta="$(porta_de "$nome")"
  if rodando "$nome"; then
    echo "  $nome já está no ar (porta $porta)"; return
  fi
  if porta_ocupada "$porta"; then
    liberar_porta "$nome" || return 1
  fi
  # shellcheck disable=SC2046
  nohup "$PY" -m $(comando_de "$nome") >> "$RUN/$nome.log" 2>&1 &
  echo $! > "$RUN/$nome.pid"
  for _ in $(seq 1 40); do                 # espera até 20 s pelo /health
    if saudavel "$nome"; then verde "  $nome no ar: http://127.0.0.1:$porta/mcp"; return; fi
    if ! rodando "$nome"; then break; fi
    sleep 0.5
  done
  vermelho "  $nome não subiu. Últimas linhas do log ($RUN/$nome.log):"
  tail -n 15 "$RUN/$nome.log" >&2
  return 1
}

descer() {
  local nome="$1" p; p="$(pid_de "$nome")"
  if [[ -n "$p" ]] && kill -0 "$p" 2>/dev/null; then
    kill "$p"
    for _ in $(seq 1 20); do kill -0 "$p" 2>/dev/null || break; sleep 0.25; done
    kill -0 "$p" 2>/dev/null && kill -9 "$p"
    echo "  $nome parado"
  else
    echo "  $nome não estava rodando"
  fi
  rm -f "$RUN/$nome.pid"
}

banco_app() { echo "${PRISMA_APP_DB:-$(valor_env PRISMA_APP_DB)}" | sed "s|^~|$HOME|" | grep . || echo "${PRISMA_DIR:-$HOME/.prisma}/app/prisma.db"; }

agente_sql_pronto() {
  [[ -f "$SQL_DIR/agente.py" ]] || { vermelho "Não encontrei o agente-sql em $SQL_DIR (defina PRISMA_SQL_DIR)."; return 1; }
}

agente_sql_pluggy() {   # baixa da Pluggy para o banco do app (PRISMA_APP_DB), usando o .env único
  agente_sql_pronto || return 1
  PRISMA_ENV_FILE="$PWD/.env" "$PY" "$SQL_DIR/gerar_banco.py" || return 1
  chmod 600 "$(banco_app)"* 2>/dev/null || true       # dados financeiros reais: só o seu usuário lê
  verde "Pronto. Agora: ./prisma.sh especialista resumo  ou  ./prisma.sh consultas status"
}

agente_sql_perguntar() {
  agente_sql_pronto || return 1
  [[ -n "$1" ]] || { vermelho 'Uso: ./prisma.sh sql "quanto gastei com mercado em outubro?"'; return 1; }
  PRISMA_ENV_FILE="$PWD/.env" "$PY" - "$SQL_DIR" "$1" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
import agente
if not agente.CONFIG.get("gemini_api_key"):
    sys.exit("Coloque a GOOGLE_API_KEY no .env.")
try:
    r = agente.responder_detalhado(sys.argv[2])
except Exception as e:
    sys.exit(f"Falhou: {e}")
print(r["resposta"])
print("\nSQL:", r["sql"])
PY
}

iniciar() {
  preparar
  echo "Subindo os agentes..."
  for a in "${AGENTES[@]}"; do subir "$a"; done   # o Indicadores sobe antes do Especialista
  echo
  "$PY" -m especialista status 2>/dev/null | "$PY" -c "
import json, sys
s = json.load(sys.stdin)
if s['pendentes']:
    print('Base de conhecimento: %d/%d arquivos indexados. Rode ./prisma.sh indexar' % (s['indexados'], s['arquivos']))
else:
    print('Base de conhecimento: %d arquivos indexados (%d pedaços)' % (s['arquivos'], s['pedacos']))
" || true
  if [[ -f "$(banco_app)" ]]; then
    echo "Dados da Pluggy: $(banco_app)"
  else
    echo "Dados da Pluggy: ainda não baixados. Preencha PLUGGY_* no .env e rode ./prisma.sh pluggy"
  fi
  echo "Token dos serviços: MCP_TOKEN em ${PRISMA_DIR:-~/.prisma}/chaves.json"
  echo "Logs: ./prisma.sh logs   ·   Parar: ./prisma.sh parar"
}

parar() {
  echo "Parando os agentes..."
  for (( i=${#AGENTES[@]}-1; i>=0; i-- )); do descer "${AGENTES[i]}"; done
  liberar >/dev/null || true             # agentes do Prisma que sobraram de outra pasta
}

liberar() {
  local falhou=0
  for a in "${AGENTES[@]}"; do liberar_porta "$a" || falhou=1; done
  return "$falhou"
}

status() {
  for a in "${AGENTES[@]}"; do
    if rodando "$a" && saudavel "$a"; then
      verde "  $a: no ar (pid $(pid_de "$a"), http://127.0.0.1:$(porta_de "$a")/mcp)"
    elif rodando "$a"; then
      amarelo "  $a: processo vivo, mas sem responder (veja ./prisma.sh logs $a)"
    else
      echo "  $a: parado"
    fi
  done
  local pa; pa="$(cat "$RUN/app.pid" 2>/dev/null || true)"
  if [[ -n "$pa" ]] && kill -0 "$pa" 2>/dev/null; then
    verde "  app (assistente do PrismaAPP): no ar (pid $pa, http://127.0.0.1:${PORTA_APP:-8010})"
  fi
}

logs() {
  mkdir -p "$RUN"
  if [[ -n "${1:-}" ]]; then touch "$RUN/$1.log"; tail -n 50 -f "$RUN/$1.log"
  else touch "$RUN"/{indicadores,especialista,consultas}.log; tail -n 20 -f "$RUN"/*.log; fi
}

case "${1:-iniciar}" in
  iniciar)   iniciar ;;
  parar)     parar ;;
  reiniciar|reinicio) parar; iniciar ;;
  liberar)   liberar && verde "Portas dos agentes livres." ;;
  status)    status ;;
  logs)      logs "${2:-}" ;;
  indexar)   preparar; "$PY" -m especialista indexar ;;
  testes)    preparar; INDICADORES_URL="" "$PY" -m pytest ;;
  app)       preparar; app_servidor "${2:-}" ;;
  pluggy)    preparar; agente_sql_pluggy ;;
  sql)       preparar; agente_sql_perguntar "${2:-}" ;;
  env)       preparar >/dev/null; mostrar_env ;;
  especialista|indicadores|consultas)
    preparar >/dev/null
    saudavel indicadores || unset INDICADORES_URL       # sem o serviço no ar, o Especialista abre o Indicadores por stdio
    agente="$1"; shift
    "$PY" -m "$agente" "$@" ;;
  orquestrador)
    preparar >/dev/null
    saudavel indicadores || unset INDICADORES_URL       # sem os serviços no ar, o orquestrador abre os agentes por stdio
    saudavel especialista && export ESPECIALISTA_URL="http://127.0.0.1:${PORTA_ESPECIALISTA}"
    shift; "$PY" -m orquestrador "$@" ;;
  ajuda|help|-h|--help) sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//' ;;
  *)         sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
