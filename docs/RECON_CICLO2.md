# Reconhecimento do ciclo 2 (Fase 6.0) — 15/09/2026

Base: `PROMPT_FASE6_NAVEGACAO_E_INTERATIVIDADE.md`. Nenhum código de feature foi escrito;
apenas leitura, uma rodada de chamadas reais ao Milldesk e leitura do JavaScript do
ChatPanel já desofuscado nas sessões anteriores.

## 1. Textual instalado e APIs disponíveis

`textual 8.2.8` (Python 3.14 no venv). Verificado por introspecção, tudo presente:

| Necessidade | API | Situação |
|---|---|---|
| Telas por modo | `App.MODES`, `App.switch_mode()` | ok |
| Detalhes/diálogos | `Screen`, `ModalScreen`, `push_screen`/`pop_screen` | ok (já usado em `EmailDetailScreen`) |
| Abas | `TabbedContent`, `TabPane` | ok |
| Listas com cursor | `ListView`/`ListItem`, `DataTable` (`cursor_type`, `move_cursor`, `get_row_index`, `cursor_row`, `sort`), `OptionList` | ok |
| Launcher | `Input`; `textual.command.Provider`/`Hit`/`CommandPalette` (`App.COMMANDS`) | ok |
| Texto longo | `Markdown`, `MarkdownViewer`, `TextArea`, `VerticalScroll` | ok |
| Avisos | `App.notify()` | ok |
| Cabeçalho/rodapé | `Header`, `Footer` (o Footer lê `Binding(show=True)` da tela ativa) | ok |

Pacotes opcionais citados no prompt: `pyperclip` e `winotify` **não estão instalados**
(ambos puros; adicionar só com aprovação). Não há necessidade de upgrade do Textual.

## 2. Como os painéis recebem estado hoje e o que precisa mudar

- `app/tui/app.py`: `SOURCE_PANELS` mapeia fonte → (id do painel, rótulo, fase). Os
  workers vivem no `App` (`_source_loop` → `_fetch_once`), publicam em `self.states[name]`
  e chamam `panel.show_state(state)`, `panel.set_error()`, `panel.mark_updated()`.
  O destaque/bell compara `panel.counters(old)` × `panel.counters(new)`.
- `BasePanel` é um `Vertical` com dois `Static`: `.panel-body` (recebe um renderable Rich
  via `set_body`) e `.panel-error`. Nada é focável; não há cursor nem seleção. Os painéis
  concretos (`EmailPanel`, `MilldeskPanel`, `ChatPanelPanel`) montam `Group`/`Table` do
  Rich e trocam o corpo inteiro a cada ciclo.
- `MilldeskPanel` mostra só 3 chamados (`MAX_TICKET_LINES`); `ChatPanelPanel` mostra todas
  as conversas numa `rich.Table` sem interação; `EmailPanel` mostra só o e-mail mais recente
  (`EmailState.latest`), porque a fonte busca apenas o UID mais alto.

O que muda para listas com cursor:

1. `BasePanel` ganha um slot de lista: o corpo passa a ser um `DataTable`
   (`cursor_type="row"`, `zebra_stripes`, `show_header` conforme o painel) e o cabeçalho
   textual (contadores) fica num `Static` acima. **Escolha: `DataTable`**, por colunas
   alinhadas, ordenação nativa e chaves de linha (`RowKey`) que resolvem a preservação do
   cursor; `ListView` exigiria um widget por item e não ordena.
2. Publicação de estado vira **diff por chave** (ID do chamado, número do WhatsApp, UID do
   e-mail): linhas novas são inseridas, existentes atualizadas célula a célula
   (`update_cell`), ausentes removidas. O cursor é re-posicionado por
   `get_row_index(chave_selecionada)`; se a chave sumiu, vai para o vizinho de índice
   mais próximo. Sem isso o `DataTable.clear()` + `add_rows` faria o cursor pular.
3. `EmailSource` precisa de `EMAIL_LIST_SIZE` (padrão 20): buscar os N UIDs mais altos com
   cabeçalhos (`fetch(..., headers_only=True, mark_seen=False)`) sem aumentar a frequência;
   `EmailState` ganha `recent: list[EmailSummary]`.
4. `MilldeskState.tickets` já traz todos os abertos do técnico (a lista completa só é
   truncada na renderização). `ChatPanelState.mine` idem. Nenhuma coleta nova para as telas
   F3/F4.

## 3. Foco e bindings

- Hoje nada é focável além do app; os bindings são todos do `App` (`q r 1 2 3 e l c`).
- `DataTable` traz bindings próprios: setas, `pageup/pagedown`, `home/end`, `enter`
  (`RowSelected`). Não usa `j/k`, `o`, `y`, `/`, `s`: livres para os painéis.
- Regra do Textual: bindings do widget focado vencem os do `App`, exceto os marcados
  `priority=True`. Com um `Input` focado (filtro `/`, launcher `:`) TODAS as teclas de
  texto vão para ele. Portanto: `F1–F6`, `Esc`, `q`, `Ctrl+P` ficam `priority=True` no
  `App`; `e`, `r`, `1/2/3`, `c`, `l` ficam normais (não funcionam dentro do `Input`, o que é
  desejável) e continuam globais fora dele.
- Indicador de foco: `BasePanel:focus-within` no CSS muda a cor da borda; `Tab` circula
  E-mail → Milldesk → ChatPanel (ordem de `compose`).
- `Esc` na raiz de uma tela volta ao Dashboard; num `ModalScreen` fecha o modal
  (`dismiss`). Isso já funciona hoje para o detalhe do e-mail.
- Atenção medida hoje (bug latente corrigido no commit `0a9e126`): `self.query_one` no
  `App` consulta a **tela ativa**; com modos, o relógio, a barra de status e `panel()`
  precisam consultar a tela do Dashboard explicitamente (`self.main_screen`), como já é
  feito. Ao trocar de modo, a tela do Dashboard continua montada (`MODES` mantém instâncias),
  então os workers podem seguir atualizando os painéis mesmo com outra tela na frente.

## 4. `showTicket` (chamada real, 15/09/2026)

Fixture anonimizada: `tests/fixtures/milldesk_showTicket.json` (nomes, assunto, textos,
local e grupo trocados; ids/datas/status mantidos; ID trocado por 4242).

- Resposta é um **objeto** (não lista), HTTP 200. Erros continuam vindo como
  `{"error": "invalidId"}` (mesmo padrão das outras rotas).
- Campos (41): `id, ticket, description, requester, start, end, analysis, reopening,
  category, subcategory, location, department, agent, stage, impact, asset, manner, level,
  priority, problem, solution, status, tickettype, urgency, observation, contactphone,
  contract, impactdetails, change, satisfaction, satisfactioncomment, resolution, group,
  slasexpirationdate, starttime, endtime, analysistime, charge_hour, worked_hour,
  communication, workflow_fields`.
- **`description` vem em HTML** (parágrafos); converter com BeautifulSoup preservando
  quebras. `resolution` veio em texto puro. Vários campos vêm `null` ou `""`.
- `slasexpirationdate` no formato `dd/mm/aaaa HH:MM` (pode ser texto, ex. `Em pausa`, como
  visto na Fase 3). `starttime` traz data e hora; `charge_hour`/`worked_hour` são strings
  decimais com vírgula.
- **`communication` existe** como string; veio vazio no chamado consultado. É o único
  candidato a "histórico de comunicações" da API. Formato desconhecido: antes de renderizar,
  consultar um chamado que tenha comunicações (pedir um ID ao usuário; 1 chamada).
- apiDoc (dump `logs/milldesk_api_data.json`, 221 rotas): **não há** rota de listar
  comunicações. Rotas de escrita (`addTicket`, `sendCommunication`, `updateTicketStatus`)
  seguem proibidas. `statusHistoryReport` existe, mas é relatório geral, sem parâmetro de
  ID na doc.
- Custo da rodada de reconhecimento: 7 chamadas em 5 s (1 `ticketsByStatus`, 5
  `showTicketsByStatus` até achar um chamado do técnico, 1 `showTicket`), sem 429. O
  `showTicket` em si é 1 chamada; cache por ID com TTL é suficiente para a Fase 6.2.

## 5. Como o ChatPanel carrega uma conversa (só leitura do JS; nada foi clicado)

- `changeTheInfo(el, numero)` (em `assets/js/chat.js`): marca o `li` como `active`, mostra um
  spinner em `#mainbox-chat`, faz **`POST inc_chat_view.php {number}`** e injeta o HTML da
  conversa em `#mainbox-chat`; define `#chat_number`, foca o textarea, rola para o fim.
  Não chama `control.php` no cliente.
- Grupos usam `inc_chatgroup_view.php`. Existe ainda `inc_chat_d.php {control: 1}`
  (recarrega a conversa aberta, usado por `refreshTransfer`) e `inc_chat_viewmore.php`
  (paginação de mensagens antigas, provável).
- **Evidência de efeito colateral no servidor**: na captura de 5 min de hoje, toda vez que o
  técnico abriu um chat no navegador dele, o servidor emitiu `refreshRead {number}` para as
  outras sessões (o handler remove o badge `unreadchat_<n>` e recalcula o total). Ou seja,
  abrir a conversa (via `inc_chat_view.php`) muito provavelmente **marca como lida no
  servidor**. Se também envia "visto" ao WhatsApp não dá para saber sem medir.
- Consequência para a Fase 6.3: a medição da seção 7.1 é obrigatória e deve ser feita com
  o usuário dedicado e um contato de teste (número do próprio técnico), observando (a) o
  badge no navegador do técnico, (b) os frames de socket (`refreshRead`), (c) o "visto" no
  celular. Ferramentas prontas: `scripts/chatpanel_diag.py --watch N` (frames + mutações)
  e o `session.bin`/HTTP puro para chamar `inc_chat_view.php` sem socket, se quisermos
  testar sem tocar na sessão da TUI.
- Alternativa sem risco, caso a leitura marque como lida: modo de detalhe só com o que já
  está na lista (última mensagem completa, tag, departamento, hora, não lidas) + `o` para
  abrir no navegador.

## 6. Riscos identificados

1. **Cursor pulando** ao publicar estado: resolvido por diff por chave (seção 2).
2. **Rate limit do Milldesk**: `showTicket` só no `Enter`, cache por ID (TTL 5 min), mesma
   fila sequencial e cooldown de 429 da coleta (o `_lock` e `REQUEST_SPACING` já existem em
   `MilldeskSource`).
3. **`Input` engolindo teclas globais**: bindings `priority=True` só para os essenciais.
4. **Leitura de conversa com efeito no servidor** (seção 5): decisão só após medição.
5. **Fechar a TUI desloga o usuário dedicado** (medido hoje): trocar de tela não fecha o
   navegador, então nada muda; mas o launcher abrindo o navegador do técnico não afeta a
   sessão do app (usuários diferentes).
6. **Terminal estreito**: `DataTable` precisa de larguras mínimas; em < 100 colunas, ocultar
   colunas secundárias (tag/departamento) em vez de quebrar linhas.
7. **Foco e mouse**: cliques já funcionam no Windows Terminal; garantir que `Tab` e `Esc`
   sempre devolvam o foco a um painel.

## 7. Plano proposto (arquivos estimados)

| Fase | Entrega | Arquivos |
|---|---|---|
| 6.1 | `App.MODES` (dashboard, email, milldesk, chatpanel, log, notas opcional), `Header`/`Footer`, `prefs.py` + `prefs.json` (última tela), `DataTable` com diff por chave nos 3 painéis, foco/`Tab`, `/` filtro, `y` copiar, `EMAIL_LIST_SIZE` | `app/tui/app.py`, `app/tui/screens/*.py` (novo pacote), `app/tui/widgets/base_panel.py` + 3 painéis, `app/prefs.py`, `app/sources/email_imap.py`, `app/state.py`, `app/config.py`, `styles.tcss`, testes (cursor, prefs, e-mail N) |
| 6.2 | `fetch_ticket(id)` com cache/TTL/rate limit, `TicketDetail`, tela de detalhe com SLA regressivo, `:md 1234`, lista Milldesk completa com SLA/idade e ordenação `s` | `app/sources/milldesk.py`, `app/state.py`, `app/tui/screens/ticket_detail.py`, `milldesk_panel.py`, testes com a fixture |
| 6.3 | Medição 7.1 → `docs/CHATPANEL_CONVERSA.md` → decisão → detalhe da conversa **ou** detalhe só com dados da lista + `o` | `scripts/chatpanel_diag_open.py`, `app/sources/chatpanel.py`, `app/tui/screens/conversation_detail.py`, fixture `chatpanel_conversation.html`, testes |
| 6.4 | Launcher `:` (Input próprio; o Command Palette fica como opção para `Ctrl+P`), comandos da seção 8, favoritos e histórico em `prefs.json`, URLs no `.env` | `app/tui/launcher.py` (parser puro), `app/tui/screens/launcher.py`, `app/prefs.py`, `app/config.py`, `.env.example`, testes do parser |
| 6.5 | Itens P1 aprovados, README (tabela de atalhos), CLAUDE.md, troubleshooting | vários |

Ordem sugerida dentro da 6.1: (a) `prefs.py` e modos com as telas vazias; (b) `DataTable`
com diff por chave no ChatPanel (mais itens, melhor teste do cursor); (c) Milldesk;
(d) E-mail com `EMAIL_LIST_SIZE`; (e) filtro `/` e `y`.

## 8. Sugestões da seção 9 com esforço estimado

P1: feed de eventos (M), SLA em destaque (P), notas (P), toast Windows (P, requer
`winotify`), modo silêncio (P), tela de saúde (M).
P2: finalizados hoje (M), e-mail lista+filtro (P, já coberto pela 6.1), ordenação/
agrupamento (P), pomodoro (P), layout configurável (M).
P3: IMAP IDLE (G), responder rápido `mailto:` (P), exportar relatório (M), painel plugável (M).

## 9. Perguntas ao usuário (seção 11 do prompt)

1. Um ID de chamado **com comunicações** para ver o formato do campo `communication`
   (1 chamada; o de reconhecimento veio vazio).
2. Padrão de URL do chamado no Milldesk web (`MILLDESK_WEB_TICKET_URL` com `{id}`).
3. URL do webmail e se o ChatPanel tem URL direta por conversa.
4. Motor de busca padrão e favoritos iniciais do launcher.
5. Quantos e-mails listar na tela F2 (sugestão: 20).
6. Toast do Windows (`winotify`) sim ou não; `pyperclip` para copiar sim ou não.
7. Quais itens da seção 8 entram neste ciclo.
8. Autorização para a medição da conversa (Fase 6.3), com um número de teste seu.
