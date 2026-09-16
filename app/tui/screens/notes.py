"""Tela Notas (F6): bloco de notas persistente em notes.md (pasta de dados), autosave.
`TextArea` sem borda e uma linha de status em text-faint ("salvo há 10s · 42 linhas")."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.timer import Timer
from textual.widgets import Static, TextArea

from app import clock
from app.paths import NOTES_PATH
from app.tui.screens.base import ModeScreen
from app.tui.widgets.base_panel import relative_age

AUTOSAVE_SECONDS = 1.0
STATUS_TICK_SECONDS = 1.0
log = logging.getLogger("notes")


def load_notes(path: Path = NOTES_PATH) -> str:
    try:
        return path.read_text(encoding="utf-8") if path.exists() else ""
    except Exception as exc:
        log.warning("não consegui ler %s: %s", path.name, exc)
        return ""


def save_notes(text: str, path: Path = NOTES_PATH) -> bool:
    try:
        path.write_text(text, encoding="utf-8")
        return True
    except Exception as exc:
        log.warning("não consegui salvar %s: %s", path.name, exc)
        return False


class NotesScreen(ModeScreen):
    MODE = "notes"
    TITLE_PT = "Notas"
    AUTO_FOCUS = "TextArea"
    FOOTER = [("^s", "salvar agora"), ("{key_escape}", "dashboard")]
    BINDINGS = [Binding("ctrl+s", "save_now", "Salvar", show=False)]

    def __init__(self, path: Path | None = None) -> None:
        super().__init__()
        self.path = path or NOTES_PATH
        self._timer: Timer | None = None
        self.dirty = False
        self.saved_at: datetime | None = None
        self.save_failed = False

    def body(self) -> ComposeResult:
        yield Static("", id="notes-status")
        yield TextArea(load_notes(self.path), id="notes-text")

    def on_mount(self) -> None:
        super().on_mount()
        self.refresh_status()
        self.set_interval(STATUS_TICK_SECONDS, self.refresh_status)

    def refresh_content(self) -> None:
        self.refresh_status()

    def refresh_status(self) -> None:
        tokens, icons = self.app.tokens, self.app.icons  # type: ignore[attr-defined]
        text = self.query_one("#notes-text", TextArea).text
        lines = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
        status = Text(style=tokens.rich("text-faint"))
        status.append(f"{self.path.name} {icons.sep} ")
        if self.save_failed:
            status.append(f"{icons.error} erro ao salvar (veja o log)", style=tokens.rich("danger"))
        elif self.dirty:
            status.append("editando…", style=tokens.rich("text-muted"))
        elif self.saved_at is not None:
            status.append(f"salvo {relative_age(self.saved_at)}")
        else:
            status.append("salva sozinho 1 s após parar de digitar")
        status.append(f" {icons.sep} {lines} linha{'s' if lines != 1 else ''}")
        self.query_one("#notes-status", Static).update(status)

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        self.dirty = True
        self.refresh_status()
        if self._timer is not None:
            self._timer.stop()
        self._timer = self.set_timer(AUTOSAVE_SECONDS, self.action_save_now)

    def action_save_now(self) -> None:
        self._timer = None
        text = self.query_one("#notes-text", TextArea).text
        ok = save_notes(text, self.path)
        self.dirty = not ok
        self.save_failed = not ok
        if ok:
            self.saved_at = clock.now()
        self.refresh_status()
