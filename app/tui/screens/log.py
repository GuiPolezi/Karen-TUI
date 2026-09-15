"""Tela Log (F5 ou l): últimas linhas de logs/app.log com rolagem e filtro por nível."""

from __future__ import annotations

from collections import deque
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.widgets import RichLog, Static

from app.logging_setup import LOG_FILE_NAME
from app.tui.screens.base import ModeScreen

MAX_LINES = 300
REFRESH_SECONDS = 2.0
LEVELS = ("TODOS", "INFO", "WARNING", "ERROR")
LEVEL_RANK = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}


def tail(path: Path, lines: int = MAX_LINES) -> list[str]:
    if not path.exists():
        return [f"(arquivo de log ainda não existe: {path})"]
    with path.open(encoding="utf-8", errors="replace") as handle:
        return [line.rstrip("\r\n") for line in deque(handle, maxlen=lines)]


def line_level(line: str) -> str:
    parts = line.split()
    return parts[2] if len(parts) > 2 and parts[2] in LEVEL_RANK else "INFO"


def filter_lines(lines: list[str], level: str) -> list[str]:
    if level == "TODOS":
        return lines
    minimum = LEVEL_RANK[level]
    return [line for line in lines if LEVEL_RANK.get(line_level(line), 1) >= minimum]


class LogScreen(ModeScreen):
    MODE = "log"
    TITLE_PT = "Log"
    AUTO_FOCUS = "RichLog"
    BINDINGS = [
        Binding("f", "cycle_level", "Filtro de nível", show=True),
        Binding("end", "scroll_end", "Fim", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.level_index = 0
        self._last_rendered: tuple[str, ...] = ()

    @property
    def log_path(self) -> Path:
        return self.app.settings.log_dir / LOG_FILE_NAME  # type: ignore[attr-defined]

    def body(self) -> ComposeResult:
        yield Static("", id="log-status")
        yield RichLog(id="log-lines", highlight=False, markup=False, wrap=False, auto_scroll=True)

    def on_mount(self) -> None:
        super().on_mount()
        self.refresh_lines()
        self.set_interval(REFRESH_SECONDS, self.refresh_lines)

    def refresh_lines(self, force: bool = False) -> None:
        level = LEVELS[self.level_index]
        lines = filter_lines(tail(self.log_path), level)
        snapshot = tuple(lines)
        self.query_one("#log-status", Static).update(
            f"{self.log_path.name} · últimas {MAX_LINES} linhas · filtro: {level} · {len(lines)} linhas  [f] muda o filtro"
        )
        if snapshot == self._last_rendered and not force:
            return
        self._last_rendered = snapshot
        widget = self.query_one("#log-lines", RichLog)
        widget.clear()
        for line in lines:
            widget.write(line)

    def action_cycle_level(self) -> None:
        self.level_index = (self.level_index + 1) % len(LEVELS)
        self.refresh_lines(force=True)

    def action_scroll_end(self) -> None:
        self.query_one("#log-lines", RichLog).scroll_end(animate=False)
