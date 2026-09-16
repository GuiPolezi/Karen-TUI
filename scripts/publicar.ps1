# Publica uma versão nova: carimba app/__init__.py, commita, cria a tag e empurra.
# O resto é com o GitHub Actions (.github/workflows/release.yml): ele roda os testes,
# monta o instalador e anexa ao release — que é de onde o Ctrl+U da TUI baixa.
#
# Uso (na pasta do projeto, com a árvore limpa):
#   powershell -ExecutionPolicy Bypass -File scripts\publicar.ps1 -Versao 0.2.0
#   powershell -ExecutionPolicy Bypass -File scripts\publicar.ps1 -Versao 0.2.0 -Simular

param(
    [Parameter(Mandatory = $true)][string]$Versao,
    [switch]$Simular
)

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

if ($Versao -notmatch '^\d+\.\d+\.\d+$') { throw "versao invalida: use X.Y.Z (recebido '$Versao')" }

$sujo = git status --porcelain
if ($sujo) { throw "há alterações não commitadas; commite ou guarde antes de publicar" }

$branch = (git rev-parse --abbrev-ref HEAD).Trim()
if ($branch -ne "main") { Write-Host "atenção: publicando a partir de '$branch'" -ForegroundColor Yellow }

$tag = "v$Versao"
if ((git tag --list $tag)) { throw "a tag $tag ja existe" }

$init = Join-Path $raiz "app\__init__.py"
$conteudo = Get-Content $init -Raw
$atual = [regex]::Match($conteudo, '__version__ = "([^"]+)"').Groups[1].Value
if (-not $atual) { throw "nao achei __version__ em $init" }
Write-Host "$atual -> $Versao" -ForegroundColor Cyan

if ($Simular) {
    Write-Host "(simulação) editaria app/__init__.py, commitaria, criaria a tag $tag e empurraria" -ForegroundColor Yellow
    exit 0
}

$novo = $conteudo -replace '__version__ = "[^"]+"', "__version__ = `"$Versao`""
[System.IO.File]::WriteAllText($init, $novo, (New-Object System.Text.UTF8Encoding($false)))

git add app/__init__.py
git commit -m "chore: versao $Versao"
if ($LASTEXITCODE -ne 0) { throw "git commit falhou" }
git tag -a $tag -m "CMD ALL-IN-ONE $Versao"
if ($LASTEXITCODE -ne 0) { throw "git tag falhou" }
git push origin HEAD
if ($LASTEXITCODE -ne 0) { throw "git push falhou" }
git push origin $tag
if ($LASTEXITCODE -ne 0) { throw "git push da tag falhou" }

Write-Host ""
Write-Host "tag $tag empurrada." -ForegroundColor Green
Write-Host "acompanhe o build em: https://github.com/GuiPolezi/Karen-TUI/actions"
Write-Host "quando terminar, o instalador aparece em: https://github.com/GuiPolezi/Karen-TUI/releases/tag/$tag"
