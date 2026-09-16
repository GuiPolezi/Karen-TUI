"""Painel base: borda com título/subtítulo, cabeçalho de contadores, lista com cursor,
filtro incremental, linha de erro, espera e destaque.

Um painel é uma "visão" de uma fonte (SOURCE). O mesmo widget serve no Dashboard
(compacto) e na tela cheia da fonte (`full=True`, mais colunas). O App mantém um registro
dos painéis vivos e publica o estado em todos (`register_panel`).

Subclasses definem: SOURCE, ICON, TITLE, COLUMNS (e COLUMNS_NARROW), `header_text(state)`,
`rows(state)`, `counters(state)`, `changed_keys(old, new)`, `browser_url(key)` e
`copy_value(key)`.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.timer import Timer
from textual.widgets import DataTable, Input, Static

from app import clock
from app.tui.widgets.keyed_table import ColumnSpec, KeyedTable, Row

WAITING_TEXT = "aguardando…"
FLASH_SECONDS = 3.0
MARK_SECONDS = 3.0
NO_MARK = Text("")
NARROW_WIDTH = 100


class BasePanel(Vertical):
    """Container com borda. Subclasses definem ícone/título e como renderizar o estado."""

    SOURCE: str = "source"
    ICON: str = "ticket"   # nome do ícone em app.tui.icons.IconSet
    TITLE: str = "PAINEL"
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
        self._flash_timer: Timer | None = None
        self._mark_timer: Timer | None = None
        self._marked: dict[str, float] = {}  # chave -> instante em que o marcador some
        self._filter = ""
        self._narrow = False
        self._waiting: str | None = WAITING_TEXT  # texto do cabeçalho enquanto não há estado
        self._not_configured_hint: str | None = None
        self.border_title = self.TITLE
        self._refresh_subtitle()

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
        """O tema mudou: refaz cabeçalho e células (estilos Rich carregam a cor)."""
        self.border_title = f"{getattr(self.icons, self.ICON, '')} {self.TITLE}".strip()
        if self.state is not None:
            self.show_state(self.state)
        elif self._not_configured_hint is not None:
            self.set_not_configured(self._not_configured_hint)
        elif self._waiting is not None:
            self.set_waiting(self._waiting)

    # --- montagem ---------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Static("", classes="panel-head")
        yield Input(placeholder="filtrar… (Esc limpa)", classes="panel-filter")
        yield KeyedTable(self._columns_for_width(), classes="panel-table")
        yield Static("", classes="panel-error")

    def on_mount(self) -> None:
        self.query_one(".panel-filter", Input).display = False
        self._narrow = self._is_narrow()
        self.border_title = f"{getattr(self.icons, self.ICON, '')} {self.TITLE}".strip()
        self.set_waiting()
        register = getattr(self.app, "register_panel", None)
        if register is not None:
            register(self)

    def on_unmount(self) -> None:
        unregister = getattr(self.app, "unregister_panel", None)
        if unregister is not None:
            unregister(self)

    def on_resize(self, event) -> None:  # noqa: ANN001
        narrow = self._is_narrow()
        if narrow != self._narrow:
            self._narrow = narrow
        self._fit_columns()

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
        return [("mark", "", 1), *columns]

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
        self.query_one(".panel-head", Static).update(self.header_text(state))
        if previous is not None:
            now = time.monotonic()
            for key in self.changed_keys(previous, state):
                self._marked[key] = now + MARK_SECONDS
            self._schedule_unmark()
        self._render_rows()

    def counters(self, state: object) -> dict[str, int]:
        """Contadores cujo AUMENTO dispara destaque e bell. Subclasses sobrescrevem."""
        return {}

    def set_waiting(self, text: str = WAITING_TEXT, token: str = "text-faint") -> None:
        self._waiting = text
        self.query_one(".panel-head", Static).update(Text(text, style=self.style(token)))

    def mark_updated(self, when: datetime | None = None) -> None:
        self._last_update = when or clock.now()
        self._refresh_subtitle()

    def set_error(self, message: str | None) -> None:
        """Mostra erro (borda `danger`) mantendo a última lista válida visível."""
        error_widget = self.query_one(".panel-error", Static)
        if message:
            self.add_class("error")
            text = Text(no_wrap=True, overflow="ellipsis")
            text.append(f"{self.icons.error} ", style=self.style("danger", bold=True))
            text.append(message, style=self.style("danger"))
            error_widget.update(text)
            error_widget.display = True
        else:
            self.remove_class("error")
            error_widget.update("")
            error_widget.display = False

    def set_not_configured(self, hint: str) -> None:
        """Fonte sem credencial: neutro (`text-faint`), nunca âmbar; sem borda de erro."""
        self._not_configured_hint = hint
        self.add_class("unconfigured")
        text = Text()
        text.append(f"{self.icons.empty} não configurado", style=self.style("text-muted"))
        text.append(f"\n{hint}", style=self.style("text-faint"))
        self.query_one(".panel-head", Static).update(text)

    def flash(self, seconds: float = FLASH_SECONDS) -> None:
        """Destaque temporário da borda (contador aumentou)."""
        self.add_class("changed")
        if self._flash_timer is not None:
            self._flash_timer.stop()
        self._flash_timer = self.set_timer(seconds, self._end_flash)

    def _end_flash(self) -> None:
        self.remove_class("changed")
        self._flash_timer = None

    # --- a ser definido pelas subclasses ---------------------------------------------

    def header_text(self, state: object) -> Any:
        return str(state)

    def rows(self, state: object) -> list[tuple[str, dict[str, Any]]]:
        """(chave, {coluna: célula}) por item; o painel escolhe as colunas visíveis."""
        return []

    def changed_keys(self, previous: object, state: object) -> set[str]:
        """Chaves novas ou cujo contador subiu; ganham o marcador ● por alguns segundos."""
        old = {key for key, _ in self.rows(previous)}
        return {key for key, _ in self.rows(state) if key not in old}

    def browser_url(self, key: str) -> str | None:
        return None

    def copy_value(self, key: str) -> str | None:
        return None

    def what(self) -> str:
        """Nome do item para mensagens ('chamado', 'conversa', 'e-mail')."""
        return "item"

    # --- lista, filtro, marcadores ---------------------------------------------------

    @property
    def selected_key(self) -> str | None:
        return self.table.selected_key

    def _render_rows(self) -> None:
        items = self.rows(self.state) if self.state is not None else []
        if self._filter:
            needle = self._filter.casefold()
            items = [(key, cells) for key, cells in items
                     if needle in " ".join(_plain(cell) for cell in cells.values()).casefold()]
        now = time.monotonic()
        columns = [key for key, _, _ in self.table.column_specs if key != "mark"]
        rows: list[Row] = []
        marker = Text(self.icons.change, style=self.style("accent", bold=True))
        for key, cells in items:
            mark = marker if self._marked.get(key, 0) > now else NO_MARK
            rows.append((key, [mark, *(cells.get(column, NO_MARK) for column in columns)]))
        self.table.set_rows(rows)

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
        box = self.query_one(".panel-filter", Input)
        box.display = True
        box.focus()

    def clear_filter(self) -> None:
        box = self.query_one(".panel-filter", Input)
        box.value = ""
        box.display = False
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

    # --- interno -----------------------------------------------------------------

    def _refresh_subtitle(self) -> None:
        stamp = self._last_update.strftime("%H:%M:%S") if self._last_update else "--:--:--"
        self.border_subtitle = f"{self.interval}s · {stamp}"


def _plain(cell: Any) -> str:
    return cell.plain if isinstance(cell, Text) else str(cell)
