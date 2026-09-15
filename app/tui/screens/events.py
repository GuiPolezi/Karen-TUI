"""Tela Eventos (F7): linha do tempo do dia (e-mails novos, chamados que entraram/saíram,
conversas transferidas, mensagens novas). Mais recente primeiro."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.widgets import Static

from app.tui.screens.base import ModeScreen
from app.tui.widgets.keyed_table import KeyedTable

SOURCE_LABEL = {"email": "e-mail", "milldesk": "Milldesk", "chatpanel": "ChatPanel"}
KIND_STYLE = {
    "new_email": "cyan", "ticket_in": "green", "ticket_out": "yellow", "ticket_status": "",
    "chat_in": "green", "chat_out": "yellow", "chat_message": "cyan",
}


class EventsScreen(ModeScreen):
    MODE = "events"
    TITLE_PT = "Eventos"
    AUTO_FOCUS = "KeyedTable"
    BINDINGS = [Binding("x", "clear_view", "Limpar tela", show=True)]

    def __init__(self) -> None:
        super().__init__()
        self._hidden: set[int] = set()  # id() dos eventos escondidos por "limpar tela"

    def body(self) -> ComposeResult:
        yield Static("", id="events-status")
        yield KeyedTable([("when", "Hora", 8), ("source", "Fonte", 9), ("text", "Evento", None)],
                         id="events-table", show_header=True)

    def on_mount(self) -> None:
        super().on_mount()
        self.refresh_events()

    def refresh_events(self) -> None:
        events = self.app.event_log.latest(300)  # type: ignore[attr-defined]
        total = len(self.app.event_log.events)  # type: ignore[attr-defined]
        visible = [e for e in events if id(e) not in self._hidden]
        rows = []
        for index, event in enumerate(visible):
            rows.append((f"{event.when.isoformat()}#{index}", [
                Text(event.when.strftime("%H:%M:%S"), style="dim"),
                Text(SOURCE_LABEL.get(event.source, event.source), style="bold"),
                Text(event.text, style=KIND_STYLE.get(event.kind, "")),
            ]))
        table = self.query_one("#events-table", KeyedTable)
        table.set_rows(rows)
        self.query_one("#events-status", Static).update(Text(
            f"{len(visible)} evento(s) hoje · derivados das diferenças entre coletas · "
            f"arquivo logs/events-AAAA-MM-DD.jsonl  [x] limpa a tela", style="dim",
        ))

    def action_clear_view(self) -> None:
        self._hidden = {id(e) for e in self.app.event_log.events}  # type: ignore[attr-defined]
        self.refresh_events()
