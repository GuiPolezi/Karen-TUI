"""Launcher (`:`): uma linha na base da tela, acima do rodapé, com prompt `:` em accent,
sugestões de comando conforme se digita (máximo 5), histórico (↑/↓) e ajuda (`?`)."""

from __future__ import annotations

from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from app.tui.launcher import HELP_LINES

HINT = "Enter executa · ↑↓ histórico · Esc fecha · help lista os comandos"
MAX_SUGGESTIONS = 5

# (comando como se digita, descrição curta) para as sugestões
COMMANDS: list[tuple[str, str]] = [
    ("g termo", "pesquisa no Google"), ("ddg termo", "pesquisa no DuckDuckGo"), ("yt termo", "pesquisa no YouTube"),
    ("md 1234", "detalhe do chamado na TUI"), ("md! 1234", "Milldesk no navegador + copia o ID"),
    ("mdweb", "abre o Milldesk no navegador"), ("mail", "abre o webmail"), ("cp", "abre o ChatPanel"),
    ("wa 5511999999999", "abre wa.me com o número"), ("open url", "abre uma URL"),
    ("fav nome", "abre um favorito"), ("fav add nome url", "salva um favorito"), ("fav rm nome", "remove um favorito"),
    ("fav", "lista os favoritos"), ("email", "tela E-mail"), ("tickets", "tela Milldesk"), ("chats", "tela ChatPanel"),
    ("log", "tela Log"), ("notes", "tela Notas"), ("dash", "Dashboard"),
    ("refresh", "atualiza tudo"), ("refresh md", "atualiza uma fonte (md · email · cp)"),
    ("theme", "lista os temas"), ("theme nome", "aplica um tema"), ("theme next", "próximo tema"),
    ("theme preview", "tela de preview dos temas (F9)"), ("theme export wt", "esquema para o Windows Terminal"),
    ("help", "lista completa dos comandos"),
]


def suggest(text: str, limit: int = MAX_SUGGESTIONS) -> list[tuple[str, str]]:
    """Comandos cujo início casa com o que foi digitado (primeira palavra ou texto todo)."""
    typed = text.strip().lower()
    if not typed:
        return []
    head = typed.split(" ")[0]
    matches = [(cmd, desc) for cmd, desc in COMMANDS
               if cmd.lower().startswith(typed) or cmd.split(" ")[0].lower().startswith(head)]
    return matches[:limit]


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

    @property
    def tokens(self):  # noqa: ANN201
        return self.app.tokens  # type: ignore[attr-defined]

    def compose(self) -> ComposeResult:
        with Vertical(id="launcher"):
            yield Static(Text(HINT, style=self.tokens.rich("text-faint")), id="launcher-hint")
            yield Static("", id="launcher-suggestions")
            with Horizontal(id="launcher-line"):
                yield Static(Text(":", style=self.tokens.rich("accent", bold=True)), id="launcher-prompt")
                yield Input(placeholder="comando… (g termo · md 1234 · tickets · theme)", id="launcher-input")

    def on_mount(self) -> None:
        self.query_one("#launcher-suggestions", Static).display = False
        self.query_one("#launcher-input", Input).focus()

    def set_message(self, message: str, error: bool = False) -> None:
        style = self.tokens.rich("danger", bold=True) if error else self.tokens.rich("ok")
        self.query_one("#launcher-hint", Static).update(Text(message, style=style))

    def on_input_changed(self, event: Input.Changed) -> None:
        tokens = self.tokens
        matches = suggest(event.value)
        box = self.query_one("#launcher-suggestions", Static)
        if not matches:
            box.display = False
            return
        text = Text()
        for index, (command, description) in enumerate(matches):
            if index:
                text.append("\n")
            text.append(f"  {command}", style=tokens.rich("text"))
            text.append(f"  {description}", style=tokens.rich("text-muted"))
        box.update(text)
        box.display = True

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

    GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
        ("Telas", [
            ("F1 / d", "Dashboard"), ("F2", "E-mail"), ("F3", "Milldesk"), ("F4", "ChatPanel"),
            ("F5 / l", "Log"), ("F6", "Notas"), ("F7", "Eventos do dia"), ("F8", "Saúde das fontes"),
            ("F9", "Temas"), ("Esc", "voltar ao Dashboard"),
        ]),
        ("Geral", [
            ("e", "último e-mail"), ("r · 1 2 3", "atualizar tudo · uma fonte"), ("c", "login ChatPanel"),
            ("m", "silêncio 30 min"), ("T", "próximo tema"), (":", "launcher"), ("?", "esta ajuda"), ("q", "sair"),
        ]),
        ("Listas", [
            ("↑ ↓ j k PgUp PgDn", "mover o cursor"), ("Enter", "abrir o item"), ("Tab", "trocar painel"),
            ("/", "filtrar (Esc limpa)"), ("o", "abrir no navegador"), ("y", "copiar"),
            ("u", "E-mail: só não lidos"), ("s", "Milldesk: ordenar"), ("t", "ChatPanel: com outros"),
            ("f", "Log: filtro de nível"), ("x", "Eventos: limpar tela"),
        ]),
        ("Detalhes", [
            ("Esc", "voltar"), ("r", "recarregar"), ("o", "abrir no navegador"), ("y", "copiar ID · número · remetente"),
        ]),
    ]

    def compose(self) -> ComposeResult:
        tokens = self.app.tokens  # type: ignore[attr-defined]
        with VerticalScroll(id="help"):
            with Horizontal(id="help-columns"):
                with Vertical(id="help-keys"):
                    for title, rows in self.GROUPS[:2]:
                        yield Static(self._table(title, rows), classes="help-group")
                with Vertical(id="help-commands"):
                    for title, rows in self.GROUPS[2:]:
                        yield Static(self._table(title, rows), classes="help-group")
            yield Static(self._table("Launcher (:)", HELP_LINES), classes="help-group", id="help-launcher")
            yield Static(Text("Esc fecha", style=tokens.rich("text-faint")), id="help-footer")

    def _table(self, title: str, rows: list[tuple[str, str]]) -> Table:
        tokens = self.app.tokens  # type: ignore[attr-defined]
        table = Table(title=title, title_justify="left", title_style=tokens.rich("text-muted", bold=True),
                      box=None, show_header=False, padding=(0, 2))
        table.add_column("k", style=tokens.rich("accent", bold=True), no_wrap=True)
        table.add_column("v", style=tokens.rich("text"))
        for key, description in rows:
            table.add_row(key, description)
        return table
