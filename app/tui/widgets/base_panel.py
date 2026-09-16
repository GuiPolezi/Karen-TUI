"""Painel base (sem borda): título com marcador de foco, contadores (Digits no Dashboard
ou uma linha de texto), um bloco extra da subclasse (cartão de e-mail, linha de SLA),
filtro incremental, lista com cursor e uma linha de rodapé (erro, "+N · F3", filtro).

Um painel é uma "visão" de uma fonte (SOURCE). O mesmo widget serve no Dashboard
(compacto) e na tela cheia da fonte (`full=True`: mais colunas, cabeçalho de coluna,
sem Digits). O App mantém um registro dos painéis vivos e publica o estado em todos
(`register_panel`).

Subclasses definem: SOURCE, ICON, TITLE, MORE_KEY, SUMMARY (chaves e rótulos dos
contadores), COLUMNS (e COLUMNS_COMPACT/COLUMNS_NARROW), `summary_values(state)`,
`rows(state)`, `counters(state)`, `extra_text(state)`, `foot_text(state)`,
`empty_text()`, `changed_keys(old, new)`, `browser_url(key)` e `copy_value(key)`.

Destaque de mudança: nada de borda. A linha nova ganha `▎` em `accent` no início da
primeira célula e o contador que subiu fica em `accent`, ambos por 3 s.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from rich.cells import cell_len
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.renderables.digits import Digits as DigitsRenderable
from textual.timer import Timer
from textual.widgets import DataTable, Digits, Input, Static

from app import clock
from app.tui.widgets.keyed_table import ColumnSpec, KeyedTable, Row

WAITING_TEXT = "aguardando a primeira coleta…"
FLASH_SECONDS = 3.0
MARK_SECONDS = 3.0
NARROW_WIDTH = 100
META_TICK_SECONDS = 0.5
NO_MARK = Text("")

SummaryKey = tuple[str, str]  # (chave do contador, rótulo)


def relative_age(since: datetime | None, now: datetime | None = None) -> str:
    """'há 6s', 'há 3 min', 'há 2 h'; '–' sem referência."""
    if since is None:
        return "–"
    seconds = max(int(((now or clock.now()) - since).total_seconds()), 0)
    if seconds < 60:
        return f"há {seconds}s"
    if seconds < 3600:
        return f"há {seconds // 60} min"
    return f"há {seconds // 3600} h"


def padded(left: Text, right: Text, width: int) -> Text:
    """`left` à esquerda e `right` encostado à direita numa linha de `width` células."""
    gap = width - cell_len(left.plain) - cell_len(right.plain)
    if gap < 1:
        left.truncate(max(width - cell_len(right.plain) - 1, 0), overflow="ellipsis")
        gap = 1
    return Text.assemble(left, " " * gap, right)


class DigitBlock(Vertical):
    """Um contador grande (Digits, altura 3) com o rótulo embaixo."""

    def __init__(self, key: str, label: str) -> None:
        super().__init__(classes="digit-block")
        self.key = key
        self.label = label

    def compose(self) -> ComposeResult:
        yield Digits("", classes="digit-value")
        yield Static(plural_label(self.label, ""), classes="digit-label")

    def set(self, value: str, token: str) -> None:
        label = plural_label(self.label, value)
        self.query_one(Digits).update(value)
        self.query_one(".digit-label", Static).update(label)
        # largura = o maior entre os dígitos (3 células por caractere) e o rótulo
        self.styles.width = max(DigitsRenderable.get_width(value), cell_len(label))
        self.set_class(token == "accent", "-accent")
        self.set_class(token == "danger", "-danger")
        self.set_class(token == "text-faint", "-faint")


def plural_label(label: str, value: str) -> str:
    """Rótulo 'singular|plural' escolhido pelo valor ('1' -> singular)."""
    if "|" not in label:
        return label
    singular, plural = label.split("|", 1)
    return singular if value.strip() == "1" else plural


class BasePanel(Vertical):
    """Painel sem borda. Subclasses definem ícone/título e como renderizar o estado."""

    SOURCE: str = "source"
    ICON: str = "ticket"        # nome do ícone em app.tui.icons.IconSet
    TITLE: str = "PAINEL"
    MORE_KEY: str = ""          # tecla da tela cheia ("F3") para a linha "+N · F3"
    SUMMARY: list[SummaryKey] = []                    # contadores (Digits ou texto)
    SUMMARY_IN_TITLE: bool = False                    # resumo na linha do título (ChatPanel)
    COLUMNS: list[ColumnSpec] = []                    # tela cheia (full=True)
    COLUMNS_COMPACT: list[ColumnSpec] | None = None   # Dashboard (padrão: COLUMNS)
    COLUMNS_NARROW: list[ColumnSpec] | None = None    # Dashboard em terminal estreito (padrão: COMPACT)
    BINDINGS = [
        Binding("o", "open_browser", "Abrir no navegador", show=False),
        Binding("y", "copy", "Copiar", show=False),
        Binding("slash", "filter", "Filtrar", show=False),
    ]

    def __init__(self, interval: int, *, id: str | None = None, full: bool = False) -> None:
        super().__init__(id=id)
        self.interval = interval
        self.full = full
        self.state: Any = None
        self._last_update: datetime | None = None
        self._error: str | None = None
        self._error_since: datetime | None = None
        self._flash_timer: Timer | None = None
        self._mark_timer: Timer | None = None
        self._marked: dict[str, float] = {}   # chave -> instante em que o marcador some
        self._hot: dict[str, float] = {}      # contador -> instante em que o destaque some
        self._filter = ""
        self._narrow = False
        self._digits = False
        self._waiting: str | None = WAITING_TEXT
        self._not_configured_hint: str | None = None
        self._spinner_frame = 0

    # --- tokens e ícones ----------------------------------------------------------

    @property
    def tokens(self):  # noqa: ANN201 — Tokens; evita import circular com o App
        return self.app.tokens  # type: ignore[attr-defined]

    @property
    def icons(self):  # noqa: ANN201
        return self.app.icons  # type: ignore[attr-defined]

    def style(self, token: str, **flags: bool) -> str:
        """Atalho: estilo Rich do token do tema atual (`self.style("danger", bold=True)`)."""
        return self.tokens.rich(token, **flags)

    def refresh_theme(self) -> None:
        """O tema mudou: refaz tudo que carrega cor em estilo Rich."""
        self._render_all()

    # --- montagem ---------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Horizontal(classes="panel-title"):
            yield Static("", classes="panel-name")
            yield Static("", classes="panel-meta")
        with Horizontal(classes="panel-digits"):
            for key, label in self.SUMMARY:
                yield DigitBlock(key, label)
        yield Static("", classes="panel-summary")
        yield Static("", classes="panel-extra")
        with Horizontal(classes="panel-filter-row"):
            yield Static("", classes="panel-filter-icon")
            yield Input(placeholder="filtrar… (Esc limpa)", classes="panel-filter")
        yield KeyedTable(self._columns_for_width(), classes="panel-table", show_header=self.full)
        yield Static("", classes="panel-foot")

    def on_mount(self) -> None:
        self.query_one(".panel-filter-row").display = False
        self.query_one(".panel-filter-icon", Static).update(Text(self.icons.search, style=self.style("accent")))
        self._narrow = self._is_narrow()
        self._digits = None  # type: ignore[assignment]  # força _apply_layout a decidir
        self._apply_layout()
        self._render_all()
        self.set_interval(META_TICK_SECONDS, self._tick_meta)
        register = getattr(self.app, "register_panel", None)
        if register is not None:
            register(self)

    def on_unmount(self) -> None:
        unregister = getattr(self.app, "unregister_panel", None)
        if unregister is not None:
            unregister(self)

    def on_resize(self, event: events.Resize) -> None:
        narrow = self._is_narrow()
        if narrow != self._narrow:
            self._narrow = narrow
        self._apply_layout()
        self._fit_columns()
        if self.state is not None:
            self._render_extra()
            self._render_foot()

    def on_descendant_focus(self, event: events.DescendantFocus) -> None:
        self._render_title()
        self._refresh_cursor_prefix()

    def on_descendant_blur(self, event: events.DescendantBlur) -> None:
        self._render_title()
        self._refresh_cursor_prefix()

    # --- layout responsivo ---------------------------------------------------------

    def _apply_layout(self) -> None:
        """Digits só no Dashboard com tela larga e alta (classes de breakpoint da tela)."""
        screen = self.screen
        digits = (not self.full and bool(self.SUMMARY) and not self.SUMMARY_IN_TITLE
                  and screen.has_class("-wide") and screen.has_class("-tall"))
        if digits != self._digits:
            self._digits = digits
            self._render_summary()  # decide o que fica visível (Digits, texto ou aviso)

    @property
    def highlighted_counters(self) -> set[str]:
        """Contadores em destaque (subiram há menos de 3 s)."""
        now = time.monotonic()
        return {key for key, until in self._hot.items() if until > now}

    @property
    def summary_text(self) -> str:
        """Texto do resumo como aparece (Digits ou linha), útil em testes."""
        if self.state is None:
            return str(self.query_one(".panel-summary", Static).render())
        if self._digits:
            return " · ".join(f"{b.query_one(Digits).value} {b.query_one('.digit-label', Static).render()}"  # type: ignore[union-attr]
                              for b in self.query(DigitBlock))
        if self.SUMMARY_IN_TITLE:
            return str(self.query_one(".panel-name", Static).render())
        return str(self.query_one(".panel-summary", Static).render())

    def _fit_columns(self) -> None:
        """A coluna sem largura fixa recebe o que sobra do painel (DataTable não tem "1fr")."""
        columns = self._columns_for_width()
        table = self.table
        width = table.size.width or self.size.width - 2
        if width <= 0:
            return
        fixed = sum(w for _, _, w in columns if w is not None)
        padding = 2 * len(columns) + 1  # 1 de espaço em cada lado da célula + barra de rolagem
        flexible = max(8, width - fixed - padding)
        fitted = [(key, label, w if w is not None else flexible) for key, label, w in columns]
        if fitted != table.column_specs:
            table.rebuild_columns(fitted)
            if self.state is not None:
                self._render_rows()

    def _is_narrow(self) -> bool:
        return self.app.size.width < NARROW_WIDTH and not self.full

    def _columns_for_width(self) -> list[ColumnSpec]:
        columns = self.COLUMNS
        if not self.full and self.COLUMNS_COMPACT is not None:
            columns = self.COLUMNS_COMPACT
        if self._narrow and self.COLUMNS_NARROW is not None:
            columns = self.COLUMNS_NARROW
        if not columns:
            return []
        # a primeira coluna ganha 1 célula para o marcador (▎ mudança / ▍ cursor)
        first_key, first_label, first_width = columns[0]
        first = (first_key, first_label, first_width + 1 if first_width is not None else None)
        labels = [(k, label.upper() if self.full else label, w) for k, label, w in (first, *columns[1:])]
        return labels

    @property
    def table(self) -> KeyedTable:
        return self.query_one(".panel-table", KeyedTable)

    # --- API usada pelo App -------------------------------------------------------

    def show_state(self, state: object) -> None:
        previous = self.state
        self.state = state
        self._waiting = None
        self._not_configured_hint = None
        self.remove_class("unconfigured")
        self._fit_columns()
        if previous is not None:
            now = time.monotonic()
            for key in self.changed_keys(previous, state):
                self._marked[key] = now + MARK_SECONDS
            self._schedule_unmark()
        self._render_all()

    def counters(self, state: object) -> dict[str, int]:
        """Contadores cujo AUMENTO dispara destaque e bell. Subclasses sobrescrevem."""
        return {}

    def set_waiting(self, text: str = WAITING_TEXT, token: str = "text-faint") -> None:
        self._waiting = text
        self._waiting_token = token
        self._render_summary()
        self._render_extra()

    def mark_updated(self, when: datetime | None = None) -> None:
        self._last_update = when or clock.now()
        self._render_meta()

    def set_error(self, message: str | None) -> None:
        """Erro: dados antigos continuam com cor normal; a linha de rodapé e a hora do
        título ficam em `danger`. Sem borda, sem texto vermelho no meio do painel."""
        if message and message != self._error:
            self._error_since = clock.now()
        if not message:
            self._error_since = None
        self._error = message or None
        self.set_class(bool(message), "error")
        self._render_meta()
        self._render_foot()

    def set_not_configured(self, hint: str) -> None:
        """Fonte sem credencial: neutro (`text-faint`), nunca âmbar."""
        self._not_configured_hint = hint
        self.add_class("unconfigured")
        self._render_all()

    def flash(self, counters: list[str] | None = None, seconds: float = FLASH_SECONDS) -> None:
        """Contador subiu: o número fica em `accent` por alguns segundos (sem mexer na borda)."""
        until = time.monotonic() + seconds
        for name in counters or [key for key, _ in self.SUMMARY]:
            self._hot[name] = until
        self._render_summary()
        if self._flash_timer is not None:
            self._flash_timer.stop()
        self._flash_timer = self.set_timer(seconds + 0.1, self._end_flash)

    def _end_flash(self) -> None:
        now = time.monotonic()
        self._hot = {key: until for key, until in self._hot.items() if until > now}
        self._flash_timer = None
        self._render_summary()

    # --- a ser definido pelas subclasses ---------------------------------------------

    def summary_values(self, state: object) -> dict[str, tuple[str, str]]:
        """chave -> (valor formatado, token de cor) para cada item de SUMMARY."""
        return {}

    def extra_text(self, state: object) -> Text | None:
        """Bloco entre os contadores e a lista (cartão de e-mail, linha de SLA...)."""
        return None

    def foot_text(self, state: object) -> Text | None:
        """Linha de rodapé da subclasse (ex.: '4 com outros técnicos')."""
        return None

    def empty_text(self) -> str:
        return "nada por aqui"

    def rows(self, state: object) -> list[tuple[str, dict[str, Any]]]:
        """(chave, {coluna: célula}) por item; o painel escolhe as colunas visíveis."""
        return []

    def changed_keys(self, previous: object, state: object) -> set[str]:
        """Chaves novas; ganham o marcador ▎ por alguns segundos."""
        old = {key for key, _ in self.rows(previous)}
        return {key for key, _ in self.rows(state) if key not in old}

    def browser_url(self, key: str) -> str | None:
        return None

    def copy_value(self, key: str) -> str | None:
        return None

    def what(self) -> str:
        """Nome do item para mensagens ('chamado', 'conversa', 'e-mail')."""
        return "item"

    # --- renderização ---------------------------------------------------------------

    def _render_all(self) -> None:
        self._render_title()
        self._render_meta()
        self._render_summary()
        self._render_extra()
        if self.state is not None:
            self._render_rows()
        self._render_foot()

    @property
    def focused_within(self) -> bool:
        try:
            focused = self.app.focused
        except Exception:  # app encerrando: não há mais tela
            return False
        return focused is not None and self in focused.ancestors_with_self

    def _render_title(self) -> None:
        icons, tokens = self.icons, self.tokens
        focused = self.focused_within
        title = Text(no_wrap=True, overflow="ellipsis")
        title.append(icons.focus if focused else " ", style=tokens.rich("accent"))
        title.append(f"{getattr(icons, self.ICON, '')} {self.TITLE}",
                     style=tokens.rich("accent" if focused else "text", bold=True))
        if self.SUMMARY_IN_TITLE and self.state is not None and not self._not_configured_hint:
            title.append("   ").append_text(self._summary_line())
        self.query_one(".panel-name", Static).update(title)

    def _render_meta(self) -> None:
        tokens, icons = self.tokens, self.icons
        text = Text(no_wrap=True, justify="right")
        fetching = self.SOURCE in getattr(self.app, "fetching", set())
        if self._error:
            text.append(f"{icons.error} {relative_age(self._error_since)}", style=tokens.rich("danger"))
            text.append(f"  {self.interval}s", style=tokens.rich("text-faint"))
        elif fetching:
            frames = icons.spinner
            text.append(f"{self.interval}s {icons.sep} ", style=tokens.rich("text-faint"))
            text.append(frames[self._spinner_frame % len(frames)], style=tokens.rich("accent"))
        else:
            text.append(f"{self.interval}s {icons.sep} {relative_age(self._last_update)}", style=tokens.rich("text-faint"))
        self.query_one(".panel-meta", Static).update(text)

    def _tick_meta(self) -> None:
        self._spinner_frame += 1
        self._render_meta()

    def _summary_line(self) -> Text:
        """'142 inbox · 7 não lidos · 3 spam' com os contadores quentes em accent."""
        tokens, icons = self.tokens, self.icons
        values = self.summary_values(self.state) if self.state is not None else {}
        hot = {key for key, until in self._hot.items() if until > time.monotonic()}
        text = Text(no_wrap=True, overflow="ellipsis")
        for index, (key, label) in enumerate(self.SUMMARY):
            value, token = values.get(key, ("–", "text-faint"))
            if index:
                text.append(f" {icons.sep} ", style=tokens.rich("text-faint"))
            text.append(value, style=tokens.rich("accent" if key in hot else token, bold=token != "text-faint"))
            text.append(f" {plural_label(label, value)}", style=tokens.rich("text-muted"))
        return text

    def _render_summary(self) -> None:
        summary = self.query_one(".panel-summary", Static)
        if self.state is None:
            if self._not_configured_hint is not None:
                summary.update(self._not_configured_text())
            else:
                summary.update(Text(self._waiting or "", style=self.style(getattr(self, "_waiting_token", "text-faint"))))
            summary.display = True
            self.query_one(".panel-digits").display = False
            return
        summary.display = not self._digits and not self.SUMMARY_IN_TITLE and bool(self.SUMMARY)
        self.query_one(".panel-digits").display = self._digits
        if self.SUMMARY_IN_TITLE:
            self._render_title()
            return
        if self._digits:
            values = self.summary_values(self.state)
            hot = {key for key, until in self._hot.items() if until > time.monotonic()}
            for block in self.query(DigitBlock):
                value, token = values.get(block.key, ("–", "text-faint"))
                block.set(value, "accent" if block.key in hot else token)
        else:
            summary.update(self._summary_line())

    def _not_configured_text(self) -> Text:
        text = Text()
        text.append(f"{self.icons.empty} não configurado", style=self.style("text-muted"))
        text.append(f"\n{self._not_configured_hint}", style=self.style("text-faint"))
        return text

    def _render_extra(self) -> None:
        extra = self.query_one(".panel-extra", Static)
        content = self.extra_text(self.state) if self.state is not None else None
        if content is None or not content.plain:
            extra.update("")
            extra.display = False
        else:
            extra.update(content)
            extra.display = True

    def _render_foot(self) -> None:
        tokens, icons = self.tokens, self.icons
        foot = self.query_one(".panel-foot", Static)
        text = Text(no_wrap=True, overflow="ellipsis")
        if self._error:
            text.append(f"{icons.error} ", style=tokens.rich("danger", bold=True))
            text.append(self._error, style=tokens.rich("danger"))
            text.append(f" {icons.sep} {relative_age(self._error_since)}", style=tokens.rich("text-faint"))
        elif self._filter:
            shown, total = self.table.row_count, len(self.rows(self.state)) if self.state is not None else 0
            text.append(f"{icons.search} {self._filter}", style=tokens.rich("accent"))
            text.append(f" {icons.sep} {shown} de {total}", style=tokens.rich("text-faint"))
        elif self.state is not None:
            hidden = self._hidden_rows()
            custom = self.foot_text(self.state)
            if hidden > 0 and self.MORE_KEY and not self.full:
                text.append(f"+{hidden} {icons.sep} {self.MORE_KEY}", style=tokens.rich("text-faint"))
                if custom is not None and custom.plain:
                    text.append(f"   {icons.sep}   ", style=tokens.rich("text-faint")).append_text(custom)
            elif custom is not None:
                text.append_text(custom)
        foot.update(text)
        foot.display = bool(text.plain)

    def _hidden_rows(self) -> int:
        table = self.table
        visible = table.size.height - (1 if self.full else 0)
        if visible <= 0:
            return 0
        return max(table.row_count - visible, 0)

    # --- lista, filtro, marcadores ---------------------------------------------------

    @property
    def selected_key(self) -> str | None:
        return self.table.selected_key

    def _prefix(self, key: str, now: float, cursor_key: str | None) -> str:
        if self._marked.get(key, 0) > now:
            return self.icons.change
        if key == cursor_key and self.focused_within:
            return self.icons.focus
        return " "

    def _with_prefix(self, prefix: str, cell: Any) -> Text:
        token = "accent"
        first = Text(prefix, style=self.style(token, bold=True))
        if isinstance(cell, Text):
            return Text.assemble(first, cell)
        return Text.assemble(first, Text(str(cell)))

    def _render_rows(self) -> None:
        items = self.rows(self.state) if self.state is not None else []
        if self._filter:
            needle = self._filter.casefold()
            items = [(key, cells) for key, cells in items
                     if needle in " ".join(_plain(cell) for cell in cells.values()).casefold()]
        now = time.monotonic()
        columns = [key for key, _, _ in self.table.column_specs]
        if not columns:
            return
        cursor_key = self.table.selected_key
        rows: list[Row] = []
        for key, cells in items:
            first = self._with_prefix(self._prefix(key, now, cursor_key), cells.get(columns[0], NO_MARK))
            rows.append((key, [first, *(cells.get(column, NO_MARK) for column in columns[1:])]))
        self.table.set_rows(rows)
        if self.state is not None and not items and not self._filter:
            self._render_empty()
        self._render_foot()

    def _render_empty(self) -> None:
        """Vazio é boa notícia: ✓ em `ok` e o texto em `text-faint` no lugar da lista."""
        extra = self.query_one(".panel-extra", Static)
        if extra.display:
            return
        text = Text(justify="center")
        text.append(f"\n{self.icons.ok} ", style=self.style("ok")).append(self.empty_text(), style=self.style("text-faint"))
        extra.update(text)
        extra.display = True

    def _refresh_cursor_prefix(self) -> None:
        """Só a primeira célula da linha do cursor (e da anterior) muda: nada de re-render da tabela."""
        table = self.table
        if not table.column_specs or self.state is None:
            return
        now = time.monotonic()
        cursor_key = table.selected_key
        first_column = table.column_specs[0][0]
        cells = dict(self.rows(self.state))
        for key in {cursor_key, getattr(self, "_previous_cursor", None)} - {None}:
            if key in table.keys and key in cells:
                table.update_cell(key, first_column,
                                  self._with_prefix(self._prefix(key, now, cursor_key), cells[key].get(first_column, NO_MARK)))
        self._previous_cursor = cursor_key

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self._refresh_cursor_prefix()

    def _schedule_unmark(self) -> None:
        if self._mark_timer is not None:
            self._mark_timer.stop()
        self._mark_timer = self.set_timer(MARK_SECONDS + 0.1, self._unmark)

    def _unmark(self) -> None:
        now = time.monotonic()
        self._marked = {key: until for key, until in self._marked.items() if until > now}
        self._mark_timer = None
        if self.state is not None:
            self._render_rows()

    def action_filter(self) -> None:
        self.query_one(".panel-filter-row").display = True
        self.query_one(".panel-filter", Input).focus()

    def clear_filter(self) -> None:
        box = self.query_one(".panel-filter", Input)
        box.value = ""
        self.query_one(".panel-filter-row").display = False
        self._filter = ""
        if self.state is not None:
            self._render_rows()
        self.table.focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.has_class("panel-filter"):
            self._filter = event.value.strip()
            if self.state is not None:
                self._render_rows()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.has_class("panel-filter"):
            self.table.focus()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        key = event.row_key.value
        if key is not None:
            self.app.open_detail(self.SOURCE, str(key))  # type: ignore[attr-defined]

    def action_open_browser(self) -> None:
        key = self.selected_key
        self.app.open_url(self.browser_url(key) if key else None, self.what())  # type: ignore[attr-defined]
        value = self.copy_value(key) if key else None
        if value:
            self.app.copy_text(value, self.what(), quiet=True)  # type: ignore[attr-defined]

    def action_copy(self) -> None:
        key = self.selected_key
        self.app.copy_text(self.copy_value(key) if key else None, self.what())  # type: ignore[attr-defined]

    @property
    def content_width(self) -> int:
        return max(self.size.width - 2, 20)


def _plain(cell: Any) -> str:
    return cell.plain if isinstance(cell, Text) else str(cell)
