"""Detalhe de um e-mail (tecla `e` para o mais recente, `Enter` na lista). `Esc` volta."""

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
        Binding("y", "copy_sender", "Copiar remetente"),
    ]

    def __init__(self, latest: LatestEmail | None, loading_uid: str | None = None) -> None:
        super().__init__()
        self.latest = latest
        self.loading_uid = loading_uid

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="email-detail"):
            yield Static(self._header(), id="email-detail-header")
            yield Static(self._body_text(), id="email-detail-body")
            yield Static(Text("[Esc] voltar  [y] copiar remetente", style="dim"), id="email-detail-footer")

    def show(self, latest: LatestEmail) -> None:
        """Preenche a tela quando o corpo chega (abriu com 'carregando…')."""
        self.latest = latest
        self.query_one("#email-detail-header", Static).update(self._header())
        self.query_one("#email-detail-body", Static).update(self._body_text())

    def _header(self) -> Text:
        header = Text()
        if self.latest is None:
            header.append("carregando e-mail…", style="dim")
            return header
        latest = self.latest
        sender = latest.from_name or latest.from_addr
        if latest.from_name and latest.from_addr:
            sender = f"{latest.from_name} <{latest.from_addr}>"
        when = latest.date.strftime("%d/%m/%Y %H:%M") if latest.date else "--"
        header.append("De:      ", style="dim").append(sender + "\n")
        header.append("Assunto: ", style="dim").append(latest.subject + "\n", style="bold")
        header.append("Data:    ", style="dim").append(f"{when}  ({format_email_date(latest.date)})")
        return header

    def _body_text(self) -> Text:
        if self.latest is None:
            return Text("")
        return Text(self.latest.body or self.latest.preview or "(sem conteúdo)")

    def action_copy_sender(self) -> None:
        if self.latest is not None:
            self.app.copy_text(self.latest.from_addr, "remetente")  # type: ignore[attr-defined]
