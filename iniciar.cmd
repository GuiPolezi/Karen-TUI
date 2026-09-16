@echo off
rem CMD ALL-IN-ONE: abre a TUI no Windows Terminal (se existir), atualizando pelo git antes.
rem Uso: dois cliques, ou pelo atalho criado por scripts\criar_atalho.ps1.
rem   ATUALIZAR=0 no ambiente pula o git pull.
setlocal
set "ROOT=%~dp0"

rem Já estamos dentro do Windows Terminal (ou foi chamado por ele): roda direto.
if defined WT_SESSION goto :run

rem Fora dele: reabre no Windows Terminal para ter 16 milhões de cores e os ícones.
where wt.exe >nul 2>&1
if %errorlevel%==0 (
    start "" wt.exe -d "%ROOT%." powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\iniciar.ps1"
    exit /b 0
)

:run
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\iniciar.ps1"
