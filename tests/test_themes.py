"""Temas configuráveis (Ciclo 3, 7.5): temas do usuário em themes/*.json, comandos `theme`
no launcher, tela de preview (F9) com preview ao vivo/confirmar/voltar e exportação de
esquema para o Windows Terminal."""

from __future__ import annotations

import json
from pathlib import Path

from textual.widgets import OptionList

from app.config import UrlSettings
from app.prefs import Prefs
from app.tui import demo
from app.tui.launcher import parse_command
from app.tui.screens import ThemesScreen
from app.tui.themes import (
    CARBON,
    TERMINAL,
    all_tokens,
    load_user_themes,
    tokens_from_dict,
    windows_terminal_scheme,
    write_windows_terminal_scheme,
)
from app.tui.tokens import check_contrast
from tests.helpers import make_app, wait_until

URLS = UrlSettings()


def test_user_theme_loading_valid_invalid_and_low_contrast(tmp_path: Path, caplog):
    good = {"bg": "#101418", "surface": "#161b21", "text": "#d8dee6", "text-muted": "#8d99a6",
            "accent": "#7cc7ff", "ok": "#6cc26f", "warn": "#e2b04a", "danger": "#ef6b5f"}
    (tmp_path / "meu.json").write_text(json.dumps(good), encoding="utf-8")
    (tmp_path / "quebrado.json").write_text("{ isso não é json", encoding="utf-8")
    (tmp_path / "faltando.json").write_text(json.dumps({"bg": "#000000"}), encoding="utf-8")
    (tmp_path / "corinvalida.json").write_text(json.dumps({**good, "accent": "azul"}), encoding="utf-8")
    low = {**good, "text": "#2a2a2a"}
    (tmp_path / "apagado.json").write_text(json.dumps(low), encoding="utf-8")
    with caplog.at_level("WARNING", logger="themes"):
        themes = load_user_themes(tmp_path)
    assert set(themes) == {"meu", "apagado"}
    assert themes["meu"].source == "usuário"
    assert themes["meu"].text_faint == themes["meu"].text_muted  # opcional: cai no text-muted
    assert themes["meu"].value("accent-soft") == "#7cc7ff 15%"
    messages = " ".join(caplog.messages)
    assert "quebrado.json" in messages and "faltando.json" in messages and "corinvalida.json" in messages
    assert "apagado.json" in messages and "contraste" in messages
    assert check_contrast(themes["apagado"])  # entra, mas com aviso
    assert load_user_themes(tmp_path / "inexistente") == {}


def test_tokens_from_dict_rejects_unknown_keys():
    try:
        tokens_from_dict("x", {"bg": "#000000", "cor": "#ffffff"})
    except ValueError as exc:
        assert "desconhecidas" in str(exc)
    else:
        raise AssertionError("deveria rejeitar chave desconhecida")


def test_example_theme_file_is_valid_and_readable():
    example = Path(__file__).resolve().parent.parent / "themes" / "exemplo.json"
    themes = load_user_themes(example.parent)
    assert "exemplo" in themes
    assert check_contrast(themes["exemplo"]) == []


def test_user_theme_cannot_shadow_builtin(caplog):
    shadow = {"carbon": CARBON}
    with caplog.at_level("WARNING", logger="themes"):
        catalog = all_tokens(shadow)
    assert catalog["carbon"].source == "embutido"


def test_windows_terminal_scheme_has_all_16_colors(tmp_path: Path):
    scheme = windows_terminal_scheme(CARBON)
    required = {"name", "background", "foreground", "cursorColor", "selectionBackground", "black", "red", "green",
                "yellow", "blue", "purple", "cyan", "white", "brightBlack", "brightRed", "brightGreen",
                "brightYellow", "brightBlue", "brightPurple", "brightCyan", "brightWhite"}
    assert required <= set(scheme)
    for key, value in scheme.items():
        if key != "name":
            assert value.startswith("#") and len(value) == 7 and value == value.upper(), key
    assert scheme["cyan"] == "#4FC1E9" and scheme["red"] == "#E5533F"
    path = write_windows_terminal_scheme(CARBON, tmp_path)
    assert json.loads(path.read_text(encoding="utf-8"))["name"] == "carbon"
    try:
        windows_terminal_scheme(TERMINAL)
    except ValueError:
        pass
    else:
        raise AssertionError("tema terminal não é exportável")


def test_parse_theme_commands():
    assert parse_command("theme", {}, URLS).kind == "theme_list"
    assert parse_command("theme next", {}, URLS).kind == "theme_next"
    assert parse_command("theme paper", {}, URLS).arg == "paper"
    assert parse_command("tema Paper", {}, URLS).arg == "paper"
    assert parse_command("theme preview", {}, URLS).arg == "themes"
    assert parse_command("theme export wt", {}, URLS).kind == "theme_export"
    assert parse_command("temas", {}, URLS).arg == "themes"


async def test_theme_commands_in_app(tmp_path: Path, monkeypatch):
    import app.tui.app as app_module

    monkeypatch.setattr(app_module, "write_windows_terminal_scheme",
                        lambda tokens: write_windows_terminal_scheme(tokens, tmp_path))
    app = make_app(sources=demo.demo_sources(), prefs=Prefs())
    async with app.run_test(size=(120, 35)) as pilot:
        await wait_until(lambda: "milldesk" in app.states)
        assert app.run_command("theme paper") is False
        await pilot.pause()
        assert app.theme == "paper" and app.prefs.theme == "paper"
        assert app.run_command("theme next") is False
        await pilot.pause()
        assert app.theme == "terminal"
        assert app.run_command("theme inexistente") is False
        assert "não existe" in app.last_message
        app.set_theme("carbon")
        await pilot.pause()
        assert app.run_command("theme export wt") is False
        assert (tmp_path / "carbon.json").exists()
        assert "carbon" in app.last_message and "schemes" in app.last_message
        app.set_theme("terminal")
        await pilot.pause()
        assert app.run_command("theme export wt") is False
        assert "nada a exportar" in app.last_message


async def test_preview_screen_applies_live_confirms_and_reverts():
    app = make_app(sources=demo.demo_sources(), prefs=Prefs())
    async with app.run_test(size=(120, 35)) as pilot:
        await wait_until(lambda: "milldesk" in app.states)
        await pilot.press("f9")
        await pilot.pause()
        assert app.current_mode == "themes" and isinstance(app.screen, ThemesScreen)
        option_list = app.screen.query_one("#themes-list", OptionList)
        assert option_list.highlighted == list(app.token_sets).index("carbon")
        await pilot.press("down")
        await pilot.pause()
        assert app.theme == "phosphor"  # preview ao vivo
        await pilot.press("escape")
        await pilot.pause()
        assert app.current_mode == "dashboard" and app.theme == "carbon"  # Esc volta ao anterior

        await pilot.press("f9")
        await pilot.pause()
        await pilot.press("down", "down")
        await pilot.pause()
        assert app.theme == "amber"
        await pilot.press("enter")
        await pilot.pause()
        assert app.current_mode == "dashboard" and app.theme == "amber" and app.prefs.theme == "amber"
        # a lista do Milldesk não perdeu o cursor com as trocas
        assert app.panel("milldesk").table.selected_key is not None
