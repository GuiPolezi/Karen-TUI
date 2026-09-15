"""Painel de e-mail (IMAP): contadores + lista dos últimos N e-mails com cursor."""

from __future__ import annotations

from datetime import datetime

from rich.text import Text

from app.state import EmailState, EmailSummary, LatestEmail
from app.tui.widgets.base_panel import BasePanel


def format_email_date(date: datetime | None) -> str:
    if date is None:
        return "--:--"
    if date.date() == datetime.now().date():
        return date.strftime("%H:%M")
    return date.strftime("%d/%m %H:%M")


def summary_from_latest(latest: LatestEmail) -> EmailSummary:
    """Fallback quando a fonte só trouxe o e-mail mais recente (sem lista)."""
    return EmailSummary(uid="latest", from_name=latest.from_name, from_addr=latest.from_addr,
                        subject=latest.subject, date=latest.date, unseen=False)


class EmailPanel(BasePanel):
    SOURCE = "email"
    ICON = "📧"
    TITLE = "E-MAIL"
    COLUMNS = [("date", "Data", 11), ("from", "De", 28), ("subject", "Assunto", None)]
    COLUMNS_COMPACT = [("date", "Data", 11), ("from", "De", 16), ("subject", "Assunto", None)]
    COLUMNS_NARROW = [("date", "Data", 11), ("subject", "Assunto", None)]

    def counters(self, state: EmailState) -> dict[str, int]:
        return {"total": state.total, "não lidos": state.unseen}

    def header_text(self, state: EmailState) -> Text:
        unseen_style = "bold yellow" if state.unseen else "bold"
        text = Text(no_wrap=True, overflow="ellipsis")
        text.append("Inbox: ").append(str(state.total), style="bold")
        text.append("   Não lidos: ").append(str(state.unseen), style=unseen_style)
        text.append("   Spam: ").append("-" if state.spam is None else str(state.spam), style="bold")
        if not state.recent and state.latest is None:
            text.append("   caixa vazia", style="dim")
        return text

    def summaries(self, state: EmailState) -> list[EmailSummary]:
        if state.recent:
            items = state.recent
        elif state.latest is not None:
            items = [summary_from_latest(state.latest)]
        else:
            items = []
        if getattr(self.app, "prefs", None) is not None and self.app.prefs.email_only_unseen and self.full:  # type: ignore[attr-defined]
            items = [item for item in items if item.unseen]
        return items

    def rows(self, state: EmailState) -> list[tuple[str, dict[str, Text]]]:
        rows = []
        for item in self.summaries(state):
            style = "bold" if item.unseen else ""
            rows.append((item.uid, {
                "date": Text(format_email_date(item.date), style="cyan"),
                "from": Text(item.sender, style=style),
                "subject": Text(item.subject or "(sem assunto)", style=style),
            }))
        return rows

    def item_for_key(self, key: str) -> EmailSummary | None:
        if self.state is None:
            return None
        return next((item for item in self.summaries(self.state) if item.uid == key), None)

    def browser_url(self, key: str) -> str | None:
        return self.app.settings.urls.webmail or None  # type: ignore[attr-defined]

    def copy_value(self, key: str) -> str | None:
        item = self.item_for_key(key)
        return item.from_addr if item else None

    def what(self) -> str:
        return "e-mail"
