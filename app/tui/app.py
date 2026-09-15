"""Textual App: layout, bindings, relógio, workers das fontes e telas auxiliares."""

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
from app.logging_setup import LOG_FILE_NAME
from app.sources.base import Source, SourceError
from app.tui.widgets.base_panel import BasePanel
from app.tui.widgets.chatpanel_panel import ChatPanelPanel
from app.tui.widgets.email_panel import EmailPanel
from app.tui.widgets.log_panel import LogPanel
from app.tui.widgets.milldesk_panel import MilldeskPanel
from app.tui.widgets.status_bar import StatusBar

log = logging.getLogger("tui")

NARROW_WIDTH = 100  # abaixo disso os painéis de cima empilham
LOGIN_SOURCE = "chatpanel"  # única fonte com login humano (janela visível + captcha)

# nome da fonte -> (id do painel, rótulo, fase em que é implementada)
SOURCE_PANELS: dict[str, tuple[str, str, int]] = {
    "email": ("email", "e-mail", 1),
    "milldesk": ("milldesk", "Milldesk", 2),
    "chatpanel": ("chatpanel", "ChatPanel", 4),
}


def build_default_sources(settings: Settings) -> dict[str, Source[Any]]:
    """Fontes reais, uma por painel."""
    from app.sources.chatpanel import ChatPanelSource
    from app.sources.email_imap import EmailSource
    from app.sources.milldesk import MilldeskSource

    return {
        "email": EmailSource(settings.email),
        "milldesk": MilldeskSource(settings.milldesk),
        "chatpanel": ChatPanelSource(settings.chatpanel, settings.tech_name),
    }


def increased_counters(old: dict[str, int], new: dict[str, int]) -> list[str]:
    """Nomes dos contadores que aumentaram entre dois ciclos."""
    return [key for key, value in new.items() if value > old.get(key, value)]


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
        Binding("c", "chatpanel_login", "Login ChatPanel"),
    ]

    def __init__(self, settings: Settings, sources: dict[str, Source[Any]] | None = None) -> None:
        super().__init__()
        self.settings = settings
        self._sources: dict[str, Source[Any]] = (
            sources if sources is not None else build_default_sources(settings)
        )
        self._refresh_events: dict[str, asyncio.Event] = {}
        self.states: dict[str, Any] = {}  # último estado válido por fonte
        self.bell_count = 0  # quantas vezes o bell disparou (útil em testes)
        self._login_requested = False     # tecla c (ou sessão expirada na 1ª vez)
        self._login_in_progress = False
        self._login_on_start_used = False  # a abertura automática vale uma vez por execução
        self.login_count = 0              # quantos logins foram concluídos (útil em testes)

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
            yield LogPanel(self.settings.log_dir / LOG_FILE_NAME)
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
        self.main_screen.query_one("#main", Container).set_class(width < NARROW_WIDTH, "narrow")

    def _tick_clock(self) -> None:
        now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        self.main_screen.query_one("#clock", Static).update(f"{self.settings.tech_name} · {now}")

    # --- helpers -----------------------------------------------------------

    @property
    def main_screen(self):  # noqa: ANN201 — Screen do Textual
        """Tela principal. `self.query_one` olha a tela ATIVA e quebra quando um modal
        (detalhe do e-mail) está aberto e um worker ou o relógio tenta atualizar algo."""
        return self.screen_stack[0]

    @property
    def status_bar(self) -> StatusBar:
        return self.main_screen.query_one(StatusBar)

    def panel(self, name: str) -> BasePanel:
        panel_id, _, _ = SOURCE_PANELS[name]
        return self.main_screen.query_one(f"#{panel_id}", BasePanel)

    def notify_change(self, panel: BasePanel, what: list[str]) -> None:
        """Contador aumentou: destaca o painel por 3 s e toca o bell se configurado."""
        log.info("aumentou em %s: %s", panel.TITLE, ", ".join(what))
        panel.flash()
        if self.settings.notify_bell:
            self.bell_count += 1
            self.bell()

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
                wait_seconds = await self._fetch_once(name, source, panel)
                try:
                    await asyncio.wait_for(event.wait(), timeout=wait_seconds)
                except asyncio.TimeoutError:
                    pass
        finally:
            try:
                await source.close()
            except Exception as exc:  # fechar nunca pode derrubar a saída do app
                log.warning("erro ao fechar fonte %s: %s", name, exc)

    async def _fetch_once(self, name: str, source: Source[Any], panel: BasePanel) -> float:
        """Uma coleta. Devolve quantos segundos esperar até o próximo ciclo."""
        if name == LOGIN_SOURCE and self._login_requested:
            self._login_requested = False
            if not await self._run_login(source, panel):
                return float(source.interval)
        try:
            state = await source.fetch_with_retry()
        except SourceError as exc:
            log.error("fonte %s falhou: %s", name, exc)
            wait = max(float(source.interval), exc.retry_after or 0.0)
            panel.set_error(str(exc) + (f" · aguardando {int(wait)}s" if exc.retry_after else ""))
            if self._should_login_on_start(name, source, exc):
                self._login_on_start_used = True
                self._login_requested = True
                return 0.0  # volta já para o topo do loop, que abre a janela de login
            return wait
        except Exception as exc:  # bug na fonte: mostra, registra e segue vivo
            log.exception("erro inesperado na fonte %s", name)
            panel.set_error(f"erro inesperado: {exc}")
            return float(source.interval)

        previous = self.states.get(name)
        self.states[name] = state
        panel.show_state(state)
        panel.set_error(state.error)
        panel.mark_updated(state.updated_at)
        if previous is not None:
            grew = increased_counters(panel.counters(previous), panel.counters(state))
            if grew:
                self.notify_change(panel, grew)
        return float(source.interval)

    # --- login humano do ChatPanel -------------------------------------------

    def _should_login_on_start(self, name: str, source: Source[Any], exc: SourceError) -> bool:
        """Sessão expirada pela primeira vez nesta execução: abre a janela sozinho (se ligado)."""
        from app.sources.chatpanel import SessionExpiredError

        return (
            name == LOGIN_SOURCE
            and self.settings.chatpanel.login_on_start
            and not self._login_on_start_used
            and hasattr(source, "interactive_login")
            and isinstance(exc.__cause__, SessionExpiredError)
        )

    async def _run_login(self, source: Source[Any], panel: BasePanel) -> bool:
        """Roda dentro do worker da fonte (o perfil do Chromium não pode ter dois donos)."""
        login = getattr(source, "interactive_login", None)
        if login is None:
            return False
        self._login_in_progress = True
        previous = self.states.get(LOGIN_SOURCE)
        panel.set_error(None)
        panel.set_body(
            "[yellow]janela de login aberta[/]\n"
            "[dim]faça o login no Chromium que abriu (o captcha é seu); o painel volta sozinho[/]"
        )
        self.status_bar.set_message("faça o login na janela do Chromium…", seconds=300)
        try:
            user = await login()
        except Exception as exc:
            log.warning("login do ChatPanel não concluído: %s", exc)
            if previous is not None:
                panel.show_state(previous)
            panel.set_error(str(exc))
            self.status_bar.set_message("login do ChatPanel não concluído (c tenta de novo)")
            return False
        finally:
            self._login_in_progress = False
        self.login_count += 1
        panel.set_body("[dim]login ok, lendo o painel…[/]")
        self.status_bar.set_message(f"login ok: {user} · lendo o ChatPanel…")
        return True

    def action_chatpanel_login(self) -> None:
        source = self._sources.get(LOGIN_SOURCE)
        label = SOURCE_PANELS[LOGIN_SOURCE][1]
        if source is None or not hasattr(source, "interactive_login"):
            self.status_bar.set_message(f"{label}: login não disponível")
            return
        if LOGIN_SOURCE not in self._refresh_events:
            self.status_bar.set_message(f"{label}: não configurado")
            return
        if self._login_in_progress:
            self.status_bar.set_message("login já em andamento: veja a janela do Chromium")
            return
        self._login_requested = True
        self._request_refresh(LOGIN_SOURCE)
        self.status_bar.set_message(f"abrindo a janela de login do {label}…")

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
        from app.tui.screens import EmailDetailScreen

        state = self.states.get("email")
        latest = getattr(state, "latest", None)
        if latest is None:
            self.status_bar.set_message("nenhum e-mail carregado ainda")
            return
        self.push_screen(EmailDetailScreen(latest))

    def action_toggle_log(self) -> None:
        visible = self.main_screen.query_one(LogPanel).toggle()
        self.status_bar.set_message("log aberto (l fecha)" if visible else "log fechado")
