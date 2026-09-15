"""Feed de eventos: linha do tempo do dia derivada de diffs entre estados consecutivos.

Funções puras `diff_*` (testáveis sem TUI) e `EventLog`, que guarda os últimos eventos em
memória e os persiste em logs/events-AAAA-MM-DD.jsonl (um JSON por linha).
"""

from __future__ import annotations

import json
import logging
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from app.state import ChatPanelState, EmailState, MilldeskState

MAX_EVENTS = 500
log = logging.getLogger("events")


@dataclass
class Event:
    when: datetime
    source: str  # email | milldesk | chatpanel
    kind: str    # new_email | ticket_in | ticket_out | ticket_status | chat_in | chat_out | chat_message
    text: str
    key: str = ""

    def to_json(self) -> str:
        data = asdict(self)
        data["when"] = self.when.isoformat(timespec="seconds")
        return json.dumps(data, ensure_ascii=False)

    @classmethod
    def from_json(cls, line: str) -> Event | None:
        try:
            data = json.loads(line)
            return cls(when=datetime.fromisoformat(data["when"]), source=data["source"],
                       kind=data["kind"], text=data["text"], key=data.get("key", ""))
        except Exception:
            return None


def diff_email(previous: EmailState, current: EmailState, now: datetime | None = None) -> list[Event]:
    now = now or datetime.now()
    known = {item.uid for item in previous.recent}
    events = []
    for item in current.recent:
        if item.uid not in known:
            events.append(Event(now, "email", "new_email", f"e-mail novo de {item.sender}: {item.subject}", item.uid))
    if not previous.recent and not current.recent and current.unseen > previous.unseen:
        events.append(Event(now, "email", "new_email", f"não lidos subiram para {current.unseen}"))
    return events


def diff_milldesk(previous: MilldeskState, current: MilldeskState, now: datetime | None = None) -> list[Event]:
    now = now or datetime.now()
    before = {t.id: t for t in previous.tickets}
    after = {t.id: t for t in current.tickets}
    events = []
    for ticket_id, ticket in after.items():
        if ticket_id not in before:
            events.append(Event(now, "milldesk", "ticket_in",
                                f"chamado #{ticket_id} entrou no seu nome: {ticket.subject}", str(ticket_id)))
        elif before[ticket_id].status != ticket.status:
            events.append(Event(now, "milldesk", "ticket_status",
                                f"chamado #{ticket_id}: {before[ticket_id].status} → {ticket.status}", str(ticket_id)))
    for ticket_id, ticket in before.items():
        if ticket_id not in after:
            events.append(Event(now, "milldesk", "ticket_out",
                                f"chamado #{ticket_id} saiu do seu nome: {ticket.subject}", str(ticket_id)))
    return events


def diff_chatpanel(previous: ChatPanelState, current: ChatPanelState, now: datetime | None = None) -> list[Event]:
    now = now or datetime.now()
    mine_before = {c.number: c for c in previous.mine}
    mine_after = {c.number: c for c in current.mine}
    others_before = {c.number: c for c in previous.others}
    others_after = {c.number: c for c in current.others}
    events = []
    for number, chat in mine_after.items():
        if number not in mine_before:
            if number in others_before:
                origin = others_before[number].agent or "outro técnico"
                events.append(Event(now, "chatpanel", "chat_in",
                                    f"conversa de {chat.name} transferida para você (de {origin})", number))
            else:
                events.append(Event(now, "chatpanel", "chat_in", f"conversa nova no seu nome: {chat.name}", number))
        elif chat.unread > mine_before[number].unread:
            events.append(Event(now, "chatpanel", "chat_message",
                                f"mensagem nova de {chat.name} ({chat.unread} não lidas)", number))
    for number, chat in mine_before.items():
        if number not in mine_after:
            if number in others_after:
                target = others_after[number].agent or "outro técnico"
                events.append(Event(now, "chatpanel", "chat_out",
                                    f"conversa de {chat.name} transferida para {target}", number))
            else:
                events.append(Event(now, "chatpanel", "chat_out", f"conversa de {chat.name} saiu do seu nome", number))
    return events


DIFFS = {"email": diff_email, "milldesk": diff_milldesk, "chatpanel": diff_chatpanel}


def diff_states(source: str, previous: object, current: object, now: datetime | None = None) -> list[Event]:
    diff = DIFFS.get(source)
    if diff is None or previous is None or current is None:
        return []
    try:
        return diff(previous, current, now)  # type: ignore[arg-type]
    except Exception as exc:  # um diff nunca pode derrubar a publicação de estado
        log.warning("diff de %s falhou: %s", source, exc)
        return []


class EventLog:
    """Últimos eventos em memória + arquivo diário em JSONL."""

    def __init__(self, log_dir: Path | None, max_events: int = MAX_EVENTS) -> None:
        self.log_dir = log_dir
        self.events: deque[Event] = deque(maxlen=max_events)
        if log_dir is not None:
            self._load_today()

    def path_for(self, day: datetime) -> Path | None:
        if self.log_dir is None:
            return None
        return self.log_dir / f"events-{day:%Y-%m-%d}.jsonl"

    def _load_today(self) -> None:
        path = self.path_for(datetime.now())
        if path is None or not path.exists():
            return
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                event = Event.from_json(line)
                if event is not None:
                    self.events.append(event)
        except Exception as exc:
            log.warning("não consegui ler %s: %s", path.name, exc)

    def add(self, events: list[Event]) -> None:
        if not events:
            return
        self.events.extend(events)
        path = self.path_for(events[0].when)
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                for event in events:
                    handle.write(event.to_json() + "\n")
        except Exception as exc:
            log.warning("não consegui gravar %s: %s", path.name, exc)

    def latest(self, limit: int = 200) -> list[Event]:
        return list(self.events)[-limit:][::-1]
