"""Sistema de design (Ciclo 3): contraste dos temas, largura dos glifos, nenhuma cor
literal nem emoji em app/tui, rodapé que cabe numa linha, pontos de saúde da TopBar e
troca de tema sem perder o cursor."""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

import pytest
from rich.cells import cell_len

from app.prefs import Prefs
from app.tui import demo
from app.tui.icons import ASCII, ICON_SETS, NERD, UNICODE, detect_mode, glyphs, resolve_icons
from app.tui.themes import CARBON, TERMINAL, all_tokens, build_theme, resolve_theme_name
from app.tui.tokens import TOKEN_NAMES, check_contrast, contrast
from app.tui.widgets.footer_bar import FooterBar, fit_items
from app.tui.widgets.top_bar import HealthDot
from tests.helpers import make_app, screen_text, wait_until

TUI_DIR = Path(__file__).resolve().parent.parent / "app" / "tui"
COLOR_WORDS = r"(?:red|green|yellow|blue|magenta|cyan|white|black|grey|gray|bright_[a-z]+)"
# estilo Rich literal dentro de uma string: "bold red", "cyan", "on yellow", "[red]"
RICH_LITERAL = re.compile(rf'["\'](?:(?:bold|dim|italic|on)\s+)*{COLOR_WORDS}\b[^"\']*["\']|\[(?:bold |dim )?{COLOR_WORDS}\]')
HEX_IN_STRING = re.compile(r'["\'][^"\'\n]*#[0-9a-fA-F]{6}\b[^"\'\n]*["\']')
TCSS_LITERAL = re.compile(rf"(?<![$\w-])(?:{COLOR_WORDS}|ansi_[a-z_]+)\b|#[0-9a-fA-F]{{3,8}}\b")


# --- tokens e contraste -----------------------------------------------------------------


def test_contrast_is_wcag():
    assert contrast("#000000", "#ffffff") == pytest.approx(21.0, abs=0.01)
    assert contrast("#777777", "#777777") == pytest.approx(1.0)
    assert contrast("#fff", "#000") == pytest.approx(21.0, abs=0.01)


def test_every_registered_theme_passes_minimum_contrast():
    catalog = all_tokens()
    assert {"carbon", "phosphor", "amber", "paper", "terminal", "nord", "dracula"} <= set(catalog)
    for tokens in catalog.values():
        assert check_contrast(tokens) == [], tokens.name


def test_check_contrast_reports_low_contrast():
    bad = replace(CARBON, name="ruim", text="#2a2a2a", text_muted="#1f1f1f")
    problems = check_contrast(bad)
    assert any(p.startswith("text/bg") for p in problems)
    assert any(p.startswith("text-muted/bg") for p in problems)


def test_css_variables_cover_tokens_and_textual_names():
    variables = CARBON.css_variables()
    for token in TOKEN_NAMES:
        assert token in variables
    for native in ("background", "surface", "panel", "foreground", "primary", "success", "warning", "error",
                   "block-cursor-background", "input-cursor-background", "scrollbar", "footer-key-foreground"):
        assert native in variables
    assert variables["accent-soft"] == "#4fc1e9 15%"
    assert variables["mine"] == variables["accent"]
    assert variables["other"] == variables["text-muted"]


def test_rich_styles_from_tokens():
    assert CARBON.rich("accent") == "#4fc1e9"
    assert CARBON.rich("danger", bold=True) == "bold #e5533f"
    assert CARBON.rich("text", dim=True, on="surface-raised") == "dim #d6d9de on #1e2126"
    # tema do terminal: cores ANSI viram nomes do Rich; default vira vazio
    assert TERMINAL.rich("accent") == "cyan"
    assert TERMINAL.rich("text", bold=True) == "bold"
    assert build_theme(TERMINAL).ansi is True
    assert build_theme(CARBON).variables["text-muted"] == "#8b929c"


def test_resolve_theme_name_falls_back_to_carbon():
    catalog = all_tokens()
    assert resolve_theme_name("paper", catalog) == "paper"
    assert resolve_theme_name("inexistente", catalog) == "carbon"
    assert resolve_theme_name("", catalog) == "carbon"


# --- ícones ------------------------------------------------------------------------------


@pytest.mark.parametrize("icon_set", list(ICON_SETS.values()), ids=list(ICON_SETS))
def test_icons_never_use_wide_glyphs(icon_set):
    for name, text in glyphs(icon_set):
        assert text, name
        for char in text:
            assert cell_len(char) == 1, f"{icon_set.mode}.{name}: {char!r} ocupa {cell_len(char)} células"


def test_icon_mode_detection_and_resolution():
    assert detect_mode({"WT_SESSION": "1"}, "win32") == "unicode"
    assert detect_mode({}, "win32") == "ascii"
    assert detect_mode({}, "linux") == "unicode"
    assert resolve_icons("nerd") is NERD
    assert resolve_icons("ASCII") is ASCII
    assert resolve_icons("qualquer") is UNICODE
    assert resolve_icons("auto", environ={}, platform="win32") is ASCII


# --- disciplina: nada de cor literal nem emoji fora de themes.py --------------------------


def _tui_files(suffix: str) -> list[Path]:
    return sorted(p for p in TUI_DIR.rglob(f"*{suffix}") if "__pycache__" not in p.parts)


def test_no_literal_colors_in_tui_python():
    offenders = []
    for path in _tui_files(".py"):
        if path.name == "themes.py":
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if RICH_LITERAL.search(line) or HEX_IN_STRING.search(line):
                offenders.append(f"{path.relative_to(TUI_DIR)}:{number}: {line.strip()}")
    assert not offenders, "\n".join(offenders)


def test_no_literal_colors_in_tcss():
    offenders = []
    for path in _tui_files(".tcss"):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if TCSS_LITERAL.search(line):
                offenders.append(f"{path.name}:{number}: {line.strip()}")
    assert not offenders, "\n".join(offenders)


def test_no_wide_glyphs_in_tui():
    offenders = []
    for path in [*_tui_files(".py"), *_tui_files(".tcss")]:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            wide = {ch for ch in line if ord(ch) > 0x7F and cell_len(ch) == 2}
            if wide:
                offenders.append(f"{path.relative_to(TUI_DIR)}:{number}: {' '.join(sorted(wide))}")
    assert not offenders, "\n".join(offenders)


# --- rodapé -------------------------------------------------------------------------------


def test_fit_items_drops_from_the_end_but_keeps_help():
    items = [("↑↓", "mover"), ("⏎", "abrir"), ("/", "filtrar"), ("o", "navegador"), ("?", "ajuda")]
    assert fit_items(items, 200) == items
    narrow = fit_items(items, 30)
    assert narrow[-1] == ("?", "ajuda") and len(narrow) < len(items)
    assert fit_items(items, 8) == [("?", "ajuda")]
    assert fit_items(items, 3) == []
    assert fit_items([], 50) == []


async def test_footer_shows_only_current_screen_items():
    app = make_app(sources=demo.demo_sources())
    async with app.run_test(size=(120, 35)) as pilot:
        await wait_until(lambda: "milldesk" in app.states)
        await pilot.pause()
        footer = app.screen.query_one(FooterBar)
        plain = footer.render().plain  # type: ignore[union-attr]
        assert "launcher" in plain and plain.rstrip().endswith("ajuda")
        assert "f1" not in plain.lower().split("dashboard")[0]  # teclas F não ocupam o rodapé
        await pilot.press("f3")
        await pilot.pause()
        plain = app.screen.query_one(FooterBar).render().plain  # type: ignore[union-attr]
        assert "ordem: SLA mais próximo" in plain
        await pilot.press("s")
        await pilot.pause()
        plain = app.screen.query_one(FooterBar).render().plain  # type: ignore[union-attr]
        assert "ordem: mais recente" in plain


# --- TopBar -------------------------------------------------------------------------------


async def test_topbar_health_dots_follow_source_status():
    sources = demo.demo_sources(email_error="limite de requisições (HTTP 429)", chat_unconfigured=True)
    app = make_app(sources=sources)
    async with app.run_test(size=(120, 35)) as pilot:
        await wait_until(lambda: "milldesk" in app.states and app.errors.get("email"))
        await pilot.pause(0.6)  # um tick da TopBar
        states = {dot.source: dot.state for dot in app.screen.query(HealthDot)}
        assert states == {"email": "warn", "milldesk": "ok", "chatpanel": "off"}
        assert app.source_status("email")[0] == "warn"
        assert "não configurada" in app.source_status("chatpanel")[1]
        text = screen_text(app, 120, 35)
        assert "Guilherme" in text and "CMD ALL-IN-ONE" in text and "Dashboard" in text


# --- troca de tema ------------------------------------------------------------------------


async def test_theme_switch_keeps_cursor_and_saves_pref():
    app = make_app(sources=demo.demo_sources(), prefs=Prefs())
    async with app.run_test(size=(120, 35)) as pilot:
        await wait_until(lambda: "milldesk" in app.states)
        await pilot.pause()
        assert app.theme == "carbon" and app.tokens.name == "carbon"
        panel = app.panel("milldesk")
        panel.table.select_key("4821")
        app.theme = "paper"
        await pilot.pause()
        assert app.tokens.name == "paper"
        assert panel.table.selected_key == "4821"
        assert app.prefs.theme == "paper"
        await pilot.press("T")
        await pilot.pause()
        assert app.theme != "paper" and app.theme in app.token_sets
        assert app.set_theme("inexistente") is False
        assert "não existe" in app.last_message


async def test_theme_from_settings_and_prefs_priority():
    app = make_app(settings=demo.demo_settings(theme="phosphor"), sources={}, prefs=Prefs(theme="amber"))
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        assert app.theme == "amber"
    app = make_app(settings=demo.demo_settings(theme="phosphor"), sources={}, prefs=Prefs())
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        assert app.theme == "phosphor"
