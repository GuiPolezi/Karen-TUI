"""Painel do Milldesk."""

from __future__ import annotations

from rich.console import Group
from rich.text import Text

from app.state import MilldeskState
from app.tui.widgets.base_panel import BasePanel


def format_percentage(value: float) -> str:
    text = f"{value:.1f}".replace(".", ",")
    return text[:-2] if text.endswith(",0") else text


class MilldeskPanel(BasePanel):
    ICON = "🎫"
    TITLE = "MILLDESK"

    def show_state(self, state: MilldeskState) -> None:
        count_style = "bold yellow" if state.my_tickets else "bold"
        first = Text(no_wrap=True, overflow="ellipsis")
        first.append("Chamados no meu nome:   ")
        first.append(str(state.my_tickets), style=count_style)

        second = Text(no_wrap=True, overflow="ellipsis", style="dim")
        second.append(f"{format_percentage(state.my_percentage)}% do total ({state.total_all_agents})")

        lines: list[Text] = [first, second]
        if state.note:
            lines.append(Text(f"⚠ {state.note}", style="yellow", no_wrap=True, overflow="ellipsis"))
        self.set_body(Group(*lines))
