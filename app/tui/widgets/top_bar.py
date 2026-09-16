"""Barra superior (1 linha, sem borda, fundo `surface`).

À esquerda: marcador `▍` em `accent`, nome do app em bold e nome da tela em `text-muted`.
Ao centro: um ponto de saúde por fonte (ok / coletando / aguardando / erro / não
configurada), com tooltip do motivo. À direita: estados transitórios (silêncio com tempo
restante, login em andamento), o técnico e o relógio `HH:MM:SS`.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static

from app import clock
from app.tui.icons import spinner_frame

APP_TITLE = "CMD ALL-IN-ONE"
SOURCE_ORDER = ("email", "milldesk", "chatpanel")
SOURCE_LABELS = {"email": "E-mail", "milldesk": "Milldesk", "chatpanel": "ChatPanel"}
TICK_SECONDS = 0.5

# estado -> (nome do ícone em IconSet ou None para o spinner, token de cor)
DOT_STYLE: dict[str, tuple[str | None, str]] = {
    "ok": ("online", "ok"),
    "busy": (None, "accent"),
    "wait": ("offline", "text-muted"),
    "warn": ("warn", "warn"),
    "danger": ("error", "danger"),
    "off": ("offline", "text-faint"),
}


class HealthDot(Static):
    """Um ponto de saúde de uma fonte; `set_state` troca glifo, cor e tooltip."""

    def __init__(self, source: str) -> None:
        super().__init__("", classes="topbar-dot")
        self.source = source
        self.state = "wait"
        self.detail = ""

    def set_state(self, state: str, detail: str) -> None:
        self.state, self.detail = state, detail
        icons = self.app.icons  # type: ignore[attr-defined]
        tokens = self.app.tokens  # type: ignore[attr-defined]
        icon_name, token = DOT_STYLE.get(state, DOT_STYLE["wait"])
        if icon_name is None:
            glyph = spinner_frame(icons.spinner)
        else:
            glyph = getattr(icons, icon_name)
        self.update(Text(glyph, style=tokens.rich(token)))
        self.tooltip = f"{SOURCE_LABELS.get(self.source, self.source)} · {detail}"


class TopBar(Horizontal):
    def __init__(self, screen_name: str, tech_name: str) -> None:
        super().__init__(id="topbar")
        self.screen_name = screen_name
        self.tech_name = tech_name

    def compose(self) -> ComposeResult:
        yield Static("", id="topbar-title")
        with Horizontal(id="topbar-health"):
            for source in SOURCE_ORDER:
                yield HealthDot(source)
        yield Static("", id="topbar-status")

    def on_mount(self) -> None:
        self.render_title()
        self.tick()
        self.set_interval(TICK_SECONDS, self.tick)

    def render_title(self) -> None:
        tokens = self.app.tokens  # type: ignore[attr-defined]
        icons = self.app.icons  # type: ignore[attr-defined]
        text = Text(no_wrap=True, overflow="ellipsis")
        text.append(icons.focus, style=tokens.rich("accent"))
        text.append(APP_TITLE, style=tokens.rich("text", bold=True))
        text.append(f"  {self.screen_name}", style=tokens.rich("text-muted"))
        self.query_one("#topbar-title", Static).update(text)

    def tick(self) -> None:
        app = self.app
        status_of = getattr(app, "source_status", None)
        if status_of is not None:
            for dot in self.query(HealthDot):
                state, detail = status_of(dot.source)
                dot.set_state(state, detail)
        self.render_status()

    def render_status(self) -> None:
        tokens = self.app.tokens  # type: ignore[attr-defined]
        text = Text(no_wrap=True, overflow="ellipsis", justify="right")
        extras = getattr(self.app, "topbar_extras", lambda: [])()
        for label, token in extras:
            text.append(label, style=tokens.rich(token)).append("   ")
        text.append(self.tech_name, style=tokens.rich("text-muted"))
        text.append("  ").append(clock.now().strftime("%H:%M:%S"), style=tokens.rich("text"))
        self.query_one("#topbar-status", Static).update(text)

    def refresh_theme(self) -> None:
        """Chamado pelo App quando o tema muda (as cores estão em estilos Rich)."""
        self.render_title()
        self.tick()
