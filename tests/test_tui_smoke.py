"""Smoke test da TUI: monta o app sem terminal real e verifica o skeleton."""

from pathlib import Path

import pytest

from app.config import ChatPanelSettings, EmailSettings, MilldeskSettings, Settings
from app.tui.app import CmdAllInOneApp
from app.tui.widgets.base_panel import BasePanel
from app.tui.widgets.status_bar import StatusBar
from textual.containers import Container
from textual.widgets import Static


def fake_settings() -> Settings:
    return Settings(
        tech_name="Guilherme",
        email=EmailSettings(
            host="imap.example.com", port=143, starttls=True, user="x@example.com",
            password="", inbox_folder="INBOX", spam_folder=None, refresh_seconds=30,
        ),
        milldesk=MilldeskSettings(api_key="", base_url="https://example.com/api", refresh_seconds=60),
        chatpanel=ChatPanelSettings(
            url="https://example.com/chat.php", profile_dir=Path(".p"), refresh_seconds=15, headless=True,
        ),
        notify_bell=False,
        log_level="INFO",
        log_dir=Path("logs"),
    )


async def test_three_panels_waiting_and_clock_running():
    app = CmdAllInOneApp(fake_settings())
    async with app.run_test(size=(120, 40)) as pilot:
        panels = app.query(BasePanel)
        assert len(panels) == 3
        for panel in panels:
            body = panel.query_one(".panel-body", Static)
            assert "aguardando" in str(body.content)
        clock = app.query_one("#clock", Static)
        assert "Guilherme ·" in str(clock.content)
        assert not app.query_one("#main", Container).has_class("narrow")

        await pilot.press("1")
        message = app.query_one("#status-message", Static)
        assert "Fase 1" in str(message.content)


async def test_narrow_terminal_stacks_top_row():
    app = CmdAllInOneApp(fake_settings())
    async with app.run_test(size=(80, 40)):
        assert app.query_one("#main", Container).has_class("narrow")


async def test_panel_error_keeps_body_and_marks_border():
    app = CmdAllInOneApp(fake_settings())
    async with app.run_test(size=(120, 40)) as pilot:
        panel = app.panel("email")
        panel.set_body("Inbox: 10")
        panel.set_error("timeout")
        await pilot.pause()
        assert panel.has_class("error")
        assert "Inbox: 10" in str(panel.query_one(".panel-body", Static).content)
        assert panel.query_one(".panel-error", Static).display is True

        panel.set_error(None)
        await pilot.pause()
        assert not panel.has_class("error")
        assert panel.query_one(".panel-error", Static).display is False
