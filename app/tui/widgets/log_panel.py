"""Painel de log: últimas linhas de logs/app.log, alternado com a tecla `l`."""

from __future__ import annotations

from collections import deque
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.timer import Timer
from textual.widgets import Log

MAX_LINES = 50
REFRESH_SECONDS = 2.0


def tail(path: Path, lines: int = MAX_LINES) -> list[str]:
    if not path.exists():
        return [f"(arquivo de log ainda não existe: {path})"]
    with path.open(encoding="utf-8", errors="replace") as handle:
        return [line.rstrip("\r\n") for line in deque(handle, maxlen=lines)]


class LogPanel(Vertical):
    def __init__(self, log_path: Path) -> None:
        super().__init__(id="log-panel")
        self.log_path = log_path
        self._timer: Timer | None = None
        self.border_title = f"📜 LOG · {log_path.name} (últimas {MAX_LINES} linhas)"
        self.display = False

    def compose(self) -> ComposeResult:
        yield Log(id="log-lines", auto_scroll=True)

    def toggle(self) -> bool:
        """Mostra/esconde; devolve True se ficou visível."""
        self.display = not self.display
        if self.display:
            self.refresh_lines()
            self._timer = self.set_interval(REFRESH_SECONDS, self.refresh_lines)
        elif self._timer is not None:
            self._timer.stop()
            self._timer = None
        return self.display

    def refresh_lines(self) -> None:
        widget = self.query_one("#log-lines", Log)
        widget.clear()
        widget.write_lines(tail(self.log_path))
