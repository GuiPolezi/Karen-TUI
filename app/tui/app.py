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
from app.events import EventLog, diff_states
from app.prefs import PREFS_PATH, Prefs, load_prefs, save_prefs
from app.sources.base import Source, SourceError
from app.tui.launcher import Action, parse_command
from app.tui.screens import (
    MODE_SCREENS,
    EmailDetailScreen,
    HelpScreen,
    LauncherScreen,
    ModeScreen,
    TicketDetailScreen,
)
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
        Binding("f7", "goto('events')", "Eventos", priority=True),
        Binding("f8", "goto('health')", "Saúde", priority=True),
        Binding("l", "goto('log')", "Log", show=False),
        Binding("r", "refresh_all", "Atualizar", show=True),
        Binding("1", "refresh('email')", "Atualizar e-mail", show=False),
        Binding("2", "refresh('milldesk')", "Atualizar Milldesk", show=False),
        Binding("3", "refresh('chatpanel')", "Atualizar ChatPanel", show=False),
        Binding("e", "open_email", "Último e-mail", show=True),
        Binding("c", "chatpanel_login", "Login ChatPanel", show=False),
        Binding("m", "toggle_silence", "Silenciar", show=False),
        Binding("colon", "launcher", "Launcher", show=True, key_display=":"),
        Binding("question_mark", "help", "Ajuda", show=True, key_display="?"),
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
        self.started_at = time.time()
        self.event_log = EventLog(settings.log_dir if prefs_path is not None else None)
        self.health_info: dict[str, dict[str, Any]] = {}  # por fonte: duração, próximo ciclo, última ok

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

    # --- saúde ---------------------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        """Dados da tela F8: status por fonte, Milldesk, ChatPanel, log, versões, uptime."""
        rows = []
        for name, source in self._sources.items():
            label = SOURCE_PANELS.get(name, (name, name, 0))[1]
            info = self.health_info.get(name, {})
            error = self.errors.get(name)
            if not source.configured:
                status, detail = "não configurada", getattr(source, "config_hint", "")
            elif error:
                status, detail = "erro", error
            elif name in self.states:
                status, detail = "ok", f"intervalo {source.interval}s"
            else:
                status, detail = "aguardando", "primeira coleta"
            rows.append({"name": name, "label": label, "status": status, "detail": detail,
                         "duration": info.get("duration"), "next_at": info.get("next_at"),
                         "last_ok": info.get("last_ok")})
        milldesk = self._sources.get("milldesk")
        calls = getattr(milldesk, "calls_last_minute", lambda: 0)()
        cooldown_until = getattr(milldesk, "_rate_limited_until", None)
        cooldown = "não"
        if cooldown_until is not None and milldesk is not None:
            remaining = cooldown_until - milldesk._clock()  # type: ignore[attr-defined]
            cooldown = f"sim, {int(remaining)}s" if remaining > 0 else "não"
        chat_state = self.states.get("chatpanel")
        chat_source = self._sources.get("chatpanel")
        resync = "desligada"
        if chat_source is not None:
            seconds = getattr(getattr(chat_source, "settings", None), "resync_seconds", 0)
            blocked = getattr(chat_source, "_resync_blocked", False)
            resync = "bloqueada (mesmo usuário do técnico)" if blocked else (f"a cada {seconds}s" if seconds else "desligada")
        session_file = getattr(chat_source, "session_file", None)
        log_path = self.settings.log_dir / "app.log"
        try:
            log_size_kb = log_path.stat().st_size / 1024 if log_path.exists() else 0.0
        except OSError:
            log_size_kb = 0.0
        uptime = int(time.time() - self.started_at)
        try:
            import textual

            versions = f"textual {textual.__version__}"
            try:
                import playwright

                versions += f" · playwright {playwright.__version__}"
            except Exception:
                pass
        except Exception:
            versions = "?"
        return {
            "sources": rows,
            "milldesk_calls_last_minute": calls,
            "milldesk_cooldown": cooldown,
            "chatpanel_user": getattr(chat_state, "logged_user", None),
            "chatpanel_resync": resync,
            "chatpanel_session_file": bool(session_file is not None and Path(session_file).exists()),
            "log_path": str(log_path),
            "log_size_kb": log_size_kb,
            "events_today": len(self.event_log.events),
            "versions": versions,
            "uptime": f"{uptime // 3600}h{(uptime % 3600) // 60:02d}min",
        }

    # --- launcher ----------------------------------------------------------------------

    def action_launcher(self) -> None:
        if isinstance(self.screen, LauncherScreen):
            return
        if isinstance(self.screen, ModalScreen):
            self.pop_screen()
        self.push_screen(LauncherScreen(self.prefs.history))

    def action_help(self) -> None:
        if isinstance(self.screen, HelpScreen):
            return
        if isinstance(self.screen, ModalScreen):
            self.pop_screen()
        self.push_screen(HelpScreen())

    def run_command(self, text: str) -> bool:
        """Executa um comando do launcher. Devolve True se o launcher deve ficar aberto."""
        action = parse_command(text, self.prefs.favorites, self.settings.urls)
        launcher = self.screen if isinstance(self.screen, LauncherScreen) else None
        if action.kind == "empty":
            return True
        if action.kind == "error":
            if launcher is not None:
                launcher.set_message(action.label, error=True)
            else:
                self.notify(action.label, severity="warning")
            return True
        if action.kind == "fav_list":
            self._execute(action, launcher)
            return True
        self.prefs.push_history(text.strip())
        self.save_prefs()
        if launcher is not None:
            self.pop_screen()  # fecha o launcher ANTES de agir (a ação pode abrir outra tela)
        self._execute(action, None)
        return False

    def _execute(self, action: Action, launcher: LauncherScreen | None) -> bool:
        if action.kind == "help":
            self.push_screen(HelpScreen())
            return False
        if action.kind in ("search", "open"):
            if action.copy:
                self.copy_text(action.copy, "ID do chamado", quiet=True)
            self.open_url(action.arg, action.label)
            return False
        if action.kind == "ticket":
            self.open_ticket(int(action.arg))
            return False
        if action.kind == "goto":
            self.action_goto(action.arg)
            return False
        if action.kind == "refresh":
            if action.arg:
                self.action_refresh(action.arg)
            else:
                self.action_refresh_all()
            return False
        if action.kind == "fav_add":
            self.prefs.favorites[action.arg] = action.label if action.label else ""
            self.save_prefs()
            self.notify(f"favorito '{action.arg}' salvo")
            return False
        if action.kind == "fav_rm":
            removed = self.prefs.favorites.pop(action.arg, None)
            self.save_prefs()
            self.notify(f"favorito '{action.arg}' removido" if removed else f"favorito '{action.arg}' não existe",
                        severity="information" if removed else "warning")
            return False
        if action.kind == "fav_list":
            if not self.prefs.favorites:
                message = "nenhum favorito (fav add nome url)"
            else:
                message = "favoritos: " + " · ".join(f"{name} → {url}" for name, url in self.prefs.favorites.items())
            if launcher is not None:
                launcher.set_message(message)
            else:
                self.notify(message, timeout=10)
            return True
        self.notify(f"comando não reconhecido: {action.kind}", severity="warning")
        return True

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
            try:
                ticket_id = int(key)
            except ValueError:
                self.notify(f"ID de chamado inválido: {key}", severity="warning")
                return
            self.open_ticket(ticket_id)
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

    def open_ticket(self, ticket_id: int, force: bool = False) -> None:
        """Abre (ou recarrega) o detalhe do chamado; a tela abre já com "carregando…"."""
        screen = self.screen if isinstance(self.screen, TicketDetailScreen) else None
        if screen is None or screen.ticket_id != ticket_id:
            if isinstance(self.screen, ModalScreen):
                self.pop_screen()
            screen = TicketDetailScreen(ticket_id)
            self.push_screen(screen)
        else:
            screen.set_loading()
        self.run_worker(self._load_ticket(screen, ticket_id, force), name="detail-ticket",
                        group="detail", exclusive=True, exit_on_error=False)

    async def _load_ticket(self, screen: TicketDetailScreen, ticket_id: int, force: bool) -> None:
        source = self._sources.get("milldesk")
        fetch_ticket = getattr(source, "fetch_ticket", None)
        if fetch_ticket is None:
            screen.show_error("fonte Milldesk indisponível")
            return
        try:
            detail = await fetch_ticket(ticket_id, force=force)
        except Exception as exc:
            log.warning("erro ao buscar o chamado %s: %s", ticket_id, exc)
            if screen.is_attached:
                screen.show_error(str(exc))
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
        started = time.monotonic()
        info = self.health_info.setdefault(name, {"duration": None, "next_at": None, "last_ok": None})
        try:
            state = await source.fetch_with_retry()
        except SourceError as exc:
            log.error("fonte %s falhou: %s", name, exc)
            wait = max(float(source.interval), exc.retry_after or 0.0)
            info.update(duration=time.monotonic() - started, next_at=time.time() + wait)
            self._set_error(name, str(exc) + (f" · aguardando {int(wait)}s" if exc.retry_after else ""))
            if self._should_login_on_start(name, source, exc):
                self._login_on_start_used = True
                self._login_requested = True
                return 0.0  # volta já para o topo do loop, que abre a janela de login
            return wait
        except Exception as exc:  # bug na fonte: mostra, registra e segue vivo
            log.exception("erro inesperado na fonte %s", name)
            info.update(duration=time.monotonic() - started, next_at=time.time() + source.interval)
            self._set_error(name, f"erro inesperado: {exc}")
            return float(source.interval)

        info.update(duration=time.monotonic() - started, next_at=time.time() + source.interval, last_ok=time.time())
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
            events = diff_states(name, previous, state)
            if events:
                self.event_log.add(events)
                for event in events:
                    log.info("evento: %s", event.text)
                screen = self.mode_screens.get("events")
                if screen is not None:
                    screen.refresh_events()  # type: ignore[attr-defined]

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
