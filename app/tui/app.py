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
from collections import deque
from pathlib import Path
from typing import Any

from textual.app import App
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Input

from app import __version__, clock
from app.config import Settings
from app.events import EventLog, diff_states
from app.prefs import PREFS_PATH, Prefs, load_prefs, save_prefs
from app.sources.base import Source, SourceError
from app.tui.icons import IconSet, is_legacy_console, resolve_icons
from app.paths import DATA_DIR
from app.update import UpdateStatus, check_updates, download_installer, run_installer
from app.tui.launcher import Action, parse_command
from app.tui.themes import (
    CARBON,
    load_user_themes,
    register_themes,
    resolve_theme_name,
    write_windows_terminal_scheme,
)
from app.tui.tokens import Tokens
from app.tui.screens import (
    MODE_SCREENS,
    ConversationDetailScreen,
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
LATENCY_CYCLES = 30         # ciclos guardados por fonte para a Sparkline da tela Saúde

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
        Binding("f9", "goto('themes')", "Temas", priority=True),
        Binding("l", "goto('log')", "Log", show=False),
        Binding("r", "refresh_all", "Atualizar", show=True),
        Binding("1", "refresh('email')", "Atualizar e-mail", show=False),
        Binding("2", "refresh('milldesk')", "Atualizar Milldesk", show=False),
        Binding("3", "refresh('chatpanel')", "Atualizar ChatPanel", show=False),
        Binding("e", "open_email", "Último e-mail", show=True),
        Binding("c", "chatpanel_login", "Login ChatPanel", show=False),
        Binding("m", "toggle_silence", "Silenciar", show=False),
        Binding("T", "next_theme", "Próximo tema", show=False),
        Binding("colon", "launcher", "Launcher", show=True, key_display=":"),
        Binding("question_mark", "help", "Ajuda", show=True, key_display="?"),
        Binding("ctrl+u", "update", "Atualizar programa", show=False),
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
        self._updating = False  # Ctrl+U em andamento (baixando/instalando)
        self._login_on_start_used = False
        self.login_count = 0
        self.started_at = clock.epoch()
        self.event_log = EventLog(settings.log_dir if prefs_path is not None else None)
        self.health_info: dict[str, dict[str, Any]] = {}  # por fonte: duração, próximo ciclo, última ok
        self.fetching: set[str] = set()                   # fontes coletando neste instante
        self.latency: dict[str, deque[float]] = {}        # fonte -> duração dos últimos 30 ciclos (Sparkline do F8)
        self.cooldown_until: dict[str, float] = {}        # fonte -> epoch até o qual está em cooldown (429)
        self.error_kind: dict[str, str] = {}              # fonte -> "cooldown" | "expired" | "error"
        # aparência: temas registrados, tema inicial (prefs > .env > carbon) e conjunto de ícones
        self.icons: IconSet = resolve_icons(settings.icons)
        self.legacy_console = self.icons.mode == "ascii" or (settings.icons == "auto" and is_legacy_console())
        user_themes = load_user_themes() if prefs_path is not None else {}  # testes não leem themes/
        self.token_sets: dict[str, Tokens] = register_themes(self, user_themes, legacy_console=self.legacy_console)
        self._initial_theme = resolve_theme_name(self.prefs.theme or settings.theme, self.token_sets)
        # atualização: git fetch em thread ao abrir (só com prefs em disco = execução real, não testes)
        self.update_status = UpdateStatus()
        self._update_enabled = bool(settings.update_check and prefs_path is not None)

    # --- ciclo de vida --------------------------------------------------------

    def on_mount(self) -> None:
        self.theme = self._initial_theme
        self.theme_changed_signal.subscribe(self, self._on_theme_changed)
        mode = self.prefs.last_screen if self.prefs.last_screen in self.MODES else "dashboard"
        self.switch_mode(mode)
        for name, source in self._sources.items():
            self._start_source(name, source)
        if self._update_enabled:
            self.run_worker(self._check_updates, name="update-check", thread=True, exit_on_error=False)

    # --- atualização -------------------------------------------------------------

    def _check_updates(self) -> None:
        """Roda numa thread: git fetch pode levar segundos e não pode travar a TUI."""
        status = check_updates()
        self.call_from_thread(self.apply_update_status, status)

    def apply_update_status(self, status: UpdateStatus) -> None:
        self.update_status = status
        if status.error:
            log.info("atualização: %s", status.summary())
        elif status.available:
            log.info("atualização disponível: %s", status.summary())
            self.notify(f"atualização disponível: {status.summary()}", timeout=12)

    def action_update(self) -> None:
        """Ctrl+U: baixa o instalador do release novo, fecha a TUI e instala.

        Só faz sentido no executável; no repositório de desenvolvimento quem atualiza é o
        `git pull` do `iniciar.cmd`. Quando o release não tem instalador, abre a página.
        """
        status = self.update_status
        if self._updating:
            self.notify("atualização já em andamento…")
            return
        if not status.available:
            self.notify(f"atualização: {status.summary()}")
            return
        if not status.can_install:
            self.notify(f"atualização: {status.summary()}", timeout=10)
            self.open_url(status.page_url, "página do release")
            return
        self._updating = True
        self.notify(f"baixando a versão {status.latest}… a TUI fecha sozinha no fim", timeout=8)
        self.run_worker(self._download_and_install, name="update-install", thread=True, exit_on_error=False)

    def _download_and_install(self) -> None:
        """Roda numa thread: download de dezenas de MB não pode travar a TUI."""
        status = self.update_status
        marco = [0]

        def progress(baixado: int, total: int) -> None:
            if not total:
                return
            porcento = int(baixado * 100 / total)
            if porcento >= marco[0] + 25:
                marco[0] = porcento - porcento % 25
                self.call_from_thread(self.notify, f"baixando atualização: {porcento}%")

        try:
            instalador = download_installer(status, progress=progress)
        except Exception as exc:
            log.warning("download da atualização falhou: %s", exc)
            self._updating = False
            self.call_from_thread(self.notify, f"não consegui baixar a atualização: {exc}", severity="error")
            return
        try:
            run_installer(instalador)
        except Exception as exc:
            log.warning("não consegui iniciar o instalador: %s", exc)
            self._updating = False
            self.call_from_thread(self.notify, f"baixei em {instalador}, mas não consegui instalar: {exc}",
                                  severity="error")
            return
        log.info("instalador disparado; fechando a TUI")
        self.call_from_thread(self.exit)

    # --- aparência ----------------------------------------------------------------

    @property
    def tokens(self) -> Tokens:
        """Paleta do tema atual (para estilos Rich fora do CSS)."""
        return self.token_sets.get(self.theme, CARBON)

    def get_theme_variable_defaults(self) -> dict[str, str]:
        """Os tokens do `carbon` como padrão: o CSS é validado antes de o tema inicial ser
        aplicado, e um tema do Textual não mapeado ainda precisa de `$bg`, `$text-faint`..."""
        return {**super().get_theme_variable_defaults(), **CARBON.css_variables()}

    def _on_theme_changed(self, theme: Any) -> None:
        """Tema trocado: nada é recriado; painéis re-renderizam as células e as barras
        refazem os textos Rich. A escolha vai para prefs.json."""
        for panels in self.panels.values():
            for panel in panels:
                panel.refresh_theme()
        for screen in self.mode_screens.values():
            screen.refresh_theme()
        current = self.screen
        refresh = getattr(current, "refresh_theme", None)
        if refresh is not None and current not in self.mode_screens.values():
            refresh()
        if self.prefs.theme != self.theme:
            self.prefs.theme = self.theme
            self.save_prefs()

    def set_theme(self, name: str) -> bool:
        """Aplica um tema pelo nome (com `notify`); False se não existir."""
        if name not in self.token_sets:
            self.notify(f"tema '{name}' não existe (theme lista os disponíveis)", severity="warning")
            return False
        self.theme = name
        self.notify(f"tema: {name}")
        return True

    def terminal_info(self) -> str:
        """Diagnóstico da tela Saúde: profundidade de cor, tema, ícones e onde o app roda.
        Se aparecer "16 cores", o terminal não é o Windows Terminal e os temas ficam iguais."""
        import os

        color_system = getattr(self.console, "color_system", None) or "?"
        depth = {"truecolor": "16 milhões de cores", "256": "256 cores", "standard": "16 cores",
                 "windows": "16 cores (conhost)"}.get(color_system, color_system)
        host = "Windows Terminal" if os.environ.get("WT_SESSION") else (os.environ.get("TERM_PROGRAM") or "conhost/outro")
        return (f"{host} {self.icons.sep} {depth} {self.icons.sep} tema {self.theme} "
                f"{self.icons.sep} ícones {self.icons.mode}" + (" (modo conhost: sem dim)" if self.legacy_console else ""))

    def export_windows_terminal_scheme(self) -> Path | None:
        """`theme export wt`: grava o esquema do tema atual em docs/design/windows-terminal/
        e copia o JSON para a área de transferência."""
        tokens = self.tokens
        if tokens.ansi:
            self.notify("o tema 'terminal' já usa as cores do Windows Terminal; nada a exportar", severity="warning")
            return None
        try:
            path = write_windows_terminal_scheme(tokens)
        except OSError as exc:
            self.notify(f"não consegui gravar o esquema: {exc}", severity="error")
            return None
        self.copy_text(path.read_text(encoding="utf-8"), "esquema", quiet=True)
        self.notify(f"esquema '{tokens.name}' em {path} (copiado): cole em \"schemes\" do settings.json "
                    f"do Windows Terminal e use \"colorScheme\": \"{tokens.name}\" no perfil", timeout=12)
        return path

    def action_next_theme(self) -> None:
        names = list(self.token_sets)
        index = names.index(self.theme) if self.theme in names else -1
        self.set_theme(names[(index + 1) % len(names)])

    def source_status(self, name: str) -> tuple[str, str]:
        """Estado curto de uma fonte para a TopBar: (ok|busy|wait|warn|danger|off, motivo)."""
        source = self._sources.get(name)
        if source is None:
            return "off", "não implementada"
        if not source.configured:
            return "off", f"não configurada · {getattr(source, 'config_hint', 'veja o .env')}"
        if name in self.fetching:
            return "busy", "coletando…"
        error = self.errors.get(name)
        if error:
            kind = self.error_kind.get(name, "error")
            if kind == "cooldown":
                remaining = int(self.cooldown_until.get(name, 0) - clock.epoch())
                return "warn", f"aguardando {max(remaining, 0)}s · {error}"
            return "danger", error
        info = self.health_info.get(name, {})
        if name in self.states:
            last_ok = info.get("last_ok")
            ago = f"há {int(clock.epoch() - last_ok)}s" if last_ok else ""
            next_at = info.get("next_at")
            soon = f"próxima em {max(int(next_at - clock.epoch()), 0)}s" if next_at else ""
            return "ok", " · ".join(p for p in ("ok", ago, soon) if p)
        return "wait", "primeira coleta"

    def topbar_extras(self) -> list[tuple[str, str]]:
        """Estados transitórios mostrados à direita da TopBar: (texto, token de cor)."""
        extras: list[tuple[str, str]] = []
        if self.update_status.available:
            extras.append((f"{self.icons.update} {self.update_status.badge()}", "accent"))
        if self._login_in_progress:
            extras.append((f"{self.icons.login} login", "accent"))
        if self.silenced:
            remaining = max(int((self.prefs.silenced_until - clock.epoch()) / 60), 0)
            extras.append((f"{self.icons.mute} {remaining}m", "warn"))
        return extras

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

    NOTIFICATION_TIMEOUT = 4.0  # segundos (spec: 4 s; nunca mais de 3 empilhados)
    MAX_NOTIFICATIONS = 3

    def notify(self, message: str, **kwargs: Any) -> None:  # type: ignore[override]
        self.last_message = message
        self.messages.append(message)
        super().notify(message, **kwargs)
        try:  # nunca mais de 3: a mais antiga sai
            while len(self._notifications) > self.MAX_NOTIFICATIONS:
                oldest = next(iter(self._notifications))
                del self._notifications[oldest]
            self._refresh_notifications()
        except Exception:  # API interna do Textual: se mudar, só perde o limite
            pass

    @property
    def silenced(self) -> bool:
        return clock.epoch() < self.prefs.silenced_until

    def notify_change(self, name: str, what: list[str]) -> None:
        """Contador aumentou: destaca os painéis da fonte por 3 s, toca o bell/toast."""
        label = SOURCE_PANELS.get(name, (name, name, 0))[1]
        log.info("aumentou em %s: %s", label, ", ".join(what))
        for panel in self.panels.get(name, []):
            panel.flash(what)
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
            self.prefs.silenced_until = clock.epoch() + SILENCE_MINUTES * 60
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
            panel = next((node for node in focused.ancestors if isinstance(node, BasePanel)), None)
            if panel is not None:
                panel.clear_filter()
            return
        if isinstance(self.screen, ModalScreen):
            self.pop_screen()
            return
        if self.current_mode != "dashboard":
            cancel = getattr(self.screen, "cancel", None)  # ex.: Temas volta ao tema anterior
            if cancel is not None:
                cancel()
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
        uptime = int(clock.epoch() - self.started_at)
        try:
            import textual

            versions = f"CMD ALL-IN-ONE {__version__} · textual {textual.__version__}"
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
            "latency": {name: list(values) for name, values in self.latency.items()},
            "terminal": self.terminal_info(),
            "data_dir": str(DATA_DIR),
            "update": self.update_status.summary() if self._update_enabled else "verificação desligada (UPDATE_CHECK=false)",
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
        if action.kind == "update":
            self.action_update()
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
        if action.kind == "theme_list":
            names = " · ".join(f"[{n}]" if n == self.theme else n for n in self.token_sets)
            message = f"temas: {names}"
            if launcher is not None:
                launcher.set_message(message)
            else:
                self.notify(message, timeout=10)
            return True
        if action.kind == "theme_set":
            self.set_theme(action.arg)
            return False
        if action.kind == "theme_next":
            self.action_next_theme()
            return False
        if action.kind == "theme_export":
            self.export_windows_terminal_scheme()
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
            self.open_conversation(key)

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

    def _chat_item(self, number: str) -> Any:
        state = self.states.get("chatpanel")
        if state is None:
            return None
        for item in [*state.mine, *state.others]:
            if item.number == number:
                return item
        return None

    def open_conversation(self, number: str, force: bool = False) -> None:
        """Abre (ou recarrega) a conversa; a tela abre já com "carregando…"."""
        item = self._chat_item(number)
        screen = self.screen if isinstance(self.screen, ConversationDetailScreen) else None
        if screen is None or screen.number != number:
            if isinstance(self.screen, ModalScreen):
                self.pop_screen()
            screen = ConversationDetailScreen(number, item)
            self.push_screen(screen)
        else:
            screen.item = item
            screen.set_loading()
        self.run_worker(self._load_conversation(screen, number), name="detail-chat",
                        group="detail", exclusive=True, exit_on_error=False)

    async def _load_conversation(self, screen: ConversationDetailScreen, number: str) -> None:
        source = self._sources.get("chatpanel")
        fetch = getattr(source, "fetch_conversation", None)
        if fetch is None:
            screen.show_error("fonte ChatPanel indisponível")
            return
        item = screen.item
        try:
            detail = await fetch(number, item.name if item is not None else "")
        except Exception as exc:
            log.warning("erro ao ler a conversa %s: %s", number, exc)
            if screen.is_attached:
                screen.show_error(str(exc))
            return
        if screen.is_attached:
            screen.show(detail)

    def _refresh_open_conversation(self, state: Any) -> None:
        """Conversa aberta ganhou mensagem (não lidas/última mensagem mudaram): recarrega."""
        screen = self.screen if isinstance(self.screen, ConversationDetailScreen) else None
        if screen is None:
            return
        item = self._chat_item(screen.number)
        if item is None:
            return
        snapshot = (item.unread, item.last_message, item.time)
        if snapshot != screen.snapshot:
            screen.snapshot = snapshot
            screen.item = item
            self.run_worker(self._load_conversation(screen, screen.number), name="detail-chat",
                            group="detail", exclusive=True, exit_on_error=False)

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
        self.fetching.add(name)
        try:
            state = await source.fetch_with_retry()
        except SourceError as exc:
            log.error("fonte %s falhou: %s", name, exc)
            wait = max(float(source.interval), exc.retry_after or 0.0)
            info.update(duration=time.monotonic() - started, next_at=clock.epoch() + wait)
            expired = self._is_session_expired(exc)
            if exc.retry_after and not expired:
                self.error_kind[name] = "cooldown"
                self.cooldown_until[name] = clock.epoch() + wait
            else:
                self.error_kind[name] = "expired" if expired else "error"
            self._set_error(name, str(exc) + (f" · aguardando {int(wait)}s" if exc.retry_after else ""))
            if self._should_login_on_start(name, source, exc):
                self._login_on_start_used = True
                self._login_requested = True
                return 0.0  # volta já para o topo do loop, que abre a janela de login
            return wait
        except Exception as exc:  # bug na fonte: mostra, registra e segue vivo
            log.exception("erro inesperado na fonte %s", name)
            info.update(duration=time.monotonic() - started, next_at=clock.epoch() + source.interval)
            self.error_kind[name] = "error"
            self._set_error(name, f"erro inesperado: {exc}")
            return float(source.interval)
        finally:
            self.fetching.discard(name)
            self.latency.setdefault(name, deque(maxlen=LATENCY_CYCLES)).append(time.monotonic() - started)

        info.update(duration=time.monotonic() - started, next_at=clock.epoch() + source.interval, last_ok=clock.epoch())
        self.error_kind.pop(name, None)
        self.cooldown_until.pop(name, None)
        self._publish(name, state)
        return float(source.interval)

    @staticmethod
    def _is_session_expired(exc: SourceError) -> bool:
        from app.sources.chatpanel import SessionExpiredError

        return isinstance(exc.__cause__, SessionExpiredError)

    def _publish(self, name: str, state: Any) -> None:
        previous = self.states.get(name)
        self.states[name] = state
        self.errors[name] = state.error
        panels = self.panels.get(name, [])
        for panel in panels:
            panel.show_state(state)
            panel.set_error(state.error)
            panel.mark_updated(state.updated_at)
        if name == "chatpanel":
            self._refresh_open_conversation(state)
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
            panel.set_waiting("janela de login aberta · faça o login no Chromium (o captcha é seu)", token="warn")
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
