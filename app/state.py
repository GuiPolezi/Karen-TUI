"""Dataclasses do estado compartilhado publicado por cada fonte."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta


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
class EmailSummary:
    """Uma linha da lista de e-mails recentes (só cabeçalhos)."""

    uid: str
    from_name: str
    from_addr: str
    subject: str
    date: datetime | None
    unseen: bool = False

    @property
    def sender(self) -> str:
        return self.from_name or self.from_addr


@dataclass
class EmailState:
    total: int = 0
    unseen: int = 0
    spam: int | None = None
    latest: LatestEmail | None = None
    recent: list[EmailSummary] = field(default_factory=list)  # mais novo primeiro
    updated_at: datetime = field(default_factory=datetime.now)
    error: str | None = None


# --- Milldesk ---------------------------------------------------------------


def parse_datetime_br(text: str | None) -> datetime | None:
    """'27/10/2026 14:34' ou '27/10/2026' -> datetime; texto como 'Em pausa' -> None."""
    if not text:
        return None
    match = re.search(r"(\d{2})/(\d{2})/(\d{4})(?:\s+(\d{2}):(\d{2}))?", text)
    if not match:
        return None
    day, month, year, hour, minute = match.groups()
    try:
        return datetime(int(year), int(month), int(day), int(hour or 0), int(minute or 0))
    except ValueError:
        return None


def format_remaining(delta: timedelta | None) -> str:
    """Contagem regressiva curta: '3d 04h', '02h15', '-45min' (vencido), '' sem prazo."""
    if delta is None:
        return ""
    negative = delta.total_seconds() < 0
    seconds = abs(int(delta.total_seconds()))
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    if days:
        text = f"{days}d {hours:02d}h"
    elif hours:
        text = f"{hours:02d}h{minutes:02d}"
    else:
        text = f"{minutes}min"
    return f"-{text}" if negative else text


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

    @property
    def sla_deadline(self) -> datetime | None:
        return parse_datetime_br(self.sla_expiration)

    def sla_remaining(self, now: datetime | None = None) -> timedelta | None:
        deadline = self.sla_deadline
        if deadline is None:
            return None
        return deadline - (now or datetime.now())

    @property
    def opened_at(self) -> datetime | None:
        return parse_datetime_br(f"{self.start} {self.starttime}".strip())


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


@dataclass
class Communication:
    """Uma entrada do histórico do chamado (campo `communication` do showTicket)."""

    when: str   # dd/mm/aaaa HH:MM:SS
    who: str
    text: str


@dataclass
class TicketDetail:
    """Resposta de showTicket já limpa (descrição em texto, comunicações separadas)."""

    id: int
    subject: str
    requester: str
    agent: str
    status: str
    stage: str
    priority: str
    urgency: str
    category: str
    subcategory: str
    department: str
    location: str
    group: str
    tickettype: str
    manner: str
    level: str
    impact: str
    start: str
    starttime: str
    end: str
    endtime: str
    sla_expiration: str | None
    description: str
    resolution: str
    communications: list[Communication] = field(default_factory=list)
    worked_hour: str = ""
    charge_hour: str = ""
    fetched_at: datetime = field(default_factory=datetime.now)

    @property
    def sla_deadline(self) -> datetime | None:
        return parse_datetime_br(self.sla_expiration)

    def sla_remaining(self, now: datetime | None = None) -> timedelta | None:
        deadline = self.sla_deadline
        if deadline is None:
            return None
        return deadline - (now or datetime.now())


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
    others: list[ChatItem] = field(default_factory=list)  # em atendimento por outros técnicos
    total_unread_tab: int = 0
    logged_user: str | None = None
    updated_at: datetime = field(default_factory=datetime.now)
    error: str | None = None
