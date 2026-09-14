"""Telas secundárias: detalhe do e-mail mais recente (tecla `e`, `Esc` volta)."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from app.state import LatestEmail
from app.tui.widgets.email_panel import format_email_date


class EmailDetailScreen(ModalScreen[None]):
    BINDINGS = [
        Binding("escape", "dismiss", "Voltar"),
        Binding("e", "dismiss", "Voltar"),
        Binding("q", "dismiss", "Voltar"),
    ]

    def __init__(self, latest: LatestEmail) -> None:
        super().__init__()
        self.latest = latest

    def compose(self) -> ComposeResult:
        latest = self.latest
        sender = latest.from_name or latest.from_addr
        if latest.from_name and latest.from_addr:
            sender = f"{latest.from_name} <{latest.from_addr}>"
        when = latest.date.strftime("%d/%m/%Y %H:%M") if latest.date else "--"

        header = Text()
        header.append("De:      ", style="dim")
        header.append(sender + "\n")
        header.append("Assunto: ", style="dim")
        header.append(latest.subject + "\n", style="bold")
        header.append("Data:    ", style="dim")
        header.append(when)

        with VerticalScroll(id="email-detail"):
            yield Static(header, id="email-detail-header")
            yield Static(Text(latest.body or latest.preview or "(sem conteúdo)"), id="email-detail-body")
            yield Static(Text(f"[Esc] voltar · {format_email_date(latest.date)}", style="dim"), id="email-detail-footer")
