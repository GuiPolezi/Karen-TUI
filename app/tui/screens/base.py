"""Tela de modo: TopBar com o nome da tela, corpo definido pela subclasse e FooterBar com
os atalhos da tela. Trocar de tela nunca pausa a coleta (workers ficam no App)."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen

from app.tui.widgets.footer_bar import FooterBar, FooterItem, format_items
from app.tui.widgets.top_bar import TopBar

# atalhos comuns a todas as telas de modo; `{nome}` é substituído pelo ícone do conjunto
COMMON_FOOTER: list[FooterItem] = [(":", "launcher"), ("?", "ajuda")]


class ModeScreen(Screen):
    MODE = "dashboard"
    TITLE_PT = "Dashboard"
    FOOTER: list[FooterItem] = []  # atalhos específicos da tela, antes dos comuns

    def compose(self) -> ComposeResult:
        yield TopBar(self.TITLE_PT, self.app.settings.tech_name)  # type: ignore[attr-defined]
        yield from self.body()
        yield FooterBar()

    def body(self) -> ComposeResult:
        yield from ()

    def on_mount(self) -> None:
        register = getattr(self.app, "register_mode_screen", None)
        if register is not None:
            register(self)

    # --- rodapé ---------------------------------------------------------------------

    def footer_items(self) -> list[FooterItem]:
        return format_items([*self.FOOTER, *COMMON_FOOTER], self.app.icons)  # type: ignore[attr-defined]

    def refresh_footer(self) -> None:
        for footer in self.query(FooterBar):
            footer.refresh_items()

    # --- tema -------------------------------------------------------------------------

    def refresh_theme(self) -> None:
        """O tema mudou: barras e conteúdo com estilos Rich precisam re-renderizar."""
        for bar in self.query(TopBar):
            bar.refresh_theme()
        self.refresh_footer()
        self.refresh_content()

    def refresh_content(self) -> None:
        """Subclasses re-renderizam o que não é painel (painéis o App já cuida)."""
