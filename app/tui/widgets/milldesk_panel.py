"""Painel do Milldesk: chamados abertos no nome do técnico, com SLA e ordenação."""

from __future__ import annotations

from datetime import datetime

from rich.text import Text
from textual.binding import Binding

from app.state import MilldeskState, MilldeskTicket, format_remaining
from app.tui.widgets.base_panel import BasePanel

SORT_MODES = ("sla", "data", "status")
SORT_LABELS = {"sla": "SLA mais próximo", "data": "mais recente", "status": "status"}
SLA_WARNING_HOURS = 4


def format_percentage(value: float) -> str:
    text = f"{value:.1f}".replace(".", ",")
    return text[:-2] if text.endswith(",0") else text


def sla_style(ticket: MilldeskTicket, now: datetime | None = None) -> str:
    remaining = ticket.sla_remaining(now)
    if remaining is None:
        return "dim"
    hours = remaining.total_seconds() / 3600
    if hours < 0:
        return "bold red"
    if hours < SLA_WARNING_HOURS:
        return "bold yellow"
    return "green"


def sla_text(ticket: MilldeskTicket, now: datetime | None = None) -> str:
    remaining = ticket.sla_remaining(now)
    if remaining is None:
        return (ticket.sla_expiration or "")[:9]
    return format_remaining(remaining)


def sorted_tickets(tickets: list[MilldeskTicket], mode: str, now: datetime | None = None) -> list[MilldeskTicket]:
    now = now or datetime.now()
    if mode == "status":
        return sorted(tickets, key=lambda t: (t.status, -(t.opened_at or datetime.min).timestamp()))
    if mode == "data":
        return sorted(tickets, key=lambda t: (t.opened_at or datetime.min), reverse=True)
    far = datetime.max
    return sorted(tickets, key=lambda t: (t.sla_deadline or far, t.id))


class MilldeskPanel(BasePanel):
    SOURCE = "milldesk"
    ICON = "🎫"
    TITLE = "MILLDESK"
    COLUMNS = [("id", "#", 6), ("time", "Abertura", 11), ("subject", "Assunto", None),
               ("status", "Status", 20), ("sla", "SLA", 9)]
    COLUMNS_COMPACT = [("id", "#", 6), ("subject", "Assunto", None), ("status", "Status", 12), ("sla", "SLA", 8)]
    COLUMNS_NARROW = [("id", "#", 6), ("subject", "Assunto", None), ("sla", "SLA", 8)]
    BINDINGS = [*BasePanel.BINDINGS, Binding("s", "cycle_sort", "Ordenar", show=False)]

    def counters(self, state: MilldeskState) -> dict[str, int]:
        return {"abertos": state.my_tickets}

    @property
    def sort_mode(self) -> str:
        prefs = getattr(self.app, "prefs", None)
        mode = getattr(prefs, "milldesk_sort", "sla")
        return mode if mode in SORT_MODES else "sla"

    def header_text(self, state: MilldeskState) -> Text:
        count_style = "bold yellow" if state.my_tickets else "bold green"
        text = Text(no_wrap=True, overflow="ellipsis")
        text.append("Abertos no meu nome: ").append(str(state.my_tickets), style=count_style)
        text.append(f"  (todos: {state.open_total})", style="dim")
        if state.my_open_by_status:
            text.append("  ·  " + " · ".join(f"{name} {n}" for name, n in state.my_open_by_status.items()), style="dim")
        text.append(
            f"\nHistórico: {state.my_history} chamados · {format_percentage(state.my_percentage)}% de "
            f"{state.total_all_agents}  ·  ordem: {SORT_LABELS[self.sort_mode]}",
            style="dim",
        )
        if state.note:
            text.append(f"\n⚠ {state.note}", style="yellow")
        return text

    def rows(self, state: MilldeskState) -> list[tuple[str, dict[str, Text]]]:
        now = datetime.now()
        rows = []
        for ticket in sorted_tickets(state.tickets, self.sort_mode, now):
            opened = ticket.opened_at
            when = opened.strftime("%d/%m %H:%M") if opened else ticket.starttime
            rows.append((str(ticket.id), {
                "id": Text(f"#{ticket.id}", style="cyan"),
                "time": Text(when, style="dim"),
                "subject": Text(ticket.subject),
                "status": Text(ticket.status, style="dim"),
                "sla": Text(sla_text(ticket, now), style=sla_style(ticket, now)),
            }))
        return rows

    def item_for_key(self, key: str) -> MilldeskTicket | None:
        if self.state is None:
            return None
        return next((t for t in self.state.tickets if str(t.id) == key), None)

    def action_cycle_sort(self) -> None:
        prefs = getattr(self.app, "prefs", None)
        if prefs is None:
            return
        index = SORT_MODES.index(self.sort_mode)
        prefs.milldesk_sort = SORT_MODES[(index + 1) % len(SORT_MODES)]
        self.app.save_prefs()  # type: ignore[attr-defined]
        self.app.notify(f"Milldesk ordenado por {SORT_LABELS[prefs.milldesk_sort]}")
        self.app.refresh_panels("milldesk")  # type: ignore[attr-defined]

    def browser_url(self, key: str) -> str | None:
        return self.app.settings.urls.milldesk or None  # type: ignore[attr-defined]

    def copy_value(self, key: str) -> str | None:
        return key

    def what(self) -> str:
        return "chamado"
