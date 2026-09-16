# Direção de design — CMD ALL-IN-ONE (Ciclo 3)

> **Status: Fase 7.0 concluída, aguardando aprovação da direção.** Nada de visual foi
> alterado ainda. Este documento vira o guia de estilo do projeto ao fim do ciclo.
>
> Capturas "antes": `docs/design/antes/` (SVG com cores + `.txt` em texto puro, 120×35 e
> 90×30, mais 120×22 e 80×24 para o Dashboard). Regerar com
> `python scripts/design_screenshots.py` (fixtures, sem rede).

---

## 1. Diagnóstico — o que atrapalha a leitura hoje

Critério: *glanceability*. Em menos de um segundo, sem ler, o técnico precisa saber se
tem algo novo, o que é urgente e onde está. Lendo as capturas com esse critério:

### 1.1 A moldura come a tela

- Três painéis com borda `round` no Dashboard: cada um gasta **2 linhas e 2 colunas**
  só de moldura, mais 1 de `padding`. Em 120×35 o ChatPanel tem 18 linhas para 3
  conversas; em **90×30 sobra uma linha de conteúdo** para o ChatPanel
  (`dashboard_90x30`); em **80×24 o ChatPanel e o Footer nem aparecem**
  (`dashboard_80x24`), porque `#top-row` tem altura fixa de 13 e, empilhado, 26.
- A borda muda de cor para dizer quatro coisas diferentes (repouso `$primary`, foco
  `$accent`, erro `$error`, não configurado `$warning`) e de espessura para uma quinta
  (mudança = `heavy $warning`). Cinco significados no mesmo canal visual.

### 1.2 Os números não são números

- O cabeçalho de cada painel é uma **frase**: `Inbox: 142   Não lidos: 7   Spam: 3`.
  O rótulo tem o mesmo peso do valor; o olho lê a linha inteira para achar o 7.
- O Milldesk gasta **3 linhas** de texto corrido (contagem, SLA mais próximo,
  histórico) e o truncamento `…` corta justamente o que importa:
  `Em atendiment…`, `#4802 Certificado digital do prefe…`, `ordem: SL…`.
- `Histórico: 1184 chamados · 23,4% de 5061` é informação de relatório, não de
  cockpit; aparece o dia inteiro no lugar mais nobre do painel.

### 1.3 A cor está gasta antes de acontecer alguma coisa

- Em repouso a tela já é colorida: `cyan` em hora, ID e tag; `green` em "online" e SLA
  folgado; `yellow` em qualquer contador maior que zero (`Não lidos: 7`, `Abertos no
  meu nome: 12`). Quando algo realmente muda, a borda amarela grossa
  (`dashboard_mudanca_120x35`) disputa atenção com o amarelo que já estava lá.
- Verde/amarelo/vermelho servem tanto para estado (SLA, sessão) quanto para
  categoria (tipo de evento em F7: `cyan`/`green`/`yellow`; lado da mensagem na
  conversa: `green`/`cyan`).
- **86 estilos Rich literais** em `app/tui/**` (`"cyan"`, `"bold yellow"`, `"green"`,
  `"bold red"`…), fora do `.tcss`. Trocar de tema hoje não trocaria nada disso.

### 1.4 Alinhamento e largura

- **Emoji nos títulos** (`📧 🎫 💬`) e na TopBar (`🔇`): largura 2 em `cell_len`,
  renderizados com largura variável no conhost e no SVG. Únicos glifos de largura 2
  no código.
- A coluna `mark` (1 célula + 2 de padding) deixa **3 colunas de vazio permanente** à
  esquerda de toda linha (`     08:11`), mesmo sem marcador.
- Datas absolutas em toda parte (`15/09 06:14`, `16/09/2026 08:14:20` na TopBar). Só o
  F8 usa "há 2s". A TopBar gasta 19 células com data completa que ninguém consulta.

### 1.5 Barras: TopBar e Footer

- TopBar com fundo `$primary` (azul saturado): a linha mais chamativa da tela é a que
  menos informa. Não há nenhum indicador de saúde das fontes fora do F8.
- Footer padrão do Textual lista **todos os bindings globais** (`q f1…f8 r e : ?`):
  estoura em 120 colunas (`e Últi`), muda de ordem por tela (Notas:
  `f6 Notas  f7 Eventos  ^s Salvar  f1 Dashboard…`) e empurra os atalhos da tela atual
  (`u`, `s`, `t`, `f`, `x`) para antes de `q Sair`. Com o filtro aberto
  (`milldesk_filtro_120x35`) o Footer perde metade dos itens.

### 1.6 Estados

| Estado | Hoje | Problema |
|---|---|---|
| Primeira coleta | `aguardando…` em texto dim | ok como fallback, mas não diz o que está acontecendo |
| Erro com dados | borda `$error` + `✖ timeout · aguardando 600s` no rodapé; dados somem (`aguardando…`) quando o erro é na primeira coleta | próximo do desejado; falta manter os dados antigos visíveis com hora |
| Não configurado | borda `$warning` + `não configurado` amarelo | amarelo = "atenção" para algo que é decisão do usuário |
| Vazio | `nenhuma conversa no meu nome` dim na 2ª linha do cabeçalho | invisível; vazio aqui é boa notícia e deveria parecer |
| Carregando detalhe | `#4821  carregando…` | modal abre "vazia" |
| Silêncio | `🔇` na TopBar | emoji, sem tempo restante |
| Cooldown 429 | texto no rodapé do painel | não aparece na TopBar |

### 1.7 Modais, launcher, ajuda e telas auxiliares

- Modais com 90–92% da tela deixam o Dashboard **vazando 2 colunas** de cada lado
  (`detalhe_chamado_120x35`): ruído sem função. Cabeçalho do chamado em 5 linhas
  corridas de `Rótulo: valor   Rótulo: valor`. Rodapé de atalhos repetido em texto
  dentro da modal, além do Footer.
- Launcher: caixa de 5 linhas no topo, cobrindo o painel de e-mail, com a dica em
  texto corrido.
- Ajuda: 30 linhas sem agrupar por tela; a parte do launcher só aparece rolando.
- **Bug** (Log/F5): a dica `[f] muda o filtro` é interpretada como markup Rich e some
  (`log_120x35`: `11 linhas   muda o filtro`).
- Eventos (F7): `HH:MM:SS` repetido em toda linha; cor por tipo de evento.
- Saúde (F8): tabela Rich sem status visual; `Duração 0.0s`.
- Notas (F6): `TextArea` com moldura dupla (`▊` `▎`) e status estático (`salva
  sozinho 1 s após parar de digitar`).

### 1.8 Bug encontrado (e corrigido) durante a auditoria

Redimensionar o terminal cruzando 100 colunas com dados carregados **derrubava o app**
(`KeyedTable.rebuild_columns` re-inseria células no número antigo de colunas). Corrigido
em commit próprio (`fix(tui): redimensionar o terminal…`), com teste de regressão. A
seleção agora também sobrevive à remontagem.

---

## 2. Inventário do que existe

### 2.1 `styles.tcss` (260 linhas)

- **Sem cor literal** — usa só variáveis do Textual: `$primary`, `$accent`, `$surface`,
  `$background`, `$secondary`, `$error`, `$warning`, `$text`, `$text-muted`. Bom ponto
  de partida; o problema está nos estilos Rich dentro dos widgets, não no CSS.
- Bordas: `BasePanel` `round $primary` → `:focus-within` `round $accent` → `.error`
  `round $error` → `.unconfigured` `round $warning` → `.changed` `heavy $warning`.
  Modais e `#log-lines`: `round $primary` / `round $secondary`; separadores internos
  `border-bottom: solid $secondary`.
- Cursor da lista: `.datatable--cursor { background: $accent 30% }`. Zebra desligada.
- Layout do Dashboard: `#top-row { height: 13 }` fixo; `#main.narrow` empilha (classe
  aplicada por `if width < 100` em `DashboardScreen.on_resize`, não por breakpoint).
- Modais: `align: center middle`, fundo `$background 60%`, caixa 90–92%.

### 2.2 Estilos Rich literais por arquivo

| Arquivo | Ocorrências | Cores usadas |
|---|---|---|
| `screens/ticket_detail.py` | 27 | dim, bold, cyan, bold cyan, bold red, bold yellow, green |
| `screens/conversation_detail.py` | 16 | dim, bold, green, cyan, bold yellow, bold red, italic |
| `widgets/milldesk_panel.py` | 13 | dim, cyan, yellow, bold yellow, bold red, green, bold green, bold white on red |
| `widgets/chatpanel_panel.py` | 10 | dim, bold, green, cyan, bold yellow |
| `screens/health.py` | 7 | bold, dim, green, bold red, yellow |
| `screens/email_detail.py` | 6 | dim, bold |
| `widgets/email_panel.py` | 5 | bold, dim, cyan, bold yellow |
| `screens/launcher.py` | 4 | dim, bold cyan, bold red, green |
| `screens/events.py` | 3 + `KIND_STYLE` | dim, bold, cyan, green, yellow |
| `widgets/base_panel.py` | 2 | bold yellow (`MARK ●`), `[yellow]` |
| `app.py` | 1 | `[yellow]` (login) |

### 2.3 Emoji e glifos

Largura 2 (`rich.cells.cell_len`): `📧` `🎫` `💬` (ícones dos painéis) e `🔇`
(TopBar). Todos os outros glifos em uso têm largura 1: `● ○ ✖ ⏱ ⚠ ▌ ▐ … ·`. Os glifos
propostos na seção 6 foram todos verificados com largura 1, inclusive os Nerd Font
(`U+F0E0 U+F3FF U+F075 U+F111 U+F10C`).

### 2.4 Larguras de coluna (`ColumnSpec`, `None` = flexível)

| Painel | Tela cheia | Dashboard | Estreito (< 100) |
|---|---|---|---|
| E-mail | data 11 · de 28 · assunto ∗ | data 11 · de 16 · assunto ∗ | data 11 · assunto ∗ |
| Milldesk | id 6 · abertura 11 · assunto ∗ · status 20 · sla 9 | id 6 · assunto ∗ · status 12 · sla 8 | id 6 · assunto ∗ · sla 8 |
| ChatPanel | online 1 · hora 5 · contato 30 · tag 12 · depto 12 · msg ∗ · não lidas 3 | online 1 · hora 5 · contato 26 · tag 12 · msg ∗ · não lidas 3 | online 1 · hora 5 · contato 20 · msg ∗ · não lidas 3 |

Mais a coluna `mark` (1) sempre à esquerda. A flexível recebe `largura − fixas −
2·colunas − 1` (`BasePanel._fit_columns`); `DataTable` não tem `1fr`.

### 2.5 Como as barras e os painéis são compostos

- **TopBar** (`widgets/top_bar.py`): `Horizontal#header` com dois `Static`: título
  (`CMD ALL-IN-ONE  ·  Tela`, `1fr`, bold) e relógio (`{extra}{técnico} · dd/mm/aaaa
  HH:MM:SS`, atualizado a cada 1 s). `extra` é `🔇 ` quando silenciado.
- **Footer**: `textual.widgets.Footer` padrão, alimentado pelos `BINDINGS` com
  `show=True` do App e da tela.
- **BasePanel** (`Vertical` com borda): `Static.panel-head` (texto do cabeçalho,
  `Text` com `no_wrap` + `ellipsis`), `Input.panel-filter` (oculto até `/`),
  `KeyedTable.panel-table`, `Static.panel-error` (oculto). `border_title` =
  `ICON TITLE`; `border_subtitle` = `30s · HH:MM:SS`.
- **KeyedTable** (`DataTable`, `cursor_type="row"`, sem cabeçalho no painel): células
  são `rich.text.Text` já estilizadas pela subclasse (`rows()`); `set_rows()` faz diff
  por chave e preserva o cursor.
- **Destaque de mudança**: `App.notify_change` → `panel.flash()` adiciona a classe
  `changed` (borda `heavy $warning`) por 3 s; `show_state()` marca as chaves de
  `changed_keys()` com `●` bold yellow na coluna `mark` por 3 s (`_marked` + timer).

---

## 3. Verificação do Textual instalado (8.2.8, Python 3.14.4)

| Item | Resultado |
|---|---|
| `textual.theme.Theme` | ✓ dataclass: `name primary secondary warning error success accent foreground background surface panel boost dark luminosity_spread text_alpha variables ansi` |
| `App.register_theme` / `App.theme` / `App.available_themes` / `App.get_theme` / `App.search_themes` | ✓ |
| `theme_changed_signal` | ✓ **atributo de instância** (não aparece na classe); assinar em `on_mount` |
| Temas embutidos | ✓ 21: `textual-dark/light`, `nord`, `gruvbox`, `catppuccin-mocha/latte/frappe/macchiato`, `dracula`, `tokyo-night`, `monokai`, `flexoki`, `solarized-dark/light`, `rose-pine(-dawn/-moon)`, `atom-one-dark/light`, **`ansi-dark`/`ansi-light`** |
| `App.ansi_color` | ✓ reactive; os temas `ansi-*` usam `ansi_red`, `ansi_default` etc. |
| `App.get_css_variables()` | ✓ 168 variáveis geradas do tema; `Theme.variables` injeta variáveis próprias (é por aqui que os tokens da seção 6 entram) |
| Variáveis relevantes | `$primary $accent $surface $panel $background $foreground $success $warning $error $boost` com `-lighten-1..3`, `-darken-1..3`, `-muted`; `$text $text-muted $text-disabled`; `$border $border-blurred`; `$footer-*`; `$block-cursor-*`; `$input-*`; `$scrollbar-*` |
| `Digits`, `Sparkline`, `ProgressBar`, `Rule` (horizontal/vertical), `LoadingIndicator`, `Label`, `Tooltip`, `OptionList` | ✓ |
| `border_title` / `border_subtitle` + `border-title-align` / `border-subtitle-align` / `-color` / `-style` / `-background` | ✓ |
| Estilos de borda | `ascii blank block dashed double heavy hidden hkey inner none outer panel round solid tab tall thick vkey wide` |
| `HORIZONTAL_BREAKPOINTS` / `VERTICAL_BREAKPOINTS` | ✓ em `App` e **`Screen`** (não em `Widget`); aplicam classes na tela |
| `App.animation_level` | ✓ atributo de instância (`full`), lê `TEXTUAL_ANIMATIONS` |
| `widget.styles.animate()` / `widget.animate()` | ✓ `(attribute, value, *, duration, easing, on_complete, level)`; `opacity` e `text_opacity` são animáveis. Células de `DataTable` não são widgets: o fade da linha continua sendo timer + re-render da célula (como hoje), e o `animate` fica para marcadores fora da tabela |
| Estilos de texto | `bold dim italic underline strike reverse blink overline` (`italic` e `dim` dependem do terminal) |
| `App.save_screenshot()` / `export_screenshot()` | ✓ usados em `scripts/design_screenshots.py` |
| `pytest-textual-snapshot` | **não instalado**; 1.1.0 no PyPI (puro Python, depende de `syrupy` + `jinja2`). Entra no `[dev]` na 7.1 |
| `Footer(compact=True)` | ✓ existe, mas continua listando todos os bindings; será substituído |

---

## 4. Direção proposta

**Mood:** cockpit silencioso. **Três adjetivos:** quieto, denso, legível.

**Referências:** `lazygit` (painel focado = só o título muda de cor; sem borda grossa),
`btop` (números grandes com rótulo pequeno embaixo; cor só na barra), `k9s` (uma linha
de contexto no topo, uma de atalhos embaixo, o resto é lista), `helix` (statusline com
tecla em destaque e descrição apagada), `starship` (ícones com fallback, nada de largura
2).

**Decisões que este documento propõe (para aprovação):**

1. **Painéis sem borda em repouso** (≥ 100 colunas). Separação por espaço e por um
   `Rule` vertical `dim`. Ganho: 2 linhas por painel; em 90×30 o ChatPanel passa de 1
   para ~8 linhas úteis.
2. **Painel focado = título em `accent` + marcador `▍`**, sem borda. Recomendo esta
   opção sobre "borda `accent`" porque a borda devolveria as 2 linhas perdidas só no
   painel focado, fazendo o layout pular ao trocar de painel com `Tab`. A 7.2 entrega
   as duas em screenshot, como pede a spec; a recomendação é esta.
3. **Uma cor de destaque.** Hora, ID, tag e "online" deixam de ser `cyan`/`green`;
   viram `text-muted`. `accent` fica reservado para foco, seleção, tecla e mudança
   recente. Verde/âmbar/vermelho **só** em SLA, sessão, erro e saúde.
4. **Contadores viram `Digits`** (altura 3) no Dashboard com ≥ 100 colunas e ≥ 30
   linhas; nos demais casos, uma linha de texto (`142 inbox · 7 não lidos · 3 spam`).
   `Histórico` sai do Dashboard (fica no F3 e no F8).
5. **Coluna `mark` deixa de existir.** O marcador `▎` passa a ser o primeiro caractere
   da primeira célula (hora/ID), em `accent`, por 3 s; em repouso o lugar fica vazio
   (1 célula, não 3).
6. **TopBar nova**, 1 linha, fundo `surface`: marcador `▍` + nome + tela; três pontos de
   saúde ao centro (`ok/warn/danger/muted`), com tooltip; técnico + `HH:MM:SS` +
   ícones transitórios à direita. Sai a data.
7. **Footer próprio**: só os atalhos da tela atual, tecla em `accent`, descrição em
   `text-muted`; os `F1…F8` saem do rodapé (ficam em `?` e no nome da tela na TopBar).
   Nunca mais de uma linha; o que não cabe some, `?` sempre cabe.
8. **Tempo relativo** nas listas e nos títulos (`há 3 min`, `há 27s`); absoluto nos
   detalhes; contagem regressiva no SLA (`1h 42m`).
9. **Modais** com largura máxima 100 e altura `auto` (máx. 90%), sem o Dashboard
   vazando: fundo atrás em `bg 85%`. Cabeçalho em duas colunas rótulo/valor. Rodapé
   de atalhos em texto sai (o Footer já mostra).
10. **Todo estado tem um desenho** (seção 7 da spec); "não configurado" passa a ser
    neutro (`text-faint`), nunca âmbar.

---

## 5. Mockups em 120 colunas

### 5.1 Dashboard (120×35, tema `carbon`, painel de e-mail focado)

Legenda de cor: `▍`/`▎`/teclas/linha selecionada = `accent`; rótulos e horas =
`text-muted`; "há Ns", `›`, `+7 · F3` = `text-faint`; só a barra e o tempo do SLA usam
`ok/warn/danger`.

```
▍CMD ALL-IN-ONE  Dashboard                             ● ● ●                          Guilherme  08:14:20

  ▍✉ E-MAIL                               30s · há 6s  │  ▣ MILLDESK                            60s · há 27s
                                                       │
     142          7          3                         │      12                 1 vencido
    inbox     não lidos     spam                       │    abertos no meu nome  ·  37 no total
                                                       │
  ▎Fulano de Tal <fulano@cm.sp.gov.br>         08:11   │    Em atendimento 7  ·  Aguardando cliente 4  ·  Pausado 1
   Erro ao gerar relatório de empenhos                 │
   Bom dia, ao tentar gerar o relatório de empenhos…   │    SLA ▸ #4802 Certificado digital do pref…  ▮▮▮▮  vencido 1h05
                                                       │
   07:33  Maria Souza        RE: Acesso ao portal da…  │    #4802  Certificado digital do prefeito ve…   vencido 1h05
   07:02  Suporte Milldesk   [#4831] Novo chamado at…  │    #4821  Backup noturno não executa desde s…   1h41
   05:14  Hércules Andrade   Certificado digital ven…  │   ▎#4833  Novo: sistema de protocolo fora do…   3h59
   03:14  Diego Leone        Porta 21 continua fecha…  │    #4831  Impressora fiscal não imprime cupom   5h59
   ontem  Contabilidade      Fechamento do mês: rela…  │    #4744  Câmera do plenário sem imagem         23h59
                                                       │    +7 · F3

  ◉ CHATPANEL   3 conversas · 1 não lida                                                       15s · há 2s

  ▎● 08:09  Diego Leone · PM Iaras       Prefeitura › Suporte   Porta 21 continua fechada, consegue ver…   1
   ○ 08:07  Hércules · CM Tatuí TI       Câmara › Suporte       Fabio: Hércules, consegue me mandar o pr…
   ○ 07:14  Ana Paula · CM Itu           Câmara › Suporte       Obrigada! Funcionou.

   4 com outros técnicos · 6 não lidas na aba

 ↑↓ mover  ⏎ abrir  ⇥ painel  / filtrar  o navegador  y copiar  e último e-mail  m silêncio  : launcher  ? ajuda
```

Notas:

- O cartão do e-mail mais recente (3 linhas: remetente + hora, assunto `bold`, prévia
  `text-muted`) substitui a primeira linha da lista; a lista continua abaixo com os
  seguintes. `▎` no cartão = chegou neste ciclo.
- No Milldesk, `1 vencido` é `danger` só quando > 0; `SLA ▸` é a única linha com barra
  (`▮▮▮▯`, cor `ok/warn/danger` na barra e no tempo). Tempo relativo curto (`1h41`),
  data em `text-muted` só na tela cheia.
- `+7 · F3` em `text-faint` diz que há mais e como ver.
- ChatPanel: `Tag › Depto` colapsados em `text-muted`; nome de quem enviou (`Fabio:`) em
  `text-faint`; não lidas = número em `accent` à direita, sem badge; `●/○` em
  `text-muted` (não verde).
- Cursor: linha com fundo `accent-soft` + `▍` em `accent` na primeira coluna (no mockup,
  a primeira linha de cada painel).

### 5.2 Dashboard em 90×30 (painéis empilhados, `Digits` viram texto)

```
▍CMD ALL-IN-ONE  Dashboard                ● ● ●                  Guilherme  08:14:20

  ▍✉ E-MAIL   142 inbox · 7 não lidos · 3 spam                          30s · há 6s
  ▎Fulano de Tal                                                            08:11
   Erro ao gerar relatório de empenhos
   07:33  Maria Souza        RE: Acesso ao portal da transparência
   07:02  Suporte Milldesk   [#4831] Novo chamado atribuído a você
   05:14  Hércules Andrade   Certificado digital vencendo

  ▣ MILLDESK   12 abertos · 1 vencido                                   60s · há 27s
   SLA ▸ #4802 Certificado digital do prefeito ve…   ▮▮▮▮  vencido 1h05
   #4802  Certificado digital do prefeito vencendo             vencido 1h05
   #4821  Backup noturno não executa desde sexta               1h41
  ▎#4833  Novo: sistema de protocolo fora do ar                3h59
   #4831  Impressora fiscal não imprime cupom                  5h59
   +8 · F3

  ◉ CHATPANEL   3 conversas · 1 não lida                                15s · há 2s
  ▎● 08:09  Diego Leone · PM Iaras     Porta 21 continua fechada, consegue…   1
   ○ 08:07  Hércules · CM Tatuí TI     Fabio: Hércules, consegue me mandar…
   ○ 07:14  Ana Paula · CM Itu         Obrigada! Funcionou.
   4 com outros técnicos · 6 não lidas na aba

 ↑↓ mover  ⏎ abrir  ⇥ painel  / filtrar  o navegador  : launcher  ? ajuda
```

Abaixo de 25 linhas: some o cartão do e-mail e a lista do Milldesk; ficam contadores e
`SLA ▸`.

### 5.3 TopBar — estados

```
▍CMD ALL-IN-ONE  Dashboard                     ● ● ●                            Guilherme  08:14:20
▍CMD ALL-IN-ONE  Milldesk                      ● ⠹ ○                            Guilherme  08:14:20
▍CMD ALL-IN-ONE  Dashboard                     ● ! ✗                  mudo 27m   Guilherme  08:14:20
▍CMD ALL-IN-ONE  Dashboard                     ● ● ●                  ⟳ login    Guilherme  08:14:20
```

- Linha 1: tudo ok. Linha 2: Milldesk coletando (spinner braille no lugar do ponto),
  ChatPanel não configurado (`○` em `text-faint`).
- Linha 3: Milldesk em cooldown 429 (`!` em `warn`), ChatPanel com sessão expirada (`✗`
  em `danger`), silêncio ligado com tempo restante (`warn`).
- Linha 4: janela de login do ChatPanel aberta.
- Tooltip em cada ponto: `Milldesk · ok · há 27s · próxima em 33s` / motivo do erro.

### 5.4 Footer — por tela

```
Dashboard  ↑↓ mover  ⏎ abrir  ⇥ painel  / filtrar  o navegador  y copiar  e e-mail  m silêncio  : launcher  ? ajuda
E-mail     ↑↓ mover  ⏎ abrir  u só não lidos  / filtrar  o navegador  y copiar remetente  : launcher  ? ajuda
Milldesk   ↑↓ mover  ⏎ abrir  s ordenar: SLA  / filtrar  o navegador  y copiar ID  2 atualizar  : launcher  ? ajuda
ChatPanel  ↑↓ mover  ⏎ abrir  t com outros  / filtrar  o navegador  y copiar número  c login  : launcher  ? ajuda
Modal      Esc voltar  r recarregar  o navegador  y copiar ID
```

Tecla em `accent`, descrição em `text-muted`, dois espaços entre itens. Em 90 colunas
somem, nesta ordem: `e último e-mail`, `m silêncio`, `y copiar`, `o navegador`.

### 5.5 Estados do painel (corpo, sem borda)

```
coletando (título)      ▣ MILLDESK                                60s · ⠹
erro com dados          ▣ MILLDESK                                60s · há 4 min
                        …lista normal, cores normais…
                        ✗ timeout · há 4 min                       (danger, rodapé do painel)
erro sem dados          ▣ MILLDESK                                60s · –
                                        ✗
                              timeout ao consultar a API
                              2 tenta de novo                     (tecla em accent)
sessão expirada         ◉ CHATPANEL                               15s · –
                                        ✗
                              sessão expirada
                              c abre a janela de login
não configurado         ◉ CHATPANEL                               15s · –
                                        –
                              não configurado · veja .env         (text-faint)
vazio                   ▣ MILLDESK   0 abertos                    60s · há 27s
                                        ✓
                              nenhum chamado no seu nome          (✓ em ok, texto text-faint)
cooldown 429            ▣ MILLDESK   aguardando 2m40              60s · há 4 min   (warn)
filtro ativo            ⌕ backup · 1 de 12                        (acima da lista; Esc limpa)
```

### 5.6 Detalhe do chamado (modal, largura 100)

```
      ╭──────────────────────────────────────────────────────────────────────────────────────────────────╮
      │ #4821  Backup noturno não executa desde sexta                                                    │
      │                                                                                                  │
      │   status      Em atendimento          solicitante  Hércules Andrade                              │
      │   etapa       Atendimento             técnico      Guilherme                                     │
      │   prioridade  Alta · urgência Alta    local        Câmara de Tatuí                               │
      │   categoria   Servidores / Backup     abertura     16/09 05:14 · há 3h                           │
      │   SLA         16/09 09:56             ▮▮▮▯  1h 41m                                               │
      │                                                                                                  │
      │   O job de backup noturno (Veeam) não roda desde sexta-feira. O log mostra "Unable to           │
      │   connect to repository". O repositório é o NAS da sala do servidor; ping responde, mas o       │
      │   compartilhamento SMB não abre.                                                                 │
      │                                                                                                  │
      │   05:14  Hércules Andrade   Abri o chamado; segue print do erro em anexo.                        │
      │   06:14  Guilherme          Verificando credenciais do serviço no NAS. Retorno até as 16h.       │
      │   07:49  Hércules Andrade   Ok, aguardo.                                                         │
      ╰──────────────────────────────────────────────────────────────────────────────────────────────────╯
 Esc voltar  r recarregar  o navegador  y copiar ID
```

Borda `round accent`; rótulos em `text-faint`; a barra de SLA é o único ponto de cor.
Enquanto carrega: cabeçalho já preenchido com o que a lista sabe (ID, assunto, status,
SLA) e `LoadingIndicator` no lugar do corpo.

---

## 6. Design tokens

Arquivo único `app/tui/tokens.py` (dataclass `Tokens` + `contrast()` pura + validação)
e `styles.tcss` usando **somente** `$token`. Implementação no Textual: cada tema vira
um `textual.theme.Theme` cujo `primary`/`accent` = `accent`, `success/warning/error` =
`ok/warn/danger`, `foreground/background/surface/panel` = `text/bg/surface/surface-raised`,
e `Theme.variables` injeta os tokens que o Textual não tem (`text-faint`,
`accent-soft`, `mine`, `other`, `surface-raised`) e **sobrescreve** os que coincidem
(`text`, `text-muted`, `border`, `surface`, `accent`), para que os widgets nativos
(Input, DataTable, OptionList, Tooltip) obedeçam à mesma paleta.

| Token | Uso | `carbon` |
|---|---|---|
| `bg` | fundo da app | `#0e0f11` |
| `surface` | TopBar, Footer, fundo de painel | `#15171a` |
| `surface-raised` | linha selecionada, modais, inputs | `#1e2126` |
| `border` | borda em repouso e `Rule` (sempre `dim`) | `#2a2e35` |
| `text` | texto principal | `#d6d9de` |
| `text-muted` | secundário: horas, rótulos, descrições | `#8b929c` |
| `text-faint` | terciário: separadores, placeholders, "há 3 min" | `#5e6570` |
| `accent` | foco, seleção, teclas, mudança recente, marcador da TopBar | `#4fc1e9` (ciano-frio) |
| `accent-soft` | fundo da linha selecionada | `accent 15%` |
| `ok` / `warn` / `danger` | estado semântico | `#5cc46c` / `#e0a83a` / `#e5533f` |
| `mine` | itens no meu nome | = `accent` |
| `other` | itens de outros técnicos | = `text-muted` |

Escalas: espaçamento `0 1 2`; tipografia `bold` / normal / `dim` (`italic` só em citação
de mensagem; conhost ignora); bordas `round` na cor `border`, focado `round accent`
(mesma espessura) quando houver borda. Destaque de mudança: célula em `accent` +
`▎`, 3 s, sem tocar na borda.

### 6.1 Ícones (`app/tui/icons.py`, `ICONS=nerd|unicode|ascii`, autodetecção + override)

| Conceito | nerd | unicode | ascii | largura verificada |
|---|---|---|---|---|
| e-mail | `U+F0E0` | `✉` | `@` | 1 |
| chamado | `U+F3FF` | `▣` | `#` | 1 |
| conversa | `U+F075` | `◉` | `*` | 1 |
| online / offline | `U+F111` / `U+F10C` | `●` / `○` | `o` / `.` | 1 |
| mudança | `▎` | `▎` | `>` | 1 |
| foco / marcador | `▍` | `▍` | `|` | 1 |
| coletando | `⠋⠙⠹⠸⠼⠴⠦⠧` | idem | `|/-\` | 1 |
| erro / aviso / ok | `✗` `!` `✓` | idem | `x` `!` `+` | 1 |
| filtro / SLA / mais | `⌕` `▸` `…` | idem | `?` `>` `...` | 1 |
| barra de SLA | `▮▯` | idem | `#-` | 1 |
| não lida | número, nunca ícone | | | |

Teste automatizado (7.1) percorre `icons.py` e falha em qualquer glifo com `cell_len`
≠ 1. Autodetecção Nerd Font: `ICONS` no `.env` > `WT_SESSION` + fonte configurada não
detectável pelo app → padrão `unicode`; `nerd` só por opt-in (sem como detectar a
fonte do terminal com segurança).

### 6.2 Contraste (WCAG, calculado)

| Tema | text/bg (≥ 4.5) | text-muted/bg (≥ 3) | text-faint/bg | accent/bg | ok · warn · danger /bg |
|---|---|---|---|---|---|
| `carbon` | 13.6 | 6.1 | 3.3 | 9.3 | 8.7 · 9.0 · 5.2 |
| `phosphor` | 13.8 | 7.3 | 3.9 | 14.9 | 10.8 · 14.6 · 6.6 |
| `amber` | 12.1 | 6.2 | 3.4 | 13.3 | 10.0 · 15.3 · 6.6 |
| `paper` | 12.5 | 5.4 | 2.9 | 9.1 | 4.6 · 4.4 · 5.1 |

Todos passam os mínimos da spec; `text-faint` não tem mínimo (é decorativo por
definição) mas fica ≥ 2.9 em todos.

---

## 7. Temas

| Nome | Ideia | Paleta proposta (bg · text · accent) |
|---|---|---|
| `carbon` (padrão) | quase-preto, texto cinza-claro, um ciano frio; o "silêncio por padrão" | `#0e0f11` · `#d6d9de` · `#4fc1e9` |
| `phosphor` | monocromático verde CRT; `danger` é o único vermelho | `#050a06` · `#9fe8a2` · `#33ff66` |
| `amber` | mesmo conceito em âmbar | `#0b0803` · `#ffbd5c` · `#ffcc33` |
| `paper` | claro: off-white, grafite, azul-marinho | `#f6f3ec` · `#2b2d30` · `#1f3a93` |
| `terminal` | `ansi_color=True`: herda as 16 cores do Windows Terminal (`accent` = `ansi_cyan`, `ok/warn/danger` = `ansi_green/yellow/red`, `text-muted` = `ansi_bright_black`) — base: tema `ansi-dark` do Textual | — |
| `nord` `gruvbox` `catppuccin-mocha` `dracula` `tokyo-night` `monokai` `flexoki` | temas embutidos do Textual mapeados para os tokens: `accent` = `primary` do tema (o `accent` deles costuma ser magenta/laranja e viraria segunda cor), `text-muted` = `foreground 65%`, `text-faint` = `foreground 45%`, `surface-raised` = `panel` | — |
| `themes/*.json` | temas do usuário com os tokens da seção 6 (gitignored; `themes/exemplo.json` committado); parse inválido ou contraste ruim = aviso no log | — |

Seleção: `THEME` no `.env` → `prefs.json` (prioridade) → tecla `T` cicla com preview →
launcher `theme`, `theme nome`, `theme next`, `theme preview` (F9), `theme export wt`.

---

## 8. Riscos e limites conhecidos

- **`DataTable` não anima**: o fade de 3 s da célula continua sendo timer + `update_cell`
  (uma célula, não a tabela). `animate` só para o `▎` da TopBar/cartão.
- **Nerd Font não é detectável** pelo app; `ICONS=nerd` é opt-in documentado.
- **`dim` no conhost** é ignorado: `text-faint` cai para `text-muted` quando
  `ansi_color` está ativo ou `TERM_PROGRAM` não é o Windows Terminal (heurística; a 7.4
  mede em screenshot nos dois).
- **Sobrescrever `$text`, `$surface`, `$accent`** via `Theme.variables` muda widgets
  nativos (Input, OptionList, Tooltip, notificações): é o objetivo, mas a 7.1 precisa
  conferir um por um.
- **Breakpoints** ficam na `Screen` (`HORIZONTAL_BREAKPOINTS = [(0,"-narrow"),(100,"-wide")]`,
  `VERTICAL_BREAKPOINTS = [(0,"-short"),(25,"-tall"),(30,"-digits")]`); `BasePanel` ainda
  precisa saber se está estreito para escolher `COLUMNS_*` — lê a classe da tela em vez
  do `if` atual.

---

## 9. Perguntas para o usuário (respostas necessárias antes da 7.1)

1. **`accent` do `carbon`**: recomendo **ciano-frio `#4fc1e9`** (contraste 9.3, não
   colide com `ok/warn/danger`). Alternativas com contraste ok: âmbar `#e0a83a`,
   verde `#5cc46c`, roxo `#b48ead` (7.4).
2. **Nerd Font**: usa hoje no Windows Terminal? Qual fonte e tamanho? (Define o
   padrão de `ICONS` e a fonte sugerida em `docs/design/windows-terminal/`.)
3. **Painel focado**: recomendo **título em `accent` + `▍`, sem borda** (seção 4,
   decisão 2). A 7.2 mostra os dois em screenshot se quiser decidir depois.
4. **Tamanho do terminal em tela cheia** (colunas × linhas)? Define os snapshots-alvo
   e o limiar de 30 linhas para `Digits`.
5. **Bell**: manter, ou confiar só em destaque visual + toast?
6. **Referências visuais** que goste (screenshot de outra TUI)?

Decisões adicionais desta fase que dependem de aprovação: tirar `F1…F8` do Footer
(decisão 7), tirar `Histórico` do Dashboard (decisão 4), tirar os rodapés de texto das
modais (decisão 9).

---

## 10. Índice das capturas "antes"

Cada nome existe em `_120x35` e `_90x30` (`.svg` e `.txt`):

| Captura | O que mostra |
|---|---|
| `dashboard` | repouso com dados |
| `dashboard_mudanca` | chamado novo: borda `heavy` amarela + `●` na linha |
| `dashboard_erros` | e-mail com timeout (primeira coleta) e ChatPanel com sessão expirada |
| `dashboard_inicio` | ChatPanel não configurado |
| `dashboard_silencio` | `🔇` na TopBar |
| `dashboard_notify` | dois toasts do `notify` |
| `email` `milldesk` `chatpanel` | telas cheias F2–F4 |
| `milldesk_filtro` | filtro `/` com `bac` |
| `log` `notes` `events` `health` | F5–F8 |
| `detalhe_email` `detalhe_chamado` `detalhe_conversa` | modais |
| `launcher` `ajuda` | `:` com `md 48` digitado; `?` |
| `dashboard_120x22` `dashboard_80x24` | terminal baixo e terminal estreito e baixo |
