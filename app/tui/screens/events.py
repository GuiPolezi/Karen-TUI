"""Tela Eventos (F7): linha do tempo do dia (e-mails novos, chamados que entraram/saíram,
conversas transferidas, mensagens novas). Mais recente primeiro; a hora só aparece
quando muda o minuto (agrupamento visual)."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.widgets import Static

from app.tui.screens.base import ModeScreen
from app.tui.widgets.keyed_table import KeyedTable

SOURCE_LABEL = {"email": "e-mail", "milldesk": "Milldesk", "chatpanel": "ChatPanel"}
SOURCE_ICON = {"email": "email", "milldesk": "ticket", "chatpanel": "chat"}


class EventsScreen(ModeScreen):
    MODE = "events"
    TITLE_PT = "Eventos"
    AUTO_FOCUS = "KeyedTable"
    FOOTER = [("{key_up_down}", "mover"), ("x", "limpar tela")]
    BINDINGS = [Binding("x", "clear_view", "Limpar tela", show=False)]

    def __init__(self) -> None:
        super().__init__()
        self._hidden: set[int] = set()  # id() dos eventos escondidos por "limpar tela"

    def body(self) -> ComposeResult:
        yield Static("", id="events-status")
        yield KeyedTable([("when", "", 6), ("icon", "", 2), ("source", "", 9), ("text", "", None)],
                         id="events-table", show_header=False)

    def on_mount(self) -> None:
        super().on_mount()
        self.refresh_events()

    def refresh_content(self) -> None:
        self.refresh_events()

    def refresh_events(self) -> None:
        tokens, icons = self.app.tokens, self.app.icons  # type: ignore[attr-defined]
        events = self.app.event_log.latest(300)  # type: ignore[attr-defined]
        visible = [e for e in events if id(e) not in self._hidden]
        rows = []
        previous_minute = None
        for index, event in enumerate(visible):
            minute = event.when.strftime("%H:%M")
            when = minute if minute != previous_minute else ""
            previous_minute = minute
            rows.append((f"{event.when.isoformat()}#{index}", [
                Text(when, style=tokens.rich("text-faint")),
                Text(getattr(icons, SOURCE_ICON.get(event.source, "ticket")), style=tokens.rich("text-muted")),
                Text(SOURCE_LABEL.get(event.source, event.source), style=tokens.rich("text-muted")),
                Text(event.text, style=tokens.rich("text")),
            ]))
        table = self.query_one("#events-table", KeyedTable)
        table.set_rows(rows)
        self.query_one("#events-status", Static).update(Text(
            f"{len(visible)} evento(s) hoje {icons.sep} derivados das diferenças entre coletas {icons.sep} "
            f"logs/events-AAAA-MM-DD.jsonl", style=tokens.rich("text-faint"),
        ))

    def action_clear_view(self) -> None:
        self._hidden = {id(e) for e in self.app.event_log.events}  # type: ignore[attr-defined]
        self.refresh_events()
