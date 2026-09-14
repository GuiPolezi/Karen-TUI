# CMD ALL-IN-ONE — Dashboard TUI de Suporte (Sino Informática)

> **Como usar este arquivo:** cole-o inteiro como primeiro prompt no Claude Code (ou salve como `CLAUDE.md` na raiz do projeto e diga "leia o CLAUDE.md e comece pela Fase 0").
> Idioma do projeto: código e comentários em **português**, nomes de variáveis em inglês.

---

## 1. Objetivo

Construir um aplicativo de terminal (TUI) que roda no Windows Terminal/CMD e mostra, **em tempo real e em uma única tela**, três indicadores do dia a dia do técnico de suporte:

| Painel | O que mostra | Fonte |
|---|---|---|
| **E-MAIL** | Total de e-mails na caixa de entrada, quantos não lidos, e o e-mail mais recente (remetente, assunto, data, prévia do corpo). Opcional: contagem da pasta de spam. | IMAP |
| **MILLDESK** | Quantos chamados (tickets) estão no nome do técnico logado. | API REST Milldesk |
| **CHATPANEL (WhatsApp)** | Quais conversas estão em atendimento no nome do técnico, com nome do contato, última mensagem, horário, badge de não lidas, tag e departamento. Total de não lidas. | Scraping do painel web (não há API) |

Cada painel se atualiza sozinho em intervalos configuráveis, mostra `última atualização HH:MM:SS`, e em caso de falha exibe o erro **sem derrubar os outros painéis**.

---

## 2. Stack e decisões de arquitetura

- **Linguagem:** Python 3.11+
- **TUI:** [`textual`](https://textual.textualize.io/) (async nativo, funciona bem no Windows Terminal). Cada fonte de dados é um *worker* assíncrono independente que publica no estado da app.
- **HTTP:** `httpx` (async)
- **IMAP:** `imap-tools` (ou `imaplib` + `email` da stdlib se preferir zero dependências)
- **Scraping ChatPanel:** `playwright` (Chromium headless com perfil persistente) + `beautifulsoup4` para parsear o HTML
- **Config:** `python-dotenv`, arquivo `.env` (nunca commitar; gerar `.env.example`)
- **Gerenciador:** `uv` (ou `venv` + `pip`), com `pyproject.toml`
- **Logs:** `logging` para `logs/app.log` com rotação; nada de `print` na TUI
- **Testes:** `pytest`, com fixtures de HTML/JSON reais salvas em `tests/fixtures/`

### Estrutura de pastas esperada

```
cmd-all-in-one/
├── app/
│   ├── main.py              # entrypoint: `python -m app` ou `uv run app`
│   ├── config.py            # carrega .env, valida, expõe Settings
│   ├── state.py             # dataclasses do estado compartilhado (EmailState, MilldeskState, ChatPanelState)
│   ├── tui/
│   │   ├── app.py           # Textual App, layout, bindings, timers
│   │   ├── widgets/
│   │   │   ├── email_panel.py
│   │   │   ├── milldesk_panel.py
│   │   │   ├── chatpanel_panel.py
│   │   │   └── status_bar.py
│   │   └── styles.tcss
│   └── sources/
│       ├── base.py          # interface Source: async fetch() -> State, intervalo, tratamento de erro
│       ├── email_imap.py
│       ├── milldesk.py
│       └── chatpanel.py
├── tests/
│   └── fixtures/
│       ├── chatpanel_chat.html      # HTML real do painel (fornecido pelo usuário)
│       └── milldesk_ticketsByAgent.json
├── scripts/
│   └── chatpanel_login.py   # abre Chromium visível uma vez para o usuário logar e salvar sessão
├── .env.example
├── pyproject.toml
├── README.md
└── CLAUDE.md
```

---

## 3. Configuração (`.env`)

Gerar `.env.example` com estes campos. **Nunca** escrever valores reais em código ou em fixtures.

```env
# --- Identidade do técnico ---
TECH_NAME=Guilherme                      # exatamente como aparece no ChatPanel e no Milldesk

# --- E-mail (IMAP) ---
EMAIL_IMAP_HOST=imap.sinoinformatica.com.br
EMAIL_IMAP_PORT=143                      # 143 = STARTTLS; 993 = SSL direto
EMAIL_IMAP_STARTTLS=true
EMAIL_USER=suporte@sinoinformatica.com.br
EMAIL_APP_PASSWORD=                      # preencher; se tiver "#" ou "*", manter entre aspas simples
EMAIL_INBOX_FOLDER=INBOX
EMAIL_SPAM_FOLDER=Junk E-Mail
EMAIL_REFRESH_SECONDS=30

# --- Milldesk ---
MILLDESK_API_KEY=
MILLDESK_BASE_URL=https://v1.milldesk.com/api
MILLDESK_REFRESH_SECONDS=60

# --- ChatPanel ---
CHATPANEL_URL=https://srv02.chatpanel.space/8b1847a98299/chat.php
CHATPANEL_PROFILE_DIR=.chatpanel-profile # perfil persistente do Chromium (gitignored)
CHATPANEL_REFRESH_SECONDS=15
CHATPANEL_HEADLESS=true
```

> ⚠️ A porta 143 é texto puro por padrão. Implementar `STARTTLS` quando `EMAIL_IMAP_STARTTLS=true`; se o servidor recusar, cair para 993/SSL e logar o aviso. Nunca enviar senha sem TLS silenciosamente.

---

## 4. Fonte 1 — E-mail (IMAP)

### Requisitos
- Conectar, autenticar, selecionar `EMAIL_INBOX_FOLDER` em modo **somente leitura** (não marcar nada como lido).
- Obter via `STATUS INBOX (MESSAGES UNSEEN)`: total e não lidos.
- Buscar o e-mail mais recente (`SORT`/`SEARCH ALL` → maior UID). Extrair: `From` (nome + endereço), `Subject` (decodificar RFC 2047), `Date` (converter para horário local), e uma **prévia do corpo** de até ~300 caracteres: preferir `text/plain`; se só houver `text/html`, remover tags e colapsar espaços.
- Opcional: contagem de `EMAIL_SPAM_FOLDER`.
- Loop: reconectar automaticamente se a conexão cair; timeout de 20 s por operação.
- Melhoria futura (não bloquear a Fase 1): usar `IMAP IDLE` para push em vez de polling.

### Estado publicado
```python
@dataclass
class EmailState:
    total: int; unseen: int; spam: int | None
    latest: LatestEmail | None   # from_name, from_addr, subject, date, preview
    updated_at: datetime; error: str | None
```

---

## 5. Fonte 2 — Milldesk (API REST)

Documentação: `https://v1.milldesk.com/api` (apiDoc). Todas as rotas são `GET https://v1.milldesk.com/api/:api_key/<rota>`. **Erros vêm com HTTP 200** e corpo `{"error": "invalidApiKey"}` — tratar isso como erro, não como sucesso.

### Rota principal: contagem de chamados por técnico
```
GET /api/:api_key/ticketsByAgent
→ [ { "agent": "Nome do técnico", "amount": "12", "percentage": "8.5" }, ... ]
```
- Filtrar o item cujo `agent` == `TECH_NAME` (comparação case-insensitive, sem acentos, `strip()`).
- `amount` e `percentage` chegam como **string** → converter.
- Se o técnico não aparecer na lista, exibir `0` e uma nota "técnico não encontrado na resposta".
- **VERIFICAR NA FASE 3:** se `amount` conta apenas chamados **abertos** ou todo o histórico. Fazer uma chamada real, comparar com o painel do Milldesk e registrar a conclusão no README. Se for histórico, procurar na doc uma rota de listagem filtrável por status/técnico (seções "Exportar dados" → "Listar solicitações de atividades", "Listar status da solicitação", "Listar técnicos") e ajustar.

### Rota auxiliar: detalhe de um ticket
```
GET /api/:api_key/showTicket?id=:id
```
Campos úteis: `id, ticket (assunto), requester, agent, status, stage, priority, urgency, start, starttime, end, endtime, slaexpirationdate, description, resolution`. Erros: `invalidApiKey`, `invalidId`.
Usar para um modo de detalhe (tecla `Enter` no painel Milldesk → pede ID → mostra o ticket) — opcional.

### Outras rotas conhecidas (para referência, não implementar agora)
`ticketsByRequester`, e a seção "Exportar dados": `Listar alterações, ativos, categorias, cidades, classes, contratos, departamentos, estados, etapas, feriados, fornecedores, grupos, regiões, regras, serviços, solicitantes, soluções, status da alteração, status da solicitação, subcategorias, tarefas, tipos de atividades, tipos de ativos, tipos de solicitações, técnicos, urgências`. Relatórios de SLA: `Violados x Atendidos por SLA/ativo/categoria/classe/departamento`.

### Estado publicado
```python
@dataclass
class MilldeskState:
    my_tickets: int; my_percentage: float
    total_all_agents: int          # soma de amount de todos
    updated_at: datetime; error: str | None
```

---

## 6. Fonte 3 — ChatPanel (scraping, sem API)

O ChatPanel é um painel web PHP/jQuery. As listas de conversas são preenchidas por XHR (`control.php`) e re-renderizadas via socket.io. **Não existe API pública.**

### Estratégia A (implementar primeiro): Playwright com sessão persistente
1. `scripts/chatpanel_login.py`: abre Chromium **visível** com `launch_persistent_context(CHATPANEL_PROFILE_DIR)`, navega para `CHATPANEL_URL`, e espera o usuário logar manualmente. Ao detectar `#int_username` no DOM, salva e fecha. Rodar uma única vez.
2. `sources/chatpanel.py`: abre o mesmo perfil em headless, mantém a página aberta (não recarregar a cada ciclo — o socket.io já atualiza o DOM), e a cada `CHATPANEL_REFRESH_SECONDS` lê `page.content()` e parseia com BeautifulSoup.
3. Se detectar redirecionamento para login (ausência de `#int_username`), publicar erro `"sessão expirada — rode scripts/chatpanel_login.py"`.
4. Validar a hipótese de que abrir uma segunda sessão headless **não derruba** a sessão do navegador do técnico. Se derrubar, mudar para a Estratégia B.

### Estratégia B (fallback): userscript empurra dados para o app
O usuário já usa Tampermonkey neste painel (ver script de referência na seção 9). Criar um userscript que, a cada 10 s, coleta os mesmos dados do DOM e faz `POST http://127.0.0.1:8765/chatpanel` (`GM_xmlhttpRequest`). O app sobe um servidor HTTP local mínimo (`aiohttp` ou `http.server` em thread) que recebe e publica o estado. Vantagem: zero risco de sessão; desvantagem: depende do navegador aberto.

### Estratégia C (otimização futura): replicar o XHR
Descobrir via DevTools qual chamada a `control.php` retorna as listas e replicá-la com `httpx` + cookie de sessão. Só investigar depois de A funcionar.

### Seletores DOM (extraídos do HTML real — usar `tests/fixtures/chatpanel_chat.html`)

**Identidade do usuário logado**
- `input#int_username` → `value="Guilherme"` (fonte primária)
- `input#chat_userid` → `value="12"`
- Fallback: `.dropdown-item.text-center.border-bottom span`

**Aba "Atende"** (`#atende-tab-pane`), que é a aba relevante:
- `#box-atende-chats li.checkforactive` → seção **"SUAS CONVERSAS"** (atribuídas ao usuário logado). ⚠️ No HTML de referência esta div está vazia; validar em produção se as conversas do próprio usuário aparecem aqui ou dentro de `#box-atendeothers-chats` com badge do próprio nome. **Tratar ambos os casos e deduplicar por número.**
- `#box-atendeothers-chats li.checkforactive` → seção **"EM ATENDIMENTO"** (por outros usuários). Cada `li` tem badges; filtrar os que têm badge de pessoa == `TECH_NAME`.
- `#total-unread2` → badge com total de não lidas da aba Atende.

**Estrutura de cada `li.checkforactive`** (exemplo real):
```html
<li class="checkforactive" id="chat_5511984568840">
  <a onclick="changeTheInfo(this,'5511984568840')">
    <span class="avatar avatar-md online me-2"><img src="..."></span>
    <p class="mb-0 fw-medium">
      Celso - CM Itu <span class="float-end text-muted fw-normal fs-11">15:28</span>
    </p>
    <p class="fs-12 mb-0">
      <span class="chat-msg text-truncate">Só um momento</span>
      <span class="badge bg-primary2 rounded-pill float-end unread-count2" id="unreadchat_5511984568840">1</span>
    </p>
    <p class="mb-0">
      <span class="badge bg-teal-transparent"><i class="bi bi-tag"></i> Câmara</span>          <!-- TAG -->
      <span class="badge bg-primary2-transparent"><i class="bi bi-star"></i> Suporte</span>    <!-- DEPARTAMENTO -->
      <span class="badge bg-success-transparent"><i class="bi bi-person"></i> SINO Admin</span> <!-- USUÁRIO ATENDENDO -->
    </p>
  </a>
</li>
```

Regras de extração por item:
| Campo | Seletor / regra |
|---|---|
| `number` | `li[id]` → remover prefixo `chat_` |
| `name` | texto direto de `p.mb-0.fw-medium` (excluir o `span.float-end`) |
| `time` | `p.mb-0.fw-medium span.float-end` |
| `last_message` | `span.chat-msg` (colapsar quebras; pode começar com `*Nome:*` quando enviada por técnico) |
| `unread` | `span.unread-count2` → int, ou 0 se ausente |
| `tag` | badge contendo `i.bi-tag` |
| `department` | badge contendo `i.bi-star` |
| `agent` | badge contendo `i.bi-person` |
| `online` | `span.avatar` tem classe `online` |
| `is_mine` | `agent` == `TECH_NAME` (normalizado) **ou** o `li` está em `#box-atende-chats` |

Ignorar `li.pb-0` (cabeçalhos "SUAS CONVERSAS" / "EM ATENDIMENTO") e `li.chat-inactive` (encerradas, aba "Todos").

**Extras opcionais (aba "Todos", `#users-tab-pane`)**
- `#box-active-chats li.checkforactive` → todas as ativas
- `#box-noactive-chats li.chat-inactive` → encerradas recentes (últimas do dia, com horário `HH:MM`)

### Estado publicado
```python
@dataclass
class ChatItem:
    number: str; name: str; time: str; last_message: str
    unread: int; tag: str | None; department: str | None; agent: str | None; online: bool

@dataclass
class ChatPanelState:
    mine: list[ChatItem]; mine_unread: int
    others_count: int; total_unread_tab: int
    logged_user: str | None
    updated_at: datetime; error: str | None
```

---

## 7. TUI — layout e comportamento

```
┌ CMD ALL-IN-ONE ──────────────────────────── Guilherme · 14/09/2026 15:31:07 ┐
│ ┌ 📧 E-MAIL  (30s · 15:31:02) ─────────┐ ┌ 🎫 MILLDESK (60s · 15:30:40) ───┐ │
│ │ Inbox: 142   Não lidos: 7   Spam: 3  │ │ Chamados no meu nome:   12       │ │
│ │──────────────────────────────────────│ │ 8.5% do total (141)              │ │
│ │ De:   Fulano <fulano@cm.sp.gov.br>   │ │                                  │ │
│ │ Ass.: Erro ao gerar relatório        │ │                                  │ │
│ │ 15:28 · Bom dia, ao tentar gerar…    │ │                                  │ │
│ └──────────────────────────────────────┘ └──────────────────────────────────┘ │
│ ┌ 💬 CHATPANEL — minhas conversas: 2 · não lidas: 1  (15s · 15:31:05) ──────┐ │
│ │ ● 15:26  Diego Leone - PM Iaras     [Prefeitura] Suporte   • Porta 21…  1 │ │
│ │ ○ 15:24  Hércules - CM Tatui TI     [Câmara]     Suporte   *Fabio:* Hé…   │ │
│ └────────────────────────────────────────────────────────────────────────────┘ │
│ [r] atualizar tudo  [1/2/3] atualizar painel  [e] abrir e-mail  [q] sair      │
└───────────────────────────────────────────────────────────────────────────────┘
```

- Layout responsivo: em terminal estreito (< 100 colunas), empilhar os painéis verticalmente.
- Cada painel mostra no título: intervalo e hora da última atualização; borda **vermelha** + mensagem quando `error` está preenchido (mantendo os últimos dados válidos visíveis).
- Contadores que **aumentaram** desde o último ciclo piscam/destacam por 3 s e disparam bell do terminal (`\a`) — configurável (`NOTIFY_BELL=true`).
- Bindings: `q` sair · `r` forçar refresh geral · `1`/`2`/`3` refresh individual · `e` abrir o e-mail mais recente em tela cheia (corpo completo) · `Esc` voltar · `l` alternar painel de log (últimas 50 linhas do `app.log`).
- Barra de status inferior com atalhos e mensagens transitórias.
- A UI **nunca** deve congelar: todo I/O em workers `@work(thread=False)`/async; timeouts em tudo.

---

## 8. Fases de implementação (executar em ordem, commit a cada fase)

### Fase 0 — Bootstrap
- `pyproject.toml`, `uv` lock, `.gitignore` (`.env`, `.chatpanel-profile/`, `logs/`), `.env.example`, `README.md` com instruções Windows.
- `config.py` com validação: abortar com mensagem clara se faltar variável.
- Skeleton Textual com três painéis mostrando "aguardando…" e relógio funcionando.

### Fase 1 — E-mail
- `sources/email_imap.py` completo + worker + widget.
- Teste manual: `python -m app.sources.email_imap` imprime o estado em JSON (cada source deve ter esse modo standalone para debug).

### Fase 2 — Milldesk
- `sources/milldesk.py` com `ticketsByAgent`; teste com fixture JSON; teste do caso `{"error": "invalidApiKey"}`.

### Fase 3 — Validação Milldesk (obrigatória)
- Chamar a API real, comparar `amount` com o painel do Milldesk e **documentar no README** se é "abertos" ou "histórico". Ajustar rota se necessário.

### Fase 4 — ChatPanel
- Parser puro (`parse_chatpanel_html(html, tech_name) -> ChatPanelState`) testado contra `tests/fixtures/chatpanel_chat.html`. Com o fixture e `tech_name="SINO Admin"` deve retornar 2 conversas (`5511984568840`, `5514988010122`); com `"Fabio"`, 1 (`5516997484965`); com `"Guilherme"`, 0.
- Script de login + worker Playwright (Estratégia A). Registrar no README o resultado do teste de "sessão concorrente".
- Se A falhar → implementar B (userscript + servidor local).

### Fase 5 — Polimento
- Destaque de mudanças, bell, painel de log, modo detalhe de e-mail, empilhamento responsivo.
- `README.md` final: instalação (`uv sync`, `playwright install chromium`), primeiro login, como rodar, troubleshooting (sessão expirada, IMAP sem TLS, técnico não encontrado).

---

## 9. Referência: userscript já em uso pelo usuário

Este script Tampermonkey roda hoje no ChatPanel e registra finalizações (POST em `control.php` com `control=5`). Serve como referência de (a) como o usuário já interage com o DOM do painel e (b) padrão para a Estratégia B. Um bônus possível é um contador **"finalizados hoje"** alimentado por ele.

Pontos relevantes do script:
- Nome do técnico: `.dropdown-item.text-center.border-bottom span`
- Nome do contato aberto: `.chatnameperson` (limpar número de telefone do texto)
- Conteúdo da conversa aberta: `#main-chat-content` (`innerText`)
- Detecção de finalização: intercepta `XMLHttpRequest` para URL `control.php` com body `control=5`, lendo `chat_number` e `instanceid` do body form-urlencoded
- Envio externo: `GM_xmlhttpRequest` POST JSON (requer `@grant GM_xmlhttpRequest` e `@connect *`)

---

## 10. Regras gerais para o Claude Code

1. **Segredos:** nunca hardcode. Nunca commitar `.env`. Nunca colocar chaves reais em fixtures ou logs (mascarar `api_key` nos logs como `****1776`).
2. **Robustez > features:** cada source isolada; falha em uma não afeta as outras; sempre há timeout; sempre há retry com backoff (3 tentativas, 2/4/8 s).
3. **Modo debug por source:** `python -m app.sources.<nome>` imprime o estado em JSON e sai.
4. **Windows-first:** testar no Windows Terminal; usar `pathlib`; evitar dependências que exigem compilação.
5. **Não inventar endpoints:** se a documentação do Milldesk não tiver algo, perguntar ao usuário em vez de adivinhar.
6. **Perguntar antes de decisões irreversíveis:** trocar de estratégia de scraping, mudar stack, adicionar servidor HTTP local.
7. Ao terminar cada fase, listar: o que foi feito, como testar, e o que precisa do usuário (ex.: "rode `scripts/chatpanel_login.py` e faça login").

---

## 11. Pendências que dependem do usuário

- [ ] Preencher `.env` (senha do e-mail, `MILLDESK_API_KEY`).
- [ ] Confirmar se a caixa `suporte@` é compartilhada — se sim, "e-mails não lidos" reflete a equipe toda, não só o técnico (aceitável, mas documentar).
- [ ] Rodar o login manual do ChatPanel na Fase 4.
- [ ] Validar na Fase 3 o significado de `amount` em `ticketsByAgent`.
- [ ] Confirmar em produção onde aparecem as conversas do próprio usuário (`#box-atende-chats` vs badge em `#box-atendeothers-chats`).
