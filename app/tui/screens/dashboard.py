"""Dashboard: os três painéis compactos. É a tela inicial (F1 ou d)."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal

from app.tui.screens.base import ModeScreen
from app.tui.widgets.chatpanel_panel import ChatPanelPanel
from app.tui.widgets.email_panel import EmailPanel
from app.tui.widgets.milldesk_panel import MilldeskPanel

NARROW_WIDTH = 100  # abaixo disso os painéis de cima empilham


class DashboardScreen(ModeScreen):
    MODE = "dashboard"
    TITLE_PT = "Dashboard"
    AUTO_FOCUS = "#email .panel-table"
    BINDINGS = [
        Binding("tab", "focus_next", "Próximo painel", show=False),
        Binding("shift+tab", "focus_previous", "Painel anterior", show=False),
    ]

    def body(self) -> ComposeResult:
        settings = self.app.settings  # type: ignore[attr-defined]
        with Container(id="main"):
            with Horizontal(id="top-row"):
                yield EmailPanel(settings.email.refresh_seconds, id="email")
                yield MilldeskPanel(settings.milldesk.refresh_seconds, id="milldesk")
            yield ChatPanelPanel(settings.chatpanel.refresh_seconds, id="chatpanel")

    def on_mount(self) -> None:
        super().on_mount()
        self._apply_layout(self.app.size.width)

    def on_resize(self, event) -> None:  # noqa: ANN001 — tipo vem do Textual
        self._apply_layout(event.size.width)

    def _apply_layout(self, width: int) -> None:
        self.query_one("#main", Container).set_class(width < NARROW_WIDTH, "narrow")
