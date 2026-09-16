"""Detalhe de um chamado do Milldesk ("ler ticket"): Enter na lista ou `:md 1234`.

Abre imediatamente (cabeçalho com o ID e o indicador de carga) e é preenchida quando o
worker do App traz o TicketDetail (1 chamada showTicket, com cache). `r` recarrega
ignorando o cache.
"""

from __future__ import annotations

from datetime import datetime

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.widgets import Static

from app import clock
from app.state import TicketDetail, format_remaining
from app.tui.icons import UNICODE, IconSet
from app.tui.screens.detail import DetailScreen, label_value_grid
from app.tui.themes import CARBON
from app.tui.tokens import Tokens
from app.tui.widgets.milldesk_panel import BAR_BLOCKS

SLA_WARNING_HOURS = 4
SLA_REFRESH_SECONDS = 30.0


def sla_line(detail: TicketDetail, now: datetime | None = None, *, tokens: Tokens = CARBON,
             icons: IconSet = UNICODE) -> Text:
    """'SLA: 27/10/2026 14:34  ▮▮▯▯  faltam 3d 04h' com a cor (ok/warn/danger) só na barra e no tempo."""
    now = now or clock.now()
    text = Text()
    text.append("SLA: ", style=tokens.rich("text-faint"))
    remaining = detail.sla_remaining(now)
    if remaining is None:
        text.append(detail.sla_expiration or "sem prazo", style=tokens.rich("text-muted"))
        return text
    hours = remaining.total_seconds() / 3600
    if hours < 0:
        token, label, filled = "danger", f"vencido há {format_remaining(-remaining)}", BAR_BLOCKS
    elif hours < SLA_WARNING_HOURS:
        token, label, filled = "warn", f"faltam {format_remaining(remaining)}", 3
    else:
        token, label, filled = "ok", f"faltam {format_remaining(remaining)}", 2 if hours < 24 else 1
    style = tokens.rich(token, bold=token == "danger")
    text.append(detail.sla_expiration or "", style=tokens.rich("text"))
    text.append("  ").append(icons.bar_on * filled + icons.bar_off * (BAR_BLOCKS - filled), style=tokens.rich(token))
    text.append("  ").append(label, style=style)
    return text


def header_grid(detail: TicketDetail, tokens: Tokens = CARBON):  # noqa: ANN201 — rich Table
    """Cabeçalho em duas colunas rótulo/valor (sem ':' nem texto corrido)."""
    value = tokens.rich("text")
    category = " / ".join(p for p in (detail.category, detail.subcategory) if p) or "-"
    pairs: list[tuple[str, Text | str]] = [
        ("status", detail.status or "-"), ("solicitante", detail.requester or "-"),
        ("etapa", detail.stage or "-"), ("técnico", detail.agent or "-"),
        ("prioridade", Text(f"{detail.priority or '-'}  ", style=value).append("urgência ", style=tokens.rich("text-faint")).append(detail.urgency or "-", style=value)),
        ("local", detail.location or "-"),
        ("categoria", category), ("abertura", detail.starttime or detail.start or "-"),
    ]
    if detail.department or detail.tickettype:
        pairs.append(("departamento", detail.department or "-"))
        pairs.append(("tipo", detail.tickettype or "-"))
    if detail.endtime or detail.end:
        pairs.append(("encerramento", detail.endtime or detail.end))
    if detail.worked_hour and detail.worked_hour != "0,0000":
        pairs.append(("horas", detail.worked_hour))
    return label_value_grid(pairs, tokens)


def header_text(detail: TicketDetail, tokens: Tokens = CARBON) -> Text:
    """Primeira linha do cabeçalho: '#4821  Assunto' (ID em text-muted, assunto em bold)."""
    text = Text(no_wrap=True, overflow="ellipsis")
    text.append(f"#{detail.id}  ", style=tokens.rich("text-muted", bold=True))
    text.append(detail.subject, style=tokens.rich("text", bold=True))
    return text


def communications_text(detail: TicketDetail, tokens: Tokens = CARBON) -> Text:
    text = Text()
    text.append("Comunicações", style=tokens.rich("text-muted", bold=True))
    if not detail.communications:
        text.append("\n(nenhuma)", style=tokens.rich("text-faint"))
        return text
    for entry in detail.communications:
        text.append("\n\n")
        if entry.when or entry.who:
            text.append(f"{entry.when[:16]}  ", style=tokens.rich("text-faint")).append(entry.who, style=tokens.rich("text", bold=True))
            text.append("\n")
        text.append(entry.text or "(vazio)", style=tokens.rich("text"))
    return text


class TicketDetailScreen(DetailScreen):
    PREFIX = "ticket"
    FOOTER = [("{key_escape}", "voltar"), ("r", "recarregar"), ("o", "navegador"), ("y", "copiar ID")]
    BINDINGS = [
        Binding("escape", "dismiss", "Voltar"),
        Binding("q", "dismiss", "Voltar"),
        Binding("r", "reload", "Recarregar"),
        Binding("o", "open_browser", "Navegador"),
        Binding("y", "copy_id", "Copiar ID"),
    ]

    def __init__(self, ticket_id: int, detail: TicketDetail | None = None) -> None:
        super().__init__()
        self.ticket_id = ticket_id
        self.detail = detail
        self._pending_error: str | None = None  # chegou antes de os widgets montarem

    def body_widgets(self) -> ComposeResult:
        yield Static("", id="ticket-fields")
        yield Static("", id="ticket-sla")
        yield Static("", id="ticket-body")
        yield Static("", id="ticket-resolution")
        yield Static("", id="ticket-communications")

    def on_mount(self) -> None:
        if self._pending_error is not None:
            self.show_error(self._pending_error)
        elif self.detail is not None:
            self.show(self.detail)
        else:
            self.set_loading()
        self.set_interval(SLA_REFRESH_SECONDS, self._refresh_sla)

    def _ready(self) -> bool:
        """Os widgets já foram compostos? (o worker pode responder antes disso)"""
        return bool(self.query("#ticket-header"))

    def refresh_content(self) -> None:
        if self.detail is not None:
            self.show(self.detail)

    def set_loading(self) -> None:
        if not self._ready():
            return
        self.query_one("#ticket-header", Static).update(
            Text(f"#{self.ticket_id}", style=self.tokens.rich("text-muted", bold=True))
        )
        self.set_busy(True)

    def show_error(self, message: str) -> None:
        if not self._ready():
            self._pending_error = message
            return
        self._pending_error = None
        self.set_busy(False)
        header = Text(f"#{self.ticket_id}  ", style=self.tokens.rich("text-muted", bold=True))
        header.append_text(self.error_text(message))
        self.query_one("#ticket-header", Static).update(header)

    def show(self, detail: TicketDetail) -> None:
        self.detail = detail
        self._pending_error = None
        if not self._ready():
            return  # on_mount aplica self.detail
        tokens = self.tokens
        self.set_busy(False)
        self.query_one("#ticket-header", Static).update(header_text(detail, tokens))
        self.query_one("#ticket-fields", Static).update(header_grid(detail, tokens))
        self._refresh_sla()
        body = Text("Descrição\n", style=tokens.rich("text-muted", bold=True))
        body.append(detail.description or "(sem descrição)", style=tokens.rich("text"))
        self.query_one("#ticket-body", Static).update(body)
        resolution = self.query_one("#ticket-resolution", Static)
        if detail.resolution:
            resolution.update(Text("Resolução\n", style=tokens.rich("text-muted", bold=True))
                              .append(detail.resolution, style=tokens.rich("text")))
            resolution.display = True
        else:
            resolution.display = False
        self.query_one("#ticket-communications", Static).update(communications_text(detail, tokens))

    def _refresh_sla(self) -> None:
        if self.detail is not None and self._ready():
            self.query_one("#ticket-sla", Static).update(sla_line(self.detail, tokens=self.tokens, icons=self.icons))

    def action_reload(self) -> None:
        self.app.open_ticket(self.ticket_id, force=True)  # type: ignore[attr-defined]

    def action_open_browser(self) -> None:
        self.app.copy_text(str(self.ticket_id), "ID do chamado", quiet=True)  # type: ignore[attr-defined]
        self.app.open_url(self.app.settings.urls.milldesk or None, "Milldesk")  # type: ignore[attr-defined]

    def action_copy_id(self) -> None:
        self.app.copy_text(str(self.ticket_id), "ID do chamado")  # type: ignore[attr-defined]
