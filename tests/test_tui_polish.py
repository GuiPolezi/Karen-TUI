"""Fase 5: destaque + bell em aumento de contador, detalhe do e-mail, painel de log."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from textual.widgets import Log, Static

from app.sources.base import Source
from app.state import EmailState, LatestEmail
from app.tui.app import CmdAllInOneApp, increased_counters
from app.tui.screens import EmailDetailScreen
from app.tui.widgets.log_panel import LogPanel, tail
from tests.helpers import fake_settings, screen_text
from tests.test_tui_workers import wait_until


class GrowingEmailSource(Source[EmailState]):
    """Cada fetch devolve mais não lidos que o anterior."""

    name = "email"

    def __init__(self, unseen_sequence: list[int]):
        super().__init__(interval=60, timeout=1.0)
        self.sequence = list(unseen_sequence)
        self.calls = 0

    async def fetch(self) -> EmailState:
        unseen = self.sequence[min(self.calls, len(self.sequence) - 1)]
        self.calls += 1
        return EmailState(
            total=10, unseen=unseen, spam=None,
            latest=LatestEmail(
                from_name="Fulano", from_addr="fulano@x.br", subject="Assunto teste",
                date=datetime(2026, 9, 14, 15, 28), preview="prévia",
                body="Linha 1\nLinha 2\n\nCorpo completo do e-mail.",
            ),
            updated_at=datetime(2026, 9, 14, 15, 31, 2),
        )


def test_increased_counters_only_reports_growth():
    assert increased_counters({"a": 1, "b": 5}, {"a": 2, "b": 3}) == ["a"]
    assert increased_counters({}, {"a": 2}) == []  # sem base de comparação não é aumento
    assert increased_counters({"a": 2}, {"a": 2}) == []


async def test_counter_growth_flashes_panel_and_rings_bell(tmp_path: Path):
    source = GrowingEmailSource([3, 3, 7])
    app = CmdAllInOneApp(fake_settings(notify_bell=True, log_dir=tmp_path), sources={"email": source})
    async with app.run_test(size=(120, 30)) as pilot:
        await wait_until(lambda: source.calls == 1)
        await pilot.pause()
        panel = app.panel("email")
        assert not panel.has_class("changed")

        await pilot.press("1")  # 3 -> 3: nada muda
        await wait_until(lambda: source.calls == 2)
        await pilot.pause()
        assert not panel.has_class("changed")
        assert app.bell_count == 0

        await pilot.press("1")  # 3 -> 7: destaque + bell
        await wait_until(lambda: source.calls == 3)
        await pilot.pause()
        assert panel.has_class("changed")
        assert app.bell_count == 1


async def test_bell_disabled_still_flashes(tmp_path: Path):
    source = GrowingEmailSource([1, 2])
    app = CmdAllInOneApp(fake_settings(notify_bell=False, log_dir=tmp_path), sources={"email": source})
    async with app.run_test(size=(120, 30)) as pilot:
        await wait_until(lambda: source.calls == 1)
        await pilot.press("1")
        await wait_until(lambda: source.calls == 2)
        await pilot.pause()
        assert app.panel("email").has_class("changed")
        assert app.bell_count == 0


async def test_email_detail_screen_opens_and_closes(tmp_path: Path):
    source = GrowingEmailSource([1])
    app = CmdAllInOneApp(fake_settings(log_dir=tmp_path), sources={"email": source})
    async with app.run_test(size=(120, 30)) as pilot:
        await wait_until(lambda: "email" in app.states)
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        assert isinstance(app.screen, EmailDetailScreen)
        text = screen_text(app, 120, 30)
        assert "Assunto teste" in text
        assert "Corpo completo do e-mail." in text
        assert "Fulano <fulano@x.br>" in text
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, EmailDetailScreen)


async def test_email_detail_without_state_shows_message(tmp_path: Path):
    app = CmdAllInOneApp(fake_settings(log_dir=tmp_path), sources={})
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.press("e")
        await pilot.pause()
        assert not isinstance(app.screen, EmailDetailScreen)
        assert "nenhum e-mail" in str(app.query_one("#status-message", Static).content)


def test_tail_reads_last_lines(tmp_path: Path):
    path = tmp_path / "app.log"
    path.write_text("\n".join(f"linha {i}" for i in range(1, 81)) + "\n", encoding="utf-8")
    lines = tail(path, 50)
    assert len(lines) == 50
    assert lines[0] == "linha 31" and lines[-1] == "linha 80"
    assert tail(tmp_path / "nao-existe.log")[0].startswith("(arquivo de log")


async def test_log_panel_toggles_and_shows_file(tmp_path: Path):
    (tmp_path / "app.log").write_text("2026-09-14 INFO app: iniciando\n2026-09-14 ERROR x: falhou\n", encoding="utf-8")
    app = CmdAllInOneApp(fake_settings(log_dir=tmp_path), sources={})
    async with app.run_test(size=(120, 40)) as pilot:
        log_panel = app.query_one(LogPanel)
        assert log_panel.display is False
        await pilot.press("l")
        await pilot.pause()
        assert log_panel.display is True
        assert "falhou" in "".join(str(line) for line in app.query_one("#log-lines", Log).lines)
        assert "log aberto" in str(app.query_one("#status-message", Static).content)
        await pilot.press("l")
        await pilot.pause()
        assert log_panel.display is False
