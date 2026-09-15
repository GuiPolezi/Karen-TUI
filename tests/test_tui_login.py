"""Login humano do ChatPanel pela TUI: automático na 1ª sessão expirada e pela tecla `c`."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from textual.widgets import Static

from app.config import ChatPanelSettings
from app.sources.base import Source
from app.sources.chatpanel import SESSION_EXPIRED, LoginNotCompletedError, SessionExpiredError
from app.state import ChatPanelState
from app.tui.app import CmdAllInOneApp
from tests.helpers import fake_settings, screen_text
from tests.test_tui_workers import wait_until


class FakeChatSource(Source[ChatPanelState]):
    name = "chatpanel"

    def __init__(self, expired: bool = True, login_fails: bool = False):
        super().__init__(interval=60, timeout=1.0)
        self.expired = expired
        self.login_fails = login_fails
        self.fetches = 0
        self.logins = 0

    async def fetch(self) -> ChatPanelState:
        self.fetches += 1
        if self.expired:
            raise SessionExpiredError(SESSION_EXPIRED)
        return ChatPanelState(logged_user="Guilherme", updated_at=datetime(2026, 9, 15, 9, 0, 0))

    async def interactive_login(self, timeout: float = 300.0) -> str:
        self.logins += 1
        if self.login_fails:
            raise LoginNotCompletedError("janela de login fechada antes de completar o login")
        self.expired = False
        return "Guilherme"


def settings(login_on_start: bool):
    return fake_settings(
        chatpanel=ChatPanelSettings(
            url="https://example.com/chat.php", profile_dir=Path(".p"), refresh_seconds=15,
            headless=True, login_on_start=login_on_start,
        )
    )


async def test_expired_session_opens_login_once_and_recovers():
    source = FakeChatSource()
    app = CmdAllInOneApp(settings(login_on_start=True), sources={"chatpanel": source})
    async with app.run_test(size=(120, 30)) as pilot:
        await wait_until(lambda: "chatpanel" in app.states)
        await pilot.pause()
        assert source.logins == 1
        assert source.fetches == 2  # expirada → login → leitura ok
        assert app.login_count == 1
        assert not app.panel("chatpanel").has_class("error")
        assert "login ok: Guilherme" in str(app.query_one("#status-message", Static).content)


async def test_login_on_start_disabled_waits_for_key_c():
    source = FakeChatSource()
    app = CmdAllInOneApp(settings(login_on_start=False), sources={"chatpanel": source})
    async with app.run_test(size=(120, 30)) as pilot:
        await wait_until(lambda: app.panel("chatpanel").has_class("error"))
        await pilot.pause()
        assert source.logins == 0
        assert "pressione c" in screen_text(app, 120, 30)

        await pilot.press("c")
        await wait_until(lambda: "chatpanel" in app.states)
        await pilot.pause()
        assert source.logins == 1
        assert not app.panel("chatpanel").has_class("error")


async def test_failed_login_shows_error_and_keeps_worker_alive():
    source = FakeChatSource(login_fails=True)
    app = CmdAllInOneApp(settings(login_on_start=True), sources={"chatpanel": source})
    async with app.run_test(size=(120, 30)) as pilot:
        await wait_until(lambda: source.logins == 1)
        await wait_until(lambda: app.panel("chatpanel").has_class("error"))
        await pilot.pause()
        text = screen_text(app, 120, 30)
        assert "janela de login fechada" in text
        assert app.login_count == 0
        # a abertura automática é uma vez por execução; a tecla c tenta de novo
        await pilot.press("c")
        await wait_until(lambda: source.logins == 2)


async def test_key_c_without_chatpanel_source_only_shows_message():
    app = CmdAllInOneApp(settings(login_on_start=True), sources={})
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.press("c")
        assert "login não disponível" in str(app.query_one("#status-message", Static).content)
