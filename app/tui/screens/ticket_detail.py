"""Detalhe de um chamado do Milldesk ("ler ticket"): Enter na lista ou `:md 1234`.

Abre imediatamente com "carregando…" e é preenchida quando o worker do App traz o
TicketDetail (1 chamada showTicket, com cache). `r` recarrega ignorando o cache.
"""

from __future__ import annotations

from datetime import datetime

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from app.state import TicketDetail, format_remaining

SLA_WARNING_HOURS = 4
SLA_REFRESH_SECONDS = 30.0


def sla_line(detail: TicketDetail, now: datetime | None = None) -> Text:
    """'SLA: 27/10/2026 14:34 · faltam 3d 04h' com cor (verde/amarelo/vermelho/cinza)."""
    now = now or datetime.now()
    text = Text()
    text.append("SLA: ", style="dim")
    remaining = detail.sla_remaining(now)
    if remaining is None:
        text.append(detail.sla_expiration or "sem prazo", style="dim")
        return text
    hours = remaining.total_seconds() / 3600
    if hours < 0:
        style, label = "bold red", f"VENCIDO há {format_remaining(-remaining)}"
    elif hours < SLA_WARNING_HOURS:
        style, label = "bold yellow", f"faltam {format_remaining(remaining)}"
    else:
        style, label = "green", f"faltam {format_remaining(remaining)}"
    text.append(detail.sla_expiration or "", style=style).append("  ·  ").append(label, style=style)
    return text


def header_text(detail: TicketDetail) -> Text:
    text = Text()
    text.append(f"#{detail.id}  ", style="bold cyan").append(detail.subject, style="bold")
    text.append("\n")
    text.append("Status: ", style="dim").append(detail.status or "-")
    text.append("   Etapa: ", style="dim").append(detail.stage or "-")
    text.append("   Prioridade: ", style="dim").append(detail.priority or "-")
    text.append("   Urgência: ", style="dim").append(detail.urgency or "-")
    text.append("\n")
    text.append("Solicitante: ", style="dim").append(detail.requester or "-")
    text.append("   Técnico: ", style="dim").append(detail.agent or "-")
    text.append("   Local: ", style="dim").append(detail.location or "-")
    text.append("\n")
    text.append("Categoria: ", style="dim").append(" / ".join(p for p in (detail.category, detail.subcategory) if p) or "-")
    text.append("   Departamento: ", style="dim").append(detail.department or "-")
    text.append("   Tipo: ", style="dim").append(detail.tickettype or "-")
    text.append("\n")
    text.append("Abertura: ", style="dim").append(detail.starttime or detail.start or "-")
    if detail.endtime or detail.end:
        text.append("   Encerramento: ", style="dim").append(detail.endtime or detail.end)
    if detail.worked_hour and detail.worked_hour != "0,0000":
        text.append("   Horas: ", style="dim").append(detail.worked_hour)
    return text


def communications_text(detail: TicketDetail) -> Text:
    text = Text()
    text.append("Comunicações", style="bold")
    if not detail.communications:
        text.append("\n(nenhuma)", style="dim")
        return text
    for entry in detail.communications:
        text.append("\n\n")
        if entry.when or entry.who:
            text.append(f"{entry.when}  ", style="cyan").append(entry.who, style="bold")
            text.append("\n")
        text.append(entry.text or "(vazio)")
    return text


class TicketDetailScreen(ModalScreen[None]):
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

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="ticket-detail"):
            yield Static("", id="ticket-header")
            yield Static("", id="ticket-sla")
            yield Static("", id="ticket-body")
            yield Static("", id="ticket-resolution")
            yield Static("", id="ticket-communications")
            yield Static(Text("[Esc] voltar  [r] recarregar  [o] abrir no navegador  [y] copiar ID", style="dim"),
                         id="ticket-footer")

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

    def set_loading(self) -> None:
        if not self._ready():
            return
        self.query_one("#ticket-header", Static).update(
            Text(f"#{self.ticket_id}  carregando…", style="dim")
        )

    def show_error(self, message: str) -> None:
        if not self._ready():
            self._pending_error = message
            return
        self._pending_error = None
        self.query_one("#ticket-header", Static).update(
            Text(f"#{self.ticket_id}  ", style="bold cyan").append(f"✖ {message}", style="bold red")
        )

    def show(self, detail: TicketDetail) -> None:
        self.detail = detail
        self._pending_error = None
        if not self._ready():
            return  # on_mount aplica self.detail
        self.query_one("#ticket-header", Static).update(header_text(detail))
        self._refresh_sla()
        body = Text("Descrição\n", style="bold")
        body.append(detail.description or "(sem descrição)")
        self.query_one("#ticket-body", Static).update(body)
        resolution = self.query_one("#ticket-resolution", Static)
        if detail.resolution:
            resolution.update(Text("Resolução\n", style="bold").append(detail.resolution))
            resolution.display = True
        else:
            resolution.display = False
        self.query_one("#ticket-communications", Static).update(communications_text(detail))

    def _refresh_sla(self) -> None:
        if self.detail is not None:
            self.query_one("#ticket-sla", Static).update(sla_line(self.detail))

    def action_reload(self) -> None:
        self.app.open_ticket(self.ticket_id, force=True)  # type: ignore[attr-defined]

    def action_open_browser(self) -> None:
        self.app.copy_text(str(self.ticket_id), "ID do chamado", quiet=True)  # type: ignore[attr-defined]
        self.app.open_url(self.app.settings.urls.milldesk or None, "Milldesk")  # type: ignore[attr-defined]

    def action_copy_id(self) -> None:
        self.app.copy_text(str(self.ticket_id), "ID do chamado")  # type: ignore[attr-defined]
