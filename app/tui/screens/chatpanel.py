"""Tela ChatPanel (F4): minhas conversas completas + "com outros técnicos" (t)."""

from __future__ import annotations

from textual.app import ComposeResult

from app.tui.screens.base import ModeScreen
from app.tui.widgets.chatpanel_panel import ChatPanelPanel


class ChatPanelScreen(ModeScreen):
    MODE = "chatpanel"
    TITLE_PT = "ChatPanel"
    AUTO_FOCUS = ".panel-table"
    FOOTER = [("{key_up_down}", "mover"), ("{key_enter}", "abrir"), ("t", "com outros"), ("/", "filtrar"),
              ("o", "navegador"), ("y", "copiar número"), ("c", "login"), ("3", "atualizar")]

    def body(self) -> ComposeResult:
        yield ChatPanelPanel(self.app.settings.chatpanel.refresh_seconds, id="chatpanel-full", full=True)  # type: ignore[attr-defined]
