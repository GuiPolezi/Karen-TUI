"""Painel do Milldesk: chamados abertos no nome do técnico, com SLA e ordenação.

As funções puras (`sla_token`, `sla_text`, `sla_bar`, `nearest_sla`, `sorted_tickets`)
devolvem nomes de token (`danger`, `warn`, `ok`, `text-faint`), nunca cores; o painel
converte com `self.style()`.
"""

from __future__ import annotations

from datetime import datetime

from rich.text import Text
from textual.binding import Binding

from app import clock
from app.state import MilldeskState, MilldeskTicket, format_remaining
from app.tui.icons import UNICODE, IconSet
from app.tui.themes import CARBON
from app.tui.tokens import Tokens
from app.tui.widgets.base_panel import BasePanel

SORT_MODES = ("sla", "data", "status")
SORT_LABELS = {"sla": "SLA mais próximo", "data": "mais recente", "status": "status"}
SLA_WARNING_HOURS = 4
SLA_ALERT_MINUTES = 30
HEADER_REFRESH_SECONDS = 30.0
BLINK_SECONDS = 1.0
BAR_BLOCKS = 4


def format_percentage(value: float) -> str:
    text = f"{value:.1f}".replace(".", ",")
    return text[:-2] if text.endswith(",0") else text


def sla_token(ticket: MilldeskTicket, now: datetime | None = None) -> str:
    """Token de cor do SLA: `danger` vencido, `warn` < 4 h, `ok` folgado, `text-faint` sem prazo."""
    remaining = ticket.sla_remaining(now)
    if remaining is None:
        return "text-faint"
    hours = remaining.total_seconds() / 3600
    if hours < 0:
        return "danger"
    if hours < SLA_WARNING_HOURS:
        return "warn"
    return "ok"


def sla_text(ticket: MilldeskTicket, now: datetime | None = None) -> str:
    remaining = ticket.sla_remaining(now)
    if remaining is None:
        return (ticket.sla_expiration or "")[:9]
    return format_remaining(remaining)


def sla_bar(ticket: MilldeskTicket, now: datetime | None = None, icons: IconSet = UNICODE) -> str:
    """Barra de 4 blocos: quanto mais perto do prazo, mais cheia (vencido = cheia)."""
    remaining = ticket.sla_remaining(now)
    if remaining is None:
        return icons.bar_off * BAR_BLOCKS
    hours = remaining.total_seconds() / 3600
    filled = 4 if hours < 1 else 3 if hours < SLA_WARNING_HOURS else 2 if hours < 24 else 1
    return icons.bar_on * filled + icons.bar_off * (BAR_BLOCKS - filled)


def overdue_count(tickets: list[MilldeskTicket], now: datetime | None = None) -> int:
    now = now or clock.now()
    return sum(1 for t in tickets if (r := t.sla_remaining(now)) is not None and r.total_seconds() < 0)


def nearest_sla(tickets: list[MilldeskTicket], now: datetime | None = None) -> MilldeskTicket | None:
    """Chamado com o prazo de SLA mais próximo (vencidos primeiro); None sem prazos."""
    with_deadline = [t for t in tickets if t.sla_deadline is not None]
    if not with_deadline:
        return None
    return min(with_deadline, key=lambda t: t.sla_deadline or datetime.max)


def sla_alert(ticket: MilldeskTicket, now: datetime | None = None) -> bool:
    """True quando faltam menos de 30 min (e ainda não venceu): o tempo pisca."""
    remaining = ticket.sla_remaining(now or clock.now())
    return remaining is not None and 0 <= remaining.total_seconds() < SLA_ALERT_MINUTES * 60


def sla_highlight(ticket: MilldeskTicket, now: datetime | None = None, *, tokens: Tokens = CARBON,
                  icons: IconSet = UNICODE, width: int = 0, blink: bool = False) -> Text:
    """'SLA ▸ #id assunto   ▮▮▮▯  faltam 02h15': a cor só na barra e no tempo.
    `blink=True` é a fase apagada do piscar (< 30 min): o tempo fica em `text`."""
    now = now or clock.now()
    remaining = ticket.sla_remaining(now)
    minutes = (remaining.total_seconds() / 60) if remaining is not None else None
    if minutes is not None and minutes < 0:
        token, label = "danger", f"vencido há {format_remaining(-remaining)}"
    elif minutes is not None and minutes < SLA_ALERT_MINUTES:
        token, label = ("text" if blink else "danger"), f"faltam {format_remaining(remaining)} {icons.warn}"
    elif minutes is not None and minutes < SLA_WARNING_HOURS * 60:
        token, label = "warn", f"faltam {format_remaining(remaining)}"
    elif minutes is not None:
        token, label = "ok", f"faltam {format_remaining(remaining)}"
    else:
        token, label = "text-faint", "sem prazo"
    left = Text(no_wrap=True)
    left.append(f"SLA {icons.sla} ", style=tokens.rich("text-faint"))
    left.append(f"#{ticket.id} ", style=tokens.rich("text-muted")).append(ticket.subject, style=tokens.rich("text"))
    right = Text(no_wrap=True)
    right.append(sla_bar(ticket, now, icons), style=tokens.rich(token)).append("  ")
    right.append(label, style=tokens.rich(token, bold=True))
    if width <= 0:
        return Text.assemble(left, "  ", right)
    from app.tui.widgets.base_panel import padded

    return padded(left, right, width)


def sorted_tickets(tickets: list[MilldeskTicket], mode: str, now: datetime | None = None) -> list[MilldeskTicket]:
    now = now or clock.now()
    if mode == "status":
        return sorted(tickets, key=lambda t: (t.status, -(t.opened_at or datetime.min).timestamp()))
    if mode == "data":
        return sorted(tickets, key=lambda t: (t.opened_at or datetime.min), reverse=True)
    far = datetime.max
    return sorted(tickets, key=lambda t: (t.sla_deadline or far, t.id))


class MilldeskPanel(BasePanel):
    SOURCE = "milldesk"
    ICON = "ticket"
    TITLE = "MILLDESK"
    MORE_KEY = "F3"
    RETRY_KEY = "2"
    SUMMARY = [("abertos", "aberto no meu nome|abertos no meu nome"), ("vencidos", "vencido|vencidos")]
    COLUMNS = [("id", "#", 6), ("time", "Abertura", 11), ("subject", "Assunto", None),
               ("status", "Status", 20), ("sla", "SLA", 9)]
    COLUMNS_COMPACT = [("id", "#", 6), ("subject", "Assunto", None), ("sla", "SLA", 8)]
    COLUMNS_NARROW = [("id", "#", 6), ("subject", "Assunto", None), ("sla", "SLA", 8)]
    BINDINGS = [*BasePanel.BINDINGS, Binding("s", "cycle_sort", "Ordenar", show=False)]

    def counters(self, state: MilldeskState) -> dict[str, int]:
        return {"abertos": state.my_tickets, "vencidos": overdue_count(state.tickets)}

    def summary_values(self, state: MilldeskState) -> dict[str, tuple[str, str]]:
        overdue = overdue_count(state.tickets)
        return {
            "abertos": (str(state.my_tickets), "text" if state.my_tickets else "text-faint"),
            "vencidos": (str(overdue), "danger" if overdue else "text-faint"),
        }

    def empty_text(self) -> str:
        return "nenhum chamado no seu nome"

    @property
    def sort_mode(self) -> str:
        prefs = getattr(self.app, "prefs", None)
        mode = getattr(prefs, "milldesk_sort", "sla")
        return mode if mode in SORT_MODES else "sla"

    def extra_text(self, state: MilldeskState) -> Text | None:
        tokens, icons = self.tokens, self.icons
        sep = f" {icons.sep} "
        text = Text(no_wrap=True, overflow="ellipsis")
        parts = [f"{name} {n}" for name, n in state.my_open_by_status.items()]
        text.append(sep.join(parts), style=tokens.rich("text-muted"))
        nearest = nearest_sla(state.tickets)
        if nearest is not None:
            text.append("\n").append_text(sla_highlight(nearest, tokens=tokens, icons=icons, width=self.content_width,
                                                        blink=self._blink_phase))
        if self.full:
            text.append(
                f"\nhistórico: {state.my_history} chamados{sep}{format_percentage(state.my_percentage)}% de "
                f"{state.total_all_agents}{sep}{state.open_total} abertos no total",
                style=tokens.rich("text-faint"),
            )
        if state.note:
            text.append(f"\n{icons.warn} {state.note}", style=tokens.rich("warn"))
        return text

    _blink_phase = False  # fase apagada do piscar do SLA (< 30 min)

    def on_mount(self) -> None:
        super().on_mount()
        self.set_interval(HEADER_REFRESH_SECONDS, self._refresh_countdowns)
        self.set_interval(BLINK_SECONDS, self._blink_tick)

    def _refresh_countdowns(self) -> None:
        """A contagem regressiva do SLA anda mesmo sem estado novo."""
        if self.state is not None:
            self.show_state(self.state)

    @property
    def blink_enabled(self) -> bool:
        """SLA_BLINK no .env e animações ligadas (TEXTUAL_ANIMATIONS=none desliga)."""
        settings = getattr(self.app, "settings", None)
        if settings is not None and not getattr(settings, "sla_blink", True):
            return False
        return getattr(self.app, "animation_level", "full") != "none"

    def _blink_tick(self) -> None:
        """Só o tempo do SLA alterna danger/text a cada segundo, e só abaixo de 30 min."""
        if self.state is None or not self.blink_enabled:
            if self._blink_phase:
                self._blink_phase = False
                self._render_extra()
            return
        nearest = nearest_sla(self.state.tickets)
        if nearest is None or not sla_alert(nearest):
            if self._blink_phase:
                self._blink_phase = False
                self._render_extra()
            return
        self._blink_phase = not self._blink_phase
        self._render_extra()

    def rows(self, state: MilldeskState) -> list[tuple[str, dict[str, Text]]]:
        now = clock.now()
        muted = self.style("text-muted")
        rows = []
        for ticket in sorted_tickets(state.tickets, self.sort_mode, now):
            opened = ticket.opened_at
            when = opened.strftime("%d/%m %H:%M") if opened else ticket.starttime
            token = sla_token(ticket, now)
            rows.append((str(ticket.id), {
                "id": Text(f"#{ticket.id}", style=muted),
                "time": Text(when, style=muted),
                "subject": Text(ticket.subject, style=self.style("text")),
                "status": Text(ticket.status, style=muted),
                "sla": Text(sla_text(ticket, now), style=self.style(token, bold=token == "danger")),
            }))
        return rows

    def item_for_key(self, key: str) -> MilldeskTicket | None:
        if self.state is None:
            return None
        return next((t for t in self.state.tickets if str(t.id) == key), None)

    def action_cycle_sort(self) -> None:
        prefs = getattr(self.app, "prefs", None)
        if prefs is None:
            return
        index = SORT_MODES.index(self.sort_mode)
        prefs.milldesk_sort = SORT_MODES[(index + 1) % len(SORT_MODES)]
        self.app.save_prefs()  # type: ignore[attr-defined]
        self.app.notify(f"Milldesk ordenado por {SORT_LABELS[prefs.milldesk_sort]}")
        self.app.refresh_panels("milldesk")  # type: ignore[attr-defined]
        refresh = getattr(self.screen, "refresh_footer", None)
        if refresh is not None:
            refresh()

    def browser_url(self, key: str) -> str | None:
        return self.app.settings.urls.milldesk or None  # type: ignore[attr-defined]

    def copy_value(self, key: str) -> str | None:
        return key

    def what(self) -> str:
        return "chamado"
