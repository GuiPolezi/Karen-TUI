# CMD ALL-IN-ONE

Dashboard de terminal (TUI) para o técnico de suporte da Sino Informática. Em uma única
tela, atualizada sozinha, mostra:

| Painel | O que mostra | Fonte |
|---|---|---|
| **E-MAIL** | total, não lidos, spam e o e-mail mais recente | IMAP |
| **MILLDESK** | chamados no nome do técnico | API REST Milldesk |
| **CHATPANEL** | conversas do WhatsApp em atendimento pelo técnico | scraping do painel web |

A especificação completa está em `PROMPT_CMD_ALL_IN_ONE.md`.

## Status das fases

- [x] Fase 0 — bootstrap (config, skeleton da TUI, testes)
- [x] Fase 1 — E-mail (IMAP)
- [ ] Fase 2 — Milldesk
- [ ] Fase 3 — validação do Milldesk (`amount` = abertos ou histórico?)
- [ ] Fase 4 — ChatPanel (Playwright)
- [ ] Fase 5 — polimento

## Requisitos

- Windows 10/11 com Windows Terminal (funciona também no CMD/PowerShell comum)
- Python 3.11 ou superior
- Git

## Instalação (Windows)

```powershell
# 1. clonar/abrir a pasta do projeto e criar o ambiente virtual
python -m venv .venv
.venv\Scripts\Activate.ps1

# 2. instalar o projeto e as dependências de desenvolvimento
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

# 3. (necessário só a partir da Fase 4) baixar o Chromium do Playwright
playwright install chromium
```

Se preferir o `uv`: `uv sync` faz os passos 1 e 2.

## Configuração

```powershell
Copy-Item .env.example .env
notepad .env
```

Preencha pelo menos:

- `TECH_NAME` exatamente como aparece no ChatPanel e no Milldesk
- `EMAIL_APP_PASSWORD` (se tiver `#` ou `*`, deixe entre aspas simples)
- `MILLDESK_API_KEY`

Regras de validação:

- Variável **ausente** do `.env` aborta o app com a lista do que falta.
- Segredo **vazio** (`EMAIL_APP_PASSWORD`, `MILLDESK_API_KEY`) não aborta: o painel
  correspondente mostra "não configurado" e os outros continuam funcionando.
- Intervalos de atualização precisam ser de pelo menos 5 segundos.

## Como rodar

```powershell
.venv\Scripts\Activate.ps1
python -m app
```

Atalhos: `q` sair · `r` atualizar tudo · `1`/`2`/`3` atualizar um painel · `e` abrir o
e-mail mais recente · `l` painel de log · `Esc` voltar.

Em terminais com menos de 100 colunas, os painéis de E-mail e Milldesk empilham
verticalmente.

## E-mail (IMAP)

- A pasta é aberta em modo **somente leitura**: nada é marcado como lido.
- Porta 143 com `EMAIL_IMAP_STARTTLS=true` usa STARTTLS. Se o servidor recusar, o app
  cai para SSL direto na porta 993 e registra um aviso em `logs/app.log`. Porta 143 com
  STARTTLS desligado é recusada: a senha nunca sai em texto puro.
- Validado em 14/09/2026 contra `imap.sinoinformatica.com.br`: STARTTLS na 143 aceito,
  pasta `Junk E-Mail` lida, datas convertidas para o fuso local.
- A conexão fica aberta entre ciclos e reconecta sozinha se cair.
- A caixa `suporte@` é compartilhada, então "não lidos" reflete a equipe toda, não só o
  técnico (a confirmar com o usuário).

## Modo debug por fonte

Cada fonte tem um modo standalone que imprime o estado em JSON e sai (a partir da fase
em que é implementada):

```powershell
python -m app.sources.email_imap
python -m app.sources.milldesk
python -m app.sources.chatpanel
```

## Testes

```powershell
python -m pytest
```

## Logs

`logs/app.log`, com rotação (1 MB, 3 arquivos). A chave do Milldesk aparece mascarada
(`****1776`). Nada é impresso no terminal enquanto a TUI está aberta.

## Troubleshooting

Esta seção será completada na Fase 5 (sessão expirada do ChatPanel, IMAP sem TLS,
técnico não encontrado).
