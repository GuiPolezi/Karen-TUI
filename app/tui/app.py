"""Textual App: layout, bindings, relógio e workers das fontes."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.widgets import Static

from app.config import Settings
from app.sources.base import Source, SourceError
from app.tui.widgets.base_panel import BasePanel
from app.tui.widgets.chatpanel_panel import ChatPanelPanel
from app.tui.widgets.email_panel import EmailPanel
from app.tui.widgets.milldesk_panel import MilldeskPanel
from app.tui.widgets.status_bar import StatusBar

log = logging.getLogger("tui")

NARROW_WIDTH = 100  # abaixo disso os painéis de cima empilham

# nome da fonte -> (id do painel, rótulo, fase em que é implementada)
SOURCE_PANELS: dict[str, tuple[str, str, int]] = {
    "email": ("email", "e-mail", 1),
    "milldesk": ("milldesk", "Milldesk", 2),
    "chatpanel": ("chatpanel", "ChatPanel", 4),
}


def build_default_sources(settings: Settings) -> dict[str, Source[Any]]:
    """Fontes reais, uma por painel. Fontes de fases futuras ainda não entram aqui."""
    from app.sources.email_imap import EmailSource
    from app.sources.milldesk import MilldeskSource

    return {
        "email": EmailSource(settings.email),
        "milldesk": MilldeskSource(settings.milldesk, settings.tech_name),
    }


class CmdAllInOneApp(App[None]):
    TITLE = "CMD ALL-IN-ONE"
    CSS_PATH = "styles.tcss"
    BINDINGS = [
        Binding("q", "quit", "Sair"),
        Binding("r", "refresh_all", "Atualizar tudo"),
        Binding("1", "refresh('email')", "Atualizar e-mail"),
        Binding("2", "refresh('milldesk')", "Atualizar Milldesk"),
        Binding("3", "refresh('chatpanel')", "Atualizar ChatPanel"),
        Binding("e", "open_email", "Abrir e-mail"),
        Binding("l", "toggle_log", "Log"),
    ]

    def __init__(self, settings: Settings, sources: dict[str, Source[Any]] | None = None) -> None:
        super().__init__()
        self.settings = settings
        self._sources: dict[str, Source[Any]] = (
            sources if sources is not None else build_default_sources(settings)
        )
        self._refresh_events: dict[str, asyncio.Event] = {}
        self.states: dict[str, Any] = {}  # último estado válido por fonte

    # --- layout ------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Horizontal(id="header"):
            yield Static(self.TITLE, id="title")
            yield Static("", id="clock")
        with Container(id="main"):
            with Horizontal(id="top-row"):
                yield EmailPanel(self.settings.email.refresh_seconds, id="email")
                yield MilldeskPanel(self.settings.milldesk.refresh_seconds, id="milldesk")
            yield ChatPanelPanel(self.settings.chatpanel.refresh_seconds, id="chatpanel")
        yield StatusBar()

    def on_mount(self) -> None:
        self._tick_clock()
        self.set_interval(1.0, self._tick_clock)
        self._apply_layout(self.size.width)
        for name, source in self._sources.items():
            self._start_source(name, source)

    def on_resize(self, event) -> None:  # noqa: ANN001 — tipo vem do Textual
        self._apply_layout(event.size.width)

    def _apply_layout(self, width: int) -> None:
        self.query_one("#main", Container).set_class(width < NARROW_WIDTH, "narrow")

    def _tick_clock(self) -> None:
        now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        self.query_one("#clock", Static).update(f"{self.settings.tech_name} · {now}")

    # --- helpers -----------------------------------------------------------

    @property
    def status_bar(self) -> StatusBar:
        return self.query_one(StatusBar)

    def panel(self, name: str) -> BasePanel:
        panel_id, _, _ = SOURCE_PANELS[name]
        return self.query_one(f"#{panel_id}", BasePanel)

    # --- workers -----------------------------------------------------------

    def _start_source(self, name: str, source: Source[Any]) -> None:
        panel = self.panel(name)
        panel.interval = source.interval
        if not source.configured:
            hint = getattr(source, "config_hint", "verifique o .env")
            panel.set_not_configured(hint)
            log.warning("fonte %s não configurada: %s", name, hint)
            return
        self._refresh_events[name] = asyncio.Event()
        self.run_worker(
            self._source_loop(name, source, panel),
            name=f"source-{name}",
            group=f"source-{name}",
            exclusive=True,
            exit_on_error=False,
        )

    async def _source_loop(self, name: str, source: Source[Any], panel: BasePanel) -> None:
        event = self._refresh_events[name]
        try:
            while True:
                event.clear()
                await self._fetch_once(name, source, panel)
                try:
                    await asyncio.wait_for(event.wait(), timeout=source.interval)
                except asyncio.TimeoutError:
                    pass
        finally:
            try:
                await source.close()
            except Exception as exc:  # fechar nunca pode derrubar a saída do app
                log.warning("erro ao fechar fonte %s: %s", name, exc)

    async def _fetch_once(self, name: str, source: Source[Any], panel: BasePanel) -> None:
        try:
            state = await source.fetch_with_retry()
        except SourceError as exc:
            log.error("fonte %s falhou: %s", name, exc)
            panel.set_error(str(exc))
            return
        except Exception as exc:  # bug na fonte: mostra, registra e segue vivo
            log.exception("erro inesperado na fonte %s", name)
            panel.set_error(f"erro inesperado: {exc}")
            return
        self.states[name] = state
        panel.show_state(state)
        panel.set_error(state.error)
        panel.mark_updated(state.updated_at)

    # --- ações -------------------------------------------------------------

    def action_refresh_all(self) -> None:
        started = [
            SOURCE_PANELS[name][1] for name in self._refresh_events if self._request_refresh(name)
        ]
        if started:
            self.status_bar.set_message("atualizando " + ", ".join(started) + "…")
        else:
            self.status_bar.set_message("nenhuma fonte ativa para atualizar")

    def action_refresh(self, name: str) -> None:
        _, label, phase = SOURCE_PANELS[name]
        if self._request_refresh(name):
            self.status_bar.set_message(f"atualizando {label}…")
        elif name in self._sources:
            self.status_bar.set_message(f"{label}: não configurado")
        else:
            self.status_bar.set_message(f"{label}: não implementado (Fase {phase})")

    def _request_refresh(self, name: str) -> bool:
        event = self._refresh_events.get(name)
        if event is None:
            return False
        event.set()
        return True

    def action_open_email(self) -> None:
        self.status_bar.set_message("detalhe do e-mail chega na Fase 5")

    def action_toggle_log(self) -> None:
        self.status_bar.set_message("painel de log chega na Fase 5")
