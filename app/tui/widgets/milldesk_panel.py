"""Painel do Milldesk. Renderização real chega na Fase 2."""

from __future__ import annotations

from app.tui.widgets.base_panel import BasePanel


class MilldeskPanel(BasePanel):
    ICON = "🎫"
    TITLE = "MILLDESK"
