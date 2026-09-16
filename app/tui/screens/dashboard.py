"""Dashboard: os três painéis compactos. É a tela inicial (F1 ou d).

Layout responsivo por classes de breakpoint da própria tela (Textual):
- largura: `-narrow` (< 100 colunas: E-mail e Milldesk empilham) / `-wide`
- altura: `-short` (< 25 linhas: só contadores e SLA) / `-mid` / `-tall` (>= 30: Digits)
O CSS e os painéis leem essas classes; não há `if` de largura espalhado.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.widgets import Rule

from app.tui.screens.base import ModeScreen
from app.tui.widgets.base_panel import BasePanel
from app.tui.widgets.chatpanel_panel import ChatPanelPanel
from app.tui.widgets.email_panel import EmailPanel
from app.tui.widgets.milldesk_panel import MilldeskPanel

NARROW_WIDTH = 100   # abaixo disso os painéis de cima empilham
SHORT_HEIGHT = 25    # abaixo disso o Dashboard esconde cartão e lista dos painéis de cima
TALL_HEIGHT = 30     # a partir daqui os contadores viram Digits


class DashboardScreen(ModeScreen):
    MODE = "dashboard"
    TITLE_PT = "Dashboard"
    AUTO_FOCUS = "#email .panel-table"
    HORIZONTAL_BREAKPOINTS = [(0, "-narrow"), (NARROW_WIDTH, "-wide")]
    VERTICAL_BREAKPOINTS = [(0, "-short"), (SHORT_HEIGHT, "-mid"), (TALL_HEIGHT, "-tall")]
    FOOTER = [("{key_up_down}", "mover"), ("{key_enter}", "abrir"), ("{key_tab}", "painel"), ("/", "filtrar"),
              ("o", "navegador"), ("y", "copiar"), ("e", "e-mail"), ("m", "silêncio"), ("T", "tema")]
    BINDINGS = [
        Binding("tab", "focus_next", "Próximo painel", show=False),
        Binding("shift+tab", "focus_previous", "Painel anterior", show=False),
    ]

    def body(self) -> ComposeResult:
        settings = self.app.settings  # type: ignore[attr-defined]
        with Container(id="main"):
            with Horizontal(id="top-row"):
                yield EmailPanel(settings.email.refresh_seconds, id="email")
                yield Rule(orientation="vertical", id="top-rule")
                yield MilldeskPanel(settings.milldesk.refresh_seconds, id="milldesk")
            yield ChatPanelPanel(settings.chatpanel.refresh_seconds, id="chatpanel")

    def on_resize(self, event) -> None:  # noqa: ANN001 — tipo vem do Textual
        # as classes de breakpoint já foram aplicadas pelo Textual; os painéis releem
        for panel in self.query(BasePanel):
            panel.call_after_refresh(lambda p=panel: p.on_resize(event) if p.is_attached else None)
