"""Textual App: layout, bindings, relógio e ponto de encaixe dos workers."""

from __future__ import annotations

from datetime import datetime

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.widgets import Static

from app.config import Settings
from app.tui.widgets.base_panel import BasePanel
from app.tui.widgets.chatpanel_panel import ChatPanelPanel
from app.tui.widgets.email_panel import EmailPanel
from app.tui.widgets.milldesk_panel import MilldeskPanel
from app.tui.widgets.status_bar import StatusBar

NARROW_WIDTH = 100  # abaixo disso os painéis de cima empilham

# nome da fonte -> (id do painel, fase em que é implementada)
SOURCE_PANELS: dict[str, tuple[str, int]] = {
    "email": ("email", 1),
    "milldesk": ("milldesk", 2),
    "chatpanel": ("chatpanel", 4),
}


class CmdAllInOneApp(App[None]):
    TITLE = "CMD ALL-IN-ONE"
    CSS_PATH = "styles.tcss"
    BINDINGS = [
        Binding("q", "quit", "Sair"),
        Binding("r", "refresh_all", "Atualizar tudo"),
        Binding("1", "refresh('email')", "Atualizar e-mail"),
        Binding("2", "refresh('milldesk')", "Atualizar Milldesk"),
        Binding("3", "refresh('chatpanel')", "Atualizar ChatPanel"),
        Binding("e", "open_email", "Abrir e-mail"),
        Binding("l", "toggle_log", "Log"),
    ]

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings

    # --- layout ------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Horizontal(id="header"):
            yield Static(self.TITLE, id="title")
            yield Static("", id="clock")
        with Container(id="main"):
            with Horizontal(id="top-row"):
                yield EmailPanel(self.settings.email.refresh_seconds, id="email")
                yield MilldeskPanel(self.settings.milldesk.refresh_seconds, id="milldesk")
            yield ChatPanelPanel(self.settings.chatpanel.refresh_seconds, id="chatpanel")
        yield StatusBar()

    def on_mount(self) -> None:
        self._tick_clock()
        self.set_interval(1.0, self._tick_clock)
        self._apply_layout(self.size.width)

    def on_resize(self, event) -> None:  # noqa: ANN001 — tipo vem do Textual
        self._apply_layout(event.size.width)

    def _apply_layout(self, width: int) -> None:
        self.query_one("#main", Container).set_class(width < NARROW_WIDTH, "narrow")

    def _tick_clock(self) -> None:
        now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        self.query_one("#clock", Static).update(f"{self.settings.tech_name} · {now}")

    # --- helpers -----------------------------------------------------------

    @property
    def status_bar(self) -> StatusBar:
        return self.query_one(StatusBar)

    def panel(self, name: str) -> BasePanel:
        panel_id, _ = SOURCE_PANELS[name]
        return self.query_one(f"#{panel_id}", BasePanel)

    # --- ações -------------------------------------------------------------

    def action_refresh_all(self) -> None:
        for name in SOURCE_PANELS:
            self.action_refresh(name)

    def action_refresh(self, name: str) -> None:
        _, phase = SOURCE_PANELS[name]
        self.status_bar.set_message(f"{name}: não implementado (Fase {phase})")

    def action_open_email(self) -> None:
        self.status_bar.set_message("detalhe do e-mail chega na Fase 5")

    def action_toggle_log(self) -> None:
        self.status_bar.set_message("painel de log chega na Fase 5")
