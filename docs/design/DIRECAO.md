# Guia de estilo — CMD ALL-IN-ONE (Ciclo 3)

> Este documento nasceu como a direção de design da Fase 7.0 (diagnóstico + mockups) e,
> com o ciclo concluído, virou o **guia de estilo** do projeto: tokens, regras, anatomia
> das telas e estados. Toda feature nova nasce dentro desta linguagem.
>
> Capturas: `docs/design/antes/` (estado anterior ao ciclo) e `docs/design/depois/`
> (atual), em SVG com cores e `.txt` em texto puro, nos tamanhos 120×35, 90×30, 200×50
> (tela cheia), 120×22 e 80×24. Regerar com `python scripts/design_screenshots.py`.
> Regressão visual: `python -m pytest tests/test_snapshots.py` (atualizar só com
> mudança intencional: `--snapshot-update`, e dizer por quê no commit).

---

## 1. Princípios

1. **Hierarquia por tipografia e espaço, não por caixas.** Painéis não têm borda; a
   separação é espaço e um `Rule` vertical em `border`. Só as modais têm borda
   (`round accent`).
2. **Uma cor de destaque.** `accent` marca foco (título do painel + `▍`), seleção
   (fundo `accent-soft` + `▍`), teclas de atalho, o contador que subiu e a linha que
   chegou (`▎`). Nada mais é colorido "para ficar bonito".
3. **Cor semântica limitada:** `ok` / `warn` / `danger` só para estado (SLA, sessão,
   erro, saúde); nunca para categoria (tipo de evento, tag, lado da conversa).
4. **Números são a interface.** Contadores grandes (`Digits`) no Dashboard, rótulo
   pequeno embaixo; o resto é contexto em `text-muted`.
5. **Silêncio por padrão.** Em repouso a tela é quase monocromática; a cor aparece
   quando algo acontece e some sozinha em 3 s.
6. **Sem emoji.** Ícones vêm de `app/tui/icons.py` (`nerd` / `unicode` / `ascii`) e
   nenhum glifo ocupa 2 células (teste automatizado).
7. **Truncar com `…` no fim**; colunas com largura fixa para hora e contadores e
   flexível para assunto/contato.
8. **Tempo relativo nas listas e títulos** (`há 6s`, `há 3 min`, `ontem`); absoluto nos
   detalhes; contagem regressiva no SLA.
9. **Todo estado tem um desenho** (seção 6).
10. **Tokens, não cores.** Nenhum `.tcss` ou widget usa cor literal; só `themes.py`
    tem `#rrggbb` (teste faz grep em `app/tui/**`).

---

## 2. Tokens (`app/tui/tokens.py`)

| Token | Uso | `carbon` |
|---|---|---|
| `bg` | fundo da app | `#0e0f11` |
| `surface` | TopBar, Footer, fundo de campo | `#15171a` |
| `surface-raised` | linha selecionada sem foco, modais, cursor apagado | `#1e2126` |
| `border` | `Rule`, borda de campo, separadores | `#2a2e35` |
| `text` | texto principal | `#d6d9de` |
| `text-muted` | rótulos, horas, status, "Tag › Depto" | `#8b929c` |
| `text-faint` | "há 6s", `+7 · F3`, placeholders, marcos | `#5e6570` |
| `accent` | foco, seleção, teclas, mudança recente, marcador da TopBar | `#4fc1e9` |
| `accent-soft` | fundo da linha selecionada | `accent 15%` |
| `ok` / `warn` / `danger` | estado semântico | `#5cc46c` / `#e0a83a` / `#e5533f` |
| `mine` | itens no meu nome (padrão = `accent`) | |
| `other` | itens de outros técnicos (padrão = `text-muted`) | |

- No CSS: `$bg`, `$text-muted`, `$accent-soft`... `Tokens.css_variables()` também
  preenche as variáveis nativas do Textual (`$primary`, `$panel`, `$block-cursor-*`,
  `$input-*`, `$scrollbar*`, `$footer-*`) para que Input, DataTable, OptionList,
  Tooltip e Toast sigam a paleta.
- Em Python: `self.app.tokens.rich("danger", bold=True)` (ou `self.style(...)` nos
  painéis). Funções puras recebem `tokens=`/`icons=` com padrão `CARBON`/`UNICODE` e
  devolvem **nomes de token** (`sla_token(...) -> "warn"`), nunca cores.
- Contraste (WCAG): `text`/`bg` ≥ 4.5, `text-muted`/`bg` ≥ 3, `accent`/`ok`/`warn`/
  `danger` ≥ 3 — testado para todos os temas embutidos; temas do Textual passam por
  `ensure_contrast()`; temas do usuário só geram aviso no log.
- Escalas: espaçamento `0 1 2`; tipografia `bold` / normal / `dim` (`italic` só em
  mídia de mensagem). Em conhost (sem `dim`), `text-faint` = `text-muted`.

### 2.1 Temas (`app/tui/themes.py`)

| Nome | Ideia |
|---|---|
| `carbon` (padrão) | quase-preto, cinza-claro, ciano-frio |
| `phosphor` | monocromático verde CRT; `danger` é o único vermelho |
| `amber` | o mesmo em âmbar |
| `paper` | claro: off-white, grafite, azul-marinho |
| `terminal` | `ansi=True`: as 16 cores do esquema do próprio terminal |
| `nord` `gruvbox` `catppuccin-mocha` `dracula` `tokyo-night` `monokai` `flexoki` | temas do Textual mapeados (`accent` = `primary` do tema, legibilizado) |
| `themes/*.json` | temas do usuário (`themes/exemplo.json` é o modelo) |

Seleção: `THEME` no `.env` → `prefs.json` (prioridade) → `T` / `theme nome` /
`F9`. A troca não recria widgets: o App troca o tema do Textual (variáveis CSS) e pede
aos painéis e telas que re-rendam os textos Rich (`refresh_theme()`); o cursor das
listas não se move.

### 2.2 Ícones (`app/tui/icons.py`)

| Conceito | nerd | unicode | ascii |
|---|---|---|---|
| e-mail / chamado / conversa | `` `` `` | `✉` `▣` `◉` | `@` `#` `*` |
| online / offline | `` `` | `●` `○` | `o` `.` |
| mudança / foco | `▎` `▍` | `▎` `▍` | `>` `|` |
| erro / aviso / ok / vazio | `✗` `!` `✓` `–` | idem | `x` `!` `+` `-` |
| filtro / SLA / mais / separador / seta | `⌕` `▸` `…` `·` `›` | idem | `?` `>` `...` `.` `>` |
| barra de SLA | `▮` `▯` | idem | `#` `-` |
| silêncio / login | `` `` | `◌` `⟳` | `M` `L` |
| coletando | `⠋⠙⠹⠸⠼⠴⠦⠧` | idem | `|/-\` |
| teclas | `↑↓` `⏎` `⇥` `Esc` | idem | `^v` `Enter` `Tab` `Esc` |

`ICONS=auto`: `unicode` no Windows Terminal e fora do Windows, `ascii` no conhost;
`nerd` é sempre opt-in (o app não detecta a fonte).

---

## 3. Anatomia das telas

```
 ▍CMD ALL-IN-ONE  Dashboard                    ● ● ●                      Guilherme  08:14:20   ← TopBar (1 linha, surface)
                                                                                                 ← corpo com margem lateral 1
 ↑↓ mover  ⏎ abrir  ⇥ painel  / filtrar  o navegador  y copiar  : launcher  ? ajuda            ← FooterBar (1 linha, surface)
```

- **TopBar** (`widgets/top_bar.py`): `▍` em `accent` + nome em bold + tela em
  `text-muted`; ao centro um ponto por fonte (`●` ok, spinner coletando, `○` aguardando /
  não configurada, `!` cooldown em `warn`, `✗` erro/sessão em `danger`) com tooltip do
  motivo; à direita estados transitórios (`◌ 27m` silêncio em `warn`, `⟳ login`), o
  técnico e `HH:MM:SS`. Sem data, sem fundo colorido.
- **FooterBar** (`widgets/footer_bar.py`): só os atalhos da tela atual (`FOOTER` da
  tela ou `footer_items()`), tecla em `accent`, descrição em `text-muted`, dois espaços
  entre itens, uma linha; o que não cabe some da direita para a esquerda e `? ajuda`
  fica sempre. `F1…F8` não ocupam o rodapé (estão em `?`).
- **Painel** (`widgets/base_panel.py`, sem borda):
  1. título: `▍` (só focado) + ícone + NOME (bold; `accent` quando focado) e, à direita,
     `30s · há 6s` em `text-faint` (spinner enquanto coleta; `✗ há N` em `danger` com
     erro; `aguardando 2m40` em `warn` em cooldown);
  2. contadores: `Digits` (altura 3) no Dashboard com ≥ 100 colunas e ≥ 30 linhas, senão
     `142 inbox · 7 não lidos · 3 spam` (valor bold, rótulo `text-muted`, singular /
     plural pelo valor); o ChatPanel põe o resumo na linha do título;
  3. extra: cartão do e-mail (remetente + hora / assunto bold / prévia `text-muted`),
     status + linha `SLA ▸` do Milldesk;
  4. filtro `⌕ ___` (só quando ativo), lista (`KeyedTable`; cabeçalho de coluna em
     `text-faint` maiúsculas nas telas cheias), ou o desenho do estado;
  5. rodapé: `+N · F3` / `✗ erro · há 2 min` / `⌕ texto · 3 de 12` / `4 com outros técnicos`.
- **Dashboard**: E-mail | `Rule` | Milldesk em cima (3 partes de altura), ChatPanel
  embaixo (2 partes). Breakpoints na tela: `-narrow`/`-wide` (100 colunas),
  `-short`/`-mid`/`-tall` (25 e 30 linhas). Estreito empilha; baixo esconde cartão e
  lista dos painéis de cima; alto liga os `Digits`.
- **Listas cheias (F2–F4)**: o mesmo painel com `full=True`: mais colunas, cabeçalho,
  sem Digits, sem cartão.
- **Modais** (`screens/detail.py`): centradas, largura 100, altura 92%, `round accent`,
  cabeçalho com grade rótulo (`text-faint`) / valor (`text`), corpo rolável com margem 2,
  `LoadingIndicator` enquanto o worker busca, FooterBar própria. Fundo atrás em `bg 90%`.
  Conversa: contato à esquerda em `text`, empresa à direita em `accent`, marcos centrados
  em `text-faint`.
- **Launcher (`:`)**: uma linha na base acima do rodapé, prompt `:` em `accent`, até 5
  sugestões em `text` + `text-muted` acima, histórico com `↑↓`.
- **Ajuda (`?`)**: duas colunas (tecla `accent` / ação `text`) por grupo — Telas, Geral,
  Listas, Detalhes — e os comandos do launcher.
- **Eventos (F7)**: `HH:MM` só quando muda o minuto, ícone da fonte, texto.
- **Saúde (F8)**: uma linha por fonte com ponto de status e `Sparkline` da latência dos
  últimos 30 ciclos (derivada em memória, sem chamada nova).
- **Notas (F6)**: `TextArea` sem borda e status `notes.md · salvo há 10s · 42 linhas`.
- **Temas (F9)**: lista (↑↓ aplica ao vivo, ⏎ confirma, Esc volta), tokens com amostra
  e contraste, painel de exemplo com todos os estados.
- **Notificações**: canto inferior direito, fundo `surface-raised`, borda esquerda na cor
  semântica, 4 s, nunca mais de 3.

---

## 4. Micro-interações

| Evento | Desenho |
|---|---|
| Coletando | spinner braille no lugar de "há Ns" no título; nada mais muda |
| Contador subiu | número em `accent` por 3 s; bell/toast como sempre (`m` silencia) |
| Contador desceu | nada (só o F7 registra) |
| Item novo | `▎` em `accent` no início da linha por 3 s; o cursor não se move |
| Seleção | fundo `accent-soft` + `▍` na primeira célula (só essa célula é atualizada) |
| SLA < 30 min | o tempo alterna `danger`/`text` a cada 1 s (`SLA_BLINK=false` ou `TEXTUAL_ANIMATIONS=none` desligam); nada mais pisca |
| Troca de tema | variáveis CSS + re-render dos textos; nenhum widget recriado; cursor preservado |

Animação: só o spinner e o piscar do SLA. Fades de cor em células de `DataTable` não
são possíveis (células não são widgets); o "fade" é a troca de estilo após 3 s.

---

## 5. Estados

| Estado | Desenho |
|---|---|
| Primeira coleta | `aguardando a primeira coleta…` em `text-faint` no lugar dos contadores |
| Erro sem dados | `✗` centrado em `danger`, mensagem em `text-muted`, tecla em `accent` (`1`/`2`/`3` tenta de novo; `c abre a janela de login` se a sessão expirou) |
| Erro com dados antigos | lista com cor normal; `✗ mensagem · há 2 min` no rodapé; `✗ há N` no título; detalhe só no log |
| Cooldown 429 | `aguardando 2m40` em `warn` no título; ponto da TopBar em `warn` |
| Sessão expirada | erro sem dados + ponto em `danger` na TopBar |
| Não configurado | `–` e `não configurado · CHATPANEL_URL vazio no .env` em `text-faint`, centrados; nunca âmbar |
| Vazio | `✓ nenhum chamado no seu nome` centrado (✓ em `ok`) |
| Filtro sem resultado | `⌕ nada encontrado`; rodapé `⌕ texto · 0 de 12` |
| Silêncio | `◌ 27m` em `warn` na TopBar; o destaque visual continua |
| Terminal estreito / baixo | breakpoints (seção 3) |
| conhost | `ICONS=ascii`, `text-faint` = `text-muted`; tema `terminal` para as 16 cores |

---

## 6. Como manter a linguagem numa feature nova

1. Cor: escolha um **token** (`self.style("text-muted")`, `$accent` no CSS). Se a
   feature "precisa" de uma cor nova, ela não precisa: é `accent` (destaque), uma cor
   semântica (estado) ou cinza (contexto).
2. Ícone: acrescente ao `IconSet` nos **três** conjuntos e rode `tests/test_design.py`
   (largura 1 obrigatória).
3. Tempo: `app.clock.now()`/`epoch()` (congelável), `relative_age()` nas listas.
4. Estado: se a feature pode falhar, estar vazia ou não configurada, desenhe os três
   casos com `_placeholder()` / `set_error()` / `set_not_configured()`.
5. Atalho: entra no `FOOTER` da tela (formato `{key_enter}`), na ajuda (`HelpScreen.GROUPS`)
   e no README.
6. Snapshot: `python -m pytest tests/test_snapshots.py --snapshot-update` só com a
   mudança visual explicada no commit; capturas com `scripts/design_screenshots.py`.

---

## 7. Antes → depois (resumo do que mudou no ciclo)

| Antes (`docs/design/antes/`) | Depois (`docs/design/depois/`) |
|---|---|
| 3 painéis com borda `round` (+ `heavy` amarela na mudança); em 90×30 o ChatPanel tinha 1 linha; em 80×24 sumia com o Footer | painéis sem borda, `Rule` vertical, altura 3:2, breakpoints; ChatPanel com ~8 linhas em 90×30 |
| `Inbox: 142   Não lidos: 7` em texto; cabeçalho do Milldesk com 3 linhas truncadas | `Digits` com rótulo; `SLA ▸ #4802 … ▮▮▮▮ vencido há 1h05`; `+7 · F3` |
| `cyan`/`green`/`yellow` em repouso; 86 estilos literais | uma cor de destaque; 0 estilos literais fora de `themes.py` (teste) |
| emoji `📧 🎫 💬 🔇` (largura 2) | `✉ ▣ ◉ ◌` (largura 1), com nerd/ascii |
| Footer do Textual com `q f1…f8 r e : ?` estourando 120 colunas | rodapé próprio com os atalhos da tela |
| TopBar azul com data completa e sem saúde | TopBar em `surface` com três pontos de saúde e tooltips |
| erro = texto vermelho no painel; não configurado = âmbar | estados desenhados e centrados; não configurado neutro |
| modais 92% com o Dashboard vazando | modais centradas, largura 100, grade rótulo/valor, indicador de carga |
| um tema, cores fixas | 12 temas + temas do usuário, `T`, `F9`, `theme export wt` |

Bugs corrigidos no caminho: crash ao redimensionar o terminal com dados carregados
(`KeyedTable.rebuild_columns`); `[f]` engolido pelo markup na tela Log; `.p/session.bin`
versionado por engano.

---

## 8. Verificação do Textual (8.2.8) — referência

| Item | Situação |
|---|---|
| `Theme`, `register_theme`, `theme`, `available_themes`, `theme_changed_signal` (instância) | usados |
| `App.ansi_color` / temas `ansi-*` | tema `terminal` |
| `get_theme_variable_defaults()` + `Theme.variables` | tokens injetados como variáveis CSS (os do `carbon` são o padrão para validar o CSS) |
| `Digits`, `Sparkline`, `Rule`, `LoadingIndicator`, `OptionList`, `Tooltip` | usados |
| `HORIZONTAL_BREAKPOINTS` / `VERTICAL_BREAKPOINTS` (na `Screen`) | Dashboard |
| `animation_level` (instância; `TEXTUAL_ANIMATIONS`) | desliga o piscar do SLA |
| `pytest-textual-snapshot` 1.1 | 12 snapshots em `tests/__snapshots__/` |
| células de `DataTable` não animam | destaque por timer + `update_cell` |
