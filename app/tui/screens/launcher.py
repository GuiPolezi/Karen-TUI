"""Launcher (`:`): uma linha de comando dentro da TUI, com histórico (↑/↓) e ajuda (`?`)."""

from __future__ import annotations

from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from app.tui.launcher import HELP_LINES

HINT = "Enter executa · ↑/↓ histórico · Esc fecha · help lista os comandos"


class LauncherScreen(ModalScreen[None]):
    BINDINGS = [
        Binding("escape", "dismiss", "Fechar", priority=True),
        Binding("up", "history(-1)", "Anterior", show=False),
        Binding("down", "history(1)", "Próximo", show=False),
    ]

    def __init__(self, history: list[str]) -> None:
        super().__init__()
        self.history = list(history)
        self._cursor = len(self.history)  # posição no histórico; len = linha nova
        self._draft = ""

    def compose(self) -> ComposeResult:
        tokens = self.app.tokens  # type: ignore[attr-defined]
        with Vertical(id="launcher"):
            yield Input(placeholder="comando… (ex.: g erro 500 · md 1234 · tickets)", id="launcher-input")
            yield Static(Text(HINT, style=tokens.rich("text-faint")), id="launcher-hint")

    def on_mount(self) -> None:
        self.query_one("#launcher-input", Input).focus()

    def set_message(self, message: str, error: bool = False) -> None:
        tokens = self.app.tokens  # type: ignore[attr-defined]
        style = tokens.rich("danger", bold=True) if error else tokens.rich("ok")
        self.query_one("#launcher-hint", Static).update(Text(message, style=style))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        # o App fecha este modal antes de executar ações que trocam de tela
        self.app.run_command(event.value.strip())  # type: ignore[attr-defined]

    def action_history(self, step: int) -> None:
        if not self.history:
            return
        box = self.query_one("#launcher-input", Input)
        if self._cursor == len(self.history):
            self._draft = box.value
        self._cursor = max(0, min(len(self.history), self._cursor + step))
        box.value = self.history[self._cursor] if self._cursor < len(self.history) else self._draft
        box.cursor_position = len(box.value)


class HelpScreen(ModalScreen[None]):
    BINDINGS = [
        Binding("escape", "dismiss", "Fechar"),
        Binding("q", "dismiss", "Fechar"),
        Binding("question_mark", "dismiss", "Fechar", show=False),
    ]

    SHORTCUTS = [
        ("F1 / d", "Dashboard"), ("F2", "E-mail (u: só não lidos)"), ("F3", "Milldesk (s: ordenar)"),
        ("F4", "ChatPanel (t: com outros)"), ("F5 / l", "Log (f: filtro de nível)"), ("F6", "Notas"),
        ("F7", "Eventos do dia (x: limpar tela)"), ("F8", "Saúde das fontes"),
        ("↑ ↓ j k PgUp PgDn", "mover o cursor"), ("Enter", "abrir o item"), ("Esc", "voltar / limpar filtro"),
        ("Tab", "trocar painel"), ("/", "filtrar a lista"), ("o", "abrir no navegador"), ("y", "copiar"),
        ("e", "último e-mail"), ("r · 1 2 3", "atualizar"), ("c", "login ChatPanel"),
        ("m", "silêncio 30 min"), ("T", "próximo tema"), (":", "launcher"), ("?", "esta ajuda"), ("q", "sair"),
    ]

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="help"):
            with Horizontal(id="help-columns"):
                yield Static(self._table("Atalhos", self.SHORTCUTS), id="help-keys")
                yield Static(self._table("Launcher (:)", HELP_LINES), id="help-commands")
            yield Static(Text("Esc fecha", style=self.app.tokens.rich("text-faint")), id="help-footer")  # type: ignore[attr-defined]

    def _table(self, title: str, rows: list[tuple[str, str]]) -> Table:
        tokens = self.app.tokens  # type: ignore[attr-defined]
        table = Table(title=title, title_justify="left", title_style=tokens.rich("text-muted", bold=True),
                      box=None, show_header=False, padding=(0, 2))
        table.add_column("k", style=tokens.rich("accent", bold=True), no_wrap=True)
        table.add_column("v", style=tokens.rich("text"))
        for key, description in rows:
            table.add_row(key, description)
        return table
