"""Capturas SVG (e texto) de todas as telas da TUI com dados de fixture, sem rede.

Uso: python scripts/design_screenshots.py [pasta de saída]   (padrão: docs/design/antes)

Gera, para cada tela/estado, um `.svg` (cores) e um `.txt` (texto puro, útil para diff
e para ler no terminal) em dois tamanhos: 120x35 e 90x30. As fontes são falsas
(`FakeSource`) e publicam um estado fixo; Log e Notas leem linhas de exemplo em vez
dos arquivos reais. Nada aqui toca `.env`, rede ou `prefs.json`.
"""

from __future__ import annotations

import asyncio
import io
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console  # noqa: E402

from app import clock  # noqa: E402
from app.prefs import Prefs  # noqa: E402
from app.tui import demo  # noqa: E402
from app.tui.app import CmdAllInOneApp  # noqa: E402
from app.tui.screens import ConversationDetailScreen, EmailDetailScreen, TicketDetailScreen  # noqa: E402
from app.tui.screens import log as log_screen  # noqa: E402
from app.tui.screens import notes as notes_screen  # noqa: E402

SIZES = ((120, 35), (90, 30))
FROZEN = datetime(2026, 9, 16, 8, 14, 20)  # hora fixa: capturas comparáveis entre execuções
CLOCK = demo.Clock(FROZEN)


def make_app(*, email_error: str | None = None, chat_unconfigured: bool = False, chat_expired: bool = False,
             milldesk_empty: bool = False, prefs: Prefs | None = None, theme: str | None = None,
             icons: str | None = None) -> CmdAllInOneApp:
    sources = demo.demo_sources(CLOCK, email_error=email_error, chat_unconfigured=chat_unconfigured,
                                chat_expired=chat_expired, milldesk_empty=milldesk_empty)
    overrides = {k: v for k, v in (("theme", theme), ("icons", icons)) if v}
    settings = demo.demo_settings(**overrides)
    app = CmdAllInOneApp(settings, sources=sources, prefs=prefs or Prefs(), prefs_path=None)
    app.event_log.events.extend(demo.sample_events(CLOCK))
    return app


# --- captura ---------------------------------------------------------------------------------


def _text(app: CmdAllInOneApp, width: int, height: int) -> str:
    console = Console(width=width, height=height, record=True, file=io.StringIO(), force_terminal=True,
                      color_system="truecolor", legacy_windows=False)
    console.print(app.screen._compositor)
    return console.export_text()


async def _wait_states(app: CmdAllInOneApp, names: tuple[str, ...] = ("email", "milldesk", "chatpanel")) -> None:
    for _ in range(200):
        if all(n in app.states or app.errors.get(n) for n in names):
            return
        await asyncio.sleep(0.02)


def _save(app: CmdAllInOneApp, out: Path, name: str, width: int, height: int) -> None:
    stem = f"{name}_{width}x{height}"
    (out / f"{stem}.svg").write_text(app.export_screenshot(title=f"{name} {width}x{height}"), encoding="utf-8")
    (out / f"{stem}.txt").write_text(_text(app, width, height), encoding="utf-8")
    print(f"  {stem}")


async def capture_all(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    clock.freeze(FROZEN)
    from app.sources import base as sources_base

    sources_base.RETRY_DELAYS = (0.01, 0.01, 0.01)  # erros de fixture falham na hora, sem 2/4/8 s
    log_screen.tail = lambda path, lines=300: demo.sample_log(CLOCK)  # type: ignore[assignment]
    notes_screen.load_notes = lambda path=None: demo.SAMPLE_NOTES  # type: ignore[assignment]

    for width, height in SIZES:
        print(f"-- {width}x{height}")
        app = make_app()
        async with app.run_test(size=(width, height)) as pilot:
            await _wait_states(app)
            await pilot.pause()
            _save(app, out, "dashboard", width, height)

            # destaque de mudança (borda amarela grossa) e marcador ● na linha nova
            new_state = demo.milldesk_state(CLOCK)
            new_state.tickets.insert(0, demo.new_ticket(CLOCK))
            new_state.my_tickets += 1
            app._publish("milldesk", new_state)
            await pilot.pause()
            _save(app, out, "dashboard_mudanca", width, height)

            for key, mode in (("f2", "email"), ("f3", "milldesk"), ("f4", "chatpanel"), ("f5", "log"),
                              ("f6", "notes"), ("f7", "events"), ("f8", "health")):
                await pilot.press(key)
                await pilot.pause()
                _save(app, out, mode, width, height)

            await pilot.press("f3")
            await pilot.pause()
            await pilot.press("slash")
            await pilot.press("b", "a", "c")
            await pilot.pause()
            _save(app, out, "milldesk_filtro", width, height)
            await pilot.press("escape")
            await pilot.pause()

            await pilot.press("f1")
            await pilot.pause()
            app.push_screen(EmailDetailScreen(demo.email_state(CLOCK).latest))
            await pilot.pause()
            _save(app, out, "detalhe_email", width, height)
            await pilot.press("escape")
            await pilot.pause()

            app.push_screen(TicketDetailScreen(4821, demo.ticket_detail(CLOCK)))
            await pilot.pause()
            _save(app, out, "detalhe_chamado", width, height)
            await pilot.press("escape")
            await pilot.pause()

            item = demo.chatpanel_state(CLOCK).mine[0]
            app.push_screen(ConversationDetailScreen(item.number, item, demo.conversation_detail(CLOCK)))
            await pilot.pause()
            _save(app, out, "detalhe_conversa", width, height)
            await pilot.press("escape")
            await pilot.pause()

            await pilot.press("colon")
            await pilot.pause()
            await pilot.press("m", "d", " ", "4", "8")
            await pilot.pause()
            _save(app, out, "launcher", width, height)
            await pilot.press("escape")
            await pilot.pause()

            await pilot.press("question_mark")
            await pilot.pause()
            _save(app, out, "ajuda", width, height)
            await pilot.press("escape")
            await pilot.pause()

            app.notify("Milldesk: abertos")
            app.notify("e-mail: não lidos", severity="warning")
            await pilot.pause()
            _save(app, out, "dashboard_notify", width, height)

        # estados: erro com dados antigos (e-mail), sessão expirada (ChatPanel)
        app = make_app(email_error="timeout", chat_expired=True)
        async with app.run_test(size=(width, height)) as pilot:
            await _wait_states(app)
            await pilot.pause()
            _save(app, out, "dashboard_erros", width, height)

        # estados: não configurado (ChatPanel) + aguardando primeira coleta
        app = make_app(chat_unconfigured=True)
        async with app.run_test(size=(width, height)) as pilot:
            await pilot.pause()
            _save(app, out, "dashboard_inicio", width, height)

        # silêncio ligado (ícone na TopBar)
        app = make_app(prefs=Prefs(silenced_until=FROZEN.timestamp() + 1800))
        async with app.run_test(size=(width, height)) as pilot:
            await _wait_states(app)
            await pilot.pause()
            _save(app, out, "dashboard_silencio", width, height)

        # vazio (nenhum chamado no meu nome) e filtro sem resultado
        app = make_app(milldesk_empty=True)
        async with app.run_test(size=(width, height)) as pilot:
            await _wait_states(app)
            await pilot.pause()
            _save(app, out, "dashboard_vazio", width, height)
            await pilot.press("f2")
            await pilot.pause()
            await pilot.press("slash")
            await pilot.press("z", "z", "z")
            await pilot.pause()
            _save(app, out, "email_filtro_vazio", width, height)

    # conhost: ICONS=ascii (e text-faint = text-muted, sem dim) e tema terminal
    for name, kwargs in (("dashboard_ascii", {"icons": "ascii"}), ("dashboard_terminal", {"theme": "terminal"}),
                         ("dashboard_paper", {"theme": "paper"}), ("dashboard_phosphor", {"theme": "phosphor"})):
        app = make_app(**kwargs)
        async with app.run_test(size=(120, 35)) as pilot:
            await _wait_states(app)
            await pilot.pause()
            _save(app, out, name, 120, 35)

    # tela cheia (alvo real), terminal muito baixo e terminal estreito
    for width, height in ((200, 50), (120, 22), (80, 24)):
        print(f"-- {width}x{height}")
        app = make_app()
        async with app.run_test(size=(width, height)) as pilot:
            await _wait_states(app)
            await pilot.pause()
            _save(app, out, "dashboard", width, height)


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("docs/design/antes")
    asyncio.run(capture_all(target))
    print(f"capturas em {target}")
