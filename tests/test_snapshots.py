"""Regressão visual (pytest-textual-snapshot): telas com dados de exemplo e relógio
congelado. Atualizar com `python -m pytest tests/test_snapshots.py --snapshot-update`
**só** quando a mudança visual for intencional (e dizer por quê no commit)."""

from __future__ import annotations

import asyncio
from datetime import datetime

import pytest

from app import clock
from app.prefs import Prefs
from app.tui import demo
from app.tui.app import CmdAllInOneApp

FROZEN = datetime(2026, 9, 16, 8, 14, 20)
CLOCK = demo.Clock(FROZEN)
SIZES = [(120, 35), (90, 30), (200, 50)]


@pytest.fixture(autouse=True)
def frozen_clock():
    clock.freeze(FROZEN)
    yield
    clock.freeze(None)


def demo_app(theme: str = "carbon", **sources_kwargs) -> CmdAllInOneApp:
    app = CmdAllInOneApp(demo.demo_settings(theme=theme), sources=demo.demo_sources(CLOCK, **sources_kwargs),
                         prefs=Prefs(), prefs_path=None)
    app.event_log.events.extend(demo.sample_events(CLOCK))
    return app


async def ready(pilot) -> None:  # noqa: ANN001
    app = pilot.app
    for _ in range(200):
        if all(name in app.states or app.errors.get(name) for name in ("email", "milldesk", "chatpanel")):
            break
        await asyncio.sleep(0.02)
    await pilot.pause()


@pytest.mark.parametrize("size", SIZES, ids=[f"{w}x{h}" for w, h in SIZES])
@pytest.mark.parametrize("theme", ["carbon", "paper"])
def test_dashboard(snap_compare, size, theme):
    assert snap_compare(demo_app(theme), terminal_size=size, run_before=ready)


def test_dashboard_errors(snap_compare):
    assert snap_compare(demo_app(email_error="timeout", chat_expired=True), terminal_size=(120, 35), run_before=ready)


def test_dashboard_not_configured(snap_compare):
    assert snap_compare(demo_app(chat_unconfigured=True), terminal_size=(120, 35), run_before=ready)
