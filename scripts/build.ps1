# Monta o executável e o instalador do CMD ALL-IN-ONE.
#
# Uso (na pasta do projeto, com o venv já criado):
#   powershell -ExecutionPolicy Bypass -File scripts\build.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\build.ps1 -PularTestes
#
# Saída:
#   dist\CMD-ALL-IN-ONE\CMD-ALL-IN-ONE.exe          (pasta do programa)
#   dist\CMD-ALL-IN-ONE-Setup-<versao>.exe          (instalador, se o Inno Setup existir)
#
# O Chromium do Playwright NÃO entra no pacote (700 MB): quem baixa é a primeira
# execução do programa (app\firstrun.py).

param(
    [switch]$PularTestes,
    [switch]$PularInstalador
)

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

$python = Join-Path $raiz ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "venv não encontrado em $python (crie com: python -m venv .venv)" }

$versao = (& $python -c "import app; print(app.__version__)").Trim()
Write-Host "CMD ALL-IN-ONE $versao" -ForegroundColor Cyan

# 1. dependências de build
& $python -m pip install --quiet --upgrade pyinstaller
if ($LASTEXITCODE -ne 0) { throw "pip install pyinstaller falhou" }

# 2. testes (a falha aqui para o build de propósito)
if (-not $PularTestes) {
    Write-Host "rodando os testes…" -ForegroundColor Cyan
    & $python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "testes falharam: build interrompido" }
}

# 3. ícone
& $python scripts\gerar_icone.py
if ($LASTEXITCODE -ne 0) { throw "geração do ícone falhou" }

# 4. executável
Write-Host "empacotando com o PyInstaller…" -ForegroundColor Cyan
if (Test-Path "dist\CMD-ALL-IN-ONE") { Remove-Item -Recurse -Force "dist\CMD-ALL-IN-ONE" }
& $python -m PyInstaller packaging\cmd-all-in-one.spec --noconfirm --distpath dist --workpath build\pyinstaller --log-level WARN
if ($LASTEXITCODE -ne 0) { throw "PyInstaller falhou" }

$exe = "dist\CMD-ALL-IN-ONE\CMD-ALL-IN-ONE.exe"
if (-not (Test-Path $exe)) { throw "executável não gerado em $exe" }

# 5. fumaça: o executável sobe, acha os caminhos e enxerga as dependências?
$dadosTeste = Join-Path $env:TEMP "cmd-all-in-one-build-check"
if (Test-Path $dadosTeste) { Remove-Item -Recurse -Force $dadosTeste }
$env:CMD_DATA_DIR = $dadosTeste
$env:PLAYWRIGHT_SKIP_INSTALL = "1"
$saida = (& $exe --verificar) -join "`n"
Remove-Item Env:\CMD_DATA_DIR; Remove-Item Env:\PLAYWRIGHT_SKIP_INSTALL
if ($LASTEXITCODE -ne 0) { throw "o executavel nao passou no --verificar" }
# sem acento na comparacao: o console devolve a saida na codepage do Windows
if ($saida -notmatch '"modo": "execut') { throw "o --verificar nao reconheceu o modo executavel" }
if ($saida -notmatch '"css_existe": true') { throw "o styles.tcss nao foi empacotado: a TUI nao subiria" }
if ($saida -match '"AUSENTE"') { throw "faltou alguma dependencia no pacote (veja o --verificar)" }

# o erro classico do executavel: o Playwright procura o navegador dentro do pacote
# (.local-browsers) em vez de %LOCALAPPDATA%\ms-playwright. So da para checar se esta
# maquina ja tem os navegadores baixados; no CI nao tem, entao a checagem e pulada.
$env:CMD_DATA_DIR = $dadosTeste
$navegador = (& $exe --verificar --navegador) -join "`n"
Remove-Item Env:\CMD_DATA_DIR
if ($navegador -match '"baixados": \[\s*\]') {
    Write-Host "sem navegador do Playwright nesta maquina: pulei o teste de abertura" -ForegroundColor Yellow
}
elseif ($navegador -notmatch '"ok": true') {
    Write-Host $navegador
    throw "o executavel nao conseguiu abrir o Chromium (veja o erro acima)"
}
else { Write-Host "navegador abre pelo executavel" -ForegroundColor Green }
Write-Host "executável ok" -ForegroundColor Green

# 6. instalador (Inno Setup)
if (-not $PularInstalador) {
    $iscc = (Get-Command iscc.exe -ErrorAction SilentlyContinue).Source
    if (-not $iscc) {
        foreach ($p in @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe")) {
            if (Test-Path $p) { $iscc = $p; break }
        }
    }
    if ($iscc) {
        Write-Host "montando o instalador…" -ForegroundColor Cyan
        & $iscc "/DAppVersion=$versao" "packaging\instalador.iss"
        if ($LASTEXITCODE -ne 0) { throw "Inno Setup falhou" }
    }
    else {
        Write-Host "Inno Setup 6 não encontrado: só a pasta dist\CMD-ALL-IN-ONE foi gerada." -ForegroundColor Yellow
        Write-Host "Instale com: winget install JRSoftware.InnoSetup" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "pronto:" -ForegroundColor Green
Get-ChildItem dist -Filter "CMD-ALL-IN-ONE*" | ForEach-Object {
    $tamanho = if ($_.PSIsContainer) {
        (Get-ChildItem $_.FullName -Recurse -File | Measure-Object -Property Length -Sum).Sum
    } else { $_.Length }
    "{0,-40} {1,8:N0} MB" -f $_.Name, ($tamanho / 1MB)
}
