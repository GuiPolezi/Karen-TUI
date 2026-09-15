# CMD ALL-IN-ONE

Dashboard de terminal (TUI) para técnico de suporte. Em uma única tela, atualizada
sozinha, mostra:

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
- [x] Fase 4 — ChatPanel (Playwright, Estratégia A, login humano integrado à TUI)
- [x] Fase 5 — polimento (destaque + bell, painel de log, detalhe do e-mail, coleta
  incremental do Milldesk por causa do limite de requisições)

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

# 3. baixar o Chromium do Playwright (~150 MB, uma vez)
playwright install chromium
```

## Configuração

```powershell
Copy-Item .env.example .env
notepad .env
```

Preencha pelo menos:

- `TECH_NAME` exatamente como aparece no ChatPanel e no Milldesk
- `EMAIL_IMAP_HOST`, `EMAIL_USER` e `EMAIL_APP_PASSWORD` (se a senha tiver `#` ou `*`,
  deixe entre aspas simples)
- `MILLDESK_API_KEY`
- `MILLDESK_AGENT_NAME` se o seu nome no Milldesk for diferente do `TECH_NAME`
- `CHATPANEL_URL` (endereço do `chat.php` do seu painel)

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
e-mail mais recente em tela cheia · `c` abrir a janela de login do ChatPanel · `l`
mostrar/esconder as últimas 50 linhas do log · `Esc` voltar.

Quando um contador aumenta entre dois ciclos (não lidos, chamados abertos, conversas ou
não lidas do ChatPanel), o painel ganha borda grossa amarela por 3 segundos e o terminal
toca o bell. `NOTIFY_BELL=false` no `.env` desliga o som, mantendo o destaque.

Em terminais com menos de 100 colunas, os painéis de E-mail e Milldesk empilham
verticalmente.

## E-mail (IMAP)

- A pasta é aberta em modo **somente leitura**: nada é marcado como lido.
- Porta 143 com `EMAIL_IMAP_STARTTLS=true` usa STARTTLS. Se o servidor recusar, o app
  cai para SSL direto na porta 993 e registra um aviso em `logs/app.log`. Porta 143 com
  STARTTLS desligado é recusada: a senha nunca sai em texto puro.
- `EMAIL_SPAM_FOLDER` é opcional; se a pasta não existir, o contador de spam some.
- Datas são convertidas para o fuso local.
- A conexão fica aberta entre ciclos e reconecta sozinha se cair.
- Se a caixa for compartilhada pela equipe, "não lidos" reflete a equipe toda, não só o
  técnico.

## Milldesk

- `ticketsByAgent.amount` é o **histórico** de chamados do técnico, não os abertos.
- Para contar os abertos, o app usa `ticketsByStatus` (agregado leve) para descobrir
  quais status têm chamados e chama `showTicketsByStatus?status=...` só para esses,
  filtrando pelo campo `agent`. `Fechado` nunca é consultado.
- O painel mostra **"Abertos no meu nome"** como destaque, a quebra por status, até 3
  chamados (mais recentes primeiro) e o histórico de `ticketsByAgent` como linha secundária.
- Peculiaridades da API: `starttime` às vezes vem com a data junto, `slasexpirationdate`
  pode ser texto (`Em pausa`), e erros vêm com HTTP 200 e corpo
  `{"error": "invalidApiKey"}` ou `{"error": "invalidStatus"}`.
- O nome no Milldesk pode ser diferente do nome no ChatPanel. Use `MILLDESK_AGENT_NAME`
  no `.env`; vazio significa usar `TECH_NAME`. Cuidado com homônimos: a comparação é
  exata (ignorando acentos e maiúsculas), então um nome abreviado não casa com o nome
  completo de outra pessoa.
- Só rotas de leitura são usadas. `addTicket`, `updateTicketStatus` e
  `sendCommunication` nunca são chamadas.

**Limite de requisições:** a API responde `HTTP 429` com cerca de dez chamadas por
minuto. Por isso a coleta é incremental:

- todo ciclo faz só uma chamada, `ticketsByStatus`, e compara as quantidades por status
  com o ciclo anterior;
- `showTicketsByStatus` só é chamada para os status cuja quantidade mudou;
- `ticketsByAgent` e uma recarga completa acontecem a cada 10 minutos;
- as chamadas são sequenciais, com 0,4 s entre elas;
- um `429` não é retentado: o painel mostra o erro e espera 3 minutos, mantendo os
  últimos dados na tela.

## ChatPanel (WhatsApp)

O ChatPanel não tem API. O app usa um Chromium headless (Playwright) com perfil
persistente que fica com o painel aberto e, a cada `CHATPANEL_REFRESH_SECONDS`, lê o
HTML e extrai as conversas com BeautifulSoup. A página não é recarregada a cada ciclo: o
socket.io do painel já atualiza o DOM.

### Login (sempre humano: a tela tem captcha)

A tela de login do ChatPanel pede usuário, senha e um captcha aritmético. Por isso o
login nunca é totalmente automático: o app abre a janela e pré-preenche o que pode, e a
pessoa responde o captcha e clica em "Acessar Painel".

Dentro da TUI:

- Ao iniciar, se o app detecta sessão expirada (ou ainda não há perfil salvo), ele abre
  sozinho um Chromium visível **uma vez por execução** (`CHATPANEL_LOGIN_ON_START=true`).
  Faça o login; a janela fecha sozinha e o painel volta a ler o ChatPanel.
- A tecla `c` abre a janela a qualquer momento (sessão caiu de novo, login cancelado...).
- `CHATPANEL_USER` e `CHATPANEL_PASSWORD` no `.env` (opcionais) deixam usuário e senha
  já preenchidos; sobra só o captcha. A senha é mascarada nos logs como as outras.
- A janela espera 5 minutos; se fechar antes ou o tempo acabar, o painel mostra o motivo
  e `c` tenta de novo.

Fora da TUI, `python scripts\chatpanel_login.py` faz o mesmo (sem limite de tempo).
Feche o app antes: o Chromium não abre o mesmo perfil em dois processos. A sessão fica
salva em `CHATPANEL_PROFILE_DIR` (`.chatpanel-profile/`, ignorado pelo git).

**Limitação conhecida:** o ChatPanel aceita **uma sessão por usuário**. Cada login feito
pelo app derruba a sessão do seu navegador, e cada login no navegador derruba a do app.
Quando a sessão cair, pressione `c` e refaça o login. Alternativas (usuário dedicado ao
dashboard, userscript + servidor local) foram avaliadas e descartadas: o fluxo fica
assim, sem depender de servidor local nem de extensão no navegador.

### O que o painel mostra

- Conversas em `#box-atende-chats` ("SUAS CONVERSAS") contam como suas sempre; as de
  `#box-atendeothers-chats` ("EM ATENDIMENTO") contam quando o badge de pessoa é igual a
  `TECH_NAME`. Números repetidos são deduplicados.
- Por conversa: online, hora, contato, tag, departamento, última mensagem, não lidas.
- Rodapé: quantas estão com outros técnicos e o total de não lidas da aba Atende.
- Sem sessão válida o painel fica vermelho com "sessão expirada — pressione c para fazer
  login". O app tenta um reload antes de declarar isso e, na primeira vez por execução,
  abre a janela de login sozinho.

### Modo offline do parser

```powershell
python -m app.sources.chatpanel tests\fixtures\chatpanel_chat.html
```

## Modo debug por fonte

Cada fonte tem um modo standalone que imprime o estado em JSON e sai:

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

`logs/app.log`, com rotação (1 MB, 3 arquivos). Chave do Milldesk e senhas aparecem
mascaradas (`****1776`, `********`). Nada é impresso no terminal enquanto a TUI está
aberta.

## Troubleshooting

**"sessão expirada — pressione c para fazer login"** no painel do ChatPanel
: A sessão salva no perfil headless não vale mais. Causa mais comum: alguém fez login com o
  mesmo usuário em outro navegador (o ChatPanel aceita uma sessão por usuário). Pressione
  `c`, faça o login na janela que abre (responda o captcha) e o painel volta sozinho. Sem
  login, o app tenta de novo a cada 2 minutos.

**"janela de login fechada antes de completar o login"** ou **"tempo esgotado (300s)..."**
: A janela do Chromium foi fechada ou ficou 5 minutos sem login. Pressione `c` de novo.

**A janela de login abre toda vez que inicio o app**
: A sessão está sendo derrubada pelo seu login no navegador (uma sessão por usuário).
  Se preferir, desligue a abertura automática com `CHATPANEL_LOGIN_ON_START=false` e use
  `c` quando quiser.

**"limite de requisições da API (HTTP 429 ...)"** no painel do Milldesk
: A API do Milldesk recusou por excesso de chamadas. O painel mantém os últimos dados e
  espera 3 minutos. Se acontecer com frequência, aumente `MILLDESK_REFRESH_SECONDS` ou
  verifique se outro programa usa a mesma chave.

**"técnico não encontrado na resposta"** no painel do Milldesk
: `MILLDESK_AGENT_NAME` (ou `TECH_NAME`, se aquele estiver vazio) não bate com nenhum
  `agent` da API e você não tem chamado aberto. Rode `python -m app.sources.milldesk` e
  confira a grafia exata do seu nome no Milldesk.

**"porta 143 sem STARTTLS enviaria a senha em texto puro"** no painel de e-mail
: `EMAIL_IMAP_STARTTLS=false` com `EMAIL_IMAP_PORT=143`. Use `true`, ou porta `993`.

**"STARTTLS ... falhou; tentando SSL direto na porta 993"** em `logs/app.log`
: Aviso, não erro: o servidor recusou STARTTLS e o app caiu para SSL. Se preferir, deixe
  `EMAIL_IMAP_PORT=993` e `EMAIL_IMAP_STARTTLS=false` para evitar a tentativa.

**"LOGIN failed" ou "AUTHENTICATIONFAILED"** no painel de e-mail
: Senha errada em `EMAIL_APP_PASSWORD`. Se a senha tem `#` ou `*`, deixe entre aspas
  simples no `.env`.

**Acentos quebrados no terminal**
: Use o Windows Terminal. No CMD antigo, rode `chcp 65001` antes de `python -m app`.

**Painéis empilhados**
: O terminal tem menos de 100 colunas. Alargue a janela; o layout volta sozinho.

**A TUI abriu, mas o Chromium não**
: Rode `playwright install chromium` dentro do venv. O download é de ~150 MB.

**Quero ver o que está acontecendo**
: Tecla `l` mostra as últimas 50 linhas de `logs/app.log` dentro da TUI. `LOG_LEVEL=DEBUG`
  no `.env` registra também cada ciclo de coleta.
