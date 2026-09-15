# CMD ALL-IN-ONE — Ciclo 2: navegação, interatividade e detalhes

> **Como usar:** cole este arquivo inteiro como primeiro prompt de uma nova sessão do
> Claude Code, na raiz do projeto, e diga: *"Leia `CLAUDE.md`, `PROMPT_CMD_ALL_IN_ONE.md`
> e este arquivo. Execute a Fase 6.0 (reconhecimento) e pare para eu aprovar o plano."*
>
> Este documento **complementa** `PROMPT_CMD_ALL_IN_ONE.md` (Fases 0–5, já concluídas).
> Todas as regras de `CLAUDE.md` continuam valendo; as regras da seção 2 abaixo se somam a elas.

---

## 1. Objetivo deste ciclo

Hoje a TUI é um **painel de leitura passiva**: mostra contadores e a última linha de cada
fonte, e o técnico precisa sair do terminal (minimizar, abrir navegador, abrir o Milldesk)
para agir sobre qualquer coisa. O objetivo do ciclo 2 é transformar o app em um
**cockpit de trabalho** em que o técnico fica o dia inteiro sem sair do terminal:

1. **Telas** — navegar entre visões (dashboard, e-mail, Milldesk, ChatPanel, log, notas)
   dentro do próprio terminal, com atalhos de uma tecla e sem perder o estado.
2. **Teclado** — mover-se com as setas dentro das listas, selecionar um item e abrir
   seu detalhe com `Enter`, voltar com `Esc`.
3. **Detalhes** — "ler ticket" no Milldesk e "ler conversa" no ChatPanel, no mesmo
   espírito do "ler e-mail" (`e`) que já existe.
4. **Launcher** — uma linha de comando dentro da TUI para pesquisar na web (abre o
   navegador com o resultado) e abrir atalhos (ticket por ID, contato do WhatsApp,
   URLs favoritas) sem digitar no navegador.
5. **Melhorias oportunistas** listadas na seção 9, a serem priorizadas junto com o usuário.

Design visual (cores, tema, tipografia dos painéis) **fica para o ciclo 3** — neste ciclo,
mantenha o estilo atual e concentre-se em estrutura, navegação e dados.

---

## 2. Regras adicionais deste ciclo

1. **Somente leitura continua absoluto.** Nenhuma feature nova pode escrever no Milldesk,
   marcar e-mail como lido ou alterar estado no ChatPanel. Se uma feature só for possível
   com escrita (ex.: abrir a conversa no painel marca como lida no servidor), **pare,
   documente a evidência e pergunte** — não implemente "por padrão".
2. **Rate limit do Milldesk é sagrado** (~10 req/min, `429` não é retentado). Todo
   detalhe sob demanda deve: ser 1 chamada; ter cache por ID (TTL configurável, padrão
   5 min); respeitar o mesmo espaçamento de 0,4 s e o cooldown de 3 min após `429`;
   nunca disparar em loop (ex.: ao navegar com as setas — só ao pressionar `Enter`).
3. **Nada de bloqueio na UI.** Todo detalhe é buscado em worker (`@work(exclusive=True)`
   por painel, para que um `Enter` repetido cancele o anterior). A tela de detalhe abre
   imediatamente com "carregando…" e preenche depois.
4. **Reconhecimento antes de código.** A Fase 6.0 é obrigatória e termina com um plano
   para aprovação. Não altere `app/tui/app.py` antes disso.
5. **Verificar a API do Textual instalado.** Não assuma nomes de classes de memória:
   rode `python -c "import textual; print(textual.__version__)"` e consulte a doc da
   versão instalada (`https://textual.textualize.io/`) antes de usar `Screen`, `MODES`,
   `ListView`, `DataTable`, `Command Palette` etc. Se a versão for antiga e faltar algo
   essencial, proponha o upgrade (com changelog) e pergunte.
6. **Cada tela e cada detalhe precisa ser testável offline.** Detalhes devem aceitar
   um dicionário/fixture e renderizar sem rede (`tests/fixtures/milldesk_showTicket.json`,
   `tests/fixtures/chatpanel_conversation.html`).
7. **Preferências do usuário** (última tela aberta, filtros, favoritos do launcher) vão
   em um arquivo JSON fora do `.env` (`prefs.json` na raiz, gitignored), lido e escrito
   por `app/prefs.py`. Nunca segredo nesse arquivo.
8. **Sem novas dependências que exijam compilação.** Se precisar de algo além do que já
   existe, prefira stdlib (`webbrowser`, `urllib.parse`, `json`) ou pacotes puros
   (`pyperclip`, `winotify`) e pergunte antes de adicionar.

---

## 3. Fase 6.0 — Reconhecimento e plano (obrigatória, sem código de feature)

Antes de qualquer implementação:

1. Leia `app/tui/app.py`, `app/tui/widgets/*.py`, `app/state.py`, `app/sources/*.py`,
   `app/tui/styles.tcss` e os testes.
2. Produza um **relatório curto** (`docs/RECON_CICLO2.md`, committado) com:
   - versão do Textual e quais APIs de navegação estão disponíveis (`Screen`,
     `ModalScreen`, `App.MODES`/`switch_mode`, `push_screen`/`pop_screen`,
     `TabbedContent`, `ListView`, `DataTable`, `OptionList`, `Command Palette`, `Input`,
     `Markdown`, `notify`);
   - como os painéis recebem estado hoje (`SOURCE_PANELS`, `set_body`) e o que precisa
     mudar para que **listas** (não só texto) sejam renderizadas e mantenham o cursor
     entre atualizações (o item selecionado não pode "pular" quando o worker publica
     novo estado);
   - quais widgets já são focáveis; como o foco e os bindings globais (`q`, `r`,
     `1/2/3`, `e`, `c`, `l`) vão conviver com bindings locais das listas;
   - o que `showTicket` retorna de fato (rodar 1 chamada real com um ID que o usuário
     fornecer e salvar a resposta **anonimizada** como fixture);
   - como o ChatPanel carrega as mensagens de uma conversa (ver seção 7.2) — apenas
     investigação, sem clicar em nada ainda;
   - riscos identificados e perguntas para o usuário (seção 11).
3. Apresente o **plano de fases** (6.1 → 6.5 abaixo, ajustado ao que encontrou) com
   estimativa de arquivos tocados e **pare para aprovação**.

---

## 4. Feature A — Navegação por telas (Fase 6.1)

### 4.1 Modelo

Adotar a arquitetura de **modos** do Textual (`App.MODES` + `switch_mode`), um `Screen`
por tela, e `push_screen`/`ModalScreen` para detalhes e diálogos. Os workers de coleta
continuam vivendo no `App` (não nas telas): trocar de tela **nunca** pausa a coleta, e
toda tela lê o mesmo estado publicado.

| Tecla | Tela | Conteúdo |
|---|---|---|
| `F1` ou `d` | **Dashboard** | O layout atual (3 painéis + rodapé). É a tela inicial. |
| `F2` | **E-mail** | Lista dos últimos N e-mails (não só o mais recente), com cursor; `Enter` abre o e-mail (reaproveita a tela de `e`). |
| `F3` | **Milldesk** | Lista dos chamados abertos no meu nome (todos, não só 3), ordenável por data/SLA/status; `Enter` abre o ticket (seção 6). |
| `F4` | **ChatPanel** | Lista completa das minhas conversas + seção "com outros técnicos" recolhível; `Enter` abre a conversa (seção 7). |
| `F5` | **Log** | O painel de log atual, agora como tela com rolagem e filtro por nível. |
| `F6` | **Notas** | Bloco de notas persistente (seção 9, item P1-3) — opcional nesta fase. |
| `Esc` | — | Fecha detalhe/diálogo; se já estiver na raiz de uma tela, volta ao Dashboard. |
| `Tab` / `Shift+Tab` | — | Circula o foco entre painéis/listas da tela atual. |

Regras:

- O `Header` mostra o nome da tela ativa e o relógio; o `Footer` mostra os bindings da
  tela (use `Binding(..., show=True)` com descrições curtas em português).
- A última tela aberta é lembrada em `prefs.json` e restaurada no próximo start.
- Bindings globais (`q`, `r`, `c`, `l`, `1/2/3`, `F1–F6`, `:`) funcionam em qualquer tela.
  `e` continua abrindo o e-mail mais recente de qualquer lugar.
- As telas cheias de E-mail/Milldesk/ChatPanel **reutilizam** o mesmo estado e as
  mesmas fontes; se precisarem de mais dados (ex.: últimos 20 e-mails em vez de 1),
  estenda a fonte com um parâmetro (`EMAIL_LIST_SIZE=20`) sem aumentar a frequência de
  coleta.
- Mouse: como o Textual já suporta cliques no Windows Terminal, permita clique para
  focar/selecionar item, mas **toda** ação precisa ter equivalente por teclado.

### 4.2 Critérios de aceite

- Trocar de tela em < 100 ms, sem re-executar coleta.
- Voltar ao Dashboard preserva o destaque/bell de mudanças que aconteceram enquanto o
  usuário estava em outra tela (contadores que subiram devem estar destacados ao voltar,
  ou aparecer um resumo "enquanto você estava fora: +2 não lidos, +1 chamado").
- Terminal estreito (< 100 colunas): telas cheias continuam usáveis (listas em 1 coluna).

---

## 5. Feature B — Interatividade por teclado (Fase 6.1, junto com A)

Substituir, nos painéis que mostram itens (Milldesk: chamados; ChatPanel: conversas;
E-mail: lista), o texto estático por um widget de lista com cursor (`ListView` ou
`DataTable` com `cursor_type="row"` — escolher no reconhecimento e justificar; `DataTable`
tende a ser melhor para colunas alinhadas e ordenação).

Comportamento:

- `↑`/`↓` movem o cursor; `j`/`k` como alternativa; `Home`/`End`; `PgUp`/`PgDn`.
- `Enter` abre o detalhe do item; `Esc` volta.
- `o` abre o item **no navegador** (ticket no Milldesk web, conversa no ChatPanel web,
  e-mail no webmail) — as URLs-padrão vêm do `.env` (seção 11).
- `y` copia o identificador principal (ID do ticket, número do WhatsApp, endereço do
  remetente) para a área de transferência (`pyperclip`; se indisponível, mostrar em
  `notify()` para cópia manual).
- `/` abre um filtro incremental na lista (por nome, assunto, número, status); `Esc`
  limpa.
- Ao chegar novo estado do worker: **manter a seleção** pelo identificador (ID/número/
  UID), não pelo índice. Se o item selecionado sumiu, ir para o vizinho mais próximo.
- Item com mudança recente (novo ou contador subiu) recebe marcador `●` por 3 s,
  coerente com o destaque de borda que já existe.
- Sempre há um indicador de foco visível (borda ou título do painel destacado), para o
  usuário saber em qual painel as setas vão agir. No Dashboard, `Tab` circula
  E-mail → Milldesk → ChatPanel.

Critério de aceite: com a TUI aberta, é possível navegar até qualquer conversa/chamado e
abrir seu detalhe **sem tirar as mãos do teclado**, e o cursor não se perde quando o
painel atualiza no meio da navegação.

---

## 6. Feature C — Detalhe do ticket Milldesk ("ler ticket") (Fase 6.2)

### 6.1 Dados

Rota: `GET /api/:api_key/showTicket?id=:id` (única rota nova; erros `invalidApiKey`,
`invalidId` chegam com HTTP 200). Campos esperados: `id, ticket, requester, agent,
status, stage, priority, urgency, start, starttime, end, endtime, slaexpirationdate,
description, resolution`. **Confirmar na fixture real** o nome exato dos campos e se
`description` vem em HTML (se vier, converter para texto com BeautifulSoup, preservando
quebras de parágrafo).

Não existe, na doc conhecida, rota de **comunicações/histórico** do ticket. Regra 6 do
`CLAUDE.md`: **não inventar**. Procure na apiDoc (`https://v1.milldesk.com/api`) se há
algo como "Listar comunicações"; se houver, registre a rota e pergunte antes de usar; se
não houver, o detalhe mostra o que `showTicket` traz e ponto.

### 6.2 Implementação

- `app/sources/milldesk.py`: novo método `async fetch_ticket(id) -> TicketDetail`,
  com cache `{id: (detail, fetched_at)}`, TTL `MILLDESK_DETAIL_TTL_SECONDS=300`, e
  participação no mesmo controle de rate limit da coleta (fila sequencial, 0,4 s,
  cooldown de 429). Modo debug: `python -m app.sources.milldesk --ticket 1234`.
- `app/state.py`: dataclass `TicketDetail` + `to_json()`.
- `app/tui/screens/ticket_detail.py`: `ModalScreen` (ou `Screen` empilhada) com:
  cabeçalho (ID, assunto, status, prioridade/urgência, solicitante, técnico);
  linha de SLA com **contagem regressiva** e cor (verde > 4 h, amarelo < 4 h, vermelho
  vencido, cinza quando for texto tipo `Em pausa`); descrição com rolagem
  (`VerticalScroll` + `Static`/`Markdown`); resolução, se houver; rodapé com
  `[o] abrir no navegador  [y] copiar ID  [r] recarregar (ignora cache)  [Esc] voltar`.
- Também acessível pelo launcher: `:md 1234` abre o detalhe direto pelo ID.
- Lista do painel Milldesk passa a mostrar, por chamado: ID, assunto (truncado), status,
  SLA restante e idade. Ordenação padrão: SLA mais próximo primeiro; `s` alterna.

### 6.3 Testes

- Fixture `tests/fixtures/milldesk_showTicket.json` (anonimizada).
- Testes: parse do detalhe; `invalidId`; cache hit/miss/TTL; conversão de
  `slaexpirationdate` em texto e em data; render da tela com fixture.

---

## 7. Feature D — Detalhe da conversa ChatPanel ("ler conversa") (Fase 6.3)

Esta é a feature de **maior risco**, porque o ChatPanel não tem API e abrir uma conversa
no painel pode ter efeitos colaterais no servidor. Por isso ela tem uma etapa de medição
obrigatória antes de qualquer código de UI.

### 7.1 Efeitos colaterais a medir (antes de implementar)

Com a TUI fechada e o usuário dedicado logado, usando `scripts/chatpanel_diag.py` (ou um
novo `scripts/chatpanel_diag_open.py`), medir e registrar em
`docs/CHATPANEL_CONVERSA.md`:

1. O que `changeTheInfo(this, '<numero>')` dispara: quais requisições a `control.php`
   (parâmetros `control=…`), quais eventos de socket, e o que muda em `#main-chat-content`.
2. Se abrir a conversa **zera o badge de não lidas** só no DOM local ou também no
   servidor (verificar se, no navegador do técnico, o contador some).
3. Se abrir a conversa **envia "visto"/read receipt ao contato** no WhatsApp.
4. Se existe uma requisição de "carregar mensagens" que pode ser reproduzida **dentro da
   página** (mesma técnica da ressincronização, `page.evaluate` chamando o endpoint
   diretamente) **sem** passar por `changeTheInfo` — essa é a opção preferida, pois
   não altera qual conversa está "aberta" no painel.

Decisão, apresentada ao usuário com a evidência:

- Se existe forma de ler mensagens sem efeito colateral → implementar (7.2).
- Se abrir a conversa só muda o DOM local do usuário dedicado → aceitável; documentar.
- Se marca como lida no servidor ou envia "visto" → **não implementar** a leitura;
  substituir por "abrir esta conversa no navegador" (`o`) e por um modo de detalhe
  que mostra apenas o que já está na lista (última mensagem completa, tag, departamento,
  horário, não lidas). Perguntar antes de decidir.

### 7.2 Implementação (se aprovada)

- `app/sources/chatpanel.py`: `async fetch_conversation(number, limit=50) ->
  ConversationDetail`, executado dentro da mesma página headless. Parser puro
  `parse_conversation_html(html) -> list[ChatMessage]` (autor, horário, texto, se é do
  técnico/`*Nome:*`, tipo: texto/mídia/áudio), testado com
  `tests/fixtures/chatpanel_conversation.html`. Modo debug:
  `python -m app.sources.chatpanel --conversation 5511999999999`.
- Tela `app/tui/screens/conversation_detail.py`: cabeçalho (contato, número, tag,
  departamento, online, técnico atual); mensagens em ordem cronológica, técnico à
  direita/contato à esquerda ou com prefixo e cor diferentes; rolagem começa no fim;
  `r` recarrega; `o` abre no navegador; `y` copia o número; `Esc` volta.
- Atualização enquanto a tela está aberta: a cada ciclo do ChatPanel, se a conversa
  aberta ganhou mensagens, recarregar o detalhe (sem novo login, sem reload da página).

---

## 8. Feature E — Launcher e pesquisa web (Fase 6.4)

Uma linha de comando dentro da TUI, aberta com `:` (ou `Ctrl+P`, se o Command Palette do
Textual for usado como base — avaliar no reconhecimento; a paleta nativa já dá busca
fuzzy, histórico e `Provider`s customizados, o que economiza código).

Sintaxe `prefixo argumento`; sem prefixo = pesquisa no motor padrão. Tudo abre com
`webbrowser.open_new_tab(url)` (stdlib), montando a URL com `urllib.parse.quote_plus`.

| Comando | Ação |
|---|---|
| `g termo` / `termo` | Google: `https://www.google.com/search?q=…` |
| `ddg termo`, `yt termo` | DuckDuckGo, YouTube |
| `md 1234` | Abre o **detalhe** do ticket na TUI; `md! 1234` abre no navegador |
| `wa 5511999999999` | `https://wa.me/<numero>` (ou a conversa no ChatPanel, se houver URL direta) |
| `cp` / `mail` / `mdweb` | Abre ChatPanel / webmail / Milldesk web |
| `open url` | Abre uma URL qualquer |
| `fav nome` | Atalho salvo em `prefs.json` (`favorites: {nome: url}`), gerenciado com `fav add nome url` / `fav rm nome` |
| `email`, `tickets`, `chats`, `log`, `notes`, `dash` | Troca de tela |
| `refresh` / `refresh md` | Equivalente a `r` / `2` |
| `help` | Lista de comandos |

Detalhes:

- Motores e URLs base configuráveis (`SEARCH_ENGINE_URL`, `MILLDESK_WEB_TICKET_URL`
  com `{id}`, `WEBMAIL_URL`, `CHATPANEL_WEB_URL`). Se o usuário não informar um padrão de
  URL, o comando correspondente mostra "não configurado" em `notify()` — nunca chutar URL.
- Histórico dos últimos 50 comandos (`prefs.json`), navegável com `↑`/`↓` na linha.
- Feedback sempre por `notify()` ("abrindo Google: …"); erro de comando não fecha a linha.
- Limitação a documentar: abrir o navegador tira o foco do terminal (é o SO); o app não
  tem como "voltar" sozinho. Sugerir ao usuário atalho do Windows Terminal (ex.:
  `Win+`` ` no modo quake) e registrar no README.

---

## 9. Sugestões adicionais (priorizar com o usuário ao fim da Fase 6.0)

Apresente esta lista com uma estimativa de esforço (P = pequeno, M = médio, G = grande) e
peça para o usuário marcar o que entra neste ciclo. Não implemente sem confirmação.

**P1 — alto valor, baixo risco**

1. **Feed de eventos** (`F7` ou seção no Dashboard): linha do tempo do dia com
   "15:31 e-mail novo de X", "15:28 chamado #123 entrou no seu nome", "15:20 conversa de
   Y transferida para você", "chamado #99 saiu do seu nome". Deriva de diffs entre
   estados consecutivos; persiste em `logs/events-YYYY-MM-DD.jsonl`. Resolve o
   "o que aconteceu enquanto eu estava em outra tela".
2. **SLA em destaque no Dashboard**: o chamado com SLA mais próximo aparece em linha
   própria com contagem regressiva; vermelho piscante quando faltar < 30 min.
3. **Notas persistentes** (`F6`): `TextArea` salvo em `notes.md` (autosave), útil para
   colar número de protocolo, senha temporária, checklist do dia.
4. **Windows toast opcional** (`NOTIFY_TOAST=true`, pacote puro `winotify`): notificação
   do sistema quando um contador sobe e o terminal não está em foco. Complementa o bell.
5. **Modo foco / silêncio** (`m`): silencia bell e toast por N minutos; mostra ícone no
   header e um resumo ao sair.
6. **Tela de saúde** (`F8` ou `?`): status de cada fonte (ok/erro/não configurada),
   latência da última coleta, próximo ciclo, chamadas Milldesk no último minuto (útil
   contra o 429), versão do Chromium, tamanho do log.

**P2 — valor médio**

7. **"Finalizados hoje"** no ChatPanel (já previsto na seção 9 do prompt original):
   contar conversas que saíram de "EM ATENDIMENTO" no meu nome durante o dia e
   entraram em `#box-noactive-chats`. Sem escrita, só diff.
8. **E-mail: lista dos últimos N + filtro de não lidos** (`u` alterna), e busca por
   remetente/assunto na tela F2.
9. **Ordenação e agrupamento** no Milldesk (por status, prioridade, solicitante) e no
   ChatPanel (por não lidas, departamento).
10. **Pomodoro/timer** no header (`t` inicia 25 min; bell ao fim) — simples e útil para
    quem fica o dia no terminal.
11. **Layout do Dashboard configurável**: `prefs.json` define ordem e tamanho relativo
    dos painéis; teclas `Ctrl+↑/↓` reordenam.

**P3 — explorar depois / maior esforço**

12. **IMAP IDLE** para e-mail em push (previsto como melhoria futura na Fase 1).
13. **Atalhos "responder rápido"**: montar `mailto:` com assunto/remetente preenchidos e
    abrir no cliente padrão (não envia nada — só abre o compositor).
14. **Exportar relatório do dia** (`export`): Markdown com contadores, tickets, conversas e
    eventos, para o fechamento do turno.
15. **Painel plugável**: interface `Panel` + registro em `SOURCE_PANELS` documentada para
    que uma quarta fonte (ex.: monitor de servidores, calendário) entre sem tocar em
    `app.py`.

---

## 10. Fases e entregas

| Fase | Conteúdo | Commit |
|---|---|---|
| 6.0 | Reconhecimento, fixtures reais anonimizadas, `docs/RECON_CICLO2.md`, plano e lista de perguntas → **parar para aprovação** | `docs: reconhecimento ciclo 2` |
| 6.1 | Telas (modos) + listas com cursor + foco + prefs.json + últimos N e-mails | `feat: telas e navegação por teclado` |
| 6.2 | Detalhe do ticket Milldesk (fonte + cache + tela + testes) | `feat: detalhe do ticket` |
| 6.3 | Medição do ChatPanel → decisão → detalhe da conversa (ou alternativa) | `feat: detalhe da conversa` |
| 6.4 | Launcher (`:`), pesquisa web, favoritos, histórico | `feat: launcher e pesquisa web` |
| 6.5 | Itens P1 aprovados + README/CLAUDE.md atualizados + troubleshooting das novas telas | `feat: ciclo 2 — polimento` |

Ao fim de cada fase, como sempre: o que foi feito, como testar (comandos exatos), o que
depende do usuário. Atualizar a tabela de atalhos do README a cada fase — ela é a
documentação oficial dos bindings.

---

## 11. Perguntas para o usuário (responder antes da 6.1)

1. Um ID de ticket real para a chamada de reconhecimento de `showTicket` (será
   anonimizado na fixture).
2. Padrão de URL do ticket no Milldesk web (ex.: `https://<conta>.milldesk.com/…/{id}`)
   para o comando `o`/`md!`.
3. URL do webmail (para `o` em e-mails) e se o ChatPanel tem URL direta por conversa.
4. Motor de busca padrão (Google) e favoritos iniciais do launcher.
5. Quantos e-mails listar na tela F2 (sugestão: 20).
6. Se o Windows toast (`winotify`) é bem-vindo ou se o bell basta.
7. Quais itens da seção 9 entram neste ciclo.
8. Autorização para a medição da seção 7.1 (será feita com a TUI fechada e o usuário
   dedicado; abrirá conversas reais uma vez para observar o comportamento).

---

## 12. Definição de pronto do ciclo

- Todos os atalhos documentados no README funcionam em qualquer tela.
- `python -m pytest` verde, com testes novos para: preservação do cursor entre
  atualizações, parse do detalhe de ticket, cache/TTL, parse de conversa (se aprovado),
  parser de comandos do launcher (`"g foo"`, `"md 12"`, `"fav add x y"`, entrada vazia).
- Nenhuma nova chamada de escrita em nenhuma fonte (grep por `addTicket`,
  `updateTicketStatus`, `sendCommunication`, `control=5` etc. continua sem ocorrências
  fora dos testes/documentação).
- `logs/app.log` sem tracebacks em 1 hora de uso normal navegando entre telas.
- `docs/RECON_CICLO2.md` e `docs/CHATPANEL_CONVERSA.md` refletem as medições feitas,
  com data.
