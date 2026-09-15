"""Textual App: modos (telas), workers das fontes, publicação de estado nos painéis,
bindings globais, avisos, abrir no navegador/copiar e o login humano do ChatPanel.

Os workers vivem aqui, não nas telas: trocar de tela nunca pausa a coleta. Cada painel
vivo (no Dashboard ou numa tela cheia) se registra em `register_panel` e recebe o mesmo
estado publicado.
"""

from __future__ import annotations

import asyncio
import logging
import time
import webbrowser
from pathlib import Path
from typing import Any

from textual.app import App
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Input

from app.config import Settings
from app.prefs import PREFS_PATH, Prefs, load_prefs, save_prefs
from app.sources.base import Source, SourceError
from app.tui.screens import MODE_SCREENS, EmailDetailScreen, ModeScreen
from app.tui.widgets.base_panel import BasePanel

log = logging.getLogger("tui")

LOGIN_SOURCE = "chatpanel"  # única fonte com login humano (janela visível + captcha)
SILENCE_MINUTES = 30

# nome da fonte -> (id do painel no Dashboard, rótulo, fase em que é implementada)
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
    ENABLE_COMMAND_PALETTE = False  # o launcher (Fase 6.4) decide o que fazer com Ctrl+P
    MODES = dict(MODE_SCREENS)
    BINDINGS = [
        Binding("q", "quit", "Sair", priority=True),
        Binding("escape", "escape", "Voltar", show=False, priority=True),
        Binding("f1", "goto('dashboard')", "Dashboard", priority=True),
        Binding("d", "goto('dashboard')", "Dashboard", show=False),
        Binding("f2", "goto('email')", "E-mail", priority=True),
        Binding("f3", "goto('milldesk')", "Milldesk", priority=True),
        Binding("f4", "goto('chatpanel')", "ChatPanel", priority=True),
        Binding("f5", "goto('log')", "Log", priority=True),
        Binding("f6", "goto('notes')", "Notas", priority=True),
        Binding("l", "goto('log')", "Log", show=False),
        Binding("r", "refresh_all", "Atualizar", show=True),
        Binding("1", "refresh('email')", "Atualizar e-mail", show=False),
        Binding("2", "refresh('milldesk')", "Atualizar Milldesk", show=False),
        Binding("3", "refresh('chatpanel')", "Atualizar ChatPanel", show=False),
        Binding("e", "open_email", "Último e-mail", show=True),
        Binding("c", "chatpanel_login", "Login ChatPanel", show=False),
        Binding("m", "toggle_silence", "Silenciar", show=False),
    ]

    def __init__(
        self,
        settings: Settings,
        sources: dict[str, Source[Any]] | None = None,
        prefs: Prefs | None = None,
        prefs_path: Path | None = PREFS_PATH,
    ) -> None:
        super().__init__()
        self.settings = settings
        self._sources: dict[str, Source[Any]] = (
            sources if sources is not None else build_default_sources(settings)
        )
        self.prefs = prefs if prefs is not None else load_prefs(prefs_path) if prefs_path else Prefs()
        self._prefs_path = prefs_path
        self._refresh_events: dict[str, asyncio.Event] = {}
        self.states: dict[str, Any] = {}       # último estado válido por fonte
        self.errors: dict[str, str | None] = {}  # último erro por fonte (para painéis novos)
        self.panels: dict[str, list[BasePanel]] = {}  # painéis vivos por fonte
        self.mode_screens: dict[str, ModeScreen] = {}
        self.bell_count = 0    # quantas vezes o bell disparou (útil em testes)
        self.messages: list[str] = []  # avisos emitidos (útil em testes)
        self.last_message = ""
        self._away: dict[str, list[str]] = {}  # mudanças enquanto o Dashboard não estava na frente
        self._login_requested = False
        self._login_in_progress = False
        self._login_on_start_used = False
        self.login_count = 0

    # --- ciclo de vida --------------------------------------------------------

    def on_mount(self) -> None:
        mode = self.prefs.last_screen if self.prefs.last_screen in self.MODES else "dashboard"
        self.switch_mode(mode)
        for name, source in self._sources.items():
            self._start_source(name, source)

    def register_mode_screen(self, screen: ModeScreen) -> None:
        self.mode_screens[screen.MODE] = screen

    def register_panel(self, panel: BasePanel) -> None:
        self.panels.setdefault(panel.SOURCE, []).append(panel)
        source = self._sources.get(panel.SOURCE)
        if source is not None:
            panel.interval = source.interval
            if not source.configured:
                panel.set_not_configured(getattr(source, "config_hint", "verifique o .env"))
                return
        state = self.states.get(panel.SOURCE)
        if state is not None:
            panel.show_state(state)
            panel.mark_updated(state.updated_at)
        panel.set_error(self.errors.get(panel.SOURCE))

    def unregister_panel(self, panel: BasePanel) -> None:
        panels = self.panels.get(panel.SOURCE, [])
        if panel in panels:
            panels.remove(panel)

    @property
    def dashboard(self) -> ModeScreen:
        return self.mode_screens["dashboard"]

    @property
    def main_screen(self) -> ModeScreen:  # compatibilidade com código antigo
        return self.dashboard

    def panel(self, name: str) -> BasePanel:
        """Painel da fonte no Dashboard."""
        panel_id, _, _ = SOURCE_PANELS[name]
        return self.dashboard.query_one(f"#{panel_id}", BasePanel)

    def save_prefs(self) -> None:
        if self._prefs_path is not None:
            save_prefs(self.prefs, self._prefs_path)

    # --- avisos ----------------------------------------------------------------

    def notify(self, message: str, **kwargs: Any) -> None:  # type: ignore[override]
        self.last_message = message
        self.messages.append(message)
        super().notify(message, **kwargs)

    @property
    def silenced(self) -> bool:
        return time.time() < self.prefs.silenced_until

    @property
    def header_extra(self) -> str:
        return "🔇 " if self.silenced else ""

    def notify_change(self, name: str, what: list[str]) -> None:
        """Contador aumentou: destaca os painéis da fonte por 3 s, toca o bell/toast."""
        label = SOURCE_PANELS.get(name, (name, name, 0))[1]
        log.info("aumentou em %s: %s", label, ", ".join(what))
        for panel in self.panels.get(name, []):
            panel.flash()
        if self.current_mode != "dashboard":
            self._away.setdefault(label, []).extend(what)
        if self.silenced:
            return
        if self.settings.notify_bell:
            self.bell_count += 1
            self.bell()
        if self.settings.notify_toast:
            self._toast(f"{label}: {', '.join(what)}")

    def _toast(self, message: str) -> None:
        try:
            from winotify import Notification  # type: ignore[import-not-found]
        except ImportError:
            log.debug("NOTIFY_TOAST=true mas winotify não está instalado (pip install winotify)")
            return

        def show() -> None:
            try:
                Notification(app_id=self.TITLE, title=self.TITLE, msg=message).show()
            except Exception as exc:  # toast nunca pode derrubar a TUI
                log.warning("toast falhou: %s", exc)

        self.run_worker(show, thread=True, exit_on_error=False)

    def action_toggle_silence(self) -> None:
        if self.silenced:
            self.prefs.silenced_until = 0.0
            self.notify("som e toasts reativados")
        else:
            self.prefs.silenced_until = time.time() + SILENCE_MINUTES * 60
            self.notify(f"modo silêncio por {SILENCE_MINUTES} min (m desliga)")
        self.save_prefs()

    # --- telas -------------------------------------------------------------------

    def action_goto(self, mode: str) -> None:
        if mode not in self.MODES or mode == self.current_mode:
            return
        if isinstance(self.screen, ModalScreen):
            self.pop_screen()
        self.switch_mode(mode)
        self.prefs.last_screen = mode
        self.save_prefs()
        if mode == "dashboard" and self._away:
            summary = " · ".join(f"{label}: {', '.join(what)}" for label, what in self._away.items())
            self._away = {}
            self.notify(f"enquanto você estava fora: {summary}", timeout=8)

    def action_escape(self) -> None:
        focused = self.focused
        if isinstance(focused, Input) and focused.has_class("panel-filter"):
            panel = focused.parent
            if isinstance(panel, BasePanel):
                panel.clear_filter()
            return
        if isinstance(self.screen, ModalScreen):
            self.pop_screen()
            return
        if self.current_mode != "dashboard":
            self.action_goto("dashboard")

    # --- navegador e área de transferência ------------------------------------------

    def open_url(self, url: str | None, what: str = "") -> bool:
        if not url:
            self.notify(f"URL de {what or 'destino'} não configurada no .env", severity="warning")
            return False
        try:
            webbrowser.open_new_tab(url)
        except Exception as exc:
            self.notify(f"não consegui abrir o navegador: {exc}", severity="error")
            return False
        self.notify(f"abrindo {what or url} no navegador")
        return True

    def copy_text(self, text: str | None, what: str = "", quiet: bool = False) -> bool:
        if not text:
            self.notify(f"nada para copiar ({what})", severity="warning")
            return False
        try:
            import pyperclip

            pyperclip.copy(text)
        except Exception:
            self.notify(f"copie manualmente: {text}", severity="warning", timeout=10)
            return False
        if not quiet:
            self.notify(f"{what or 'valor'} copiado: {text}")
        return True

    # --- detalhes --------------------------------------------------------------------

    def open_detail(self, source: str, key: str) -> None:
        if source == "email":
            self.run_worker(self._open_email(key), name="detail-email", group="detail",
                            exclusive=True, exit_on_error=False)
        elif source == "milldesk":
            self.notify(f"detalhe do chamado #{key} chega na Fase 6.2")
        elif source == "chatpanel":
            self.notify(f"detalhe da conversa {key} chega na Fase 6.3")

    async def _open_email(self, uid: str) -> None:
        state = self.states.get("email")
        latest = getattr(state, "latest", None)
        if uid == "latest" or latest is None and state is None:
            if latest is None:
                self.notify("nenhum e-mail carregado ainda")
                return
            self.push_screen(EmailDetailScreen(latest))
            return
        screen = EmailDetailScreen(None, loading_uid=uid)
        self.push_screen(screen)
        source = self._sources.get("email")
        fetch_body = getattr(source, "fetch_body", None)
        if fetch_body is None:
            if latest is not None:
                screen.show(latest)
            return
        try:
            detail = await fetch_body(uid)
        except Exception as exc:
            log.warning("erro ao buscar o e-mail %s: %s", uid, exc)
            self.notify(f"não consegui buscar o e-mail: {exc}", severity="error")
            return
        if detail is None:
            self.notify("e-mail não encontrado (pode ter sido movido)", severity="warning")
            return
        if screen.is_attached:
            screen.show(detail)

    def action_open_email(self) -> None:
        state = self.states.get("email")
        latest = getattr(state, "latest", None)
        if latest is None:
            self.notify("nenhum e-mail carregado ainda")
            return
        if isinstance(self.screen, ModalScreen):
            self.pop_screen()
        self.push_screen(EmailDetailScreen(latest))

    # --- workers -----------------------------------------------------------------------

    def _start_source(self, name: str, source: Source[Any]) -> None:
        if not source.configured:
            hint = getattr(source, "config_hint", "verifique o .env")
            log.warning("fonte %s não configurada: %s", name, hint)
            for panel in self.panels.get(name, []):
                panel.set_not_configured(hint)
            return
        self._refresh_events[name] = asyncio.Event()
        self.run_worker(
            self._source_loop(name, source),
            name=f"source-{name}",
            group=f"source-{name}",
            exclusive=True,
            exit_on_error=False,
        )

    async def _source_loop(self, name: str, source: Source[Any]) -> None:
        event = self._refresh_events[name]
        try:
            while True:
                event.clear()
                wait_seconds = await self._fetch_once(name, source)
                try:
                    await asyncio.wait_for(event.wait(), timeout=wait_seconds)
                except asyncio.TimeoutError:
                    pass
        finally:
            try:
                await source.close()
            except Exception as exc:  # fechar nunca pode derrubar a saída do app
                log.warning("erro ao fechar fonte %s: %s", name, exc)

    async def _fetch_once(self, name: str, source: Source[Any]) -> float:
        """Uma coleta. Devolve quantos segundos esperar até o próximo ciclo."""
        if name == LOGIN_SOURCE and self._login_requested:
            self._login_requested = False
            if not await self._run_login(source):
                return float(source.interval)
        try:
            state = await source.fetch_with_retry()
        except SourceError as exc:
            log.error("fonte %s falhou: %s", name, exc)
            wait = max(float(source.interval), exc.retry_after or 0.0)
            self._set_error(name, str(exc) + (f" · aguardando {int(wait)}s" if exc.retry_after else ""))
            if self._should_login_on_start(name, source, exc):
                self._login_on_start_used = True
                self._login_requested = True
                return 0.0  # volta já para o topo do loop, que abre a janela de login
            return wait
        except Exception as exc:  # bug na fonte: mostra, registra e segue vivo
            log.exception("erro inesperado na fonte %s", name)
            self._set_error(name, f"erro inesperado: {exc}")
            return float(source.interval)

        self._publish(name, state)
        return float(source.interval)

    def _publish(self, name: str, state: Any) -> None:
        previous = self.states.get(name)
        self.states[name] = state
        self.errors[name] = state.error
        panels = self.panels.get(name, [])
        for panel in panels:
            panel.show_state(state)
            panel.set_error(state.error)
            panel.mark_updated(state.updated_at)
        if previous is not None:
            reference = panels[0] if panels else _panel_class_for(name)
            if reference is not None:
                grew = increased_counters(reference.counters(previous), reference.counters(state))
                if grew:
                    self.notify_change(name, grew)

    def _set_error(self, name: str, message: str | None) -> None:
        self.errors[name] = message
        for panel in self.panels.get(name, []):
            panel.set_error(message)

    def refresh_panels(self, name: str) -> None:
        """Re-renderiza os painéis da fonte com o estado atual (após mudar ordenação etc.)."""
        state = self.states.get(name)
        if state is None:
            return
        for panel in self.panels.get(name, []):
            panel.show_state(state)

    # --- login humano do ChatPanel ---------------------------------------------------

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

    async def _run_login(self, source: Source[Any]) -> bool:
        """Roda dentro do worker da fonte (o perfil do Chromium não pode ter dois donos)."""
        login = getattr(source, "interactive_login", None)
        if login is None:
            return False
        self._login_in_progress = True
        self._set_error(LOGIN_SOURCE, None)
        for panel in self.panels.get(LOGIN_SOURCE, []):
            panel.set_waiting("[yellow]janela de login aberta[/] · faça o login no Chromium (o captcha é seu)")
        self.notify("faça o login na janela do Chromium…", timeout=20)
        try:
            user = await login()
        except Exception as exc:
            log.warning("login do ChatPanel não concluído: %s", exc)
            self._set_error(LOGIN_SOURCE, str(exc))
            self.notify("login do ChatPanel não concluído (c tenta de novo)", severity="warning")
            return False
        finally:
            self._login_in_progress = False
        self.login_count += 1
        self.notify(f"login ok: {user} · lendo o ChatPanel…")
        return True

    def action_chatpanel_login(self) -> None:
        source = self._sources.get(LOGIN_SOURCE)
        label = SOURCE_PANELS[LOGIN_SOURCE][1]
        if source is None or not hasattr(source, "interactive_login"):
            self.notify(f"{label}: login não disponível")
            return
        if LOGIN_SOURCE not in self._refresh_events:
            self.notify(f"{label}: não configurado")
            return
        if self._login_in_progress:
            self.notify("login já em andamento: veja a janela do Chromium")
            return
        self._login_requested = True
        self._request_refresh(LOGIN_SOURCE)
        self.notify(f"abrindo a janela de login do {label}…")

    # --- ações -------------------------------------------------------------------

    def action_refresh_all(self) -> None:
        started = [
            SOURCE_PANELS[name][1] for name in self._refresh_events if self._request_refresh(name)
        ]
        if started:
            self.notify("atualizando " + ", ".join(started) + "…")
        else:
            self.notify("nenhuma fonte ativa para atualizar")

    def action_refresh(self, name: str) -> None:
        _, label, phase = SOURCE_PANELS[name]
        if self._request_refresh(name):
            self.notify(f"atualizando {label}…")
        elif name in self._sources:
            self.notify(f"{label}: não configurado")
        else:
            self.notify(f"{label}: não implementado (Fase {phase})")

    def _request_refresh(self, name: str) -> bool:
        event = self._refresh_events.get(name)
        if event is None:
            return False
        event.set()
        return True


def _panel_class_for(name: str) -> Any:
    """Instância "vazia" da classe do painel, só para calcular contadores sem tela."""
    from app.tui.widgets.chatpanel_panel import ChatPanelPanel
    from app.tui.widgets.email_panel import EmailPanel
    from app.tui.widgets.milldesk_panel import MilldeskPanel

    classes = {"email": EmailPanel, "milldesk": MilldeskPanel, "chatpanel": ChatPanelPanel}
    cls = classes.get(name)
    return cls(0) if cls is not None else None
