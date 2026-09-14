"""Barra inferior: atalhos fixos à esquerda e mensagem transitória à direita."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.timer import Timer
from textual.widgets import Static

SHORTCUTS = (
    "[b]r[/] atualizar tudo  [b]1/2/3[/] atualizar painel  "
    "[b]e[/] abrir e-mail  [b]l[/] log  [b]q[/] sair"
)


class StatusBar(Horizontal):
    def __init__(self) -> None:
        super().__init__(id="status-bar")
        self._timer: Timer | None = None

    def compose(self) -> ComposeResult:
        yield Static(SHORTCUTS, id="status-shortcuts")
        yield Static("", id="status-message")

    def set_message(self, text: str, seconds: float = 3.0) -> None:
        """Mostra uma mensagem por alguns segundos e depois limpa."""
        self.query_one("#status-message", Static).update(text)
        if self._timer is not None:
            self._timer.stop()
        self._timer = self.set_timer(seconds, self.clear_message)

    def clear_message(self) -> None:
        self.query_one("#status-message", Static).update("")
        self._timer = None
