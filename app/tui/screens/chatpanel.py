"""Tela ChatPanel (F4): minhas conversas completas + "com outros técnicos" (t)."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding

from app.tui.screens.base import ModeScreen
from app.tui.widgets.chatpanel_panel import ChatPanelPanel


class ChatPanelScreen(ModeScreen):
    MODE = "chatpanel"
    TITLE_PT = "ChatPanel"
    AUTO_FOCUS = ".panel-table"
    BINDINGS = [
        Binding("enter", "noop", "Abrir conversa", show=True),
        Binding("t", "noop", "Com outros", show=True),
        Binding("o", "noop", "Navegador", show=True),
        Binding("y", "noop", "Copiar número", show=True),
        Binding("slash", "noop", "Filtrar", show=True),
    ]

    def body(self) -> ComposeResult:
        yield ChatPanelPanel(self.app.settings.chatpanel.refresh_seconds, id="chatpanel-full", full=True)  # type: ignore[attr-defined]

    def action_noop(self) -> None:
        """Bindings só para aparecer no rodapé; a ação real é do painel/tabela focado."""
