"""Fase 6.5: feed de eventos (diffs), persistência JSONL, tela F7, SLA em destaque e tela F8."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.events import Event, EventLog, diff_chatpanel, diff_email, diff_milldesk
from app.state import ChatItem, ChatPanelState, EmailState, EmailSummary, MilldeskState, MilldeskTicket
from app.tui.widgets.milldesk_panel import nearest_sla, sla_highlight
from tests.helpers import fake_settings, make_app, screen_text, wait_until
from tests.test_tui_polish import GrowingEmailSource

NOW = datetime(2026, 9, 15, 10, 0, 0)


def summary(uid: str, subject: str = "Assunto") -> EmailSummary:
    return EmailSummary(uid=uid, from_name="Fulano", from_addr="f@x", subject=subject, date=NOW)


def ticket(id: int, status: str = "Aberto", sla: str | None = None) -> MilldeskTicket:
    return MilldeskTicket(id=id, subject=f"T{id}", status=status, stage="", requester="",
                          start="15/09/2026", starttime="09:00", sla_expiration=sla)


def chat(number: str, name: str, agent: str, unread: int = 0) -> ChatItem:
    return ChatItem(number=number, name=name, time="10:00", last_message="oi", unread=unread, agent=agent)


def test_diff_email_reports_new_uids_only():
    before = EmailState(recent=[summary("9")], unseen=1)
    after = EmailState(recent=[summary("10", "Novo"), summary("9")], unseen=2)
    events = diff_email(before, after, NOW)
    assert [e.text for e in events] == ["e-mail novo de Fulano: Novo"]
    assert diff_email(after, after, NOW) == []
    assert diff_email(EmailState(unseen=1), EmailState(unseen=3), NOW)[0].text == "não lidos subiram para 3"


def test_diff_milldesk_in_out_and_status():
    before = MilldeskState(tickets=[ticket(1), ticket(2, "Aberto")])
    after = MilldeskState(tickets=[ticket(2, "Em análise"), ticket(3)])
    texts = [e.text for e in diff_milldesk(before, after, NOW)]
    assert texts == [
        "chamado #2: Aberto → Em análise",
        "chamado #3 entrou no seu nome: T3",
        "chamado #1 saiu do seu nome: T1",
    ]


def test_diff_chatpanel_transfers_and_messages():
    before = ChatPanelState(mine=[chat("1", "Ana", "Guilherme", 0), chat("2", "Beto", "Guilherme")],
                            others=[chat("3", "Carla", "Fabio")])
    after = ChatPanelState(mine=[chat("1", "Ana", "Guilherme", 2), chat("3", "Carla", "Guilherme"), chat("4", "Dani", "Guilherme")],
                           others=[chat("2", "Beto", "Roberto")])
    texts = [e.text for e in diff_chatpanel(before, after, NOW)]
    assert texts == [
        "mensagem nova de Ana (2 não lidas)",
        "conversa de Carla transferida para você (de Fabio)",
        "conversa nova no seu nome: Dani",
        "conversa de Beto transferida para Roberto",
    ]
    gone = ChatPanelState(mine=[], others=[])
    assert [e.text for e in diff_chatpanel(after, gone, NOW)][0] == "conversa de Ana saiu do seu nome"


def test_event_log_persists_and_reloads_today(tmp_path: Path):
    log = EventLog(tmp_path)
    log.add([Event(datetime.now(), "email", "new_email", "e-mail novo de X: Y", "10")])
    files = list(tmp_path.glob("events-*.jsonl"))
    assert len(files) == 1 and files[0].read_text(encoding="utf-8").count("\n") == 1
    reloaded = EventLog(tmp_path)
    assert [e.text for e in reloaded.events] == ["e-mail novo de X: Y"]
    files[0].write_text("linha inválida\n" + files[0].read_text(encoding="utf-8"), encoding="utf-8")
    assert len(EventLog(tmp_path).events) == 1  # linha inválida é ignorada
    assert EventLog(None).path_for(datetime.now()) is None


def test_nearest_sla_and_highlight():
    now = datetime(2026, 9, 15, 12, 0)
    tickets = [ticket(1, sla="16/09/2026 12:00"), ticket(2, sla="Em pausa"), ticket(3, sla="15/09/2026 12:20")]
    assert nearest_sla(tickets, now).id == 3
    assert nearest_sla([ticket(2, sla="Em pausa")], now) is None
    assert "⚠" in sla_highlight(tickets[2], now).plain  # < 30 min
    assert "VENCIDO" in sla_highlight(ticket(4, sla="15/09/2026 11:00"), now).plain
    assert "faltam 1d 00h" in sla_highlight(tickets[0], now).plain


async def test_events_screen_lists_new_events(tmp_path: Path):
    source = GrowingEmailSource([1, 3])
    app = make_app(fake_settings(log_dir=tmp_path), sources={"email": source})
    async with app.run_test(size=(120, 30)) as pilot:
        await wait_until(lambda: source.calls == 1)
        await pilot.press("1")
        await wait_until(lambda: source.calls == 2)
        await pilot.pause()
        assert len(app.event_log.events) == 2  # dois e-mails novos (uids 9 e 8)
        await pilot.press("f7")
        await pilot.pause()
        text = screen_text(app, 120, 30)
        assert "e-mail novo de Fulano" in text and "2 evento(s) hoje" in text
        await pilot.press("x")
        await pilot.pause()
        assert "0 evento(s)" in screen_text(app, 120, 30)


async def test_health_screen_shows_source_status(tmp_path: Path):
    source = GrowingEmailSource([1])
    app = make_app(fake_settings(log_dir=tmp_path), sources={"email": source})
    async with app.run_test(size=(120, 30)) as pilot:
        await wait_until(lambda: "email" in app.states)
        await pilot.press("f8")
        await pilot.pause()
        text = screen_text(app, 120, 30)
        assert "Fontes" in text and "e-mail" in text and "ok" in text
        assert "Uptime" in text and "textual" in text
        info = app.health()
        assert info["sources"][0]["status"] == "ok"
        assert info["sources"][0]["duration"] is not None
        assert info["milldesk_calls_last_minute"] == 0
