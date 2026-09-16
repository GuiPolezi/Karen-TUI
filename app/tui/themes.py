"""Temas: paletas embutidas do projeto, temas do Textual mapeados para os tokens e a
ponte com `textual.theme.Theme` / `App.register_theme`.

Este é o único módulo de `app/tui` autorizado a conter cores literais (o teste
`tests/test_design.py` faz grep no resto).
"""

from __future__ import annotations

import logging
from dataclasses import replace

from textual.color import Color
from textual.theme import BUILTIN_THEMES, Theme

from app.tui.tokens import Tokens, ensure_contrast

log = logging.getLogger("themes")

DEFAULT_THEME = "carbon"

CARBON = Tokens(
    name="carbon", dark=True,
    bg="#0e0f11", surface="#15171a", surface_raised="#1e2126", border="#2a2e35",
    text="#d6d9de", text_muted="#8b929c", text_faint="#5e6570",
    accent="#4fc1e9", ok="#5cc46c", warn="#e0a83a", danger="#e5533f",
)
PHOSPHOR = Tokens(
    name="phosphor", dark=True,
    bg="#050a06", surface="#0a140b", surface_raised="#102010", border="#1c3a1e",
    text="#9fe8a2", text_muted="#5fae63", text_faint="#3f7a42",
    accent="#33ff66", ok="#5fd75f", warn="#d6e65a", danger="#ff5c5c",
)
AMBER = Tokens(
    name="amber", dark=True,
    bg="#0b0803", surface="#151009", surface_raised="#20180d", border="#3a2c15",
    text="#ffbd5c", text_muted="#b8863d", text_faint="#7f5f2c",
    accent="#ffcc33", ok="#e0b040", warn="#ffe066", danger="#ff5c5c",
)
PAPER = Tokens(
    name="paper", dark=False,
    bg="#f6f3ec", surface="#efebe2", surface_raised="#e6e1d6", border="#cfc8b8",
    text="#2b2d30", text_muted="#5f6469", text_faint="#8a8f95",
    accent="#1f3a93", ok="#2e7d32", warn="#a85f00", danger="#c62828",
)
# herda as 16 cores do esquema do próprio terminal (Windows Terminal, conhost)
TERMINAL = Tokens(
    name="terminal", dark=True, ansi=True,
    bg="ansi_default", surface="ansi_default", surface_raised="ansi_default", border="ansi_bright_black",
    text="ansi_default", text_muted="ansi_bright_black", text_faint="ansi_bright_black",
    accent="ansi_cyan", ok="ansi_green", warn="ansi_yellow", danger="ansi_red",
    accent_soft="ansi_bright_black",
)

PROJECT_THEMES: tuple[Tokens, ...] = (CARBON, PHOSPHOR, AMBER, PAPER, TERMINAL)
# temas do Textual expostos ao usuário (os outros continuam registrados, mas fora do ciclo T)
TEXTUAL_THEME_NAMES: tuple[str, ...] = (
    "nord", "gruvbox", "catppuccin-mocha", "dracula", "tokyo-night", "monokai", "flexoki",
)


def tokens_from_textual_theme(theme: Theme) -> Tokens:
    """Mapeia um tema do Textual para os tokens. `accent` = `primary` do tema (o `accent`
    deles costuma ser magenta/laranja e viraria uma segunda cor de destaque)."""
    system = theme.to_color_system()
    generated = system.generate()
    bg = generated["background"]
    fg = generated["foreground"]
    surface = generated["surface"]
    raised = generated.get("panel", surface)
    background = Color.parse(bg)
    foreground = Color.parse(fg)

    def legible(color: str) -> str:
        return ensure_contrast(color, bg, fg)

    return Tokens(
        name=theme.name, dark=theme.dark, source="textual",
        bg=bg, surface=surface, surface_raised=raised,
        border=foreground.blend(background, 0.80).hex,
        text=fg,
        text_muted=foreground.blend(background, 0.38).hex,
        text_faint=foreground.blend(background, 0.58).hex,
        accent=legible(theme.primary), ok=legible(theme.success or generated["success"]),
        warn=legible(theme.warning or generated["warning"]), danger=legible(theme.error or generated["error"]),
    )


def build_theme(tokens: Tokens) -> Theme:
    """`Tokens` -> `textual.theme.Theme`, com as variáveis CSS dos tokens."""
    return Theme(
        name=tokens.name,
        primary=tokens.accent, secondary=tokens.text_muted, accent=tokens.accent,
        foreground=tokens.text, background=tokens.bg, surface=tokens.surface,
        panel=tokens.surface_raised, boost=tokens.surface_raised,
        success=tokens.ok, warning=tokens.warn, error=tokens.danger,
        dark=tokens.dark, ansi=tokens.ansi,
        variables=tokens.css_variables(),
    )


def all_tokens(extra: dict[str, Tokens] | None = None) -> dict[str, Tokens]:
    """Todos os temas disponíveis, na ordem em que `T` cicla: embutidos do projeto, temas
    do Textual mapeados e, por fim, os do usuário (`extra`)."""
    result: dict[str, Tokens] = {t.name: t for t in PROJECT_THEMES}
    for name in TEXTUAL_THEME_NAMES:
        theme = BUILTIN_THEMES.get(name)
        if theme is not None:
            result[name] = tokens_from_textual_theme(theme)
    for name, tokens in (extra or {}).items():
        if name in result:
            log.warning("tema do usuário %r tem o nome de um tema embutido; ignorado", name)
            continue
        result[name] = tokens
    return result


def register_themes(app, extra: dict[str, Tokens] | None = None, *,  # noqa: ANN001
                    legacy_console: bool = False) -> dict[str, Tokens]:
    """Registra todos os temas no App e devolve o dicionário nome -> Tokens.
    Em conhost (sem `dim`), `text-faint` vira `text-muted` para continuar legível."""
    catalog = all_tokens(extra)
    if legacy_console:
        catalog = {name: replace(tokens, text_faint=tokens.text_muted) for name, tokens in catalog.items()}
    for tokens in catalog.values():
        app.register_theme(build_theme(tokens))
    return catalog


def resolve_theme_name(preferred: str, catalog: dict[str, Tokens]) -> str:
    """Nome válido: o pedido, se existir; senão o padrão (com aviso no log)."""
    name = (preferred or "").strip()
    if name in catalog:
        return name
    if name:
        log.warning("tema %r não existe; usando %s", name, DEFAULT_THEME)
    return DEFAULT_THEME
