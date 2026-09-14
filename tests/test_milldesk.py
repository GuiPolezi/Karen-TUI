"""Testes da fonte Milldesk sem rede: parser com fixtures, erro lógico e transporte via httpx mock."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

from app.config import MilldeskSettings
from app.sources.base import SourceError
from app.sources.milldesk import (
    NOT_FOUND_NOTE,
    MilldeskApiError,
    MilldeskSource,
    build_state,
    normalize_name,
    open_statuses,
)

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str):
    return json.loads((FIXTURES / name).read_text("utf-8"))


TICKETS_BY_AGENT = load("milldesk_ticketsByAgent.json")
TICKETS_BY_STATUS = load("milldesk_ticketsByStatus.json")
SHOW_BY_STATUS = load("milldesk_showTicketsByStatus.json")
INVALID_KEY = load("milldesk_error_invalidApiKey.json")


def settings(**overrides) -> MilldeskSettings:
    base = dict(
        api_key="chave-secreta-1776", base_url="https://v1.milldesk.com/api",
        refresh_seconds=60, agent_name="Guilherme P.",
    )
    base.update(overrides)
    return MilldeskSettings(**base)


# --- parser ------------------------------------------------------------------


def test_normalize_name_ignores_case_accents_and_spaces():
    assert normalize_name("  Fábio  Júnior ") == normalize_name("fabio junior")


def test_open_statuses_skips_closed_and_empty():
    assert open_statuses(TICKETS_BY_STATUS) == ["Em atendimento", "Em Análise", "Aguardando Testes"]


def test_open_statuses_with_error_body():
    with pytest.raises(MilldeskApiError, match="invalidApiKey"):
        open_statuses(INVALID_KEY)


def test_build_state_counts_only_my_open_tickets_and_keeps_history():
    state = build_state(SHOW_BY_STATUS, TICKETS_BY_AGENT, "Guilherme P.")
    assert state.my_tickets == 3
    assert state.open_total == 5
    assert state.my_open_by_status == {"Em atendimento": 1, "Em Análise": 1, "Aguardando Testes": 1}
    # mais recente primeiro
    assert [t.id for t in state.tickets] == [7005, 7003, 7002]
    assert state.tickets[0].subject == "Configuração de Parâmetros"
    assert state.tickets[0].sla_expiration is None
    assert state.tickets[2].sla_expiration is None
    # histórico vem de ticketsByAgent (fixture usa "Guilherme P." com 12)
    assert state.my_history == 12
    assert state.my_percentage == 8.5
    assert state.total_all_agents == 141
    assert state.note is None


def test_build_state_does_not_confuse_similar_names():
    state = build_state(SHOW_BY_STATUS, TICKETS_BY_AGENT, "Guilherme Anderson dos Santos")
    assert [t.id for t in state.tickets] == [7004]
    assert state.my_history == 0  # não aparece no ticketsByAgent da fixture
    assert state.note is None  # mas tem chamado aberto, então foi encontrado


def test_ticket_time_strips_date_from_starttime():
    from app.sources.milldesk import ticket_from_api

    assert ticket_from_api({"id": "1", "starttime": "14/09/2026 13:09"}).starttime == "13:09"
    assert ticket_from_api({"id": "1", "starttime": "13:09"}).starttime == "13:09"
    assert ticket_from_api({"id": "1", "start": "14/09/2026", "starttime": ""}).start == "14/09/2026"


def test_build_state_unknown_agent_gives_zero_and_note():
    state = build_state(SHOW_BY_STATUS, TICKETS_BY_AGENT, "Ninguém")
    assert state.my_tickets == 0
    assert state.tickets == []
    assert state.my_history == 0
    assert state.note == NOT_FOUND_NOTE


def test_build_state_error_in_one_status_is_an_error():
    broken = dict(SHOW_BY_STATUS)
    broken["Em Análise"] = {"error": "invalidStatus"}
    with pytest.raises(MilldeskApiError, match="invalidStatus"):
        build_state(broken, TICKETS_BY_AGENT, "Guilherme P.")


# --- transporte --------------------------------------------------------------


def routing_handler(seen: list[str] | None = None, by_agent=TICKETS_BY_AGENT):
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(str(request.url))
        route = request.url.path.rsplit("/", 1)[-1]
        if route == "ticketsByStatus":
            return httpx.Response(200, json=TICKETS_BY_STATUS)
        if route == "showTicketsByStatus":
            status = parse_qs(request.url.query.decode())["status"][0]
            return httpx.Response(200, json=SHOW_BY_STATUS.get(status, {"error": "invalidStatus"}))
        if route == "ticketsByAgent":
            return httpx.Response(200, json=by_agent)
        return httpx.Response(404)

    return handler


def make_source(handler, **overrides) -> MilldeskSource:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return MilldeskSource(settings(**overrides), client=client)


async def test_fetch_queries_only_open_statuses_and_builds_state():
    seen: list[str] = []
    source = make_source(routing_handler(seen))
    state = await source.fetch()
    assert state.my_tickets == 3
    assert state.my_history == 12
    routes = sorted(url.split("chave-secreta-1776/", 1)[1] for url in seen)
    assert routes == [
        "showTicketsByStatus?status=Aguardando+Testes",
        "showTicketsByStatus?status=Em+An%C3%A1lise",
        "showTicketsByStatus?status=Em+atendimento",
        "ticketsByAgent",
        "ticketsByStatus",
    ]
    assert all("Fechado" not in url for url in seen)


async def test_invalid_key_with_http_200_fails_without_leaking_key():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=INVALID_KEY)

    source = make_source(handler)
    import app.sources.base as base

    original = base.RETRY_DELAYS
    base.RETRY_DELAYS = (0.01, 0.01, 0.01)
    try:
        with pytest.raises(SourceError) as info:
            await source.fetch_with_retry()
    finally:
        base.RETRY_DELAYS = original
    assert "invalidApiKey" in str(info.value)
    assert "chave-secreta-1776" not in str(info.value)


async def test_http_error_and_connection_error_are_masked():
    def handler_500(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    with pytest.raises(RuntimeError, match="HTTP 500"):
        await make_source(handler_500).fetch()

    def handler_conn(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("falhou em " + str(request.url), request=request)

    with pytest.raises(RuntimeError) as info:
        await make_source(handler_conn).fetch()
    assert "chave-secreta-1776" not in str(info.value)
    assert "****1776" in str(info.value)


async def test_non_json_response_is_an_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>login</html>")

    with pytest.raises(RuntimeError, match="não é JSON"):
        await make_source(handler).fetch()
