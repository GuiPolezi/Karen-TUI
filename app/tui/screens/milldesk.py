"""Tela Milldesk (F3): todos os chamados abertos no meu nome, ordenáveis; Enter abre."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding

from app.tui.screens.base import ModeScreen
from app.tui.widgets.milldesk_panel import MilldeskPanel


class MilldeskScreen(ModeScreen):
    MODE = "milldesk"
    TITLE_PT = "Milldesk"
    AUTO_FOCUS = ".panel-table"
    BINDINGS = [
        Binding("enter", "noop", "Abrir chamado", show=True),
        Binding("s", "noop", "Ordenar", show=True),
        Binding("o", "noop", "Navegador", show=True),
        Binding("y", "noop", "Copiar ID", show=True),
        Binding("slash", "noop", "Filtrar", show=True),
    ]

    def body(self) -> ComposeResult:
        yield MilldeskPanel(self.app.settings.milldesk.refresh_seconds, id="milldesk-full", full=True)  # type: ignore[attr-defined]

    def action_noop(self) -> None:
        """Bindings só para aparecer no rodapé; a ação real é do painel/tabela focado."""
