"""Painel do ChatPanel (WhatsApp). Renderização real chega na Fase 4."""

from __future__ import annotations

from app.tui.widgets.base_panel import BasePanel


class ChatPanelPanel(BasePanel):
    ICON = "💬"
    TITLE = "CHATPANEL"
