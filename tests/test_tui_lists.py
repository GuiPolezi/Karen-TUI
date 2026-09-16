"""Listas com cursor: preservação da seleção entre atualizações, filtro, ordenação do
Milldesk, SLA, "com outros" no ChatPanel e preferências."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult

from app.prefs import Prefs, load_prefs, save_prefs
from app.sources.base import Source
from app.state import ChatItem, ChatPanelState, MilldeskState, MilldeskTicket, format_remaining, parse_datetime_br
from app.tui.widgets.keyed_table import KeyedTable
from app.tui.widgets.milldesk_panel import sla_text, sla_token, sorted_tickets
from tests.helpers import fake_settings, make_app, wait_until

# --- KeyedTable ----------------------------------------------------------------------


class TableApp(App[None]):
    def compose(self) -> ComposeResult:
        yield KeyedTable([("a", "A", 4), ("b", "B", None)])


def rows(*keys: str, suffix: str = ""):
    return [(k, [Text(k), Text(f"valor {k}{suffix}")]) for k in keys]


async def test_keyed_table_keeps_selection_by_key_when_order_changes():
    app = TableApp()
    async with app.run_test(size=(60, 20)) as pilot:
        table = app.query_one(KeyedTable)
        table.set_rows(rows("x", "y", "z"))
        await pilot.pause()
        table.select_key("y")
        assert table.selected_key == "y"
        table.set_rows(rows("z", "y", "x"))  # mesma chave, outra posição
        await pilot.pause()
        assert table.selected_key == "y"
        assert table.keys == ["z", "y", "x"]


async def test_keyed_table_updates_cells_in_place_and_handles_removed_key():
    app = TableApp()
    async with app.run_test(size=(60, 20)) as pilot:
        table = app.query_one(KeyedTable)
        table.set_rows(rows("x", "y", "z"))
        await pilot.pause()
        table.select_key("z")
        table.set_rows(rows("x", "y", "z", suffix="!"))  # mesmas chaves: só células mudam
        await pilot.pause()
        assert table.selected_key == "z"
        assert table.get_row("z")[1].plain == "valor z!"
        table.set_rows(rows("x", "y"))  # a selecionada sumiu: vizinho mais próximo
        await pilot.pause()
        assert table.selected_key == "y"
        table.set_rows([])
        await pilot.pause()
        assert table.selected_key is None


# --- prefs -----------------------------------------------------------------------------


def test_prefs_roundtrip_and_tolerance(tmp_path: Path):
    path = tmp_path / "prefs.json"
    assert load_prefs(path).last_screen == "dashboard"
    prefs = Prefs(last_screen="email", milldesk_sort="data", favorites={"g": "https://g"})
    for i in range(60):
        prefs.push_history(f"cmd {i}")
    prefs.push_history("cmd 59")  # repetido vai para o fim, sem duplicar
    save_prefs(prefs, path)
    loaded = load_prefs(path)
    assert loaded.last_screen == "email" and loaded.milldesk_sort == "data"
    assert loaded.favorites == {"g": "https://g"}
    assert len(loaded.history) == 50 and loaded.history[-1] == "cmd 59"
    path.write_text("{ isso não é json", encoding="utf-8")
    assert load_prefs(path).last_screen == "dashboard"
    path.write_text('{"last_screen": 5, "history": "x"}', encoding="utf-8")  # tipos errados são ignorados
    assert load_prefs(path).last_screen == "dashboard"


# --- SLA e ordenação do Milldesk ---------------------------------------------------------


def ticket(id: int, start: str, sla: str | None, status: str = "Aberto") -> MilldeskTicket:
    day, time = start.split(" ")
    return MilldeskTicket(id=id, subject=f"T{id}", status=status, stage="", requester="",
                          start=day, starttime=time, sla_expiration=sla)


def test_parse_datetime_and_format_remaining():
    assert parse_datetime_br("27/10/2026 14:34") == datetime(2026, 10, 27, 14, 34)
    assert parse_datetime_br("27/10/2026") == datetime(2026, 10, 27)
    assert parse_datetime_br("Em pausa") is None
    assert format_remaining(timedelta(days=3, hours=4)) == "3d 04h"
    assert format_remaining(timedelta(hours=2, minutes=15)) == "02h15"
    assert format_remaining(timedelta(minutes=-45)) == "-45min"
    assert format_remaining(None) == ""


def test_sorted_tickets_and_sla_colors():
    now = datetime(2026, 9, 15, 12, 0)
    late = ticket(1, "14/09/2026 09:00", "15/09/2026 11:00")
    soon = ticket(2, "15/09/2026 10:00", "15/09/2026 14:00")
    far = ticket(3, "13/09/2026 08:00", "20/09/2026 09:00")
    paused = ticket(4, "15/09/2026 11:30", "Em pausa", status="Pausado")
    tickets = [far, paused, soon, late]
    assert [t.id for t in sorted_tickets(tickets, "sla", now)] == [1, 2, 3, 4]
    assert [t.id for t in sorted_tickets(tickets, "data", now)] == [4, 2, 1, 3]
    assert [t.id for t in sorted_tickets(tickets, "status", now)] == [2, 1, 3, 4]
    # tokens semânticos, nunca cores: o tema decide a cor (Ciclo 3)
    assert sla_token(late, now) == "danger" and sla_text(late, now) == "-01h00"
    assert sla_token(soon, now) == "warn" and sla_text(soon, now) == "02h00"
    assert sla_token(far, now) == "ok"
    assert sla_token(paused, now) == "text-faint" and sla_text(paused, now) == "Em pausa"


class FakeMilldeskSource(Source[MilldeskState]):
    name = "milldesk"

    def __init__(self):
        super().__init__(interval=60, timeout=1.0)

    async def fetch(self) -> MilldeskState:
        return MilldeskState(
            my_tickets=2, tickets=[ticket(1, "14/09/2026 09:00", "15/09/2026 11:00"),
                                   ticket(2, "15/09/2026 10:00", "20/09/2026 14:00")],
            open_total=5, updated_at=datetime(2026, 9, 15, 12, 0),
        )


async def test_milldesk_screen_cycles_sort_with_s_and_saves_pref():
    app = make_app(sources={"milldesk": FakeMilldeskSource()})
    async with app.run_test(size=(120, 30)) as pilot:
        await wait_until(lambda: "milldesk" in app.states)
        await pilot.press("f3")
        await pilot.pause()
        panel = app.mode_screens["milldesk"].query_one("#milldesk-full")
        assert panel.table.keys == ["1", "2"]  # SLA mais próximo primeiro
        await pilot.press("s")
        await pilot.pause()
        assert app.prefs.milldesk_sort == "data"
        assert panel.table.keys == ["2", "1"]
        assert app.panel("milldesk").table.keys == ["2", "1"]  # o Dashboard segue a mesma ordem
        await pilot.press("y")
        assert "copiado" in app.last_message or "copie manualmente" in app.last_message


async def test_resize_across_narrow_threshold_with_data_keeps_rows_and_selection():
    """Regressão: trocar COLUMNS_COMPACT -> COLUMNS_NARROW com dados derrubava o app."""
    app = make_app(sources={"milldesk": FakeMilldeskSource()})
    async with app.run_test(size=(120, 30)) as pilot:
        await wait_until(lambda: "milldesk" in app.states)
        await pilot.pause()
        panel = app.panel("milldesk")
        panel.table.select_key("2")
        await pilot.resize_terminal(80, 30)
        await pilot.pause()
        assert panel.table.keys == ["1", "2"]
        assert panel.table.selected_key == "2"
        assert [key for key, _, _ in panel.table.column_specs] == ["id", "subject", "sla"]
        await pilot.resize_terminal(120, 30)
        await pilot.pause()
        assert panel.table.keys == ["1", "2"]
        assert [key for key, _, _ in panel.table.column_specs] == ["id", "subject", "sla"]  # compacto = estreito no Milldesk


# --- ChatPanel: "com outros" e filtro -----------------------------------------------------


class FakeChatSource(Source[ChatPanelState]):
    name = "chatpanel"

    def __init__(self):
        super().__init__(interval=60, timeout=1.0)

    async def fetch(self) -> ChatPanelState:
        mine = [ChatItem("551", "Ana - CM Itu", "10:00", "oi", unread=2, tag="Câmara", agent="Guilherme"),
                ChatItem("552", "Beto - PM Iaras", "09:50", "ok", agent="Guilherme")]
        others = [ChatItem("553", "Carla - CM Franca", "09:40", "?", agent="Fabio")]
        return ChatPanelState(mine=mine, mine_unread=2, others_count=1, others=others,
                              logged_user="User CMD", updated_at=datetime(2026, 9, 15, 10, 0))


async def test_chatpanel_screen_toggles_others_and_filters():
    app = make_app(sources={"chatpanel": FakeChatSource()})
    async with app.run_test(size=(120, 30)) as pilot:
        await wait_until(lambda: "chatpanel" in app.states)
        await pilot.pause()
        assert app.panel("chatpanel").table.keys == ["551", "552"]
        await pilot.press("f4")
        await pilot.pause()
        panel = app.mode_screens["chatpanel"].query_one("#chatpanel-full")
        assert panel.table.keys == ["551", "552"]
        await pilot.press("t")
        await pilot.pause()
        assert app.prefs.chatpanel_show_others is True
        assert panel.table.keys == ["551", "552", "553"]
        assert app.panel("chatpanel").table.keys == ["551", "552"]  # o Dashboard nunca mostra outros

        await pilot.press("slash")
        await pilot.pause()
        await pilot.press("i", "a", "r")  # "iar" casa "Iaras"
        await pilot.pause()
        assert panel.table.keys == ["552"]
        await pilot.press("escape")  # limpa o filtro sem sair da tela
        await pilot.pause()
        assert panel.table.keys == ["551", "552", "553"]
        assert app.current_mode == "chatpanel"
        await pilot.press("escape")
        await pilot.pause()
        assert app.current_mode == "dashboard"


async def test_notes_screen_autosaves(tmp_path: Path):
    from app.tui.screens import notes as notes_module

    path = tmp_path / "notes.md"
    original = notes_module.NOTES_PATH
    notes_module.NOTES_PATH = path
    try:
        app = make_app()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.press("f6")
            await pilot.pause()
            assert app.mode_screens["notes"].path == path
            await pilot.press("o", "l", "a")
            await pilot.pause()
            await pilot.press("ctrl+s")
            await pilot.pause()
            assert path.read_text(encoding="utf-8") == "ola"
    finally:
        notes_module.NOTES_PATH = original
