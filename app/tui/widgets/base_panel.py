"""Painel base: borda com título/subtítulo, corpo, linha de erro, espera e destaque."""

from __future__ import annotations

from datetime import datetime

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.timer import Timer
from textual.widgets import Static

WAITING_TEXT = "[dim]aguardando…[/]"
FLASH_SECONDS = 3.0


class BasePanel(Vertical):
    """Container com borda. Subclasses definem ícone/título e como renderizar o estado."""

    ICON: str = "▪"
    TITLE: str = "PAINEL"

    def __init__(self, interval: int, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self.interval = interval
        self._last_update: datetime | None = None
        self._flash_timer: Timer | None = None
        self.border_title = f"{self.ICON} {self.TITLE}"
        self._refresh_subtitle()

    def compose(self) -> ComposeResult:
        yield Static(WAITING_TEXT, classes="panel-body")
        yield Static("", classes="panel-error")

    # --- API usada pelos workers -------------------------------------------

    def show_state(self, state: object) -> None:
        """Renderiza um estado publicado pela fonte. Subclasses sobrescrevem."""
        self.set_body(str(state))

    def counters(self, state: object) -> dict[str, int]:
        """Contadores cujo AUMENTO dispara destaque e bell. Subclasses sobrescrevem."""
        return {}

    def set_waiting(self, text: str = WAITING_TEXT) -> None:
        self.query_one(".panel-body", Static).update(text)

    def set_body(self, renderable: object) -> None:
        """Substitui o corpo do painel (Rich renderable ou markup)."""
        self.query_one(".panel-body", Static).update(renderable)  # type: ignore[arg-type]

    def mark_updated(self, when: datetime | None = None) -> None:
        self._last_update = when or datetime.now()
        self._refresh_subtitle()

    def set_error(self, message: str | None) -> None:
        """Mostra erro (borda vermelha) mantendo o último corpo válido visível."""
        error_widget = self.query_one(".panel-error", Static)
        if message:
            self.add_class("error")
            error_widget.update(f"[bold]✖[/] {message}")
            error_widget.display = True
        else:
            self.remove_class("error")
            error_widget.update("")
            error_widget.display = False

    def set_not_configured(self, hint: str) -> None:
        """Fonte sem credencial: aviso amarelo, sem borda de erro."""
        self.add_class("unconfigured")
        self.set_body(f"[yellow]não configurado[/]\n[dim]{hint}[/]")

    def flash(self, seconds: float = FLASH_SECONDS) -> None:
        """Destaque temporário da borda (contador aumentou)."""
        self.add_class("changed")
        if self._flash_timer is not None:
            self._flash_timer.stop()
        self._flash_timer = self.set_timer(seconds, self._end_flash)

    def _end_flash(self) -> None:
        self.remove_class("changed")
        self._flash_timer = None

    # --- interno -----------------------------------------------------------

    def _refresh_subtitle(self) -> None:
        stamp = self._last_update.strftime("%H:%M:%S") if self._last_update else "--:--:--"
        self.border_subtitle = f"{self.interval}s · {stamp}"
