"""Fonte 2: Milldesk via API REST (somente leitura).

Validação da Fase 3 (14/09/2026): `ticketsByAgent.amount` é o HISTÓRICO de chamados
do técnico, não os abertos. Por isso o painel usa:

1. GET /:key/ticketsByStatus            → quais status têm chamados (agregado, leve)
2. GET /:key/showTicketsByStatus?status= → chamados de cada status "aberto", com `agent`
3. GET /:key/ticketsByAgent             → histórico e percentual (linha secundária)

Limite de requisições (Fase 5, 14/09/2026): a API devolve HTTP 429 com ~10 chamadas
por minuto. Por isso a coleta é INCREMENTAL:
- todo ciclo: só o índice `ticketsByStatus` (1 chamada);
- `showTicketsByStatus` só para os status cuja quantidade mudou desde o ciclo anterior;
- `ticketsByAgent` e uma recarga completa a cada FULL_REFRESH_SECONDS;
- chamadas sequenciais com REQUEST_SPACING entre elas;
- 429 não é retentado: o worker espera RATE_LIMIT_WAIT antes do próximo ciclo.

"Fechado" nunca é consultado (a rota devolve vazio para ele mesmo assim).
Erros chegam com HTTP 200 e corpo {"error": "invalidApiKey"|"invalidStatus"}.
A api_key nunca aparece em logs nem em mensagens de erro (mascarada como ****1776).

Detalhe de um chamado (Fase 6.2): `fetch_ticket(id)` chama showTicket (1 GET), com cache
por ID (TTL MILLDESK_DETAIL_TTL_SECONDS), a mesma fila/espaçamento da coleta e respeito ao
cooldown após 429. `description` vem em HTML e `communication` é uma string HTML com
entradas "dd/mm/aaaa HH:MM:SS Nome diz: <br> texto".

Modo debug: `python -m app.sources.milldesk` imprime o MilldeskState em JSON;
`python -m app.sources.milldesk --ticket 1234` imprime o TicketDetail.
"""

from __future__ import annotations

import asyncio
import re
import sys
import time
import unicodedata
from datetime import datetime
from typing import Any, Callable

import httpx
from bs4 import BeautifulSoup

from app.config import MilldeskSettings
from app.sources.base import Source
from app.state import Communication, MilldeskState, MilldeskTicket, TicketDetail

NOT_FOUND_NOTE = "técnico não encontrado na resposta"
CLOSED_STATUSES = {"Fechado"}
FULL_REFRESH_SECONDS = 600.0   # recarrega todas as listas e o histórico a cada 10 min
REQUEST_SPACING = 0.4          # segundos entre chamadas consecutivas
RATE_LIMIT_WAIT = 180.0        # segundos de espera após HTTP 429


class MilldeskApiError(Exception):
    """A API respondeu, mas com erro lógico (ex.: invalidApiKey)."""


class RateLimitedError(Exception):
    """HTTP 429: não retentar; esperar `retry_after` segundos."""

    def __init__(self, route: str, retry_after: float = RATE_LIMIT_WAIT) -> None:
        super().__init__(f"limite de requisições da API (HTTP 429 em {route})")
        self.retry_after = retry_after


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


def open_status_counts(tickets_by_status: Any) -> dict[str, int]:
    """{status: quantidade} para status com chamados, excluindo os encerrados."""
    result: dict[str, int] = {}
    for item in _ensure_list(tickets_by_status, "ticketsByStatus"):
        status = str(item.get("status", "")).strip()
        amount = _to_int(item.get("amount"))
        if status and status not in CLOSED_STATUSES and amount > 0:
            result[status] = amount
    return result


def open_statuses(tickets_by_status: Any) -> list[str]:
    return list(open_status_counts(tickets_by_status))


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


def html_to_text(html: str | None) -> str:
    """HTML do Milldesk -> texto com quebras: <br> vira \n, <p>/<div>/<li> viram parágrafos."""
    if not html:
        return ""
    if not re.search(r"<\w+[^>]*>", html):
        return html.strip()
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for block in soup.find_all(["p", "div", "li", "tr", "h1", "h2", "h3", "h4"]):
        block.insert_before("\n")
        block.insert_after("\n")
    text = soup.get_text()
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return "\n".join(line.strip() for line in text.split("\n")).strip()


COMMUNICATION_RE = re.compile(r"(\d{2}/\d{2}/\d{4} \d{2}:\d{2}(?::\d{2})?)\s+(.+?)\s+diz:\s*")


def parse_communications(raw: str | None) -> list[Communication]:
    """Separa o campo `communication` em entradas (quando, quem, texto)."""
    text = html_to_text(raw)
    if not text:
        return []
    matches = list(COMMUNICATION_RE.finditer(text))
    if not matches:
        return [Communication(when="", who="", text=text)]
    result = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end():end].strip()
        result.append(Communication(when=match.group(1), who=match.group(2).strip(), text=body))
    return result


def _text(item: dict[str, Any], key: str) -> str:
    value = item.get(key)
    return "" if value is None else str(value).strip()


def ticket_detail_from_api(data: Any) -> TicketDetail:
    """Resposta crua de showTicket -> TicketDetail. Erros ({"error": ...}) viram exceção."""
    check_api_error(data, "showTicket")
    if isinstance(data, list):
        data = data[0] if data else {}
    if not isinstance(data, dict) or not data.get("id"):
        raise MilldeskApiError("resposta inesperada de showTicket (sem id)")
    return TicketDetail(
        id=_to_int(data.get("id")),
        subject=_text(data, "ticket") or "(sem assunto)",
        requester=_text(data, "requester"),
        agent=_text(data, "agent"),
        status=_text(data, "status"),
        stage=_text(data, "stage"),
        priority=_text(data, "priority"),
        urgency=_text(data, "urgency"),
        category=_text(data, "category"),
        subcategory=_text(data, "subcategory"),
        department=_text(data, "department"),
        location=_text(data, "location"),
        group=_text(data, "group"),
        tickettype=_text(data, "tickettype"),
        manner=_text(data, "manner"),
        level=_text(data, "level"),
        impact=_text(data, "impact"),
        start=_text(data, "start"),
        starttime=_text(data, "starttime"),
        end=_text(data, "end"),
        endtime=_text(data, "endtime"),
        sla_expiration=_text(data, "slasexpirationdate") or None,
        description=html_to_text(data.get("description")),
        resolution=html_to_text(data.get("resolution")),
        communications=parse_communications(data.get("communication")),
        worked_hour=_text(data, "worked_hour"),
        charge_hour=_text(data, "charge_hour"),
        fetched_at=datetime.now(),
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
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__(interval=settings.refresh_seconds, timeout=60.0)
        self.settings = settings
        self.agent_name = settings.agent_name
        self._client = client
        self._owns_client = client is None
        self._clock = clock
        self._lock = asyncio.Lock()
        self._last_request_at: float | None = None
        # cache incremental
        self._status_counts: dict[str, int] = {}
        self._status_lists: dict[str, Any] = {}
        self._by_agent: Any = None
        self._last_full_refresh: float | None = None
        # detalhe por ID: {id: (detalhe, instante monotônico em que foi buscado)}
        self._details: dict[int, tuple[TicketDetail, float]] = {}
        self._rate_limited_until: float | None = None  # cooldown após HTTP 429

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
            self._client = httpx.AsyncClient(timeout=30.0)
        if self._rate_limited_until is not None:
            remaining = self._rate_limited_until - self._clock()
            if remaining > 0:  # cooldown: nem tenta, para não estender o bloqueio
                raise RateLimitedError(route, retry_after=remaining)
            self._rate_limited_until = None
        async with self._lock:  # uma chamada por vez, com espaçamento
            if self._last_request_at is not None:
                elapsed = self._clock() - self._last_request_at
                if elapsed < REQUEST_SPACING:
                    await asyncio.sleep(REQUEST_SPACING - elapsed)
            try:
                response = await self._client.get(self._url(route), params=params)
            except httpx.HTTPError as exc:
                raise RuntimeError(self._mask(f"{type(exc).__name__}: {exc}")) from None
            finally:
                self._last_request_at = self._clock()
        if response.status_code == 429:
            self._rate_limited_until = self._clock() + RATE_LIMIT_WAIT
            raise RateLimitedError(route)
        if response.status_code != 200:
            raise RuntimeError(f"HTTP {response.status_code} em {route}")
        try:
            return response.json()
        except ValueError:
            raise RuntimeError(f"resposta de {route} não é JSON") from None

    def _full_refresh_due(self) -> bool:
        return (
            self._last_full_refresh is None
            or self._by_agent is None
            or self._clock() - self._last_full_refresh >= FULL_REFRESH_SECONDS
        )

    async def fetch(self) -> MilldeskState:
        counts = open_status_counts(await self._get_json("ticketsByStatus"))
        full = self._full_refresh_due()

        stale = [
            status for status, amount in counts.items()
            if full or status not in self._status_lists or self._status_counts.get(status) != amount
        ]
        for status in stale:
            self._status_lists[status] = await self._get_json("showTicketsByStatus", {"status": status})
        for status in list(self._status_lists):
            if status not in counts:  # status esvaziou: some da tela sem nova chamada
                del self._status_lists[status]
        self._status_counts = counts

        if full:
            self._by_agent = await self._get_json("ticketsByAgent")
            self._last_full_refresh = self._clock()

        self.log.debug(
            "ciclo: %d status abertos, %d recarregados%s",
            len(counts), len(stale), ", recarga completa" if full else "",
        )
        state = build_state(dict(self._status_lists), self._by_agent, self.agent_name)
        if state.note:
            self.log.warning("%s (MILLDESK_AGENT_NAME=%r)", state.note, self.agent_name)
        return state

    async def fetch_ticket(self, ticket_id: int, force: bool = False) -> TicketDetail:
        """Detalhe de um chamado: 1 GET showTicket, cache por ID com TTL. `force` ignora o cache."""
        ttl = float(self.settings.detail_ttl_seconds)
        cached = self._details.get(ticket_id)
        if cached is not None and not force and self._clock() - cached[1] < ttl:
            self.log.debug("showTicket %s: cache", ticket_id)
            return cached[0]
        data = await self._get_json("showTicket", {"id": ticket_id})
        detail = ticket_detail_from_api(data)
        self._details[ticket_id] = (detail, self._clock())
        if len(self._details) > 100:
            oldest = min(self._details, key=lambda key: self._details[key][1])
            del self._details[oldest]
        return detail

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
        if len(sys.argv) > 2 and sys.argv[1] == "--ticket":  # --ticket 1234: detalhe de um chamado
            print(to_json(await source.fetch_ticket(int(sys.argv[2]))))
            return 0
        state = await source.fetch_with_retry()
    finally:
        await source.close()
    print(to_json(state))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_debug_main()))
