# CMD ALL-IN-ONE — Ciclo 3: design, linguagem visual e temas

> **Como usar:** cole este arquivo inteiro como primeiro prompt de uma nova sessão do
> Claude Code, na raiz do projeto, e diga: *"Leia `CLAUDE.md`, o README e este arquivo.
> Execute a Fase 7.0 (auditoria visual) e pare para eu aprovar a direção de design."*
>
> Complementa `PROMPT_CMD_ALL_IN_ONE.md` (Fases 0–5) e
> `PROMPT_FASE6_NAVEGACAO_E_INTERATIVIDADE.md` (Fase 6, concluída: 8 telas, launcher,
> `KeyedTable`, detalhes de e-mail/chamado/conversa, eventos, saúde). Todas as regras do
> `CLAUDE.md` continuam valendo. **Este ciclo não adiciona fontes de dados nem chamadas
> de rede novas** — é só apresentação, interação visual e configuração de tema.

---

## 0. Quem você é neste ciclo

Assuma o papel de um **designer de interfaces de terminal** com duas referências
internas: a do artista, que decide o que *não* mostrar e faz a hierarquia nascer de
espaço, alinhamento e uma única cor de destaque; e a do hacker, que vive em `lazygit`,
`btop`, `k9s`, `helix`, `zellij` e `starship`, sabe que cada célula do terminal custa
atenção, que Unicode de largura dupla quebra alinhamento no Windows e que uma TUI bonita
é a que se lê num relance às 17h de uma sexta-feira com quinze chamados abertos.

O produto é um cockpit que o técnico olha o dia inteiro. O critério de sucesso é
**glanceability**: em menos de um segundo, sem ler nada, ele sabe se tem algo novo, o
que é urgente e onde está. Tudo o que não serve a isso é ruído e deve ser reduzido,
apagado (`dim`) ou removido.

---

## 1. Princípios de design (não negociáveis neste ciclo)

1. **Hierarquia por tipografia e espaço, não por caixas.** Menos bordas, mais
   alinhamento. Borda só onde delimita um painel focável; separadores internos com
   `Rule`/linha `dim` ou simplesmente uma linha em branco.
2. **Uma cor de destaque.** Cada tema tem um único `accent`. Ele marca: foco, item
   selecionado, número que mudou, tecla de atalho. Nada mais é colorido "para ficar
   bonito".
3. **Cor semântica limitada e consistente:** `ok` (verde), `warn` (âmbar), `danger`
   (vermelho), `muted` (cinza). Verde/âmbar/vermelho **só** para estado (SLA, sessão,
   erro), nunca para decoração ou categorias.
4. **Números são a interface.** Contadores grandes e alinhados à direita; o resto é
   contexto em texto secundário. O que subiu desde o último ciclo é a informação mais
   importante da tela.
5. **Silêncio por padrão.** A tela em repouso é quase monocromática. A cor aparece quando
   algo acontece e desaparece sozinha (3 s de destaque, depois volta ao repouso).
6. **Sem emoji nos títulos e em células de tabela.** Emoji tem largura inconsistente no
   Windows Terminal/conhost e desalinha colunas. Usar ícones Nerd Font **com fallback**
   Unicode simples e ASCII (`ICONS=nerd|unicode|ascii`, autodetecção com override).
7. **Truncar com elegância.** `…` sempre no fim (ou no meio para e-mails/números
   longos), nunca cortar palavra no meio sem indicador; colunas com largura mínima
   garantida para o que importa (assunto, contato) e largura fixa para hora/contadores.
8. **Tempo relativo onde ajuda, absoluto onde importa.** Listas mostram `há 3 min`;
   detalhes mostram `15/09 15:28`; SLA mostra contagem regressiva `1h 42m`.
9. **Todo estado tem um desenho:** carregando, vazio, não configurado, erro com dados
   antigos, erro sem dados, sessão expirada, silenciado, terminal estreito. Nenhum
   deles pode ser "texto vermelho jogado no painel".
10. **Tokens, não cores.** Nenhum `.tcss` ou widget usa cor literal (`#ff0000`,
    `yellow`). Só variáveis semânticas (seção 4). Trocar de tema não pode exigir tocar
    em widget.

---

## 2. Fase 7.0 — Auditoria visual e direção (obrigatória, parar para aprovação)

1. Gere **screenshots SVG** de cada tela no estado atual usando o próprio Textual
   (`App.save_screenshot()` num teste, ou `textual run --screenshot`), com dados de
   fixture, em dois tamanhos: 120×35 e 90×30. Salve em `docs/design/antes/`.
   Se o headless não for viável para alguma tela, descreva o layout em ASCII.
2. Inventário do que existe hoje: `styles.tcss` completo, cores literais usadas,
   bordas, uso de emoji, larguras de coluna, como o `TopBar`/`Footer` são compostos,
   como `BasePanel` e `KeyedTable` renderizam células, onde o destaque de mudança
   (borda amarela grossa) é aplicado.
3. Verifique na versão instalada do Textual (não assumir):
   - `textual.theme.Theme`, `App.register_theme`, `App.theme`, `App.available_themes`,
     temas embutidos (`nord`, `gruvbox`, `catppuccin-mocha`, `dracula`, `tokyo-night`,
     `monokai`, `flexoki`, `solarized-light`, `catppuccin-latte`, `textual-dark`,
     `textual-light`) e o sinal `theme_changed_signal`;
   - `App.ansi_color` (usar a paleta do próprio terminal);
   - widgets `Digits`, `Sparkline`, `ProgressBar`, `Rule`, `LoadingIndicator`, `Label`,
     `Static` com `border_title`/`border_subtitle`, `Tooltip`;
   - variáveis de CSS disponíveis (`$primary`, `$accent`, `$surface`, `$panel`,
     `$background`, `$foreground`, `$success`, `$warning`, `$error`, `$boost`,
     variações `-lighten-1`, `-darken-2`, `-muted`, `$text`, `$text-muted`,
     `$text-disabled`) e `App.get_css_variables()` para injetar tokens próprios;
   - `HORIZONTAL_BREAKPOINTS`/`VERTICAL_BREAKPOINTS` para layout responsivo por classe;
   - estilos de borda (`round`, `solid`, `heavy`, `tall`, `panel`, `vkey`, `none`) e
     `border-title-align`, `border-subtitle-align`;
   - `App.animation_level` e `Widget.styles.animate` para o fade do destaque;
   - `pytest-textual-snapshot` (puro Python) para testes de regressão visual.
4. Escreva `docs/design/DIRECAO.md` com: diagnóstico (o que atrapalha a leitura hoje),
   a direção proposta (mood, 3 adjetivos, referências), o **mockup ASCII do Dashboard
   e do TopBar** em 120 colunas (seção 5 é o ponto de partida; ajuste ao que existe),
   os tokens (seção 4) e a lista de temas (seção 6). **Pare e aguarde aprovação.**

---

## 3. Anatomia da tela (todas as telas)

```
┌ linha 1 ─ TOP BAR (1 linha, sem borda) ──────────────────────────────────────┐
│ ▍CMD ALL-IN-ONE  ·  Dashboard            ● ● ●     Guilherme   15:31:07  🔇  │
└──────────────────────────────────────────────────────────────────────────────┘
│                                                                              │
│                        CORPO DA TELA (painéis / lista / detalhe)             │
│                                                                              │
┌ última linha ─ FOOTER (1 linha, sem borda) ──────────────────────────────────┐
│ ↑↓ mover  ⏎ abrir  / filtrar  o navegador  y copiar  : launcher  ? ajuda    │
└──────────────────────────────────────────────────────────────────────────────┘
```

**TopBar** (substitui o `Header` padrão): à esquerda um marcador vertical na cor
`accent` + nome do app em `bold` + nome da tela em `muted`; ao centro **três pontos de
saúde** (uma por fonte: `ok`/`warn`/`danger`/`muted` = ok/atrasada/erro/não configurada),
com tooltip do motivo; à direita o técnico, o relógio e os ícones de estado transitório
(silêncio, coletando `⟳`, sessão do ChatPanel). Uma linha, sem borda, fundo `surface`.

**Footer**: só os atalhos da tela atual, tecla em `accent` e descrição em `muted`,
separados por dois espaços; nunca mais de uma linha; o que não cabe some (o `?` sempre
cabe). Remover o `Footer` padrão do Textual se ele não permitir esse visual.

**Corpo**: margem lateral de 1 célula; painéis com espaçamento de 1 célula entre si;
sem `padding` vertical interno maior que 1.

---

## 4. Design tokens (arquivo único `app/tui/tokens.py` + `styles.tcss`)

Todo tema mapeia estes tokens; widgets e `.tcss` usam **somente** eles:

| Token | Uso |
|---|---|
| `bg` | fundo da app |
| `surface` | TopBar, Footer, fundo de painel |
| `surface-raised` | linha selecionada, modais, inputs |
| `border` | borda em repouso (sempre `dim`) |
| `text` | texto principal |
| `text-muted` | secundário: horários, rótulos, descrições |
| `text-faint` | terciário: separadores, placeholders, "há 3 min" |
| `accent` | foco, seleção, teclas, mudança recente, marcador da TopBar |
| `accent-soft` | fundo de linha selecionada (accent com ~15% de opacidade ou `-darken`) |
| `ok` / `warn` / `danger` | estado semântico |
| `mine` | itens no meu nome (badge do técnico); por padrão = `accent` |
| `other` | itens de outros técnicos; por padrão = `text-muted` |

Escala de espaçamento: `0`, `1`, `2` células. Escala tipográfica do terminal: `bold`,
normal, `dim`; `italic` só em citações de mensagens (verificar suporte no Windows
Terminal; conhost ignora). Bordas: painéis em repouso `round` na cor `border`; painel
**focado** troca só a cor da borda para `accent` (mesma espessura — nada de "grossa").
Destaque de mudança: a borda **não** muda; a célula/linha que mudou recebe `accent` +
marcador `▎` à esquerda e volta ao repouso com fade de 3 s (`animate` em `opacity` ou
troca de classe com timer se `animate` não servir para cor).

Ícones (`app/tui/icons.py`, com os três conjuntos):

| Conceito | nerd | unicode | ascii |
|---|---|---|---|
| e-mail | `` | `✉` | `@` |
| chamado | `` | `▣` | `#` |
| conversa | `` | `◉` | `*` |
| online | `` | `●` | `o` |
| offline | `` | `○` | `.` |
| não lida | badge numérico, nunca ícone | | |
| mudança | `▎` (fallback `>`) | | |
| carregando | spinner `⠋⠙⠹⠸⠼⠴⠦⠧` (fallback `|/-\`) | | |
| erro / aviso / ok | `✗` `!` `✓` (fallback `x` `!` `+`) | | |

Verificar largura de cada glifo com `rich.cells.cell_len` e nunca usar glifo de largura 2
em coluna de tabela.

---

## 5. Mockup de partida — Dashboard em 120 colunas

```
▍CMD ALL-IN-ONE  Dashboard                          ● ● ●                     Guilherme   15:31:07
                                                                                                   
  ✉ E-MAIL                                     30s · há 5s  │  ▣ MILLDESK                   60s · há 27s
                                                            │
     142        7        3                                  │     12        ▎3 novo hoje
   inbox   não lidos   spam                                 │   abertos no meu nome
                                                            │
  ▎Fulano <fulano@cm.sp.gov.br>                   15:28     │   Em atendimento 7   Aguardando 4   Pausado 1
   Erro ao gerar relatório                                  │
   Bom dia, ao tentar gerar o relatório de…                 │   SLA ▸ #4821 Backup não executa      ▮▮▮▯ 1h 42m
                                                            │
                                                            │   #4831 Impressora fiscal não imprime  há 12 min
                                                            │   #4829 Acesso ao sistema de RH        há 1h
                                                            │   #4821 Backup não executa             há 3h
                                                                                                   
  ◉ CHATPANEL   2 conversas · 1 não lida                                              15s · há 2s
                                                                                                   
  ▎● 15:26  Diego Leone · PM Iaras         Prefeitura › Suporte   Porta 21 continua fechada…     1
   ○ 15:24  Hércules · CM Tatuí TI         Câmara › Suporte       Fabio: Hércules, consegue…
                                                                                                   
   4 com outros técnicos · 6 não lidas na aba                                                      
                                                                                                   
 ↑↓ mover  ⏎ abrir  ⇥ painel  / filtrar  o navegador  : launcher  ? ajuda
```

Notas do mockup:

- Painéis **sem borda** em repouso quando o terminal tem ≥ 100 colunas: a separação é
  feita por um `Rule` vertical `dim` e por espaço. O painel focado ganha uma borda
  `round` na cor `accent` (ou, se preferir, apenas o título em `accent` + marcador
  `▍`). Testar ambos e decidir na 7.2 pelo screenshot.
- Título do painel: ícone + nome em `bold`; à direita, na mesma linha, intervalo e
  "há Ns" em `text-faint`. Enquanto coleta, o "há Ns" vira o spinner.
- Contadores usam o widget `Digits` (altura 3) **apenas** no Dashboard; nas telas cheias
  voltam a ser texto para não gastar linhas.
- No E-mail, o mais recente é um "cartão" de 3 linhas: remetente + hora, assunto em
  `bold`, prévia em `text-muted`. Marcador `▎` se chegou neste ciclo.
- No Milldesk, a linha `SLA ▸` é a única com barra de progresso (`ProgressBar` fina ou
  blocos `▮▯`); cor `ok/warn/danger` só na barra e no tempo.
- No ChatPanel, tag e departamento colapsam em `Tag › Depto` em `text-muted`; a última
  mensagem em `text`; não lidas como número à direita em `accent` (sem badge colorido);
  nome do técnico que enviou (`Fabio:`) em `text-faint`.
- Terminal < 100 colunas: E-mail e Milldesk empilham (já existe) e os `Digits` viram
  texto de uma linha (`142 inbox · 7 não lidos · 3 spam`). Definir via breakpoints em
  classe CSS, não com `if` espalhado.

Aplicar a mesma linguagem às telas cheias (F2–F8) e aos detalhes:

- **Listas cheias**: cabeçalho de coluna em `text-faint` maiúsculas espaçadas, linha
  selecionada com fundo `accent-soft` e marcador `▍` em `accent`; zebra **desligada**;
  linha de filtro (`/`) aparece **acima** da lista como `Input` sem borda, com `⌕ `.
- **Detalhes** (e-mail, chamado, conversa): modal centrada com largura máxima 100,
  borda `round` `accent`, cabeçalho em duas colunas de rótulo `text-faint` / valor
  `text`, corpo com rolagem e margem de 2. Conversa: contato à esquerda em `text`,
  empresa à direita em `accent`, marcos em `text-faint`, hora em `text-faint` ao lado.
- **Eventos (F7)**: linha do tempo com hora em `text-faint`, ícone da fonte, texto;
  a hora só aparece quando muda o minuto (agrupamento visual).
- **Saúde (F8)**: tabela de 3 linhas com ponto de status + latência em `Sparkline` dos
  últimos 30 ciclos por fonte.
- **Launcher (`:`)**: uma linha na base da tela, acima do Footer, com prompt `:` em
  `accent`; sugestões de comando em `text-muted` conforme digita (`OptionList` compacta,
  máximo 5 linhas); histórico com `↑`.
- **Ajuda (`?`)**: duas colunas (tecla `accent` / ação `text`), agrupadas por tela.
- **Notas (F6)**: `TextArea` sem borda, com uma linha de status `text-faint`
  ("salvo há 10s · 42 linhas").
- **Notificações (`notify`)**: canto inferior direito, 1–2 linhas, fundo
  `surface-raised`, borda esquerda na cor semântica; timeout 4 s; nunca empilhar mais de 3.

---

## 6. Temas configuráveis

### 6.1 Modelo

- `app/tui/themes.py` registra temas como `textual.theme.Theme` (se disponível) e
  mapeia cada um para os tokens da seção 4 via `App.get_css_variables()`.
- Temas **embutidos** do projeto (todos com versão escura; `paper` é a clara):

| Nome | Ideia |
|---|---|
| `carbon` (padrão) | quase-preto `#0e0f11`, texto cinza-claro, `accent` ciano-frio; o "silêncio por padrão" da seção 1 |
| `phosphor` | monocromático verde CRT (o tema do hacker): tudo em tons de verde, `danger` é o único vermelho |
| `amber` | mesmo conceito em âmbar |
| `paper` | claro, para ambientes iluminados: fundo off-white, texto grafite, `accent` azul-marinho |
| `terminal` | `App.ansi_color = True`: herda as 16 cores do esquema do Windows Terminal; os tokens viram as cores ANSI (`accent` = ANSI cyan, etc.) |
| Temas do Textual | expor `nord`, `gruvbox`, `catppuccin-mocha`, `dracula`, `tokyo-night`, `monokai`, `flexoki` mapeados para os tokens |

- **Temas do usuário**: `themes/*.json` na raiz (gitignored, com `themes/exemplo.json`
  committado) contendo os tokens; carregados no start; erro de parse vira aviso no log
  e o tema é ignorado.
- **Seleção**: `THEME=carbon` no `.env` como padrão; `prefs.json` guarda a escolha
  feita em tempo de execução, que tem prioridade. Comandos no launcher: `theme` (lista),
  `theme nome`, `theme next`; tecla `T` cicla os temas com **preview imediato** e
  `notify` com o nome. A paleta de comandos do Textual (`Ctrl+P`) já lista temas —
  manter, se existir.
- **Preview**: tela `F9` ou comando `theme preview`: renderiza todos os tokens, um
  painel de exemplo com os estados (ok/warn/danger/selecionado/mudança/não configurado)
  e a lista de temas navegável com `↑↓`, aplicando ao vivo; `Enter` confirma, `Esc`
  volta ao anterior.
- **Contraste**: cada tema embutido deve passar contraste mínimo 4.5:1 entre `text` e
  `bg` e 3:1 entre `text-muted` e `bg` (calcular com uma função pura em `tokens.py`,
  testada). Temas do usuário com contraste ruim geram aviso no log, não erro.

### 6.2 Tema do próprio Windows Terminal

O app não pode trocar o esquema do Windows Terminal, mas pode ajudar:

- Entregar `docs/design/windows-terminal/` com um esquema de cores por tema embutido
  (`carbon.json`, `phosphor.json`…) no formato `schemes` do `settings.json`, e um
  trecho de perfil sugerido: fonte (`Cascadia Code`/`JetBrainsMono Nerd Font`, tamanho
  11–12), `padding: 4`, `useAcrylic: false` (acrílico apaga o `dim`), `cursorShape:
  bar`, `intenseTextStyle: bright` desligado (senão `bold` vira cor), scrollbar oculta.
- Comando `theme export wt` no launcher: escreve o JSON do tema atual em
  `docs/design/windows-terminal/` (ou copia para a área de transferência) e mostra no
  `notify` onde colar.
- README: seção "Aparência" explicando `THEME`, `ICONS`, `T`, `theme export wt`, e que o
  tema `terminal` é o caminho para quem prefere as cores do próprio Windows Terminal.

---

## 7. Micro-interações e estados

| Estado | Desenho |
|---|---|
| Coletando | spinner braille no lugar de "há Ns" no título do painel; nada mais muda |
| Carregando detalhe | modal abre na hora com cabeçalho preenchido e corpo com `LoadingIndicator`; sem "carregando…" em texto |
| Contador subiu | número em `accent` + `▎` por 3 s, fade para repouso; bell/toast como hoje |
| Contador desceu | sem destaque (ruído); apenas registra no F7 |
| Item novo na lista | `▎` na linha por 3 s; cursor não se move |
| Erro com dados antigos | borda do painel `danger`; **dados continuam com cor normal**; uma linha `✗ mensagem curta · há 2 min` em `danger` no rodapé do painel; detalhe do erro só no log |
| Erro sem dados | corpo do painel com `✗` centralizado, mensagem em `text-muted`, tecla sugerida em `accent` (`c` para login, `2` para tentar de novo) |
| Não configurado | corpo com `–` centralizado e `não configurado · veja .env` em `text-faint`; borda `border`, nunca `danger` |
| Sessão expirada | mesmo que erro sem dados; ponto de saúde da fonte em `danger` na TopBar |
| Cooldown de 429 | ponto de saúde em `warn`; título do painel mostra `aguardando 2m40` em `warn` |
| Silêncio (`m`) | ícone na TopBar em `warn` + tempo restante; destaque visual continua |
| Vazio | `nenhum chamado no seu nome` centralizado em `text-faint` com `✓` em `ok` (vazio aqui é boa notícia) |
| Filtro ativo | linha `⌕ texto · 3 de 12` acima da lista; `Esc` limpa |
| Terminal estreito | breakpoints em classe; `Digits` → texto; colunas `COLUMNS_NARROW` |
| Terminal muito baixo (< 25 linhas) | Dashboard esconde o cartão de e-mail e a lista do Milldesk, mantendo só contadores e SLA |

Animação: só o fade de 3 s e o spinner. `App.animation_level` respeitado
(`TEXTUAL_ANIMATIONS=none` desliga tudo). Nada pisca continuamente, exceto o tempo de
SLA abaixo de 30 min, que alterna `danger`/`text` a cada 1 s — e mesmo isso desligável
(`SLA_BLINK=false`).

---

## 8. Restrições técnicas

- **Windows Terminal é o alvo; conhost é o mínimo.** Testar (screenshot) nos dois. No
  conhost: 16 cores → o tema `terminal` deve ficar aceitável; sem Nerd Font → `ICONS`
  cai para `unicode`; sem suporte a `dim` → `text-faint` vira `text-muted`.
- **Largura de célula:** validar todo glifo com `cell_len`; teste automatizado que
  percorre `icons.py` e falha em glifo de largura 2.
- **Desempenho:** trocar tema não pode recriar widgets (só variáveis CSS +
  `refresh_css`); o fade não pode disparar redraw de toda a tabela (animar só a célula
  ou a classe da linha); em terminal de 200 colunas o Dashboard deve renderizar em < 50 ms
  por ciclo (medir com `textual console`).
- **Sem dependência nova** além de `pytest-textual-snapshot` (dev). Nerd Font é
  opcional para o usuário, nunca requisito.
- **Nada muda nas fontes de dados.** Se o design pedir um dado que não existe no
  estado (ex.: histórico de latência para o `Sparkline`), ele é derivado em memória na
  TUI a partir do que já é publicado — nunca com chamada nova.
- Manter todos os atalhos e comportamentos documentados no README; o redesign não
  remove função, só muda como ela aparece.

---

## 9. Fases e entregas

| Fase | Conteúdo | Commit |
|---|---|---|
| 7.0 | Screenshots "antes", inventário, verificação da API do Textual, `docs/design/DIRECAO.md` com mockups e tokens → **parar para aprovação** | `docs: auditoria visual e direção` |
| 7.1 | Sistema de design: `tokens.py`, `icons.py`, `themes.py` com `carbon`/`phosphor`/`amber`/`paper`/`terminal`, `styles.tcss` reescrito só com tokens, TopBar e Footer novos, teste de contraste e de largura de glifo, snapshot tests base | `feat(design): tokens, temas e barras` |
| 7.2 | Dashboard: layout sem borda, `Digits`, cartão de e-mail, linha de SLA, ChatPanel compacto, breakpoints, novo destaque de mudança com fade | `feat(design): dashboard` |
| 7.3 | Telas cheias e detalhes (F2–F8, modais, launcher, ajuda, notas, notificações) | `feat(design): telas e detalhes` |
| 7.4 | Estados e micro-interações da seção 7; conhost; terminal baixo | `feat(design): estados` |
| 7.5 | Temas do usuário (`themes/*.json`), preview `F9`, `T`, comandos `theme`, `theme export wt`, esquemas do Windows Terminal, README "Aparência", screenshots "depois" em `docs/design/depois/` | `feat(design): temas configuráveis` |

A cada fase: screenshot SVG "depois" da tela afetada nos dois tamanhos, comparação
lado a lado no relatório da fase, testes de snapshot atualizados **com justificativa**
(nunca "atualizei porque mudou"), e a lista do que depende do usuário (instalar Nerd
Font, colar esquema no Windows Terminal).

---

## 10. Definição de pronto

- Nenhuma cor literal fora de `themes.py` (teste que faz grep em `app/tui/**` e falha).
- Nenhum emoji em `app/tui/**` (teste).
- Todos os temas embutidos passam o teste de contraste.
- Snapshot tests para: Dashboard 120×35 e 90×30 em `carbon` e `paper`; cada estado da
  seção 7 pelo menos uma vez; modal de chamado; conversa; launcher aberto.
- `T` cicla temas ao vivo sem piscar a tela inteira e sem perder o cursor das listas.
- `theme export wt` gera um JSON que o Windows Terminal aceita (testar colando de fato).
- Com `ICONS=ascii` e `TEXTUAL_ANIMATIONS=none` em conhost, todas as telas continuam
  legíveis e alinhadas.
- `docs/design/DIRECAO.md` atualizado ao final como **guia de estilo** do projeto (tokens,
  regras das seções 1, 3, 4 e 7), para que futuras features nasçam dentro da linguagem.

---

## 11. Perguntas para o usuário (responder antes da 7.1)

1. Qual `accent` você prefere para o `carbon` (ciano-frio, âmbar, verde, roxo)? Uma cor
   só — ela vai aparecer em tudo que importa.
2. Você usa Nerd Font no Windows Terminal hoje? Qual fonte e tamanho?
3. Tem preferência entre "painel focado = borda `accent`" e "painel focado = título
   `accent` sem borda"? (a 7.2 vai mostrar os dois em screenshot se quiser decidir depois)
4. Terminal em tela cheia (quantas colunas × linhas costuma ter)? Isso define o
   tamanho-alvo dos snapshots e a decisão sobre `Digits`.
5. Quer manter o bell do terminal ou passar a confiar só no destaque visual + toast?
6. Alguma referência visual que você goste (screenshot de outra TUI) para o `DIRECAO.md`?
