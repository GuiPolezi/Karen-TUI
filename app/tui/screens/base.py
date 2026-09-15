"""Tela de modo: barra superior com o nome da tela, corpo definido pela subclasse e Footer
com os bindings visíveis. Trocar de tela nunca pausa a coleta (workers ficam no App)."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Footer

from app.tui.widgets.top_bar import TopBar


class ModeScreen(Screen):
    MODE = "dashboard"
    TITLE_PT = "Dashboard"

    def compose(self) -> ComposeResult:
        yield TopBar(self.TITLE_PT, self.app.settings.tech_name)  # type: ignore[attr-defined]
        yield from self.body()
        yield Footer()

    def body(self) -> ComposeResult:
        yield from ()

    def on_mount(self) -> None:
        register = getattr(self.app, "register_mode_screen", None)
        if register is not None:
            register(self)
