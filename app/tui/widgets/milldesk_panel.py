"""Painel do Milldesk: chamados abertos no nome do técnico + histórico."""

from __future__ import annotations

from rich.console import Group
from rich.rule import Rule
from rich.text import Text

from app.state import MilldeskState
from app.tui.widgets.base_panel import BasePanel

MAX_TICKET_LINES = 3


def format_percentage(value: float) -> str:
    text = f"{value:.1f}".replace(".", ",")
    return text[:-2] if text.endswith(",0") else text


def _line(style: str | None = None) -> Text:
    return Text(no_wrap=True, overflow="ellipsis", style=style or "")


class MilldeskPanel(BasePanel):
    ICON = "🎫"
    TITLE = "MILLDESK"

    def show_state(self, state: MilldeskState) -> None:
        count_style = "bold yellow" if state.my_tickets else "bold green"
        headline = _line()
        headline.append("Abertos no meu nome:  ")
        headline.append(str(state.my_tickets), style=count_style)
        headline.append(f"   (todos: {state.open_total})", style="dim")

        lines: list = [headline]

        if state.my_open_by_status:
            by_status = _line("dim")
            by_status.append(" · ".join(f"{name} {n}" for name, n in state.my_open_by_status.items()))
            lines.append(by_status)

        if state.tickets:
            lines.append(Rule(style="dim"))
            for ticket in state.tickets[:MAX_TICKET_LINES]:
                row = _line()
                row.append(f"#{ticket.id} ", style="cyan")
                row.append(f"{ticket.starttime} ", style="dim")
                row.append(ticket.subject)
                row.append(f"  [{ticket.status}]", style="dim")
                lines.append(row)
            hidden = len(state.tickets) - MAX_TICKET_LINES
            if hidden > 0:
                lines.append(Text(f"… e mais {hidden}", style="dim"))

        history = _line("dim")
        history.append(
            f"Histórico: {state.my_history} chamados · "
            f"{format_percentage(state.my_percentage)}% de {state.total_all_agents}"
        )
        lines.append(history)

        if state.note:
            lines.append(Text(f"⚠ {state.note}", style="yellow", no_wrap=True, overflow="ellipsis"))
        self.set_body(Group(*lines))
