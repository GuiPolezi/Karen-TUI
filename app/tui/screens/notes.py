"""Tela Notas (F6): bloco de notas persistente em notes.md (raiz, gitignored), autosave."""

from __future__ import annotations

import logging
from pathlib import Path

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.timer import Timer
from textual.widgets import Static, TextArea

from app.config import ROOT_DIR
from app.tui.screens.base import ModeScreen

NOTES_PATH = ROOT_DIR / "notes.md"
AUTOSAVE_SECONDS = 1.0
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

    def body(self) -> ComposeResult:
        yield Static(self._status(f"{self.path.name} · salva sozinho 1 s após parar de digitar"), id="notes-status")
        yield TextArea(load_notes(self.path), id="notes-text")

    def _status(self, message: str) -> Text:
        return Text(message, style=self.app.tokens.rich("text-faint"))  # type: ignore[attr-defined]

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        self.dirty = True
        if self._timer is not None:
            self._timer.stop()
        self._timer = self.set_timer(AUTOSAVE_SECONDS, self.action_save_now)

    def action_save_now(self) -> None:
        self._timer = None
        text = self.query_one("#notes-text", TextArea).text
        ok = save_notes(text, self.path)
        self.dirty = not ok
        self.query_one("#notes-status", Static).update(self._status(
            f"{self.path.name} · {'salvo' if ok else 'ERRO ao salvar (veja o log)'} · {len(text)} caracteres"
        ))
