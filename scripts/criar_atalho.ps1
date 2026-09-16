# Cria o atalho "CMD ALL-IN-ONE" na área de trabalho (ou na pasta passada em -Destino).
# O atalho abre o Windows Terminal já dentro da pasta do projeto rodando scripts\iniciar.ps1;
# sem Windows Terminal, aponta para iniciar.cmd.
#
# Uso (na pasta do projeto):
#   powershell -ExecutionPolicy Bypass -File scripts\criar_atalho.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\criar_atalho.ps1 -Perfil "Windows PowerShell"
#   -Perfil escolhe o perfil do Windows Terminal (o que tem o esquema de cores e a fonte).

param(
    [string]$Destino = [Environment]::GetFolderPath("Desktop"),
    [string]$Perfil = "",
    [string]$Nome = "CMD ALL-IN-ONE"
)

$root = Split-Path -Parent $PSScriptRoot
$lnk = Join-Path $Destino "$Nome.lnk"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($lnk)
$wt = Get-Command wt.exe -ErrorAction SilentlyContinue

if ($wt) {
    $profileArg = ""
    if ($Perfil) { $profileArg = "-p `"$Perfil`" " }
    $shortcut.TargetPath = $wt.Source
    $shortcut.Arguments = "$profileArg-d `"$root`" powershell -NoProfile -ExecutionPolicy Bypass -File `"$root\scripts\iniciar.ps1`""
} else {
    $shortcut.TargetPath = Join-Path $root "iniciar.cmd"
}
$shortcut.WorkingDirectory = $root
$shortcut.Description = "Dashboard de suporte: E-mail + Milldesk + ChatPanel (atualiza pelo git ao abrir)"
$shortcut.IconLocation = "$env:SystemRoot\System32\imageres.dll,109"
$shortcut.Save()

Write-Host "atalho criado: $lnk"
if ($wt) {
    $perfilTexto = if ($Perfil) { "perfil '$Perfil'" } else { "perfil padrão" }
    Write-Host "abre no Windows Terminal ($perfilTexto)"
}
else { Write-Host "Windows Terminal não encontrado: o atalho usa iniciar.cmd (conhost, 16 cores)" -ForegroundColor Yellow }
