"""Fonte 2: Milldesk via API REST (somente leitura).

Validação da Fase 3 (14/09/2026): `ticketsByAgent.amount` é o HISTÓRICO de chamados
do técnico, não os abertos. Por isso o painel usa:

1. GET /:key/ticketsByStatus            → quais status têm chamados (agregado, leve)
2. GET /:key/showTicketsByStatus?status= → chamados de cada status "aberto", com `agent`
3. GET /:key/ticketsByAgent             → histórico e percentual (linha secundária)

"Fechado" nunca é consultado (a rota devolve vazio para ele mesmo assim).
Erros chegam com HTTP 200 e corpo {"error": "invalidApiKey"|"invalidStatus"}.
A api_key nunca aparece em logs nem em mensagens de erro (mascarada como ****1776).

Modo debug: `python -m app.sources.milldesk` imprime o MilldeskState em JSON.
"""

from __future__ import annotations

import asyncio
import sys
import unicodedata
from datetime import datetime
from typing import Any

import httpx

from app.config import MilldeskSettings
from app.sources.base import Source
from app.state import MilldeskState, MilldeskTicket

NOT_FOUND_NOTE = "técnico não encontrado na resposta"
CLOSED_STATUSES = {"Fechado"}
MAX_CONCURRENT_REQUESTS = 3


class MilldeskApiError(Exception):
    """A API respondeu, mas com erro lógico (ex.: invalidApiKey)."""


# --- funções puras (testáveis sem rede) ---------------------------------------


def normalize_name(name: str) -> str:
    """Compara nomes sem acentos, sem espaços extras e sem diferenciar maiúsculas."""
    stripped = unicodedata.normalize("NFKD", name)
    without_accents = "".join(ch for ch in stripped if not unicodedata.combining(ch))
    return " ".join(without_accents.split()).casefold()


def _to_int(value: Any) -> int:
    if value is None or value == "":
        return 0
    return int(float(str(value).replace(",", ".")))


def _to_float(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    return float(str(value).replace(",", "."))


def check_api_error(data: Any, route: str = "") -> None:
    """Levanta MilldeskApiError se o corpo for {"error": "..."} (vem com HTTP 200)."""
    if isinstance(data, dict) and "error" in data:
        where = f" em {route}" if route else ""
        raise MilldeskApiError(f"API Milldesk{where}: {data['error']}")


def _ensure_list(data: Any, route: str) -> list[dict[str, Any]]:
    check_api_error(data, route)
    if not isinstance(data, list):
        raise MilldeskApiError(f"resposta inesperada de {route}: {type(data).__name__}")
    return [item for item in data if isinstance(item, dict)]


def open_statuses(tickets_by_status: Any) -> list[str]:
    """Status com pelo menos um chamado, excluindo os encerrados."""
    result: list[str] = []
    for item in _ensure_list(tickets_by_status, "ticketsByStatus"):
        status = str(item.get("status", "")).strip()
        if status and status not in CLOSED_STATUSES and _to_int(item.get("amount")) > 0:
            result.append(status)
    return result


def _time_only(value: Any) -> str:
    """A API às vezes manda "14/09/2026 13:09" em starttime; fica só "13:09"."""
    text = str(value or "").strip()
    return text.rsplit(" ", 1)[-1] if " " in text else text


def ticket_from_api(item: dict[str, Any]) -> MilldeskTicket:
    return MilldeskTicket(
        id=_to_int(item.get("id")),
        subject=str(item.get("ticket") or "").strip() or "(sem assunto)",
        status=str(item.get("status") or "").strip(),
        stage=str(item.get("stage") or "").strip(),
        requester=str(item.get("requester") or "").strip(),
        start=str(item.get("start") or "").strip(),
        starttime=_time_only(item.get("starttime")),
        sla_expiration=(str(item["slasexpirationdate"]).strip() or None)
        if item.get("slasexpirationdate") else None,
    )


def build_state(
    tickets_per_status: dict[str, Any],
    tickets_by_agent: Any,
    agent_name: str,
) -> MilldeskState:
    """Monta o estado a partir das respostas cruas das rotas."""
    wanted = normalize_name(agent_name)

    mine: list[MilldeskTicket] = []
    by_status: dict[str, int] = {}
    open_total = 0
    for status, raw in tickets_per_status.items():
        items = _ensure_list(raw, f"showTicketsByStatus?status={status}")
        open_total += len(items)
        for item in items:
            if normalize_name(str(item.get("agent") or "")) == wanted:
                ticket = ticket_from_api(item)
                ticket.status = ticket.status or status
                mine.append(ticket)
                by_status[status] = by_status.get(status, 0) + 1
    mine.sort(key=_ticket_sort_key, reverse=True)

    history = 0
    percentage = 0.0
    total_all = 0
    found_in_history = False
    for item in _ensure_list(tickets_by_agent, "ticketsByAgent"):
        total_all += _to_int(item.get("amount"))
        if not found_in_history and normalize_name(str(item.get("agent", ""))) == wanted:
            history = _to_int(item.get("amount"))
            percentage = _to_float(item.get("percentage"))
            found_in_history = True

    return MilldeskState(
        my_tickets=len(mine),
        my_open_by_status=by_status,
        tickets=mine,
        open_total=open_total,
        my_history=history,
        my_percentage=percentage,
        total_all_agents=total_all,
        note=None if (found_in_history or mine) else NOT_FOUND_NOTE,
        updated_at=datetime.now(),
    )


def _ticket_sort_key(ticket: MilldeskTicket) -> tuple[str, str, int]:
    """Mais recente primeiro: data dd/mm/aaaa vira aaaa-mm-dd para ordenar como texto."""
    parts = ticket.start.split("/")
    iso = "-".join(reversed(parts)) if len(parts) == 3 else ticket.start
    return (iso, ticket.starttime, ticket.id)


# --- fonte -----------------------------------------------------------------------


class MilldeskSource(Source[MilldeskState]):
    name = "milldesk"
    label = "Milldesk"
    config_hint = "preencha MILLDESK_API_KEY no .env"

    def __init__(
        self,
        settings: MilldeskSettings,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(interval=settings.refresh_seconds, timeout=40.0)
        self.settings = settings
        self.agent_name = settings.agent_name
        self._client = client
        self._owns_client = client is None
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    @property
    def configured(self) -> bool:
        return self.settings.configured

    def _mask(self, text: str) -> str:
        """Garante que a chave real nunca vaze em erro/log (httpx inclui a URL em alguns erros)."""
        key = self.settings.api_key
        return text.replace(key, self.settings.masked_key) if key else text

    def _url(self, route: str) -> str:
        return f"{self.settings.base_url}/{self.settings.api_key}/{route}"

    async def _get_json(self, route: str, params: dict[str, Any] | None = None) -> Any:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        async with self._semaphore:
            try:
                response = await self._client.get(self._url(route), params=params)
            except httpx.HTTPError as exc:
                raise RuntimeError(self._mask(f"{type(exc).__name__}: {exc}")) from None
        if response.status_code != 200:
            raise RuntimeError(f"HTTP {response.status_code} em {route}")
        try:
            return response.json()
        except ValueError:
            raise RuntimeError(f"resposta de {route} não é JSON") from None

    async def fetch(self) -> MilldeskState:
        by_status_agg = await self._get_json("ticketsByStatus")
        statuses = open_statuses(by_status_agg)
        self.log.debug("status com chamados abertos: %s", statuses)

        per_status_raw, by_agent = await asyncio.gather(
            asyncio.gather(*(self._get_json("showTicketsByStatus", {"status": s}) for s in statuses)),
            self._get_json("ticketsByAgent"),
        )
        tickets_per_status = dict(zip(statuses, per_status_raw))

        state = build_state(tickets_per_status, by_agent, self.agent_name)
        if state.note:
            self.log.warning("%s (MILLDESK_AGENT_NAME=%r)", state.note, self.agent_name)
        return state

    async def close(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
        self._client = None


# --- modo debug --------------------------------------------------------------------


async def _debug_main() -> int:
    from app.config import ConfigError, load_settings
    from app.logging_setup import setup_debug_logging
    from app.main import force_utf8_console
    from app.state import to_json

    force_utf8_console()
    setup_debug_logging()
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 2
    source = MilldeskSource(settings.milldesk)
    if not source.configured:
        print(source.config_hint, file=sys.stderr)
        return 2
    try:
        state = await source.fetch_with_retry()
    finally:
        await source.close()
    print(to_json(state))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_debug_main()))
