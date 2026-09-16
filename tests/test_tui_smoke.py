"""Smoke test da TUI: Dashboard com três painéis, relógio, modos e Esc."""

from textual.containers import Container
from textual.widgets import Static

from app.tui.widgets.base_panel import BasePanel
from tests.helpers import make_app, screen_text


async def test_three_panels_waiting_and_clock_running():
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.current_mode == "dashboard"
        panels = app.dashboard.query(BasePanel)
        assert len(panels) == 3
        for panel in panels:
            assert "aguardando" in panel.summary_text
        assert "Guilherme" in screen_text(app, 120, 40)  # técnico e relógio na TopBar
        assert app.dashboard.has_class("-wide") and not app.dashboard.has_class("-narrow")

        await pilot.press("1")
        assert "Fase 1" in app.last_message


async def test_narrow_terminal_stacks_top_row():
    app = make_app()
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        assert app.dashboard.has_class("-narrow")  # breakpoint horizontal da tela (< 100 colunas)


async def test_panel_error_marks_border_and_clears():
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        panel = app.panel("email")
        panel.set_error("timeout")
        await pilot.pause()
        assert panel.has_class("error")
        # sem dados: o erro é o desenho centralizado no lugar da lista (✗ + mensagem)
        assert panel.query_one(".panel-placeholder", Static).display is True
        assert "timeout" in str(panel.query_one(".panel-placeholder", Static).render())

        panel.set_error(None)
        await pilot.pause()
        assert not panel.has_class("error")
        assert panel.query_one(".panel-placeholder", Static).display is False


async def test_function_keys_switch_modes_and_escape_returns_to_dashboard():
    app = make_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        for key, mode in (("f2", "email"), ("f3", "milldesk"), ("f4", "chatpanel"), ("f5", "log"), ("f6", "notes")):
            await pilot.press(key)
            await pilot.pause()
            assert app.current_mode == mode, key
            assert app.prefs.last_screen == mode
        await pilot.press("escape")
        await pilot.pause()
        assert app.current_mode == "dashboard"
        await pilot.press("l")
        await pilot.pause()
        assert app.current_mode == "log"
        await pilot.press("f1")
        await pilot.pause()
        assert app.current_mode == "dashboard"


async def test_last_screen_is_restored_from_prefs():
    from app.prefs import Prefs

    app = make_app(prefs=Prefs(last_screen="milldesk"))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.current_mode == "milldesk"
        # o Dashboard ainda não foi criado, mas voltar a ele funciona e monta os painéis
        await pilot.press("f1")
        await pilot.pause()
        assert len(app.dashboard.query(BasePanel)) == 3
