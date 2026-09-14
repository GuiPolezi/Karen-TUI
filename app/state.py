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
class MilldeskTicket:
    id: int
    subject: str
    status: str
    stage: str
    requester: str
    start: str      # dd/mm/aaaa
    starttime: str  # HH:MM
    sla_expiration: str | None = None


@dataclass
class MilldeskState:
    my_tickets: int = 0                      # abertos no meu nome (destaque do painel)
    my_open_by_status: dict[str, int] = field(default_factory=dict)
    tickets: list[MilldeskTicket] = field(default_factory=list)
    open_total: int = 0                      # abertos de todos os técnicos
    my_history: int = 0                      # amount de ticketsByAgent (histórico)
    my_percentage: float = 0.0               # percentage de ticketsByAgent (histórico)
    total_all_agents: int = 0                # soma de amount de todos (histórico)
    note: str | None = None                  # ex.: "técnico não encontrado na resposta"
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
