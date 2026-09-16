"""Tela Temas (F9 ou `theme preview`): lista de temas navegável com ↑↓ aplicando ao vivo,
os tokens do tema atual e um painel de exemplo com os estados. `Enter` confirma, `Esc`
volta ao tema anterior."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from app.tui.screens.base import ModeScreen
from app.tui.tokens import TOKEN_NAMES, Tokens, check_contrast

TOKEN_USE = {
    "bg": "fundo", "surface": "barras e painéis", "surface-raised": "linha selecionada, modais",
    "border": "bordas e separadores", "text": "texto", "text-muted": "rótulos e horas",
    "text-faint": "separadores, há N s", "accent": "foco, teclas, mudança", "accent-soft": "fundo da seleção",
    "ok": "ok", "warn": "atenção", "danger": "erro / vencido", "mine": "no meu nome", "other": "de outros",
}


def tokens_text(tokens: Tokens) -> Text:
    """Uma linha por token: amostra, nome e valor."""
    text = Text(no_wrap=True, overflow="ellipsis")
    for token in TOKEN_NAMES:
        value = tokens.value(token)
        text.append("██ ", style=tokens.rich(token))
        text.append(f"{token:<15}", style=tokens.rich("text"))
        text.append(f"{value:<12}", style=tokens.rich("text-muted"))
        text.append(TOKEN_USE.get(token, ""), style=tokens.rich("text-faint"))
        text.append("\n")
    problems = check_contrast(tokens)
    if problems:
        text.append("\ncontraste: " + "; ".join(problems), style=tokens.rich("warn"))
    else:
        text.append("\ncontraste ok (texto ≥ 4.5, secundário ≥ 3)", style=tokens.rich("text-faint"))
    return text


def sample_text(tokens: Tokens, icons) -> Text:  # noqa: ANN001
    """Painel de exemplo com os estados: repouso, seleção, mudança, SLA, erro, vazio, não configurado."""
    t = tokens
    text = Text(no_wrap=True, overflow="ellipsis")
    text.append(f"{icons.focus}{icons.ticket} MILLDESK", style=t.rich("accent", bold=True))
    text.append(f"           60s {icons.sep} há 27s\n", style=t.rich("text-faint"))
    text.append("12", style=t.rich("text", bold=True)).append(" abertos", style=t.rich("text-muted"))
    text.append(f" {icons.sep} ", style=t.rich("text-faint"))
    text.append("1", style=t.rich("danger", bold=True)).append(" vencido\n\n", style=t.rich("text-muted"))
    text.append(f"SLA {icons.sla} ", style=t.rich("text-faint")).append("#4821 ", style=t.rich("text-muted"))
    text.append("Backup noturno   ", style=t.rich("text"))
    text.append(icons.bar_on * 3 + icons.bar_off, style=t.rich("warn")).append("  1h41\n\n", style=t.rich("warn", bold=True))
    text.append(f"{icons.focus}#4802  Certificado digital   ", style=t.rich("text", on="surface-raised"))
    text.append("-01h05\n", style=t.rich("danger", bold=True, on="surface-raised"))
    text.append(f"{icons.change}", style=t.rich("accent", bold=True)).append("#4833  Protocolo fora do ar  ", style=t.rich("text"))
    text.append("03h59\n", style=t.rich("ok"))
    text.append(" #4831  Impressora fiscal     ", style=t.rich("text")).append("05h59\n", style=t.rich("ok"))
    text.append(" #4744  Câmera do plenário    ", style=t.rich("other")).append("23h59\n\n", style=t.rich("ok"))
    text.append(f"{icons.error} ", style=t.rich("danger", bold=True)).append("timeout", style=t.rich("danger"))
    text.append(f" {icons.sep} há 2 min\n", style=t.rich("text-faint"))
    text.append(f"{icons.ok} ", style=t.rich("ok")).append("nenhum chamado no seu nome\n", style=t.rich("text-faint"))
    text.append(f"{icons.empty} não configurado {icons.sep} veja .env\n", style=t.rich("text-faint"))
    text.append("aguardando 2m40", style=t.rich("warn")).append("   ").append(f"{icons.mute} 27m", style=t.rich("warn"))
    text.append("\n\n").append(icons.key_escape, style=t.rich("accent", bold=True)).append(" voltar  ", style=t.rich("text-muted"))
    text.append(icons.key_enter, style=t.rich("accent", bold=True)).append(" confirmar", style=t.rich("text-muted"))
    return text


class ThemesScreen(ModeScreen):
    MODE = "themes"
    TITLE_PT = "Temas"
    AUTO_FOCUS = "#themes-list"
    FOOTER = [("{key_up_down}", "aplica ao vivo"), ("{key_enter}", "confirmar"), ("{key_escape}", "volta ao anterior"),
              ("T", "próximo")]
    BINDINGS = [Binding("enter", "confirm", "Confirmar", show=False)]

    def __init__(self) -> None:
        super().__init__()
        self._original: str | None = None  # tema ao entrar (Esc volta para ele)

    def body(self) -> ComposeResult:
        with Horizontal(id="themes"):
            with Vertical(id="themes-left"):
                yield Static("", id="themes-title")
                yield OptionList(id="themes-list")
            with VerticalScroll(id="themes-middle"):
                yield Static("", id="themes-tokens")
            with VerticalScroll(id="themes-right"):
                yield Static("", id="themes-sample")

    def on_mount(self) -> None:
        super().on_mount()
        self._original = self.app.theme
        self._fill_list()
        self.refresh_content()

    def on_screen_resume(self) -> None:
        self._original = self.app.theme
        self._fill_list()
        self.refresh_content()

    def _fill_list(self) -> None:
        app = self.app
        catalog: dict[str, Tokens] = app.token_sets  # type: ignore[attr-defined]
        option_list = self.query_one("#themes-list", OptionList)
        option_list.clear_options()
        for name, tokens in catalog.items():
            option_list.add_option(Option(f"{name:<18}{tokens.source}", id=name))
        names = list(catalog)
        if app.theme in names:
            option_list.highlighted = names.index(app.theme)

    def refresh_content(self) -> None:
        app = self.app
        tokens = app.tokens  # type: ignore[attr-defined]
        icons = app.icons  # type: ignore[attr-defined]
        title = Text()
        title.append("TEMAS", style=tokens.rich("text-faint")).append(f"  {tokens.name}", style=tokens.rich("accent", bold=True))
        self.query_one("#themes-title", Static).update(title)
        self.query_one("#themes-tokens", Static).update(tokens_text(tokens))
        self.query_one("#themes-sample", Static).update(sample_text(tokens, icons))

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        name = event.option.id
        if name and name != self.app.theme and name in self.app.token_sets:  # type: ignore[attr-defined]
            self.app.theme = name  # preview imediato; o App salva em prefs

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Enter na lista confirma (a lista consome a tecla antes do binding da tela)."""
        self.action_confirm()

    def action_confirm(self) -> None:
        self._original = self.app.theme
        self.app.notify(f"tema: {self.app.theme}")
        self.app.action_goto("dashboard")  # type: ignore[attr-defined]

    def cancel(self) -> None:
        """Esc: volta ao tema de quando a tela abriu."""
        if self._original and self._original != self.app.theme and self._original in self.app.token_sets:  # type: ignore[attr-defined]
            self.app.theme = self._original
