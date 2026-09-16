"""Utilitários compartilhados pelos testes."""

from __future__ import annotations

import asyncio
import io
from pathlib import Path
from typing import Any

from rich.console import Console
from textual.app import App

from app.config import ChatPanelSettings, EmailSettings, MilldeskSettings, Settings
from app.prefs import Prefs
from app.tui.app import CmdAllInOneApp


def fake_settings(**overrides) -> Settings:
    base = dict(
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
        icons="unicode",  # não depender do terminal que roda os testes
    )
    base.update(overrides)
    return Settings(**base)


def make_app(settings: Settings | None = None, sources: dict[str, Any] | None = None,
             prefs: Prefs | None = None) -> CmdAllInOneApp:
    """App de teste: preferências em memória (nunca grava prefs.json)."""
    return CmdAllInOneApp(settings or fake_settings(), sources=sources if sources is not None else {},
                          prefs=prefs or Prefs(), prefs_path=None)


async def wait_until(predicate, timeout=3.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condição não atingida a tempo")
        await asyncio.sleep(0.02)


def screen_text(app: App, width: int, height: int) -> str:
    """Renderiza a tela atual como texto puro (sem cores)."""
    console = Console(
        width=width, height=height, record=True, file=io.StringIO(),
        force_terminal=True, color_system="truecolor", legacy_windows=False,
    )
    console.print(app.screen._compositor)
    return console.export_text()
