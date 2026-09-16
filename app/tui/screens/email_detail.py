"""Detalhe de um e-mail (tecla `e` para o mais recente, `Enter` na lista). `Esc` volta."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.widgets import Static

from app.state import LatestEmail
from app.tui.screens.detail import DetailScreen, label_value_grid
from app.tui.widgets.email_panel import format_email_date


class EmailDetailScreen(DetailScreen):
    PREFIX = "email-detail"
    FOOTER = [("{key_escape}", "voltar"), ("y", "copiar remetente")]
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

    def body_widgets(self) -> ComposeResult:
        yield Static("", id="email-detail-text", classes="detail-text")

    def on_mount(self) -> None:
        self.refresh_content()

    def refresh_content(self) -> None:
        self.query_one("#email-detail-header", Static).update(self._header())
        self.query_one("#email-detail-text", Static).update(self._body_text())
        self.set_busy(self.latest is None)

    def show(self, latest: LatestEmail) -> None:
        """Preenche a tela quando o corpo chega (abriu com o indicador de carga)."""
        self.latest = latest
        if self.query("#email-detail-header"):
            self.refresh_content()

    def _header(self):  # noqa: ANN202 — Table ou Text
        tokens = self.tokens
        if self.latest is None:
            return Text(f"carregando e-mail {self.loading_uid or ''}…", style=tokens.rich("text-muted"))
        latest = self.latest
        sender = latest.from_name or latest.from_addr
        if latest.from_name and latest.from_addr:
            sender = f"{latest.from_name} <{latest.from_addr}>"
        when = latest.date.strftime("%d/%m/%Y %H:%M") if latest.date else "--"
        return label_value_grid([
            ("de", sender),
            ("assunto", Text(latest.subject, style=tokens.rich("text", bold=True))),
            ("data", Text(f"{when}  {self.icons.sep} {format_email_date(latest.date)}", style=tokens.rich("text-muted"))),
        ], tokens, columns=1)

    def _body_text(self) -> Text:
        if self.latest is None:
            return Text("")
        return Text(self.latest.body or self.latest.preview or "(sem conteúdo)", style=self.tokens.rich("text"))

    def action_copy_sender(self) -> None:
        if self.latest is not None:
            self.app.copy_text(self.latest.from_addr, "remetente")  # type: ignore[attr-defined]
