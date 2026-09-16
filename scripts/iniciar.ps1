# Inicia o CMD ALL-IN-ONE:
#   1. git fetch (com limite de 20 s) e git pull --ff-only, se houver commits novos no GitHub;
#   2. pip install -e . se o pyproject.toml mudou entre a versão antiga e a nova;
#   3. python -m app.
# Qualquer falha na atualização só avisa e abre a versão que já está na máquina.
# ATUALIZAR=0 no ambiente pula a etapa 1. Compatível com Windows PowerShell 5.1.

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$python = Join-Path $root ".venv\Scripts\python.exe"

function Short([string]$hash) { if ($hash -and $hash.Length -ge 7) { $hash.Substring(0, 7) } else { $hash } }

if (-not (Test-Path $python)) {
    Write-Host "Ambiente virtual não encontrado em .venv\." -ForegroundColor Red
    Write-Host "Siga a seção 'Instalação' do README (python -m venv .venv; pip install -e `".[dev]`")."
    Read-Host "Enter para fechar" | Out-Null
    exit 1
}

function Atualizar {
    if ($env:ATUALIZAR -eq "0") { return }
    if (-not (Test-Path (Join-Path $root ".git"))) { return }
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Write-Host "git não encontrado; abrindo sem verificar atualizações" -ForegroundColor DarkYellow
        return
    }
    Write-Host "verificando atualizações no GitHub..." -ForegroundColor DarkGray
    $env:GIT_TERMINAL_PROMPT = "0"   # nunca pedir senha aqui: se não tiver credencial salva, só avisa
    $job = Start-Job -ScriptBlock { param($r) Set-Location $r; git fetch --quiet 2>&1 | Out-String } -ArgumentList $root
    if (-not (Wait-Job $job -Timeout 20)) {
        Stop-Job $job; Remove-Job $job -Force
        Write-Host "sem resposta do GitHub em 20 s; abrindo a versão atual" -ForegroundColor DarkYellow
        return
    }
    $fetchOutput = (Receive-Job $job | Out-String).Trim()
    Remove-Job $job
    if ($fetchOutput) { Write-Host $fetchOutput -ForegroundColor DarkYellow }

    $local = (git rev-parse HEAD 2>$null | Out-String).Trim()
    $remote = (git rev-parse '@{u}' 2>$null | Out-String).Trim()
    if (-not $remote) {
        Write-Host "branch sem upstream no GitHub; abrindo a versão atual ($(Short $local))" -ForegroundColor DarkYellow
        return
    }
    if ($local -eq $remote) {
        Write-Host "já está na versão mais recente ($(Short $local))" -ForegroundColor DarkGray
        return
    }
    $behind = [int]((git rev-list --count 'HEAD..@{u}' 2>$null | Out-String).Trim())
    if ($behind -eq 0) {
        Write-Host "versão local à frente do GitHub; nada a atualizar" -ForegroundColor DarkGray
        return
    }
    $pyprojectBefore = (git rev-parse 'HEAD:pyproject.toml' 2>$null | Out-String).Trim()
    git pull --ff-only --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Host "não deu para atualizar sozinho (alterações locais ou conflito). Rode 'git status' na pasta." -ForegroundColor Yellow
        return
    }
    $new = (git rev-parse HEAD | Out-String).Trim()
    Write-Host "atualizado: $behind commit(s) ($(Short $local) -> $(Short $new))" -ForegroundColor Green
    $pyprojectAfter = (git rev-parse 'HEAD:pyproject.toml' 2>$null | Out-String).Trim()
    if ($pyprojectBefore -ne $pyprojectAfter) {
        Write-Host "dependências mudaram; reinstalando (pip install -e .)..." -ForegroundColor DarkGray
        & $python -m pip install -q -e "."
        if ($LASTEXITCODE -ne 0) { Write-Host "pip install falhou; o app pode reclamar de dependência" -ForegroundColor Yellow }
    }
}

Atualizar
& $python -m app
$code = $LASTEXITCODE
if ($code -ne 0) {
    Write-Host ""
    Write-Host "O app terminou com erro ($code). Veja logs\app.log." -ForegroundColor Red
    Read-Host "Enter para fechar" | Out-Null
}
exit $code
