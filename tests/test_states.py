"""Estados e micro-interações (Ciclo 3, seção 7): erro sem dados, não configurado, vazio,
filtro sem resultado, cooldown 429, piscar do SLA e modo conhost."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from textual.widgets import Static

from app import clock
from app.tui import demo
from app.tui.icons import is_legacy_console
from app.tui.themes import all_tokens, register_themes
from app.tui.widgets.milldesk_panel import sla_alert, sla_highlight
from tests.helpers import make_app, screen_text, wait_until


def placeholder(panel) -> str:  # noqa: ANN001
    widget = panel.query_one(".panel-placeholder", Static)
    return str(widget.render()) if widget.display else ""


async def test_error_without_data_shows_centered_drawing_with_retry_key():
    sources = demo.demo_sources(email_error="timeout")
    app = make_app(sources=sources)
    async with app.run_test(size=(120, 35)) as pilot:
        await wait_until(lambda: app.errors.get("email"))
        await pilot.pause()
        panel = app.panel("email")
        text = placeholder(panel)
        assert "✗" in text and "timeout" in text and "1 tenta de novo" in text
        assert panel.table.display is False
        assert "aguardando" not in panel.summary_text  # sem texto de espera por cima do erro


async def test_expired_session_suggests_login_and_topbar_goes_danger():
    sources = demo.demo_sources(chat_expired=True)
    app = make_app(sources=sources)
    async with app.run_test(size=(120, 35)) as pilot:
        await wait_until(lambda: app.errors.get("chatpanel"))
        await pilot.pause(0.6)
        panel = app.panel("chatpanel")
        assert "c abre a janela de login" in placeholder(panel)
        assert app.source_status("chatpanel")[0] == "danger"


async def test_not_configured_is_neutral_and_centered():
    sources = demo.demo_sources(chat_unconfigured=True)
    app = make_app(sources=sources)
    async with app.run_test(size=(120, 35)) as pilot:
        await pilot.pause()
        panel = app.panel("chatpanel")
        text = placeholder(panel)
        assert "não configurado" in text and "CHATPANEL_URL" in text
        assert panel.has_class("unconfigured") and not panel.has_class("error")


async def test_empty_list_is_good_news_and_filter_without_match():
    sources = demo.demo_sources(milldesk_empty=True)
    app = make_app(sources=sources)
    async with app.run_test(size=(120, 35)) as pilot:
        await wait_until(lambda: "milldesk" in app.states)
        await pilot.pause()
        panel = app.panel("milldesk")
        assert "✓" in placeholder(panel) and "nenhum chamado no seu nome" in placeholder(panel)
        await pilot.press("f2")
        await pilot.pause()
        await pilot.press("slash")
        await pilot.press("z", "z", "z")
        await pilot.pause()
        full = app.mode_screens["email"].query_one("#email-full")
        assert "nada encontrado" in placeholder(full)
        foot = str(full.query_one(".panel-foot", Static).render())
        assert "zzz" in foot and "0 de" in foot
        await pilot.press("escape")
        await pilot.pause()
        assert placeholder(full) == "" and full.table.display is True


async def test_cooldown_shows_countdown_in_title_and_warn_dot():
    sources = demo.demo_sources(email_error="limite de requisições da API (HTTP 429)")
    app = make_app(sources=sources)
    async with app.run_test(size=(120, 35)) as pilot:
        await wait_until(lambda: app.errors.get("email"))
        await pilot.pause(0.6)
        meta = str(app.panel("email").query_one(".panel-meta", Static).render())
        assert meta.startswith("aguardando 9m") or meta.startswith("aguardando 10m")
        assert app.source_status("email")[0] == "warn"


def test_sla_alert_and_blink_phase():
    now = datetime(2026, 9, 16, 12, 0)
    soon = demo.ticket(demo.Clock(now), 1, "T", "Aberto", now, now + timedelta(minutes=20))
    later = demo.ticket(demo.Clock(now), 2, "T", "Aberto", now, now + timedelta(hours=2))
    assert sla_alert(soon, now) and not sla_alert(later, now)
    lit = sla_highlight(soon, now)
    dark = sla_highlight(soon, now, blink=True)
    assert lit.plain == dark.plain  # só a cor muda, nunca o texto (nada "pula")
    assert lit.spans[-1].style != dark.spans[-1].style


async def test_sla_blink_respects_setting():
    app = make_app(settings=demo.demo_settings(sla_blink=False), sources=demo.demo_sources())
    async with app.run_test(size=(120, 35)) as pilot:
        await wait_until(lambda: "milldesk" in app.states)
        panel = app.panel("milldesk")
        assert panel.blink_enabled is False
    app = make_app(settings=demo.demo_settings(), sources=demo.demo_sources())
    async with app.run_test(size=(120, 35)) as pilot:
        await wait_until(lambda: "milldesk" in app.states)
        assert app.panel("milldesk").blink_enabled is True


def test_legacy_console_detection_and_faint_fallback():
    assert is_legacy_console({}, "win32") is True
    assert is_legacy_console({"WT_SESSION": "1"}, "win32") is False
    assert is_legacy_console({}, "linux") is False

    class Sink:
        def register_theme(self, theme):  # noqa: ANN001
            pass

    normal = register_themes(Sink())
    legacy = register_themes(Sink(), legacy_console=True)
    assert normal["carbon"].text_faint != normal["carbon"].text_muted
    assert legacy["carbon"].text_faint == legacy["carbon"].text_muted
    assert set(legacy) == set(all_tokens())


async def test_ascii_icons_keep_screens_aligned():
    """Com ICONS=ascii (conhost) nada de largura 2 e as telas continuam legíveis."""
    from rich.cells import cell_len

    app = make_app(settings=demo.demo_settings(icons="ascii"), sources=demo.demo_sources())
    async with app.run_test(size=(120, 35)) as pilot:
        await wait_until(lambda: "chatpanel" in app.states)
        await pilot.pause()
        text = screen_text(app, 120, 35)
        assert "@ E-MAIL" in text and "# MILLDESK" in text and "* CHATPANEL" in text
        assert all(cell_len(ch) == 1 for line in text.splitlines() for ch in line if ord(ch) > 0x7F)


@pytest.fixture(autouse=True)
def _real_clock():
    clock.freeze(None)
    yield
    clock.freeze(None)
