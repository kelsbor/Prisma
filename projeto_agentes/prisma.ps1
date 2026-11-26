<#
Prisma · controla os agentes no Windows (PowerShell / terminal do VS Code), sem WSL.
Faz o mesmo que o prisma.sh do Linux.

  .\prisma.ps1 iniciar      prepara o ambiente (venv, dependências, .env) e sobe os 3 agentes
  .\prisma.ps1 parar        para todos
  .\prisma.ps1 reiniciar    para e sobe de novo
  .\prisma.ps1 status       mostra quem está no ar
  .\prisma.ps1 logs [agente]   últimas linhas do log (indicadores, especialista ou consultas)
  .\prisma.ps1 env          mostra a configuração (.env), sem expor segredos
  .\prisma.ps1 pluggy       baixa contas e transações da Pluggy para o banco local
  .\prisma.ps1 indexar      atualiza o índice da base de conhecimento
  .\prisma.ps1 testes       roda os testes
  .\prisma.ps1 sql "pergunta"                   agente-sql (inclui saldo, fatura e limite)
  .\prisma.ps1 app [parar]  assistente do PrismaAPP (porta 8010), com o mesmo .env
  .\prisma.ps1 especialista perguntar "pergunta" [--com-dados]
  .\prisma.ps1 consultas perguntar "pergunta"
  .\prisma.ps1 indicadores juros
  .\prisma.ps1 orquestrador chat                 conversa com todos os agentes (só finanças)

Se o PowerShell bloquear scripts: powershell -ExecutionPolicy Bypass -File .\prisma.ps1 iniciar
#>

param(
    [Parameter(Position = 0)][string]$Comando = "iniciar",
    [Parameter(Position = 1, ValueFromRemainingArguments = $true)][string[]]$Resto = @()
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$Raiz = $PSScriptRoot
$NoWindows = ($env:OS -eq "Windows_NT")
if ($NoWindows) { $Py = Join-Path $Raiz ".venv\Scripts\python.exe" } else { $Py = Join-Path $Raiz ".venv/bin/python" }
$Run = Join-Path $Raiz ".run"
$PastaApp = Join-Path (Split-Path $Raiz -Parent) "PrismaAPP"
$PastaSql = Join-Path (Split-Path $Raiz -Parent) "agente-sql"
$Agentes = [ordered]@{ indicadores = 8004; especialista = 8002; consultas = 8006 }   # Indicadores antes do Especialista
$PortaApp = 8010
$Oculto = @{}
if ($NoWindows) { $Oculto = @{ WindowStyle = "Hidden" } }   # sem janela extra para cada agente
$SemBom = New-Object System.Text.UTF8Encoding $false        # .env sem BOM (o Python e o Linux leem igual)

$env:PYTHONPATH = $Raiz
$env:PRISMA_ENV_FILE = Join-Path $Raiz ".env"
$env:PYTHONUTF8 = "1"                                  # acentos certos no console do Windows
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

function Verde($t) { Write-Host $t -ForegroundColor Green }
function Amarelo($t) { Write-Host $t -ForegroundColor Yellow }
function Vermelho($t) { Write-Host $t -ForegroundColor Red }

# ------------------------------------------------------------------ ambiente
function Achar-Python {
    $tentativas = @(@("py", "-3.12"), @("py", "-3.11"), @("py", "-3.10"), @("python3.12"), @("python3.11"), @("python3"), @("python"))
    foreach ($t in $tentativas) {
        $exe = $t[0]
        $cmd = Get-Command $exe -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        $argsV = @()
        if ($t.Count -gt 1) { $argsV += $t[1] }
        $argsV += @("-c", "import sys; print(sys.version_info >= (3, 10))")
        try { $ok = & $exe @argsV 2>$null } catch { $ok = "" }
        if ("$ok".Trim() -eq "True") { return , $t }
    }
    Vermelho "Preciso do Python 3.10 ou mais novo. Instale pelo python.org (marque 'Add python.exe to PATH')"
    Vermelho "e desligue o atalho da Store: Configurações > Aplicativos > Aliases de execução > python.exe."
    exit 1
}

function Criar-Env {
    $modelo = Join-Path $Raiz ".env.example"
    if (Test-Path $modelo -PathType Leaf) { Copy-Item $modelo (Join-Path $Raiz ".env") }
    else { [System.IO.File]::WriteAllText((Join-Path $Raiz ".env"), "PLUGGY_CLIENT_ID=`nPLUGGY_CLIENT_SECRET=`nPLUGGY_ITEM_IDS=`nGOOGLE_API_KEY=`nGEMINI_MODEL=gemini-3.5-flash-lite`nPRISMA_EMBEDDINGS=local`nAPP_TOKENS=`n", $SemBom) }
    Amarelo "Criei o .env (configuração única do projeto). Preencha a GOOGLE_API_KEY e as credenciais PLUGGY_*."
}

function Valor-Env($chave) {
    $arq = Join-Path $Raiz ".env"
    if (-not (Test-Path $arq)) { return "" }
    $linha = Get-Content $arq -Encoding utf8 | Where-Object { $_ -match "^$chave=" } | Select-Object -Last 1
    if ($linha) { return ($linha -replace "^$chave=", "").Trim() }
    return ""
}

function Definir-Env($chave, $valor) {
    $arq = Join-Path $Raiz ".env"
    $linhas = @(Get-Content $arq -Encoding utf8)
    if ($linhas -match "^$chave=") { $linhas = $linhas -replace "^$chave=.*$", "$chave=$valor" }
    else { $linhas += "$chave=$valor" }
    [System.IO.File]::WriteAllLines($arq, [string[]]$linhas, $SemBom)
}

function Preparar {
    if (-not (Test-Path $Py)) {
        $base = Achar-Python
        Write-Host "Criando o ambiente virtual (.venv)..."
        $argsV = @()
        if ($base.Count -gt 1) { $argsV += $base[1] }
        & $base[0] @argsV -m venv (Join-Path $Raiz ".venv")
        if ($LASTEXITCODE -ne 0) { Vermelho "Não consegui criar o .venv."; exit 1 }
    }
    $marca = Join-Path $Raiz ".venv\.requirements.sha256"
    $hash = (Get-FileHash (Join-Path $Raiz "requirements.txt") -Algorithm SHA256).Hash
    $anterior = ""
    if (Test-Path $marca) { $anterior = (Get-Content $marca -Raw).Trim() }
    if ($hash -ne $anterior) {
        Write-Host "Instalando dependências (só quando o requirements.txt muda; a 1ª vez demora)..."
        & $Py -m pip install -q --upgrade pip
        & $Py -m pip install -q -r (Join-Path $Raiz "requirements.txt")
        if ($LASTEXITCODE -ne 0) { Vermelho "Falha ao instalar as dependências."; exit 1 }
        Set-Content -Path $marca -Value $hash
    }
    if ($NoWindows) {
        # o .vscode (mcp.json e settings.json) usa .venv/bin/python, o caminho do Linux: no Windows
        # criamos uma cópia do executável do venv nesse caminho, para os dois sistemas usarem o mesmo arquivo
        $bin = Join-Path $Raiz ".venv\bin"
        if (-not (Test-Path (Join-Path $bin "python.exe"))) {
            New-Item -ItemType Directory -Force -Path $bin | Out-Null
            Copy-Item (Join-Path $Raiz ".venv\Scripts\python.exe") (Join-Path $bin "python.exe")
        }
    }
    if (-not (Test-Path (Join-Path $Raiz ".env"))) { Criar-Env }
    New-Item -ItemType Directory -Force -Path $Run | Out-Null
}

# ------------------------------------------------------------------ serviços
function Saudavel($nome) {
    try {
        $r = Invoke-RestMethod -Uri "http://127.0.0.1:$($Agentes[$nome])/health" -TimeoutSec 2
        return ($r.agente -eq "agente-$nome")
    } catch { return $false }
}

function Pid-De($nome) {
    $arq = Join-Path $Run "$nome.pid"
    if (-not (Test-Path $arq)) { return $null }
    $id = (Get-Content $arq -Raw).Trim()
    if ($id -and (Get-Process -Id $id -ErrorAction SilentlyContinue)) { return [int]$id }
    return $null
}

function Subir($nome) {
    if (Pid-De $nome) { Write-Host "  $nome já está no ar (porta $($Agentes[$nome]))"; return }
    $log = Join-Path $Run "$nome.log"
    $argList = @("-m", $nome, "servidor", "--http", "--port", "$($Agentes[$nome])")
    $p = Start-Process -FilePath $Py -ArgumentList $argList -WorkingDirectory $Raiz -PassThru @Oculto `
        -RedirectStandardOutput "$log.out" -RedirectStandardError $log
    Set-Content -Path (Join-Path $Run "$nome.pid") -Value $p.Id
    for ($i = 0; $i -lt 60; $i++) {
        if (Saudavel $nome) { Verde "  $nome no ar: http://127.0.0.1:$($Agentes[$nome])/mcp"; return }
        if ($p.HasExited) { break }
        Start-Sleep -Milliseconds 500
    }
    Vermelho "  $nome não subiu. Últimas linhas de .run\$nome.log:"
    if (Test-Path $log) { Get-Content $log -Tail 15 }
}

function Descer($nome) {
    $id = Pid-De $nome
    if ($id) { Stop-Process -Id $id -Force; Write-Host "  $nome parado" }
    else { Write-Host "  $nome não estava rodando" }
    Remove-Item (Join-Path $Run "$nome.pid") -ErrorAction SilentlyContinue
}

function Iniciar {
    Preparar
    if (-not (Valor-Env "GOOGLE_API_KEY")) {
        Amarelo "Aviso: GOOGLE_API_KEY vazia no .env. Sem ela, o Especialista devolve só os trechos da base."
    }
    $env:INDICADORES_URL = "http://127.0.0.1:$($Agentes['indicadores'])"   # o Especialista fala com o Indicadores no ar
    Write-Host "Subindo os agentes..."
    foreach ($a in $Agentes.Keys) { Subir $a }
    $banco = Valor-Env "PRISMA_APP_DB"
    if (-not $banco) {
        $dados = $env:PRISMA_DIR
        if (-not $dados) { $dados = Join-Path $HOME ".prisma" }
        $banco = Join-Path (Join-Path $dados "app") "prisma.db"
    }
    if (Test-Path $banco) { Write-Host "Dados da Pluggy: $banco" }
    else { Write-Host "Dados da Pluggy: ainda não baixados. Preencha PLUGGY_* no .env e rode .\prisma.ps1 pluggy" }
    Write-Host "Parar: .\prisma.ps1 parar   ·   Logs: .\prisma.ps1 logs"
}

function Parar {
    Write-Host "Parando os agentes..."
    foreach ($a in @($Agentes.Keys)[($Agentes.Count - 1)..0]) { Descer $a }
}

function Status {
    foreach ($a in $Agentes.Keys) {
        $id = Pid-De $a
        if ($id -and (Saudavel $a)) { Verde "  ${a}: no ar (pid $id, http://127.0.0.1:$($Agentes[$a])/mcp)" }
        else { Write-Host "  ${a}: parado" }
    }
    $pa = Pid-De "app"
    if ($pa) { Verde "  app (assistente do PrismaAPP): no ar (pid $pa, http://127.0.0.1:$PortaApp)" }
}

function Mostrar-Env {
    if (-not (Test-Path (Join-Path $Raiz ".env"))) { Criar-Env }
    Write-Host "Configuração única: $Raiz\.env"
    foreach ($k in @("GOOGLE_API_KEY", "GEMINI_MODEL", "PRISMA_EMBEDDINGS", "APP_TOKENS", "PLUGGY_CLIENT_ID",
                     "PLUGGY_CLIENT_SECRET", "PLUGGY_ITEM_IDS", "PRISMA_APP_DB")) {
        $v = Valor-Env $k
        if (-not $v) { Write-Host ("  {0,-22} (vazio)" -f $k) }
        elseif ($k -in @("GOOGLE_API_KEY", "APP_TOKENS") -or $k -like "PLUGGY_*") { Write-Host ("  {0,-22} definido ({1} caracteres)" -f $k, $v.Length) }
        else { Write-Host ("  {0,-22} {1}" -f $k, $v) }
    }
}

# ------------------------------------------------------------------ PrismaAPP e agente-sql
function App($acao) {
    $pidf = Join-Path $Run "app.pid"
    if ($acao -eq "parar") {
        $id = Pid-De "app"
        if ($id) {
            if ($NoWindows) { & taskkill /PID $id /T /F | Out-Null } else { Stop-Process -Id $id -Force }   # /T: o uv e o uvicorn filho
            Write-Host "  servidor do app parado"
        }
        else { Write-Host "  servidor do app não estava rodando" }
        Remove-Item $pidf -ErrorAction SilentlyContinue
        return
    }
    $dir = Join-Path $PastaApp "agent"
    if (-not (Test-Path (Join-Path $dir "src\prisma_agent"))) { Vermelho "Não encontrei o assistente do app em $dir."; return }
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { Vermelho "Falta o uv: winget install astral-sh.uv (feche e abra o terminal depois)."; return }
    if (-not (Valor-Env "GOOGLE_API_KEY")) { Vermelho "Coloque a GOOGLE_API_KEY no .env antes."; return }
    $token = (Valor-Env "APP_TOKENS").Split(",")[0].Trim()
    if ($token.Length -lt 24) {
        $novo = & $Py -c "import secrets; print(secrets.token_urlsafe(32))"
        Definir-Env "APP_TOKENS" $novo.Trim()
        Amarelo "Gerei um APP_TOKENS novo no .env. Use o MESMO valor em assistant.token no local.properties do app."
    }
    if (-not (Pid-De "app")) {
        $log = Join-Path $Run "app.log"
        $argList = @("run", "--env-file", "`"$(Join-Path $Raiz '.env')`"", "uvicorn", "prisma_agent.api:app", "--app-dir", "src",
                  "--host", "127.0.0.1", "--port", "$PortaApp")
        $p = Start-Process -FilePath "uv" -ArgumentList $argList -WorkingDirectory $dir -PassThru @Oculto `
            -RedirectStandardOutput "$log.out" -RedirectStandardError $log
        Set-Content -Path $pidf -Value $p.Id
        Write-Host "Subindo o assistente do PrismaAPP (na 1ª vez o uv instala as dependências)..."
    }
    for ($i = 0; $i -lt 90; $i++) {
        try { Invoke-RestMethod -Uri "http://127.0.0.1:$PortaApp/health" -TimeoutSec 2 | Out-Null; $ok = $true; break } catch { $ok = $false; Start-Sleep 2 }
    }
    if (-not $ok) { Vermelho "O assistente do app não respondeu. Veja .run\app.log"; return }
    Verde "Assistente do PrismaAPP no ar: http://127.0.0.1:$PortaApp"
    $adb = ""
    if ($env:LOCALAPPDATA) { $adb = Join-Path $env:LOCALAPPDATA "Android\Sdk\platform-tools\adb.exe" }
    if (-not $adb -or -not (Test-Path $adb)) { $c = Get-Command adb -ErrorAction SilentlyContinue; if ($c) { $adb = $c.Source } else { $adb = "" } }
    if ($adb) {
        & $adb reverse "tcp:$PortaApp" "tcp:$PortaApp" 2>$null
        if ($LASTEXITCODE -eq 0) { Verde "adb reverse tcp:$PortaApp feito: o celular já alcança o assistente." }
        else { Write-Host "Com o celular conectado, rode: adb reverse tcp:$PortaApp tcp:$PortaApp" }
    }
    Write-Host "No local.properties do app: assistant.token=<APP_TOKENS do .env> e assistant.url=http\://127.0.0.1\:$PortaApp/"
}

function Sql($pergunta) {
    if (-not $pergunta) { Vermelho 'Uso: .\prisma.ps1 sql "quanto gastei com mercado em outubro?"'; return }
    $codigo = @"
import sys
sys.path.insert(0, sys.argv[1])
import agente
if not agente.CONFIG.get('gemini_api_key'):
    sys.exit('Coloque a GOOGLE_API_KEY no .env.')
try:
    r = agente.responder_detalhado(sys.argv[2])
except Exception as e:
    sys.exit(f'Falhou: {e}')
print(r['resposta'])
print('\nSQL:', r['sql'])
"@
    & $Py -c $codigo $PastaSql $pergunta
}

# ------------------------------------------------------------------ comandos
switch ($Comando) {
    "iniciar"   { Iniciar }
    "parar"     { Parar }
    "reiniciar" { Parar; Iniciar }
    "status"    { Status }
    "env"       { Mostrar-Env }
    "logs" {
        $nomes = @($Agentes.Keys)
        if ($Resto.Count -gt 0) { $nomes = @($Resto[0]) }
        foreach ($n in $nomes) { Write-Host "== $n"; $l = Join-Path $Run "$n.log"; if (Test-Path $l) { Get-Content $l -Tail 20 } }
    }
    "pluggy"    { Preparar; & $Py (Join-Path $PastaSql "gerar_banco.py") }
    "indexar"   { Preparar; & $Py -m especialista indexar }
    "testes"    { Preparar; $env:INDICADORES_URL = ""; & $Py -m pytest }
    "sql"       { Preparar; Sql ($Resto -join " ") }
    "app"       { Preparar; if ($Resto.Count -gt 0) { App $Resto[0] } else { App "" } }
    { $_ -in @("especialista", "indicadores", "consultas") } {
        Preparar
        if (Saudavel "indicadores") { $env:INDICADORES_URL = "http://127.0.0.1:$($Agentes['indicadores'])" }
        & $Py -m $Comando @Resto
    }
    "orquestrador" {
        Preparar
        # Com os agentes no ar, o orquestrador fala com eles por HTTP; senão, abre cada um por stdio.
        if (Saudavel "indicadores") { $env:INDICADORES_URL = "http://127.0.0.1:$($Agentes['indicadores'])" }
        else { Remove-Item Env:INDICADORES_URL -ErrorAction SilentlyContinue }
        if (Saudavel "especialista") { $env:ESPECIALISTA_URL = "http://127.0.0.1:$($Agentes['especialista'])" }
        & $Py -m orquestrador @Resto
    }
    default { Get-Content -Path $PSCommandPath -TotalCount 22 | Select-Object -Skip 1 | ForEach-Object { $_ -replace "^\s{0,2}", "" } }
}
