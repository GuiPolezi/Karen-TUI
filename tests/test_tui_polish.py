"""Destaque + bell em aumento de contador, detalhe do e-mail, tela de log e resumo
"enquanto você estava fora"."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from textual.widgets import RichLog

from app.sources.base import Source
from app.state import EmailState, EmailSummary, LatestEmail
from app.tui.app import increased_counters
from app.tui.screens import EmailDetailScreen
from app.tui.screens.log import filter_lines, tail
from tests.helpers import fake_settings, make_app, screen_text, wait_until


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
        latest = LatestEmail(
            from_name="Fulano", from_addr="fulano@x.br", subject="Assunto teste",
            date=datetime(2026, 9, 14, 15, 28), preview="prévia",
            body="Linha 1\nLinha 2\n\nCorpo completo do e-mail.",
        )
        recent = [EmailSummary(uid=str(uid), from_name="Fulano", from_addr="fulano@x.br",
                               subject=f"Assunto {uid}", date=latest.date, unseen=uid > 8)
                  for uid in range(10, 10 - max(unseen, 1), -1)]
        return EmailState(total=10, unseen=unseen, spam=None, latest=latest, recent=recent,
                          updated_at=datetime(2026, 9, 14, 15, 31, 2))


def test_increased_counters_only_reports_growth():
    assert increased_counters({"a": 1, "b": 5}, {"a": 2, "b": 3}) == ["a"]
    assert increased_counters({}, {"a": 2}) == []  # sem base de comparação não é aumento
    assert increased_counters({"a": 2}, {"a": 2}) == []


async def test_counter_growth_flashes_panel_and_rings_bell(tmp_path: Path):
    source = GrowingEmailSource([3, 3, 7])
    app = make_app(fake_settings(notify_bell=True, log_dir=tmp_path), sources={"email": source})
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

        await pilot.press("1")  # 3 -> 7: destaque + bell + marcador nas linhas novas
        await wait_until(lambda: source.calls == 3)
        await pilot.pause()
        assert panel.has_class("changed")
        assert app.bell_count == 1
        assert "●" in screen_text(app, 120, 30)


async def test_bell_disabled_still_flashes(tmp_path: Path):
    source = GrowingEmailSource([1, 2])
    app = make_app(fake_settings(notify_bell=False, log_dir=tmp_path), sources={"email": source})
    async with app.run_test(size=(120, 30)) as pilot:
        await wait_until(lambda: source.calls == 1)
        await pilot.press("1")
        await wait_until(lambda: source.calls == 2)
        await pilot.pause()
        assert app.panel("email").has_class("changed")
        assert app.bell_count == 0


async def test_silence_mode_suppresses_bell(tmp_path: Path):
    source = GrowingEmailSource([1, 5])
    app = make_app(fake_settings(notify_bell=True, log_dir=tmp_path), sources={"email": source})
    async with app.run_test(size=(120, 30)) as pilot:
        await wait_until(lambda: source.calls == 1)
        await pilot.press("m")
        assert "silêncio" in app.last_message
        await pilot.press("1")
        await wait_until(lambda: source.calls == 2)
        await pilot.pause()
        assert app.panel("email").has_class("changed")
        assert app.bell_count == 0
        await pilot.press("m")
        assert "reativados" in app.last_message


async def test_email_detail_screen_opens_and_closes(tmp_path: Path):
    source = GrowingEmailSource([1])
    app = make_app(fake_settings(log_dir=tmp_path), sources={"email": source})
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
    app = make_app(fake_settings(log_dir=tmp_path))
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.press("e")
        await pilot.pause()
        assert "nenhum e-mail" in app.last_message
        assert not isinstance(app.screen, EmailDetailScreen)


async def test_away_summary_when_returning_to_dashboard(tmp_path: Path):
    source = GrowingEmailSource([1, 4])
    app = make_app(fake_settings(log_dir=tmp_path), sources={"email": source})
    async with app.run_test(size=(120, 30)) as pilot:
        await wait_until(lambda: source.calls == 1)
        await pilot.press("f5")  # sai do Dashboard (na tela de notas o "1" iria para o texto)
        await pilot.pause()
        await pilot.press("1")
        await wait_until(lambda: source.calls == 2)
        await pilot.pause()
        await pilot.press("f1")
        await pilot.pause()
        assert "enquanto você estava fora" in app.last_message
        assert "não lidos" in app.last_message


def test_log_tail_and_level_filter(tmp_path: Path):
    path = tmp_path / "app.log"
    assert "ainda não existe" in tail(path)[0]
    path.write_text(
        "2026-09-15 10:00:00,000 INFO    a: um\n"
        "2026-09-15 10:00:01,000 WARNING b: dois\n"
        "2026-09-15 10:00:02,000 ERROR   c: tres\n",
        encoding="utf-8",
    )
    lines = tail(path)
    assert len(lines) == 3
    assert [l.split()[2] for l in filter_lines(lines, "WARNING")] == ["WARNING", "ERROR"]
    assert len(filter_lines(lines, "ERROR")) == 1
    assert filter_lines(lines, "TODOS") == lines


async def test_log_screen_shows_file_and_cycles_filter(tmp_path: Path):
    (tmp_path / "app.log").write_text(
        "2026-09-15 10:00:00,000 INFO    a: linha info\n2026-09-15 10:00:01,000 ERROR   c: linha erro\n",
        encoding="utf-8",
    )
    app = make_app(fake_settings(log_dir=tmp_path))
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.press("f5")
        await pilot.pause()
        assert app.current_mode == "log"
        assert "linha info" in screen_text(app, 120, 30)
        await pilot.press("f")  # TODOS -> INFO
        await pilot.press("f")  # INFO -> WARNING
        await pilot.pause()
        text = screen_text(app, 120, 30)
        assert "linha erro" in text and "linha info" not in text
        assert app.mode_screens["log"].query_one("#log-lines", RichLog) is not None
