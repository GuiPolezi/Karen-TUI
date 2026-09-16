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


def test_dashboard_empty_milldesk(snap_compare):
    assert snap_compare(demo_app(milldesk_empty=True), terminal_size=(120, 35), run_before=ready)


async def open_ticket(pilot) -> None:  # noqa: ANN001
    await ready(pilot)
    await pilot.press("f3")
    await pilot.pause()
    await pilot.press("enter")
    for _ in range(50):
        if pilot.app.screen.__class__.__name__ == "TicketDetailScreen" and getattr(pilot.app.screen, "detail", None):
            break
        await asyncio.sleep(0.02)
    await pilot.pause()


def test_ticket_detail_modal(snap_compare):
    assert snap_compare(demo_app(), terminal_size=(120, 35), run_before=open_ticket)


async def open_conversation(pilot) -> None:  # noqa: ANN001
    await ready(pilot)
    await pilot.press("f4")
    await pilot.pause()
    await pilot.press("enter")
    for _ in range(50):
        if pilot.app.screen.__class__.__name__ == "ConversationDetailScreen" and getattr(pilot.app.screen, "detail", None):
            break
        await asyncio.sleep(0.02)
    await pilot.pause()
    await pilot.pause()


def test_conversation_detail_modal(snap_compare):
    assert snap_compare(demo_app(), terminal_size=(120, 35), run_before=open_conversation)


async def open_launcher(pilot) -> None:  # noqa: ANN001
    await ready(pilot)
    await pilot.press("colon")
    await pilot.pause()
    await pilot.press("m", "d")
    await pilot.pause()


def test_launcher_open(snap_compare):
    assert snap_compare(demo_app(), terminal_size=(120, 35), run_before=open_launcher)


async def test_tela_com_fonte_coletando_nao_muda_entre_execucoes():
    """Mesma tela, duas renderizações, texto idêntico.

    O spinner da fonte coletando vinha de um contador de ticks, então o quadro capturado
    dependia de quantas vezes o timer tinha rodado: `test_dashboard_errors` falhava ~5 em
    10 aqui e derrubou o primeiro build da v0.2.0 no CI. Agora o quadro vem de
    `app.clock`, que os testes congelam.
    """
    from tests.helpers import screen_text

    async def render() -> str:
        app = demo_app(email_error="timeout", chat_expired=True)
        async with app.run_test(size=(120, 35)) as pilot:
            await ready(pilot)
            return screen_text(app, 120, 35)

    assert await render() == await render()
