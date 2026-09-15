"""Painel do ChatPanel (WhatsApp): conversas em atendimento no nome do técnico."""

from __future__ import annotations

from rich.text import Text
from textual.binding import Binding

from app.state import ChatItem, ChatPanelState
from app.tui.widgets.base_panel import BasePanel


class ChatPanelPanel(BasePanel):
    SOURCE = "chatpanel"
    ICON = "💬"
    TITLE = "CHATPANEL"
    COLUMNS = [("online", "", 1), ("time", "Hora", 5), ("name", "Contato", 30), ("tag", "Tag", 12),
               ("dept", "Depto", 12), ("message", "Última mensagem", None), ("unread", "", 3)]
    COLUMNS_COMPACT = [("online", "", 1), ("time", "Hora", 5), ("name", "Contato", 26), ("tag", "Tag", 12),
                       ("message", "Última mensagem", None), ("unread", "", 3)]
    COLUMNS_NARROW = [("online", "", 1), ("time", "Hora", 5), ("name", "Contato", 20),
                      ("message", "Última mensagem", None), ("unread", "", 3)]
    BINDINGS = [*BasePanel.BINDINGS, Binding("t", "toggle_others", "Com outros", show=False)]

    def counters(self, state: ChatPanelState) -> dict[str, int]:
        return {"conversas": len(state.mine), "não lidas": state.mine_unread}

    @property
    def show_others(self) -> bool:
        prefs = getattr(self.app, "prefs", None)
        return bool(self.full and prefs is not None and prefs.chatpanel_show_others)

    def header_text(self, state: ChatPanelState) -> Text:
        unread_style = "bold yellow" if state.mine_unread else "bold"
        text = Text(no_wrap=True, overflow="ellipsis")
        text.append("Minhas conversas: ").append(str(len(state.mine)), style="bold")
        text.append("   Não lidas: ").append(str(state.mine_unread), style=unread_style)
        text.append(
            f"   ·   {state.others_count} em atendimento por outros · {state.total_unread_tab} não lidas na aba",
            style="dim",
        )
        if self.full:
            text.append("   [t] " + ("esconder" if self.show_others else "mostrar") + " com outros", style="dim")
        if not state.mine:
            text.append("\nnenhuma conversa no meu nome", style="dim")
        return text

    def items(self, state: ChatPanelState) -> list[tuple[ChatItem, bool]]:
        result = [(item, True) for item in state.mine]
        if self.show_others:
            result += [(item, False) for item in state.others]
        return result

    def rows(self, state: ChatPanelState) -> list[tuple[str, dict[str, Text]]]:
        rows = []
        for item, mine in self.items(state):
            dim = "" if mine else "dim"
            name = item.name if mine else f"{item.name}  ({item.agent or '?'})"
            rows.append((item.number, {
                "online": Text("●", style="green") if item.online else Text("○", style="dim"),
                "time": Text(item.time, style="dim"),
                "name": Text(name, style=("bold " + dim).strip()),
                "tag": Text(f"[{item.tag}]" if item.tag else "", style=("cyan " + dim).strip()),
                "dept": Text(item.department or "", style="dim"),
                "message": Text(item.last_message, style=dim),
                "unread": Text(str(item.unread), style="bold yellow") if item.unread else Text(""),
            }))
        return rows

    def changed_keys(self, previous: ChatPanelState, state: ChatPanelState) -> set[str]:
        before = {item.number: item.unread for item, _ in self.items(previous)}
        changed = set()
        for item, _ in self.items(state):
            if item.number not in before or item.unread > before[item.number]:
                changed.add(item.number)
        return changed

    def item_for_key(self, key: str) -> ChatItem | None:
        if self.state is None:
            return None
        return next((item for item, _ in self.items(self.state) if item.number == key), None)

    def action_toggle_others(self) -> None:
        prefs = getattr(self.app, "prefs", None)
        if prefs is None or not self.full:
            return
        prefs.chatpanel_show_others = not prefs.chatpanel_show_others
        self.app.save_prefs()  # type: ignore[attr-defined]
        self.app.refresh_panels("chatpanel")  # type: ignore[attr-defined]

    def browser_url(self, key: str) -> str | None:
        return self.app.settings.urls.chatpanel or None  # type: ignore[attr-defined]

    def copy_value(self, key: str) -> str | None:
        return key

    def what(self) -> str:
        return "conversa"
