"""Relógio da aplicação: `now()`/`epoch()` em vez de `datetime.now()`/`time.time()` na TUI.

Em produção devolve a hora real. Testes de snapshot e capturas de design congelam a
hora com `freeze()` para que relógio, "há N s" e contagens de SLA sejam determinísticos.
"""

from __future__ import annotations

from datetime import datetime

_frozen: datetime | None = None


def now() -> datetime:
    return _frozen if _frozen is not None else datetime.now()


def epoch() -> float:
    return now().timestamp()


def freeze(moment: datetime | None) -> None:
    """Fixa a hora (None volta ao relógio real)."""
    global _frozen
    _frozen = moment


def frozen() -> bool:
    return _frozen is not None
