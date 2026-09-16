"""Temas: paletas embutidas do projeto, temas do Textual mapeados para os tokens e a
ponte com `textual.theme.Theme` / `App.register_theme`.

Este é o único módulo de `app/tui` autorizado a conter cores literais (o teste
`tests/test_design.py` faz grep no resto).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import replace
from pathlib import Path

from textual.color import Color
from textual.theme import BUILTIN_THEMES, Theme

from app.config import ROOT_DIR
from app.tui.tokens import Tokens, check_contrast, ensure_contrast

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


# --- temas do usuário (themes/*.json) ---------------------------------------------------

THEMES_DIR = ROOT_DIR / "themes"
USER_THEME_KEYS = {
    "bg", "surface", "surface-raised", "border", "text", "text-muted", "text-faint",
    "accent", "accent-soft", "ok", "warn", "danger", "mine", "other",
}
HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def tokens_from_dict(name: str, data: dict) -> Tokens:
    """Dict com os tokens da seção 4 (chaves com hífen) -> Tokens. Levanta ValueError."""
    if not isinstance(data, dict):
        raise ValueError("o JSON precisa ser um objeto com os tokens")
    unknown = set(data) - USER_THEME_KEYS - {"name", "dark"}
    if unknown:
        raise ValueError(f"chaves desconhecidas: {', '.join(sorted(unknown))}")
    required = ["bg", "surface", "text", "text-muted", "accent", "ok", "warn", "danger"]
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError(f"faltam: {', '.join(missing)}")
    colors = {key: value for key, value in data.items() if key in USER_THEME_KEYS}
    for key, value in colors.items():
        if key == "accent-soft":
            continue  # aceita "#rrggbb 15%"
        if not isinstance(value, str) or not HEX_RE.match(value.strip()):
            raise ValueError(f"{key}: esperado #rrggbb, recebido {value!r}")
    bg = colors["bg"].strip().lower()
    text = colors["text"].strip().lower()
    text_muted = colors["text-muted"].strip().lower()
    surface = colors["surface"].strip().lower()
    return Tokens(
        name=name, dark=bool(data.get("dark", True)), source="usuário",
        bg=bg, surface=surface,
        surface_raised=colors.get("surface-raised", surface).strip().lower(),
        border=colors.get("border", text_muted).strip().lower(),
        text=text, text_muted=text_muted,
        text_faint=colors.get("text-faint", text_muted).strip().lower(),
        accent=colors["accent"].strip().lower(), ok=colors["ok"].strip().lower(),
        warn=colors["warn"].strip().lower(), danger=colors["danger"].strip().lower(),
        accent_soft=colors.get("accent-soft"), mine=colors.get("mine"), other=colors.get("other"),
    )


def load_user_themes(directory: Path | None = None) -> dict[str, Tokens]:
    """Lê `themes/*.json`. Erro de parse ou de validação vira aviso no log e o arquivo é
    ignorado; contraste ruim vira aviso, mas o tema entra."""
    directory = THEMES_DIR if directory is None else directory
    result: dict[str, Tokens] = {}
    if not directory.is_dir():
        return result
    for path in sorted(directory.glob("*.json")):
        name = path.stem.strip().lower()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            tokens = tokens_from_dict(str(data.get("name", name) if isinstance(data, dict) else name), data)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            log.warning("tema %s ignorado: %s", path.name, exc)
            continue
        problems = check_contrast(tokens)
        if problems:
            log.warning("tema %s com contraste baixo: %s", path.name, "; ".join(problems))
        result[tokens.name] = tokens
    return result


# --- esquema de cores do Windows Terminal -------------------------------------------------

WT_DIR = ROOT_DIR / "docs" / "design" / "windows-terminal"
WT_PROFILE_SNIPPET = {
    "font": {"face": "Cascadia Code", "size": 11},
    "padding": "4",
    "useAcrylic": False,
    "cursorShape": "bar",
    "intenseTextStyle": "bold",
    "scrollbarState": "hidden",
    "colorScheme": "carbon",
}


def _hex_upper(value: str) -> str:
    return value.split()[0].strip().upper()


def windows_terminal_scheme(tokens: Tokens) -> dict[str, str]:
    """Esquema `schemes[]` do settings.json do Windows Terminal a partir dos tokens.
    As 16 cores ANSI são derivadas: red/green/yellow = danger/ok/warn, cyan/blue = accent."""
    if tokens.ansi:
        raise ValueError("o tema 'terminal' já usa as cores do próprio Windows Terminal")
    accent = Color.parse(tokens.accent)
    danger = Color.parse(tokens.danger)
    text = Color.parse(tokens.text)
    bg = Color.parse(tokens.bg)
    purple = accent.blend(danger, 0.5).hex
    blue = accent.blend(Color.parse("#3b82f6"), 0.5).hex
    bright = lambda c: Color.parse(c).lighten(0.12).hex  # noqa: E731
    return {
        "name": tokens.name,
        "background": _hex_upper(tokens.bg),
        "foreground": _hex_upper(tokens.text),
        "cursorColor": _hex_upper(tokens.accent),
        "selectionBackground": _hex_upper(tokens.surface_raised),
        "black": _hex_upper(tokens.bg if tokens.dark else tokens.text),
        "red": _hex_upper(tokens.danger),
        "green": _hex_upper(tokens.ok),
        "yellow": _hex_upper(tokens.warn),
        "blue": _hex_upper(blue),
        "purple": _hex_upper(purple),
        "cyan": _hex_upper(tokens.accent),
        "white": _hex_upper(tokens.text_muted if tokens.dark else tokens.surface),
        "brightBlack": _hex_upper(tokens.text_faint),
        "brightRed": _hex_upper(bright(tokens.danger)),
        "brightGreen": _hex_upper(bright(tokens.ok)),
        "brightYellow": _hex_upper(bright(tokens.warn)),
        "brightBlue": _hex_upper(bright(blue)),
        "brightPurple": _hex_upper(bright(purple)),
        "brightCyan": _hex_upper(bright(tokens.accent)),
        "brightWhite": _hex_upper(text.lighten(0.1).hex if tokens.dark else bg.hex),
    }


def write_windows_terminal_scheme(tokens: Tokens, directory: Path | None = None) -> Path:
    """Grava `<nome>.json` com o esquema (para colar em `schemes` do settings.json)."""
    directory = WT_DIR if directory is None else directory
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{tokens.name}.json"
    path.write_text(json.dumps(windows_terminal_scheme(tokens), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def resolve_theme_name(preferred: str, catalog: dict[str, Tokens]) -> str:
    """Nome válido: o pedido, se existir; senão o padrão (com aviso no log)."""
    name = (preferred or "").strip()
    if name in catalog:
        return name
    if name:
        log.warning("tema %r não existe; usando %s", name, DEFAULT_THEME)
    return DEFAULT_THEME
