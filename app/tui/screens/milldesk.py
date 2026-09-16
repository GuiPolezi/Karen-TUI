"""Tela Milldesk (F3): todos os chamados abertos no meu nome, ordenáveis; Enter abre."""

from __future__ import annotations

from textual.app import ComposeResult

from app.tui.screens.base import ModeScreen
from app.tui.widgets.milldesk_panel import SORT_LABELS, MilldeskPanel


class MilldeskScreen(ModeScreen):
    MODE = "milldesk"
    TITLE_PT = "Milldesk"
    AUTO_FOCUS = ".panel-table"

    def body(self) -> ComposeResult:
        yield MilldeskPanel(self.app.settings.milldesk.refresh_seconds, id="milldesk-full", full=True)  # type: ignore[attr-defined]

    def footer_items(self) -> list[tuple[str, str]]:
        prefs = self.app.prefs  # type: ignore[attr-defined]
        order = SORT_LABELS.get(prefs.milldesk_sort, prefs.milldesk_sort)
        self.FOOTER = [("{key_up_down}", "mover"), ("{key_enter}", "abrir"), ("s", f"ordem: {order}"),
                       ("/", "filtrar"), ("o", "navegador"), ("y", "copiar ID"), ("2", "atualizar")]
        return super().footer_items()
