"""Painel do ChatPanel (WhatsApp): conversas em atendimento no nome do técnico."""

from __future__ import annotations

from rich.table import Table
from rich.text import Text

from app.state import ChatPanelState
from app.tui.widgets.base_panel import BasePanel


class ChatPanelPanel(BasePanel):
    ICON = "💬"
    TITLE = "CHATPANEL"

    def counters(self, state: ChatPanelState) -> dict[str, int]:
        return {"conversas": len(state.mine), "não lidas": state.mine_unread}

    def show_state(self, state: ChatPanelState) -> None:
        unread_style = "bold yellow" if state.mine_unread else "bold"
        title = Text()
        title.append(f"{self.ICON} {self.TITLE} ")
        title.append(f"— minhas conversas: {len(state.mine)} · não lidas: ", style="not bold")
        title.append(str(state.mine_unread), style=unread_style)
        self.border_title = title.markup

        if not state.mine:
            body = Text("nenhuma conversa no meu nome", style="dim")
            body.append(
                f"\n{state.others_count} em atendimento por outros · "
                f"{state.total_unread_tab} não lidas na aba",
                style="dim",
            )
            self.set_body(body)
            return

        table = Table(box=None, show_header=False, expand=True, padding=(0, 1), pad_edge=False)
        table.add_column("online", width=1, no_wrap=True)
        table.add_column("hora", width=5, no_wrap=True, style="dim")
        table.add_column("contato", max_width=28, no_wrap=True, overflow="ellipsis", style="bold")
        table.add_column("tag", max_width=14, no_wrap=True, overflow="ellipsis", style="cyan")
        table.add_column("depto", max_width=12, no_wrap=True, overflow="ellipsis", style="dim")
        table.add_column("mensagem", ratio=1, no_wrap=True, overflow="ellipsis")
        table.add_column("unread", width=3, justify="right", no_wrap=True)

        for item in state.mine:
            dot = Text("●", style="green") if item.online else Text("○", style="dim")
            unread = Text(str(item.unread), style="bold yellow") if item.unread else Text("")
            table.add_row(
                dot,
                item.time,
                item.name,
                f"[{item.tag}]" if item.tag else "",
                item.department or "",
                item.last_message,
                unread,
            )

        footer = Text(
            f"{state.others_count} em atendimento por outros · {state.total_unread_tab} não lidas na aba",
            style="dim",
        )
        from rich.console import Group

        self.set_body(Group(table, footer))
