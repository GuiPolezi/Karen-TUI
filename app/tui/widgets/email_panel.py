"""Painel de e-mail (IMAP)."""

from __future__ import annotations

from datetime import datetime

from rich.console import Group
from rich.rule import Rule
from rich.text import Text

from app.state import EmailState
from app.tui.widgets.base_panel import BasePanel


def format_email_date(date: datetime | None) -> str:
    if date is None:
        return "--:--"
    if date.date() == datetime.now().date():
        return date.strftime("%H:%M")
    return date.strftime("%d/%m %H:%M")


def _line(*parts: str | tuple[str, str]) -> Text:
    text = Text(no_wrap=True, overflow="ellipsis")
    for part in parts:
        if isinstance(part, tuple):
            text.append(part[0], style=part[1])
        else:
            text.append(part)
    return text


class EmailPanel(BasePanel):
    ICON = "📧"
    TITLE = "E-MAIL"

    def counters(self, state: EmailState) -> dict[str, int]:
        return {"total": state.total, "não lidos": state.unseen}

    def show_state(self, state: EmailState) -> None:
        unseen_style = "bold yellow" if state.unseen else "bold"
        spam_text = "-" if state.spam is None else str(state.spam)
        header = _line(
            "Inbox: ", (str(state.total), "bold"),
            "   Não lidos: ", (str(state.unseen), unseen_style),
            "   Spam: ", (spam_text, "bold"),
        )

        if state.latest is None:
            self.set_body(Group(header, Rule(style="dim"), _line(("caixa vazia", "dim"))))
            return

        latest = state.latest
        sender = latest.from_name or latest.from_addr
        if latest.from_name and latest.from_addr:
            sender = f"{latest.from_name} <{latest.from_addr}>"
        self.set_body(
            Group(
                header,
                Rule(style="dim"),
                _line(("De:   ", "dim"), sender),
                _line(("Ass.: ", "dim"), (latest.subject, "bold")),
                _line((format_email_date(latest.date), "cyan"), (" · ", "dim"), latest.preview or "(sem conteúdo)"),
            )
        )
