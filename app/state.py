"""Dataclasses do estado compartilhado publicado por cada fonte."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    return str(value)


def to_json(state: object) -> str:
    """Serializa qualquer estado (dataclass) em JSON legível. Usado no modo debug."""
    return json.dumps(asdict(state), default=_json_default, ensure_ascii=False, indent=2)


# --- E-mail -----------------------------------------------------------------


@dataclass
class LatestEmail:
    from_name: str
    from_addr: str
    subject: str
    date: datetime | None
    preview: str
    body: str = ""  # corpo completo, usado no modo detalhe (tecla e)


@dataclass
class EmailState:
    total: int = 0
    unseen: int = 0
    spam: int | None = None
    latest: LatestEmail | None = None
    updated_at: datetime = field(default_factory=datetime.now)
    error: str | None = None


# --- Milldesk ---------------------------------------------------------------


@dataclass
class MilldeskState:
    my_tickets: int = 0
    my_percentage: float = 0.0
    total_all_agents: int = 0
    note: str | None = None  # ex.: "técnico não encontrado na resposta"
    updated_at: datetime = field(default_factory=datetime.now)
    error: str | None = None


# --- ChatPanel --------------------------------------------------------------


@dataclass
class ChatItem:
    number: str
    name: str
    time: str
    last_message: str
    unread: int = 0
    tag: str | None = None
    department: str | None = None
    agent: str | None = None
    online: bool = False


@dataclass
class ChatPanelState:
    mine: list[ChatItem] = field(default_factory=list)
    mine_unread: int = 0
    others_count: int = 0
    total_unread_tab: int = 0
    logged_user: str | None = None
    updated_at: datetime = field(default_factory=datetime.now)
    error: str | None = None
