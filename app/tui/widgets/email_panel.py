"""Painel de e-mail (IMAP). Renderização real chega na Fase 1."""

from __future__ import annotations

from app.tui.widgets.base_panel import BasePanel


class EmailPanel(BasePanel):
    ICON = "📧"
    TITLE = "E-MAIL"
