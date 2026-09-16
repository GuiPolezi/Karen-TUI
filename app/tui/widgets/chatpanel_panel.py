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
    MORE_KEY = "F4"
    SUMMARY = [("conversas", "conversa|conversas"), ("não lidas", "não lida|não lidas")]
    SUMMARY_IN_TITLE = True
    COLUMNS = [("online", "", 1), ("time", "Hora", 5), ("name", "Contato", 30), ("tagdept", "Tag › Depto", 24),
               ("message", "Última mensagem", None), ("unread", "", 3)]
    COLUMNS_COMPACT = [("online", "", 1), ("time", "Hora", 5), ("name", "Contato", 26), ("tagdept", "Tag › Depto", 22),
                       ("message", "Última mensagem", None), ("unread", "", 3)]
    COLUMNS_NARROW = [("online", "", 1), ("time", "Hora", 5), ("name", "Contato", 20),
                      ("message", "Última mensagem", None), ("unread", "", 3)]
    BINDINGS = [*BasePanel.BINDINGS, Binding("t", "toggle_others", "Com outros", show=False)]

    def counters(self, state: ChatPanelState) -> dict[str, int]:
        return {"conversas": len(state.mine), "não lidas": state.mine_unread}

    def summary_values(self, state: ChatPanelState) -> dict[str, tuple[str, str]]:
        return {
            "conversas": (str(len(state.mine)), "text" if state.mine else "text-faint"),
            "não lidas": (str(state.mine_unread), "text" if state.mine_unread else "text-faint"),
        }

    def empty_text(self) -> str:
        return "nenhuma conversa no seu nome"

    @property
    def show_others(self) -> bool:
        prefs = getattr(self.app, "prefs", None)
        return bool(self.full and prefs is not None and prefs.chatpanel_show_others)

    def foot_text(self, state: ChatPanelState) -> Text | None:
        icons = self.icons
        text = Text(no_wrap=True, overflow="ellipsis")
        text.append(f"{state.others_count} com outros técnicos {icons.sep} {state.total_unread_tab} não lidas na aba",
                    style=self.style("text-faint"))
        if self.full:
            text.append(f"   {icons.sep}   t ", style=self.style("text-faint"))
            text.append("esconder" if self.show_others else "mostrar", style=self.style("text-muted"))
            text.append(" com outros", style=self.style("text-faint"))
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
            tagdept = f" {icons.arrow} ".join(p for p in (item.tag, item.department) if p)
            message = Text(style=body)
            author, sep, rest = item.last_message.partition(": ")
            if sep and len(author) <= 20 and " " not in author.strip():
                message.append(f"{author}: ", style=self.style("text-faint")).append(rest)
            else:
                message.append(item.last_message)
            rows.append((item.number, {
                "online": Text(icons.online if item.online else icons.offline,
                               style=self.style("text" if item.online else "text-faint")),
                "time": Text(item.time, style=self.style("text-muted")),
                "name": Text(name, style=name_style),
                "tagdept": Text(tagdept, style=self.style("text-muted")),
                "message": message,
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
