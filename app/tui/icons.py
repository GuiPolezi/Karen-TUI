"""Ícones da TUI em três conjuntos (`ICONS=nerd|unicode|ascii|auto`).

Regra: nenhum glifo de largura 2 (emoji desalinha colunas no Windows Terminal e no
conhost). O teste `tests/test_design.py` percorre todos os conjuntos com
`rich.cells.cell_len` e falha se algum caractere ocupar mais de uma célula.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, fields

SPINNER_BRAILLE = "⠋⠙⠹⠸⠼⠴⠦⠧"
SPINNER_ASCII = "|/-\\"


@dataclass(frozen=True)
class IconSet:
    mode: str
    email: str
    ticket: str
    chat: str
    online: str
    offline: str
    change: str      # marcador de "mudou neste ciclo" (à esquerda da célula)
    focus: str       # marcador do painel focado / linha selecionada
    error: str
    warn: str
    ok: str
    empty: str       # "não configurado"
    search: str      # linha de filtro
    sla: str         # prefixo da linha de SLA
    more: str        # "+7 · F3" e truncamento
    bar_on: str      # barra de SLA cheia
    bar_off: str     # barra de SLA vazia
    mute: str        # silêncio (TopBar)
    login: str       # janela de login aberta (TopBar)
    sep: str         # separador "·"
    arrow: str       # "Tag › Depto"
    key_up_down: str
    key_enter: str
    key_tab: str
    key_escape: str
    spinner: str     # quadros do spinner, um caractere por quadro


NERD = IconSet(
    mode="nerd", email="", ticket="", chat="", online="", offline="",
    change="▎", focus="▍", error="✗", warn="!", ok="✓", empty="–", search="⌕", sla="▸", more="…",
    bar_on="▮", bar_off="▯", mute="", login="", sep="·", arrow="›",
    key_up_down="↑↓", key_enter="⏎", key_tab="⇥", key_escape="Esc", spinner=SPINNER_BRAILLE,
)
UNICODE = IconSet(
    mode="unicode", email="✉", ticket="▣", chat="◉", online="●", offline="○",
    change="▎", focus="▍", error="✗", warn="!", ok="✓", empty="–", search="⌕", sla="▸", more="…",
    bar_on="▮", bar_off="▯", mute="◌", login="⟳", sep="·", arrow="›",
    key_up_down="↑↓", key_enter="⏎", key_tab="⇥", key_escape="Esc", spinner=SPINNER_BRAILLE,
)
ASCII = IconSet(
    mode="ascii", email="@", ticket="#", chat="*", online="o", offline=".",
    change=">", focus="|", error="x", warn="!", ok="+", empty="-", search="?", sla=">", more="...",
    bar_on="#", bar_off="-", mute="M", login="L", sep=".", arrow=">",
    key_up_down="^v", key_enter="Enter", key_tab="Tab", key_escape="Esc", spinner=SPINNER_ASCII,
)

ICON_SETS: dict[str, IconSet] = {"nerd": NERD, "unicode": UNICODE, "ascii": ASCII}
ICON_MODES: tuple[str, ...] = ("auto", *ICON_SETS)


def detect_mode(environ: dict[str, str] | None = None, platform: str | None = None) -> str:
    """`auto`: unicode no Windows Terminal e fora do Windows; ascii no conhost legado.
    Nerd Font não é detectável pelo app, então `nerd` é sempre opt-in."""
    env = os.environ if environ is None else environ
    platform = platform or sys.platform
    if platform != "win32":
        return "unicode"
    if env.get("WT_SESSION") or env.get("TERM_PROGRAM") or env.get("ConEmuANSI"):
        return "unicode"
    return "ascii"


def is_legacy_console(environ: dict[str, str] | None = None, platform: str | None = None) -> bool:
    """conhost (cmd.exe/powershell fora do Windows Terminal): 16 cores e sem `dim`."""
    return detect_mode(environ, platform) == "ascii"


def resolve_icons(mode: str = "auto", **detect_kwargs: object) -> IconSet:
    mode = (mode or "auto").strip().lower()
    if mode == "auto":
        mode = detect_mode(**detect_kwargs)  # type: ignore[arg-type]
    return ICON_SETS.get(mode, UNICODE)


def glyphs(icon_set: IconSet) -> list[tuple[str, str]]:
    """(nome, texto) de cada ícone do conjunto, para testes e para a tela de preview."""
    return [(f.name, getattr(icon_set, f.name)) for f in fields(icon_set) if f.name != "mode"]
