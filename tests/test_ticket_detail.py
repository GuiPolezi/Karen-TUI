"""Fase 6.2: parse do showTicket, comunicações, cache/TTL/429 e a tela de detalhe."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest

from app.config import MilldeskSettings
from app.sources.milldesk import (
    MilldeskApiError,
    MilldeskSource,
    RateLimitedError,
    html_to_text,
    parse_communications,
    ticket_detail_from_api,
)
from app.state import TicketDetail
from app.tui.screens.ticket_detail import TicketDetailScreen, sla_line
from tests.helpers import make_app, screen_text, wait_until

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "milldesk_showTicket.json").read_text(encoding="utf-8"))


def test_html_to_text_keeps_paragraphs_and_breaks():
    assert html_to_text("<p>Um</p><p>Dois<br>três</p>") == "Um\n\nDois\ntrês"
    assert html_to_text("texto puro") == "texto puro"
    assert html_to_text(None) == ""


def test_parse_communications_splits_entries():
    entries = parse_communications(FIXTURE["communication"])
    assert [(e.when, e.who) for e in entries] == [
        ("15/09/2026 09:00:17", "Técnico Anônimo"), ("16/09/2026 10:30:00", "Solicitante Anônimo"),
    ]
    assert entries[0].text == "Primeira comunicação anonimizada.\nSegunda linha da mesma comunicação."
    assert entries[1].text == "Resposta anonimizada."
    assert parse_communications("") == []
    assert parse_communications("sem cabeçalho")[0].text == "sem cabeçalho"


def test_ticket_detail_from_fixture():
    detail = ticket_detail_from_api(FIXTURE)
    assert detail.id == 4242
    assert detail.status == "Aguardando Testes" and detail.priority == "Baixa"
    assert detail.description == "Primeiro parágrafo anonimizado.\n\nSegundo parágrafo\ncom quebra."
    assert detail.sla_expiration == "27/10/2026 14:34"
    assert detail.sla_deadline == datetime(2026, 10, 27, 14, 34)
    assert len(detail.communications) == 2
    assert ticket_detail_from_api([FIXTURE]).id == 4242  # lista com 1 item também vale


def test_ticket_detail_errors():
    with pytest.raises(MilldeskApiError, match="invalidId"):
        ticket_detail_from_api({"error": "invalidId"})
    with pytest.raises(MilldeskApiError, match="sem id"):
        ticket_detail_from_api({})


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def make_source(handler, clock: FakeClock, ttl: int = 300) -> MilldeskSource:
    settings = MilldeskSettings(api_key="k1776", base_url="https://x/api", refresh_seconds=60,
                                agent_name="Agent", detail_ttl_seconds=ttl)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return MilldeskSource(settings, client=client, clock=clock)


async def test_fetch_ticket_uses_cache_ttl_and_force():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path + "?" + request.url.query.decode())
        return httpx.Response(200, json=FIXTURE)

    clock = FakeClock()
    source = make_source(handler, clock, ttl=300)
    first = await source.fetch_ticket(4242)
    again = await source.fetch_ticket(4242)
    assert first is again and len(calls) == 1  # cache
    assert "k1776" in calls[0] and "id=4242" in calls[0]
    clock.now += 301
    await source.fetch_ticket(4242)
    assert len(calls) == 2  # TTL venceu
    await source.fetch_ticket(4242, force=True)
    assert len(calls) == 3  # r ignora o cache
    await source.close()


async def test_fetch_ticket_respects_429_cooldown():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429)

    clock = FakeClock()
    source = make_source(handler, clock)
    with pytest.raises(RateLimitedError):
        await source.fetch_ticket(1)
    with pytest.raises(RateLimitedError):  # dentro do cooldown: nem chama a API
        await source.fetch_ticket(2)
    assert calls == 1
    clock.now += 200
    with pytest.raises(RateLimitedError):
        await source.fetch_ticket(2)
    assert calls == 2
    await source.close()


def test_sla_line_colors():
    detail = ticket_detail_from_api(FIXTURE)
    now = datetime(2026, 10, 27, 12, 34)
    assert "faltam 02h00" in sla_line(detail, now).plain
    assert "vencido" in sla_line(detail, now + timedelta(hours=3)).plain
    detail.sla_expiration = "Em pausa"
    assert sla_line(detail, now).plain == "SLA: Em pausa"


class FakeMilldeskSource(MilldeskSource):
    """Lista falsa + detalhe da fixture, sem rede."""

    def __init__(self, fail: bool = False):
        super().__init__(MilldeskSettings(api_key="k", base_url="https://x/api", refresh_seconds=60, agent_name="A"))
        self.fail = fail
        self.detail_calls = 0

    async def fetch(self):
        from app.state import MilldeskState, MilldeskTicket

        return MilldeskState(my_tickets=1, tickets=[MilldeskTicket(id=4242, subject="Assunto", status="Aberto",
                             stage="", requester="", start="14/09/2026", starttime="14:34",
                             sla_expiration="27/10/2026 14:34")], updated_at=datetime(2026, 9, 15, 12, 0))

    async def fetch_ticket(self, ticket_id: int, force: bool = False) -> TicketDetail:
        self.detail_calls += 1
        if self.fail:
            raise RateLimitedError("showTicket")
        return ticket_detail_from_api(FIXTURE)


async def test_enter_opens_ticket_detail_and_r_reloads():
    source = FakeMilldeskSource()
    app = make_app(sources={"milldesk": source})
    async with app.run_test(size=(120, 36)) as pilot:
        await wait_until(lambda: "milldesk" in app.states)
        await pilot.press("f3")
        await pilot.pause()
        await pilot.press("enter")
        await wait_until(lambda: source.detail_calls == 1)
        await pilot.pause()
        assert isinstance(app.screen, TicketDetailScreen)
        text = screen_text(app, 120, 36)
        assert "#4242" in text and "ticket anonimizado" in text
        assert "Primeiro parágrafo anonimizado." in text
        assert "Técnico Anônimo" in text and "Resposta anonimizada." in text
        assert "SLA:" in text
        await pilot.press("r")
        await wait_until(lambda: source.detail_calls == 2)
        await pilot.press("y")
        assert "4242" in app.last_message
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, TicketDetailScreen)
        assert app.current_mode == "milldesk"


async def test_ticket_detail_shows_error_without_crashing():
    source = FakeMilldeskSource(fail=True)
    app = make_app(sources={"milldesk": source})
    async with app.run_test(size=(120, 36)) as pilot:
        await wait_until(lambda: "milldesk" in app.states)
        await pilot.press("f3")
        await pilot.pause()
        await pilot.press("enter")
        await wait_until(lambda: source.detail_calls == 1)
        await pilot.pause()
        assert isinstance(app.screen, TicketDetailScreen)
        assert "limite de requisições" in screen_text(app, 120, 36)
        await pilot.press("escape")
        await pilot.pause()
        assert app.current_mode == "milldesk"
