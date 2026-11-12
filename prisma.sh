#!/usr/bin/env bash
# Prisma · inicializa e controla os agentes locais.
#
#   ./prisma.sh iniciar     prepara o ambiente (venv, dependências, .env) e sobe os 4 agentes
#   ./prisma.sh parar       para todos
#   ./prisma.sh reiniciar   para e sobe de novo
#   ./prisma.sh status      mostra quem está no ar
#   ./prisma.sh liberar     derruba agentes do Prisma que ocupam as portas (ex.: de outra pasta)
#   ./prisma.sh logs [agente]  acompanha os logs (armazenamento, coletor, especialista ou risco)
#   ./prisma.sh importar TITULAR   importa os extratos de extratos_ficticios/ no Armazenamento
#   ./prisma.sh indexar     atualiza o índice da base de conhecimento (Gemini ou modelo local)
#   ./prisma.sh testes      roda os testes
#   ./prisma.sh especialista buscar "pergunta"   qualquer comando de um agente, já com o .venv
#   ./prisma.sh coletor analisar                 (o mesmo que python -m <agente> ..., sem ativar nada)
#   ./prisma.sh risco treinar                    treina a rede neural do Agente de Risco (uma vez)
#   ./prisma.sh risco perfil --titular ID        perfil de risco de um titular
#
# Cada agente sobe como serviço HTTP em 127.0.0.1, com o token de ~/.prisma/chaves.json.
# Coletor, Especialista e Risco usam o Armazenamento que está no ar (ARMAZENAMENTO_URL).

set -euo pipefail
cd "$(dirname "$0")"

PORTA_ARMAZENAMENTO="${PORTA_ARMAZENAMENTO:-8000}"
PORTA_COLETOR="${PORTA_COLETOR:-8001}"
PORTA_ESPECIALISTA="${PORTA_ESPECIALISTA:-8002}"
PORTA_RISCO="${PORTA_RISCO:-8003}"
AGENTES=(armazenamento coletor especialista risco)
RUN=".run"                      # pids e logs (fora do Git)
PY=".venv/bin/python"
export PYTHONPATH="$PWD"
export ARMAZENAMENTO_URL="http://127.0.0.1:${PORTA_ARMAZENAMENTO}"

verde()    { printf '\033[32m%s\033[0m\n' "$*"; }
amarelo()  { printf '\033[33m%s\033[0m\n' "$*"; }
vermelho() { printf '\033[31m%s\033[0m\n' "$*" >&2; }

porta_de() {
  case "$1" in
    armazenamento) echo "$PORTA_ARMAZENAMENTO" ;;
    coletor)       echo "$PORTA_COLETOR" ;;
    especialista)  echo "$PORTA_ESPECIALISTA" ;;
    risco)         echo "$PORTA_RISCO" ;;
  esac
}

comando_de() {   # argumentos de "python -m" para subir cada agente em HTTP
  case "$1" in
    armazenamento) echo "armazenamento --http --port $(porta_de "$1")" ;;
    *)             echo "$1 servidor --http --port $(porta_de "$1")" ;;
  esac
}

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
  for d in armazenamento coletor especialista risco comum; do [[ -d "$d" ]] || falta+=("$d/"); done
  [[ -f requirements.txt ]] || falta+=("requirements.txt")
  if (( ${#falta[@]} )); then
    vermelho "Esta pasta ($PWD) não parece ser a raiz do projeto Prisma. Faltando: ${falta[*]}"
    vermelho "Coloque o prisma.sh na pasta que tem armazenamento/, coletor/ e especialista/."
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
    cat > .env <<'MODELO'
# Chave do Gemini: crie em https://aistudio.google.com
GOOGLE_API_KEY=

# Opcionais
# PRISMA_MODELO_LLM=gemini-3.5-flash-lite
# PRISMA_MODELO_EMBEDDING=models/gemini-embedding-001
# PRISMA_NOTA_MINIMA=0.5
MODELO
  fi
  amarelo "Criei o .env. Coloque a GOOGLE_API_KEY nele."
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
    if grep -qE '^PRISMA_EMBEDDINGS=local' .env; then
      amarelo "Sem GOOGLE_API_KEY: a busca usa embeddings locais e o 'perguntar' devolve os trechos, sem texto do Gemini."
    else
      amarelo "Aviso: GOOGLE_API_KEY vazia no .env. Para testar a RAG sem chave, coloque PRISMA_EMBEDDINGS=local no .env."
    fi
  fi
  mkdir -p "$RUN"
}

# ---------------------------------------------------------------- serviços
pid_de()   { cat "$RUN/$1.pid" 2>/dev/null || true; }
rodando()  { local p; p="$(pid_de "$1")"; [[ -n "$p" ]] && kill -0 "$p" 2>/dev/null; }
saudavel() { "$PY" -c "import sys,urllib.request; urllib.request.urlopen(sys.argv[1], timeout=2)" \
               "http://127.0.0.1:$(porta_de "$1")/health" >/dev/null 2>&1; }

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
  [[ -n "$pid" ]] || return 0
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
  if saudavel "$nome" || [[ -n "$(pid_da_porta "$porta")" ]]; then
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

iniciar() {
  preparar
  echo "Subindo os agentes..."
  for a in "${AGENTES[@]}"; do subir "$a"; done   # o Armazenamento sobe primeiro
  echo
  "$PY" -m especialista status 2>/dev/null | "$PY" -c "
import json, sys
s = json.load(sys.stdin)
if s['pendentes']:
    print('Base de conhecimento: %d/%d arquivos indexados. Rode ./prisma.sh indexar' % (s['indexados'], s['arquivos']))
else:
    print('Base de conhecimento: %d arquivos indexados (%d pedaços)' % (s['arquivos'], s['pedacos']))
" || true
  if [[ ! -f "${PRISMA_DIR:-$HOME/.prisma}/modelos/risco_autoencoder.npz" ]]; then
    echo "Rede neural do Agente de Risco: não treinada. Rode ./prisma.sh risco treinar (uma vez, ~1 min)"
  else
    echo "Rede neural do Agente de Risco: treinada"
  fi
  echo "Token dos serviços: MCP_TOKEN em ${PRISMA_DIR:-~/.prisma}/chaves.json"
  echo "Logs: ./prisma.sh logs   ·   Parar: ./prisma.sh parar"
}

parar() {
  echo "Parando os agentes..."
  for (( i=${#AGENTES[@]}-1; i>=0; i-- )); do descer "${AGENTES[i]}"; done   # Armazenamento por último
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
}

logs() {
  mkdir -p "$RUN"
  if [[ -n "${1:-}" ]]; then touch "$RUN/$1.log"; tail -n 50 -f "$RUN/$1.log"
  else touch "$RUN"/{armazenamento,coletor,especialista,risco}.log; tail -n 20 -f "$RUN"/*.log; fi
}

case "${1:-iniciar}" in
  iniciar)   iniciar ;;
  parar)     parar ;;
  reiniciar|reinicio) parar; iniciar ;;
  liberar)   liberar && verde "Portas ${PORTA_ARMAZENAMENTO} a ${PORTA_RISCO} livres." ;;
  status)    status ;;
  logs)      logs "${2:-}" ;;
  importar)
    [[ -n "${2:-}" ]] || { vermelho "Uso: ./prisma.sh importar TITULAR (ex.: 000.000.000-00)"; exit 1; }
    preparar; rodando armazenamento || subir armazenamento
    "$PY" -m coletor importar --titular "$2" ;;
  indexar)   preparar; "$PY" -m especialista indexar ;;
  testes)    preparar; ARMAZENAMENTO_URL="" "$PY" -m pytest ;;
  armazenamento|coletor|especialista|risco)
    preparar >/dev/null
    saudavel armazenamento || unset ARMAZENAMENTO_URL   # sem o serviço no ar, o agente abre o Armazenamento por stdio
    agente="$1"; shift
    "$PY" -m "$agente" "$@" ;;
  *)         sed -n '2,19p' "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
