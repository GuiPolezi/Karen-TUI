"""Painel de e-mail (IMAP): contadores + cartão do mais recente + lista com cursor."""

from __future__ import annotations

from datetime import datetime, timedelta

from rich.text import Text

from app import clock
from app.state import EmailState, EmailSummary, LatestEmail
from app.tui.widgets.base_panel import BasePanel, padded


def format_email_date(date: datetime | None, now: datetime | None = None) -> str:
    """Hoje: 'HH:MM'; ontem: 'ontem'; antes: 'dd/mm'."""
    if date is None:
        return "--:--"
    today = (now or clock.now()).date()
    if date.date() == today:
        return date.strftime("%H:%M")
    if date.date() == today - timedelta(days=1):
        return "ontem"
    return date.strftime("%d/%m")


def summary_from_latest(latest: LatestEmail) -> EmailSummary:
    """Fallback quando a fonte só trouxe o e-mail mais recente (sem lista)."""
    return EmailSummary(uid="latest", from_name=latest.from_name, from_addr=latest.from_addr,
                        subject=latest.subject, date=latest.date, unseen=False)


class EmailPanel(BasePanel):
    SOURCE = "email"
    ICON = "email"
    TITLE = "E-MAIL"
    MORE_KEY = "F2"
    SUMMARY = [("total", "inbox"), ("não lidos", "não lido|não lidos"), ("spam", "spam")]
    COLUMNS = [("date", "Data", 6), ("from", "De", 28), ("subject", "Assunto", None)]
    COLUMNS_COMPACT = [("date", "Data", 6), ("from", "De", 18), ("subject", "Assunto", None)]
    COLUMNS_NARROW = [("date", "Data", 6), ("subject", "Assunto", None)]

    def counters(self, state: EmailState) -> dict[str, int]:
        return {"total": state.total, "não lidos": state.unseen}

    def summary_values(self, state: EmailState) -> dict[str, tuple[str, str]]:
        return {
            "total": (str(state.total), "text"),
            "não lidos": (str(state.unseen), "text" if state.unseen else "text-faint"),
            "spam": ("–" if state.spam is None else str(state.spam), "text" if state.spam else "text-faint"),
        }

    def empty_text(self) -> str:
        return "caixa vazia"

    # --- cartão do mais recente (só no Dashboard) ---------------------------------------

    def card_item(self, state: EmailState) -> EmailSummary | None:
        if self.full:
            return None
        items = self.summaries(state)
        return items[0] if items else None

    def extra_text(self, state: EmailState) -> Text | None:
        item = self.card_item(state)
        if item is None:
            return None
        tokens, icons = self.tokens, self.icons
        marked = item.uid in self._marked
        head = Text()
        head.append(icons.change if marked else " ", style=tokens.rich("accent", bold=True))
        sender = item.from_name or item.from_addr
        head.append(sender, style=tokens.rich("text", bold=item.unseen))
        if item.from_name and item.from_addr:
            head.append(f" <{item.from_addr}>", style=tokens.rich("text-muted"))
        when = Text(format_email_date(item.date), style=tokens.rich("text-muted"))
        card = padded(head, when, self.content_width)
        card.append("\n ").append(item.subject or "(sem assunto)", style=tokens.rich("text", bold=True))
        preview = ""
        if state.latest is not None and state.latest.subject == item.subject:
            preview = " ".join((state.latest.preview or state.latest.body or "").split())
        if preview:
            card.append("\n ").append(preview, style=tokens.rich("text-muted"))
        card.no_wrap = True
        card.overflow = "ellipsis"
        return card

    # --- lista ------------------------------------------------------------------------

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
        items = self.summaries(state)
        if self.card_item(state) is not None:
            items = items[1:]  # o mais recente está no cartão
        rows = []
        for item in items:
            body = self.style("text", bold=item.unseen)
            rows.append((item.uid, {
                "date": Text(format_email_date(item.date), style=self.style("text-muted")),
                "from": Text(item.sender, style=body),
                "subject": Text(item.subject or "(sem assunto)", style=body),
            }))
        return rows

    def changed_keys(self, previous: EmailState, state: EmailState) -> set[str]:
        old = {item.uid for item in self.summaries(previous)}
        return {item.uid for item in self.summaries(state) if item.uid not in old}

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
