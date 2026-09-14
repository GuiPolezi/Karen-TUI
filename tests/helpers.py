"""Utilitários compartilhados pelos testes."""

from __future__ import annotations

import io
from pathlib import Path

from rich.console import Console
from textual.app import App

from app.config import ChatPanelSettings, EmailSettings, MilldeskSettings, Settings


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
    )
    base.update(overrides)
    return Settings(**base)


def screen_text(app: App, width: int, height: int) -> str:
    """Renderiza a tela atual como texto puro (sem cores)."""
    console = Console(
        width=width, height=height, record=True, file=io.StringIO(),
        force_terminal=True, color_system="truecolor", legacy_windows=False,
    )
    console.print(app.screen._compositor)
    return console.export_text()
