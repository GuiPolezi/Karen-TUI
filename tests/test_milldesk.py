"""Testes da fonte Milldesk sem rede: parser com fixture, erro lógico e transporte via httpx mock."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.config import MilldeskSettings
from app.sources.base import SourceError
from app.sources.milldesk import (
    NOT_FOUND_NOTE,
    MilldeskApiError,
    MilldeskSource,
    normalize_name,
    parse_tickets_by_agent,
)

FIXTURES = Path(__file__).parent / "fixtures"
TICKETS_BY_AGENT = json.loads((FIXTURES / "milldesk_ticketsByAgent.json").read_text("utf-8"))
INVALID_KEY = json.loads((FIXTURES / "milldesk_error_invalidApiKey.json").read_text("utf-8"))


def settings(**overrides) -> MilldeskSettings:
    base = dict(api_key="chave-secreta-1776", base_url="https://v1.milldesk.com/api", refresh_seconds=60)
    base.update(overrides)
    return MilldeskSettings(**base)


# --- parser ------------------------------------------------------------------


def test_normalize_name_ignores_case_accents_and_spaces():
    assert normalize_name("  Fábio  Júnior ") == normalize_name("fabio junior")


def test_parse_fixture_finds_tech_and_converts_strings():
    state = parse_tickets_by_agent(TICKETS_BY_AGENT, "guilherme")
    assert state.my_tickets == 12
    assert state.my_percentage == 8.5
    assert state.total_all_agents == 141
    assert state.note is None
    assert state.error is None


def test_parse_fixture_tech_not_found_gives_zero_and_note():
    state = parse_tickets_by_agent(TICKETS_BY_AGENT, "Ninguém")
    assert state.my_tickets == 0
    assert state.my_percentage == 0.0
    assert state.total_all_agents == 141
    assert state.note == NOT_FOUND_NOTE


def test_parse_error_body_with_http_200_is_an_error():
    with pytest.raises(MilldeskApiError, match="invalidApiKey"):
        parse_tickets_by_agent(INVALID_KEY, "Guilherme")


def test_parse_unexpected_shape_is_an_error():
    with pytest.raises(MilldeskApiError, match="inesperada"):
        parse_tickets_by_agent({"agent": "x"}, "Guilherme")


# --- transporte --------------------------------------------------------------


def make_source(handler, **overrides) -> MilldeskSource:
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    return MilldeskSource(settings(**overrides), "Guilherme", client=client)


async def test_fetch_builds_url_with_key_and_parses():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json=TICKETS_BY_AGENT)

    source = make_source(handler)
    state = await source.fetch()
    assert seen == ["https://v1.milldesk.com/api/chave-secreta-1776/ticketsByAgent"]
    assert state.my_tickets == 12


async def test_invalid_key_with_http_200_fails_without_leaking_key():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=INVALID_KEY)

    source = make_source(handler)
    source.timeout = 0.5
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
