"""Interface comum das fontes de dados.

Cada fonte implementa fetch() e devolve um estado (dataclass de app.state).
fetch_with_retry() aplica timeout e retry com backoff (3 tentativas, 2/4/8 s)
e, se tudo falhar, levanta SourceError com a última mensagem. Quem chama
(o worker da TUI) decide como exibir sem derrubar os outros painéis.

Exceções com atributo `retry_after` (segundos) NÃO são retentadas: viram
SourceError imediatamente e o worker espera esse tempo antes do próximo ciclo.
É o caso de HTTP 429 (limite de requisições) e de sessão expirada.
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

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


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
                retry_after = getattr(exc, "retry_after", None)
                if retry_after is not None:
                    self.log.warning(
                        "%s; sem retentativa, próximo ciclo em %ds", describe_error(exc), retry_after
                    )
                    raise SourceError(describe_error(exc), retry_after=float(retry_after)) from exc
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
