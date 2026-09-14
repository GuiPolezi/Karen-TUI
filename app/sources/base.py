"""Interface comum das fontes de dados.

Cada fonte implementa fetch() e devolve um estado (dataclass de app.state).
fetch_with_retry() aplica timeout e retry com backoff (3 tentativas, 2/4/8 s)
e, se tudo falhar, levanta SourceError com a última mensagem. Quem chama
(o worker da TUI) decide como exibir sem derrubar os outros painéis.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Generic, TypeVar

S = TypeVar("S")

RETRY_DELAYS = (2, 4, 8)


class SourceError(Exception):
    """Falha definitiva de uma fonte após todas as tentativas."""


class Source(ABC, Generic[S]):
    name: str = "source"

    def __init__(self, interval: int, timeout: float = 20.0) -> None:
        self.interval = interval
        self.timeout = timeout
        self.log = logging.getLogger(f"source.{self.name}")

    @property
    def configured(self) -> bool:
        """False quando falta segredo/credencial; o painel mostra "não configurado"."""
        return True

    @abstractmethod
    async def fetch(self) -> S:
        """Uma coleta. Deve levantar exceção em caso de falha."""

    async def fetch_with_retry(self) -> S:
        last_error: BaseException | None = None
        for attempt, delay in enumerate((*RETRY_DELAYS, None), start=1):
            try:
                return await asyncio.wait_for(self.fetch(), timeout=self.timeout)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # qualquer falha vira erro da fonte
                last_error = exc
                self.log.warning("tentativa %d falhou: %s", attempt, describe_error(exc))
                if delay is None:
                    break
                await asyncio.sleep(delay)
        assert last_error is not None
        raise SourceError(describe_error(last_error)) from last_error

    async def close(self) -> None:
        """Libera recursos (conexão IMAP, navegador...). Padrão: nada."""


def describe_error(exc: BaseException) -> str:
    """Mensagem curta e legível para exibir no painel."""
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return "timeout"
    text = str(exc).strip()
    return text or type(exc).__name__
