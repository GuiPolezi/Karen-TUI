"""Painel de e-mail (IMAP): contadores + lista dos últimos N e-mails com cursor."""

from __future__ import annotations

from datetime import datetime

from rich.text import Text

from app import clock
from app.state import EmailState, EmailSummary, LatestEmail
from app.tui.widgets.base_panel import BasePanel


def format_email_date(date: datetime | None) -> str:
    if date is None:
        return "--:--"
    if date.date() == clock.now().date():
        return date.strftime("%H:%M")
    return date.strftime("%d/%m %H:%M")


def summary_from_latest(latest: LatestEmail) -> EmailSummary:
    """Fallback quando a fonte só trouxe o e-mail mais recente (sem lista)."""
    return EmailSummary(uid="latest", from_name=latest.from_name, from_addr=latest.from_addr,
                        subject=latest.subject, date=latest.date, unseen=False)


class EmailPanel(BasePanel):
    SOURCE = "email"
    ICON = "email"
    TITLE = "E-MAIL"
    COLUMNS = [("date", "Data", 11), ("from", "De", 28), ("subject", "Assunto", None)]
    COLUMNS_COMPACT = [("date", "Data", 11), ("from", "De", 16), ("subject", "Assunto", None)]
    COLUMNS_NARROW = [("date", "Data", 11), ("subject", "Assunto", None)]

    def counters(self, state: EmailState) -> dict[str, int]:
        return {"total": state.total, "não lidos": state.unseen}

    def header_text(self, state: EmailState) -> Text:
        label, number = self.style("text-muted"), self.style("text", bold=True)
        text = Text(no_wrap=True, overflow="ellipsis")
        text.append("Inbox ", style=label).append(str(state.total), style=number)
        text.append("   Não lidos ", style=label).append(str(state.unseen), style=number)
        text.append("   Spam ", style=label).append("-" if state.spam is None else str(state.spam), style=number)
        if not state.recent and state.latest is None:
            text.append("   caixa vazia", style=self.style("text-faint"))
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
            body = self.style("text", bold=item.unseen)
            rows.append((item.uid, {
                "date": Text(format_email_date(item.date), style=self.style("text-muted")),
                "from": Text(item.sender, style=body),
                "subject": Text(item.subject or "(sem assunto)", style=body),
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
