"""Fase 6.4: parser do launcher (offline) e a tela `:` / ajuda `?` na TUI."""

from __future__ import annotations

import pytest

from app.config import UrlSettings
from app.prefs import Prefs
from app.tui.launcher import parse_command
from app.tui.screens import HelpScreen, LauncherScreen, TicketDetailScreen
from tests.helpers import fake_settings, make_app, screen_text, wait_until
from tests.test_ticket_detail import FakeMilldeskSource

URLS = UrlSettings(webmail="https://mail.x/", milldesk="https://md.x/#", chatpanel="https://cp.x/chat.php")
NO_URLS = UrlSettings()


@pytest.mark.parametrize("text, kind, arg", [
    ("g erro 500", "search", "https://www.google.com/search?q=erro+500"),
    ("erro 500 sem prefixo", "search", "https://www.google.com/search?q=erro+500+sem+prefixo"),
    ("ddg textual", "search", "https://duckduckgo.com/?q=textual"),
    ("yt python tui", "search", "https://www.youtube.com/results?search_query=python+tui"),
    ("md 1234", "ticket", "1234"),
    ("md #1234", "ticket", "1234"),
    ("md! 1234", "open", "https://md.x/#"),
    ("wa 55 (11) 99999-9999", "open", "https://wa.me/5511999999999"),
    ("cp", "open", "https://cp.x/chat.php"),
    ("mail", "open", "https://mail.x/"),
    ("mdweb", "open", "https://md.x/#"),
    ("open example.com/x", "open", "https://example.com/x"),
    ("open http://a.b", "open", "http://a.b"),
    ("tickets", "goto", "milldesk"),
    ("dash", "goto", "dashboard"),
    ("notas", "goto", "notes"),
    ("refresh", "refresh", ""),
    ("refresh md", "refresh", "milldesk"),
    ("help", "help", ""),
    ("", "empty", ""),
])
def test_parse_command(text, kind, arg):
    action = parse_command(text, {"docs": "https://d.x"}, URLS)
    assert (action.kind, action.arg) == (kind, arg)


def test_parse_command_favorites_and_errors():
    favs = {"docs": "https://d.x"}
    assert parse_command("fav docs", favs, URLS).arg == "https://d.x"
    add = parse_command("fav add wiki wiki.x/home", favs, URLS)
    assert (add.kind, add.arg, add.label) == ("fav_add", "wiki", "https://wiki.x/home")
    assert parse_command("fav rm wiki", favs, URLS).kind == "fav_rm"
    assert parse_command("fav", favs, URLS).kind == "fav_list"
    assert "não existe" in parse_command("fav nada", favs, URLS).label
    assert parse_command("md", favs, URLS).kind == "error"
    assert parse_command("md! 12", favs, NO_URLS).kind == "error"  # sem URL não chuta
    assert "MILLDESK_WEB_URL" in parse_command("mdweb", favs, NO_URLS).label
    assert parse_command("refresh xpto", favs, URLS).kind == "error"
    assert parse_command("md! 77", favs, URLS).copy == "77"


class Browser:
    def __init__(self):
        self.opened: list[str] = []

    def __call__(self, url: str) -> bool:
        self.opened.append(url)
        return True


async def test_launcher_search_goto_ticket_and_history(monkeypatch):
    browser = Browser()
    import app.tui.app as app_module

    monkeypatch.setattr(app_module.webbrowser, "open_new_tab", browser)
    source = FakeMilldeskSource()
    app = make_app(fake_settings(urls=URLS), sources={"milldesk": source})
    async with app.run_test(size=(120, 36)) as pilot:
        await wait_until(lambda: "milldesk" in app.states)
        await pilot.press("colon")
        await pilot.pause()
        assert isinstance(app.screen, LauncherScreen)
        for ch in "g erro 500":
            await pilot.press(ch if ch != " " else "space")
        await pilot.press("enter")
        await pilot.pause()
        assert browser.opened == ["https://www.google.com/search?q=erro+500"]
        assert not isinstance(app.screen, LauncherScreen)
        assert "Google: erro 500" in app.last_message
        assert app.prefs.history == ["g erro 500"]

        await pilot.press("colon")
        await pilot.pause()
        for ch in "tickets":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause()
        assert app.current_mode == "milldesk"

        await pilot.press("colon")
        await pilot.pause()
        for ch in "md 4242":
            await pilot.press(ch if ch != " " else "space")
        await pilot.press("enter")
        await wait_until(lambda: source.detail_calls == 1)
        await pilot.pause()
        assert isinstance(app.screen, TicketDetailScreen)
        await pilot.press("escape")
        await pilot.pause()

        await pilot.press("colon")
        await pilot.pause()
        await pilot.press("up")  # histórico: último comando
        await pilot.pause()
        from textual.widgets import Input

        assert app.screen.query_one("#launcher-input", Input).value == "md 4242"
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, LauncherScreen)


async def test_launcher_errors_keep_it_open_and_help_opens(monkeypatch):
    app = make_app(fake_settings(urls=NO_URLS), prefs=Prefs())
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.press("colon")
        await pilot.pause()
        for ch in "mdweb":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, LauncherScreen)  # erro mantém aberto
        assert "MILLDESK_WEB_URL" in screen_text(app, 120, 36)
        assert app.prefs.history == []  # erro não entra no histórico

        for _ in range(5):
            await pilot.press("backspace")
        for ch in "help":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)
        assert "md 1234" in screen_text(app, 120, 36)
        await pilot.press("escape")
        await pilot.pause()
        await pilot.press("question_mark")
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)


async def test_launcher_favorites_roundtrip(monkeypatch):
    browser = Browser()
    import app.tui.app as app_module

    monkeypatch.setattr(app_module.webbrowser, "open_new_tab", browser)
    app = make_app(fake_settings(urls=URLS))
    async with app.run_test(size=(120, 36)) as pilot:
        assert app.run_command("fav add wiki wiki.x") is False
        assert app.prefs.favorites == {"wiki": "https://wiki.x"}
        assert app.run_command("fav wiki") is False
        assert browser.opened == ["https://wiki.x"]
        assert app.run_command("fav rm wiki") is False
        assert app.prefs.favorites == {}
        assert app.run_command("fav") is True
        assert "nenhum favorito" in app.last_message
