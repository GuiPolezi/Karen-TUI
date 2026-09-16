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

from app import clock
from app.state import TicketDetail, format_remaining
from app.tui.icons import UNICODE, IconSet
from app.tui.themes import CARBON
from app.tui.tokens import Tokens

SLA_WARNING_HOURS = 4
SLA_REFRESH_SECONDS = 30.0


def sla_line(detail: TicketDetail, now: datetime | None = None, *, tokens: Tokens = CARBON,
             icons: IconSet = UNICODE) -> Text:
    """'SLA: 27/10/2026 14:34 · faltam 3d 04h' com a cor (ok/warn/danger) só no prazo e no tempo."""
    now = now or clock.now()
    text = Text()
    text.append("SLA: ", style=tokens.rich("text-faint"))
    remaining = detail.sla_remaining(now)
    if remaining is None:
        text.append(detail.sla_expiration or "sem prazo", style=tokens.rich("text-muted"))
        return text
    hours = remaining.total_seconds() / 3600
    if hours < 0:
        token, label = "danger", f"vencido há {format_remaining(-remaining)}"
    elif hours < SLA_WARNING_HOURS:
        token, label = "warn", f"faltam {format_remaining(remaining)}"
    else:
        token, label = "ok", f"faltam {format_remaining(remaining)}"
    style = tokens.rich(token, bold=token == "danger")
    text.append(detail.sla_expiration or "", style=style)
    text.append(f"  {icons.sep}  ", style=tokens.rich("text-faint")).append(label, style=style)
    return text


def header_text(detail: TicketDetail, tokens: Tokens = CARBON) -> Text:
    label, value = tokens.rich("text-faint"), tokens.rich("text")
    text = Text()
    text.append(f"#{detail.id}  ", style=tokens.rich("text-muted", bold=True)).append(detail.subject, style=tokens.rich("text", bold=True))
    text.append("\n")
    text.append("Status: ", style=label).append(detail.status or "-", style=value)
    text.append("   Etapa: ", style=label).append(detail.stage or "-", style=value)
    text.append("   Prioridade: ", style=label).append(detail.priority or "-", style=value)
    text.append("   Urgência: ", style=label).append(detail.urgency or "-", style=value)
    text.append("\n")
    text.append("Solicitante: ", style=label).append(detail.requester or "-", style=value)
    text.append("   Técnico: ", style=label).append(detail.agent or "-", style=value)
    text.append("   Local: ", style=label).append(detail.location or "-", style=value)
    text.append("\n")
    text.append("Categoria: ", style=label).append(" / ".join(p for p in (detail.category, detail.subcategory) if p) or "-", style=value)
    text.append("   Departamento: ", style=label).append(detail.department or "-", style=value)
    text.append("   Tipo: ", style=label).append(detail.tickettype or "-", style=value)
    text.append("\n")
    text.append("Abertura: ", style=label).append(detail.starttime or detail.start or "-", style=value)
    if detail.endtime or detail.end:
        text.append("   Encerramento: ", style=label).append(detail.endtime or detail.end, style=value)
    if detail.worked_hour and detail.worked_hour != "0,0000":
        text.append("   Horas: ", style=label).append(detail.worked_hour, style=value)
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
            text.append(f"{entry.when}  ", style=tokens.rich("text-faint")).append(entry.who, style=tokens.rich("text", bold=True))
            text.append("\n")
        text.append(entry.text or "(vazio)", style=tokens.rich("text"))
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

    @property
    def tokens(self) -> Tokens:
        return self.app.tokens  # type: ignore[attr-defined]

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="ticket-detail"):
            yield Static("", id="ticket-header")
            yield Static("", id="ticket-sla")
            yield Static("", id="ticket-body")
            yield Static("", id="ticket-resolution")
            yield Static("", id="ticket-communications")
            yield Static(Text("Esc voltar  r recarregar  o abrir no navegador  y copiar ID",
                              style=self.tokens.rich("text-faint")), id="ticket-footer")

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
            Text(f"#{self.ticket_id}  carregando…", style=self.tokens.rich("text-muted"))
        )

    def show_error(self, message: str) -> None:
        if not self._ready():
            self._pending_error = message
            return
        self._pending_error = None
        icons = self.app.icons  # type: ignore[attr-defined]
        self.query_one("#ticket-header", Static).update(
            Text(f"#{self.ticket_id}  ", style=self.tokens.rich("text-muted", bold=True))
            .append(f"{icons.error} {message}", style=self.tokens.rich("danger", bold=True))
        )

    def show(self, detail: TicketDetail) -> None:
        self.detail = detail
        self._pending_error = None
        if not self._ready():
            return  # on_mount aplica self.detail
        tokens = self.tokens
        self.query_one("#ticket-header", Static).update(header_text(detail, tokens))
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
        if self.detail is not None:
            self.query_one("#ticket-sla", Static).update(
                sla_line(self.detail, tokens=self.tokens, icons=self.app.icons)  # type: ignore[attr-defined]
            )

    def action_reload(self) -> None:
        self.app.open_ticket(self.ticket_id, force=True)  # type: ignore[attr-defined]

    def action_open_browser(self) -> None:
        self.app.copy_text(str(self.ticket_id), "ID do chamado", quiet=True)  # type: ignore[attr-defined]
        self.app.open_url(self.app.settings.urls.milldesk or None, "Milldesk")  # type: ignore[attr-defined]

    def action_copy_id(self) -> None:
        self.app.copy_text(str(self.ticket_id), "ID do chamado")  # type: ignore[attr-defined]
