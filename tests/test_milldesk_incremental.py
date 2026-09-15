"""Coleta incremental do Milldesk: 1 chamada por ciclo quando nada muda, 429 sem retentativa."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

from app.config import MilldeskSettings
from app.sources.base import SourceError
from app.sources.milldesk import FULL_REFRESH_SECONDS, RATE_LIMIT_WAIT, MilldeskSource, RateLimitedError

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str):
    return json.loads((FIXTURES / name).read_text("utf-8"))


class FakeApi:
    """Servidor falso com contadores por rota, dados mutáveis e modo 429."""

    def __init__(self):
        self.by_status = load("milldesk_ticketsByStatus.json")
        self.lists = load("milldesk_showTicketsByStatus.json")
        self.by_agent = load("milldesk_ticketsByAgent.json")
        self.calls: list[str] = []
        self.rate_limited = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        route = request.url.path.rsplit("/", 1)[-1]
        if route == "showTicketsByStatus":
            route += "?" + parse_qs(request.url.query.decode())["status"][0]
        self.calls.append(route)
        if self.rate_limited:
            return httpx.Response(429, text="Too Many Requests")
        if route == "ticketsByStatus":
            return httpx.Response(200, json=self.by_status)
        if route.startswith("showTicketsByStatus?"):
            return httpx.Response(200, json=self.lists.get(route.split("?", 1)[1], {"error": "invalidStatus"}))
        if route == "ticketsByAgent":
            return httpx.Response(200, json=self.by_agent)
        return httpx.Response(404)

    def set_amount(self, status: str, amount: int) -> None:
        for item in self.by_status:
            if item["status"] == status:
                item["amount"] = str(amount)


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class _FastSleep:
    """Substitui asyncio.sleep dentro da fonte: registra e avanca o relogio falso."""

    def __init__(self):
        self.slept: list[float] = []
        self.clock: FakeClock | None = None

    async def __call__(self, seconds: float) -> None:
        self.slept.append(seconds)
        if self.clock is not None:
            self.clock.now += seconds


@pytest.fixture(autouse=True)
def fast_sleep(monkeypatch):
    import app.sources.milldesk as milldesk

    fake = _FastSleep()
    monkeypatch.setattr(milldesk.asyncio, "sleep", fake)
    return fake


def make(api: FakeApi, clock: FakeClock) -> MilldeskSource:
    settings = MilldeskSettings(
        api_key="chave-1776", base_url="https://v1.milldesk.com/api", refresh_seconds=60, agent_name="Guilherme P.",
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(api.handler))
    return MilldeskSource(settings, client=client, clock=clock)


async def test_first_cycle_is_full_and_following_cycles_use_only_the_index():
    api, clock = FakeApi(), FakeClock()
    source = make(api, clock)

    state = await source.fetch()
    assert state.my_tickets == 3 and state.my_history == 12
    assert api.calls.count("ticketsByStatus") == 1
    assert sum(c.startswith("showTicketsByStatus?") for c in api.calls) == 3
    assert api.calls.count("ticketsByAgent") == 1

    api.calls.clear()
    clock.now += 60
    state = await source.fetch()
    assert api.calls == ["ticketsByStatus"]  # nada mudou: só o índice
    assert state.my_tickets == 3 and state.my_history == 12


async def test_changed_status_count_reloads_only_that_status():
    api, clock = FakeApi(), FakeClock()
    source = make(api, clock)
    await source.fetch()
    api.calls.clear()

    # o chamado 7002 (meu, "Em atendimento") foi fechado: a lista encolhe e a contagem muda
    api.lists["Em atendimento"] = [t for t in api.lists["Em atendimento"] if t["id"] != "7002"]
    api.set_amount("Em atendimento", 1)
    clock.now += 60
    state = await source.fetch()
    assert api.calls == ["ticketsByStatus", "showTicketsByStatus?Em atendimento"]
    assert state.my_tickets == 2
    assert [t.id for t in state.tickets] == [7005, 7003]


async def test_emptied_status_disappears_without_extra_call():
    api, clock = FakeApi(), FakeClock()
    source = make(api, clock)
    await source.fetch()
    api.calls.clear()

    api.set_amount("Aguardando Testes", 0)
    clock.now += 60
    state = await source.fetch()
    assert api.calls == ["ticketsByStatus"]
    assert "Aguardando Testes" not in state.my_open_by_status
    assert state.my_tickets == 2


async def test_full_refresh_after_interval_reloads_everything():
    api, clock = FakeApi(), FakeClock()
    source = make(api, clock)
    await source.fetch()
    api.calls.clear()

    api.by_agent = copy.deepcopy(api.by_agent)
    api.by_agent[1]["amount"] = "13"
    clock.now += FULL_REFRESH_SECONDS + 1
    state = await source.fetch()
    assert api.calls.count("ticketsByAgent") == 1
    assert sum(c.startswith("showTicketsByStatus?") for c in api.calls) == 3
    assert state.my_history == 13


async def test_rate_limit_is_not_retried_and_carries_wait_time():
    api, clock = FakeApi(), FakeClock()
    source = make(api, clock)
    await source.fetch()  # popula o cache
    api.calls.clear()
    api.rate_limited = True

    with pytest.raises(RateLimitedError):
        await source.fetch()
    assert api.calls == ["ticketsByStatus"]

    api.calls.clear()
    with pytest.raises(SourceError) as info:  # dentro do cooldown: nem chama a API
        await source.fetch_with_retry()
    assert api.calls == []
    assert 0 < info.value.retry_after <= RATE_LIMIT_WAIT

    clock.now += RATE_LIMIT_WAIT
    with pytest.raises(SourceError) as info:
        await source.fetch_with_retry()
    assert api.calls == ["ticketsByStatus"]  # nenhuma retentativa
    assert info.value.retry_after == RATE_LIMIT_WAIT
    assert "429" in str(info.value)

    # cache sobreviveu: quando a API volta (e o cooldown passa), um ciclo normal basta
    api.rate_limited = False
    api.calls.clear()
    clock.now += RATE_LIMIT_WAIT
    state = await source.fetch()
    assert api.calls == ["ticketsByStatus"]
    assert state.my_tickets == 3


async def test_requests_are_spaced_out(fast_sleep):
    api, clock = FakeApi(), FakeClock()
    source = make(api, clock)
    fast_sleep.clock = clock
    await source.fetch()
    # 5 chamadas no primeiro ciclo -> 4 esperas de REQUEST_SPACING (o relogio falso nao avanca sozinho)
    import app.sources.milldesk as milldesk

    assert len(fast_sleep.slept) == 4
    assert all(abs(s - milldesk.REQUEST_SPACING) < 1e-6 for s in fast_sleep.slept)
