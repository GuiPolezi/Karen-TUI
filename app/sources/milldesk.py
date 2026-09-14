"""Fonte 2: Milldesk via API REST (somente leitura).

Rota usada: GET {base_url}/{api_key}/ticketsByAgent
Resposta:   [ {"agent": "Nome", "amount": "12", "percentage": "8.5"}, ... ]
Erros chegam com HTTP 200 e corpo {"error": "invalidApiKey"}: tratados como falha.

A api_key nunca aparece em logs nem em mensagens de erro (mascarada como ****1776).

Modo debug: `python -m app.sources.milldesk` imprime o MilldeskState em JSON.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import unicodedata
from datetime import datetime
from typing import Any

import httpx

from app.config import MilldeskSettings
from app.sources.base import Source
from app.state import MilldeskState

NOT_FOUND_NOTE = "técnico não encontrado na resposta"


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


def check_api_error(data: Any) -> None:
    """Levanta MilldeskApiError se o corpo for {"error": "..."} (vem com HTTP 200)."""
    if isinstance(data, dict) and "error" in data:
        raise MilldeskApiError(f"API Milldesk: {data['error']}")


def parse_tickets_by_agent(data: Any, tech_name: str) -> MilldeskState:
    check_api_error(data)
    if not isinstance(data, list):
        raise MilldeskApiError(f"resposta inesperada de ticketsByAgent: {type(data).__name__}")

    wanted = normalize_name(tech_name)
    total = 0
    mine: dict[str, Any] | None = None
    for item in data:
        if not isinstance(item, dict):
            continue
        total += _to_int(item.get("amount"))
        if mine is None and normalize_name(str(item.get("agent", ""))) == wanted:
            mine = item

    if mine is None:
        return MilldeskState(
            my_tickets=0,
            my_percentage=0.0,
            total_all_agents=total,
            note=NOT_FOUND_NOTE,
            updated_at=datetime.now(),
        )
    return MilldeskState(
        my_tickets=_to_int(mine.get("amount")),
        my_percentage=_to_float(mine.get("percentage")),
        total_all_agents=total,
        note=None,
        updated_at=datetime.now(),
    )


# --- fonte -----------------------------------------------------------------------


class MilldeskSource(Source[MilldeskState]):
    name = "milldesk"
    label = "Milldesk"
    config_hint = "preencha MILLDESK_API_KEY no .env"

    def __init__(
        self,
        settings: MilldeskSettings,
        tech_name: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(interval=settings.refresh_seconds, timeout=20.0)
        self.settings = settings
        self.tech_name = tech_name
        self._client = client
        self._owns_client = client is None

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
        self.log.debug("GET %s", self._mask(self._url(route)))
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
        data = await self._get_json("ticketsByAgent")
        state = parse_tickets_by_agent(data, self.tech_name)
        if state.note:
            self.log.warning("%s (TECH_NAME=%r)", state.note, self.tech_name)
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
    source = MilldeskSource(settings.milldesk, settings.tech_name)
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
