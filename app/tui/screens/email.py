"""Tela E-mail (F2): últimos N e-mails com cursor; Enter abre o e-mail."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding

from app.tui.screens.base import ModeScreen
from app.tui.widgets.email_panel import EmailPanel


class EmailScreen(ModeScreen):
    MODE = "email"
    TITLE_PT = "E-mail"
    AUTO_FOCUS = ".panel-table"
    FOOTER = [("{key_up_down}", "mover"), ("{key_enter}", "abrir"), ("u", "só não lidos"), ("/", "filtrar"),
              ("o", "navegador"), ("y", "copiar remetente"), ("1", "atualizar")]
    BINDINGS = [Binding("u", "toggle_unseen", "Só não lidos", show=False)]

    def body(self) -> ComposeResult:
        yield EmailPanel(self.app.settings.email.refresh_seconds, id="email-full", full=True)  # type: ignore[attr-defined]

    def action_toggle_unseen(self) -> None:
        prefs = self.app.prefs  # type: ignore[attr-defined]
        prefs.email_only_unseen = not prefs.email_only_unseen
        self.app.save_prefs()  # type: ignore[attr-defined]
        self.app.notify("mostrando só não lidos" if prefs.email_only_unseen else "mostrando todos os e-mails")
        self.app.refresh_panels("email")  # type: ignore[attr-defined]
