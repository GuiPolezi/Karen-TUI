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
- [x] Fase 2 — Milldesk
- [x] Fase 3 — validação do Milldesk (`amount` é histórico; painel usa `showTicketsByStatus`)
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
- `MILLDESK_AGENT_NAME` se o seu nome no Milldesk for diferente do `TECH_NAME`

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
- A caixa `suporte@` é compartilhada (confirmado em 14/09/2026), então "não lidos"
  reflete a equipe toda, não só o técnico. Comportamento aceito.

## Milldesk

**Validação da Fase 3 (14/09/2026, chamada real à API):**

- `ticketsByAgent.amount` é o **histórico** de chamados do técnico, não os abertos.
  Exemplo real: o técnico tinha 168 no `amount` e apenas 3 chamados abertos.
- Para contar os abertos, o app usa `ticketsByStatus` (agregado leve) para descobrir
  quais status têm chamados e chama `showTicketsByStatus?status=...` só para esses,
  filtrando pelo campo `agent`. `Fechado` nunca é consultado (a rota devolve vazio para
  ele mesmo assim). São cerca de 10 GETs por ciclo, 0,2 s cada, no máximo 3 em paralelo.
- O painel mostra **"Abertos no meu nome"** como destaque, a quebra por status, até 3
  chamados (mais recentes primeiro) e o histórico de `ticketsByAgent` como linha secundária.
- Peculiaridades da API vistas em produção: `starttime` às vezes vem com a data junto
  (`14/09/2026 13:09`), `slasexpirationdate` pode ser texto (`Em pausa`), e erros vêm com
  HTTP 200 e corpo `{"error": "invalidApiKey"}` ou `{"error": "invalidStatus"}`.
- O nome no Milldesk pode ser diferente do nome no ChatPanel. Use `MILLDESK_AGENT_NAME`
  no `.env` (ex.: `Guilherme P.`); vazio significa usar `TECH_NAME`. Cuidado com
  homônimos: a comparação é exata (ignorando acentos e maiúsculas), então
  `Guilherme P.` não casa com `Guilherme Anderson dos Santos`.
- Só rotas de leitura são usadas. `addTicket`, `updateTicketStatus` e
  `sendCommunication` nunca são chamadas.

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
