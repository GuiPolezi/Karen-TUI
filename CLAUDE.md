# CMD ALL-IN-ONE — guia para o Claude Code

A especificação completa (objetivo, stack, seletores, fases) está em
`PROMPT_CMD_ALL_IN_ONE.md`. Leia-a antes de começar uma fase. Este arquivo só resume
as regras que valem em todo o projeto.

## Idioma e estilo

- Código e comentários em **português**; nomes de variáveis/funções em inglês.
- Python 3.11+, `from __future__ import annotations`, dataclasses, type hints.
- Nada de `print` dentro da TUI: usar `logging` (vai para `logs/app.log`).

## Regras inegociáveis

1. **Segredos:** nunca hardcode; nunca commitar `.env`; nunca chave real em fixture ou log.
   Mascarar `api_key` como `****1776` (`MilldeskSettings.masked_key`).
2. **Somente leitura em todas as fontes.** IMAP em modo readonly. Nunca chamar endpoints
   de escrita do Milldesk (`addTicket`, `updateTicketStatus`, `sendCommunication`...).
3. **Robustez > features:** cada fonte isolada; falha em uma não afeta as outras;
   timeout em tudo; retry com backoff 2/4/8 s (`Source.fetch_with_retry`).
4. **Modo debug por fonte:** `python -m app.sources.<nome>` imprime o estado em JSON e sai.
5. **Windows-first:** `pathlib`, sem dependências que exijam compilação.
6. **Não inventar endpoints:** se a doc do Milldesk não tiver algo, perguntar.
7. **Perguntar antes de decisões irreversíveis:** trocar estratégia de scraping, mudar
   stack, adicionar servidor HTTP local.
8. Ao terminar cada fase: listar o que foi feito, como testar e o que depende do usuário.
   Commit a cada fase.

## Ambiente

- venv em `.venv` (`.venv\Scripts\python`), instalado com `pip install -e ".[dev]"`.
- Testes: `python -m pytest`. TUI: `python -m app`.

## Mapa rápido

- `app/config.py` — `load_settings()` lê `.env`; variável ausente aborta, segredo vazio
  marca a fonte como `configured=False`.
- `app/state.py` — dataclasses publicadas pelas fontes + `to_json()`.
- `app/sources/base.py` — `Source[S]` com `fetch()`, `fetch_with_retry()`, `close()`.
- `app/tui/app.py` — `CmdAllInOneApp`: `MODES` (uma tela por modo), workers das fontes,
  `register_panel`/`_publish` (todo painel vivo recebe o mesmo estado), `notify`,
  `open_url`, `copy_text`, `open_detail`.
- `app/tui/screens/` — `ModeScreen` (TopBar + corpo + Footer) e as telas Dashboard,
  E-mail, Milldesk, ChatPanel, Log, Notas; `email_detail.py` é a modal do e-mail.
- `app/tui/widgets/base_panel.py` — `BasePanel`: cabeçalho + `KeyedTable` + filtro;
  subclasses definem `COLUMNS`/`COLUMNS_COMPACT`/`COLUMNS_NARROW`, `rows()` (células por
  nome de coluna), `counters()`, `browser_url()`, `copy_value()`.
- `app/tui/widgets/keyed_table.py` — `KeyedTable.set_rows()` faz diff por chave e
  preserva o cursor.
- `app/prefs.py` — `prefs.json` (última tela, ordenação, favoritos, histórico). Nunca segredo.
