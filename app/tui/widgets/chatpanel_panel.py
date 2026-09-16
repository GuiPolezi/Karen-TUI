"""Painel do ChatPanel (WhatsApp): conversas em atendimento no nome do técnico."""

from __future__ import annotations

from rich.text import Text
from textual.binding import Binding

from app.state import ChatItem, ChatPanelState
from app.tui.widgets.base_panel import BasePanel


class ChatPanelPanel(BasePanel):
    SOURCE = "chatpanel"
    ICON = "chat"
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
        label, number, faint = self.style("text-muted"), self.style("text", bold=True), self.style("text-faint")
        sep = f" {self.icons.sep} "
        text = Text(no_wrap=True, overflow="ellipsis")
        text.append("Minhas conversas ", style=label).append(str(len(state.mine)), style=number)
        text.append("   Não lidas ", style=label).append(str(state.mine_unread), style=number)
        text.append(
            f"   {sep.strip()}   {state.others_count} em atendimento por outros{sep}{state.total_unread_tab} não lidas na aba",
            style=faint,
        )
        if self.full:
            text.append("   t " + ("esconder" if self.show_others else "mostrar") + " com outros", style=faint)
        if not state.mine:
            text.append(f"\n{self.icons.ok} nenhuma conversa no meu nome", style=faint)
        return text

    def items(self, state: ChatPanelState) -> list[tuple[ChatItem, bool]]:
        result = [(item, True) for item in state.mine]
        if self.show_others:
            result += [(item, False) for item in state.others]
        return result

    def rows(self, state: ChatPanelState) -> list[tuple[str, dict[str, Text]]]:
        icons = self.icons
        rows = []
        for item, mine in self.items(state):
            name = item.name if mine else f"{item.name}  ({item.agent or '?'})"
            name_style = self.style("mine" if mine else "other", bold=mine)
            body = self.style("text" if mine else "other")
            rows.append((item.number, {
                "online": Text(icons.online if item.online else icons.offline,
                               style=self.style("text" if item.online else "text-faint")),
                "time": Text(item.time, style=self.style("text-muted")),
                "name": Text(name, style=name_style),
                "tag": Text(item.tag or "", style=self.style("text-muted")),
                "dept": Text(item.department or "", style=self.style("text-muted")),
                "message": Text(item.last_message, style=body),
                "unread": Text(str(item.unread), style=self.style("accent", bold=True)) if item.unread else Text(""),
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
