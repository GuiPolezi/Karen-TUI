"""Testes da fonte de e-mail sem rede: funções puras, coleta com mailbox falso e conexão."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from app.config import EmailSettings
from app.sources import email_imap
from app.sources.email_imap import (
    EmailSource,
    collect_state,
    html_to_text,
    make_preview,
    message_to_latest,
)


def settings(**overrides) -> EmailSettings:
    base = dict(
        host="imap.example.com", port=143, starttls=True, user="suporte@example.com",
        password="segredo", inbox_folder="INBOX", spam_folder="Junk E-Mail", refresh_seconds=30,
    )
    base.update(overrides)
    return EmailSettings(**base)


# --- funções puras -----------------------------------------------------------


def test_html_to_text_strips_tags_scripts_and_collapses_spaces():
    html = "<html><head><style>p{}</style></head><body><p>Bom   dia,</p><script>x()</script><div>ao\n\ngerar</div></body></html>"
    assert html_to_text(html) == "Bom dia, ao gerar"


def test_make_preview_truncates_with_ellipsis():
    assert make_preview("a b  c\n d") == "a b c d"
    long = "x" * 500
    preview = make_preview(long)
    assert len(preview) == 300
    assert preview.endswith("…")


@dataclass
class Address:
    name: str
    email: str


@dataclass
class FakeMessage:
    uid: str = "10"
    from_: str = "Fulano <fulano@cm.sp.gov.br>"
    from_values: Address | None = field(default_factory=lambda: Address("Fulano", "fulano@cm.sp.gov.br"))
    subject: str = "Erro ao gerar relatório"
    date: datetime | None = datetime(2026, 9, 14, 18, 28, tzinfo=timezone.utc)
    text: str = "Bom dia,\n\nao tentar gerar o relatório aparece erro."
    html: str = ""


def test_message_to_latest_prefers_plain_text_and_converts_date_to_local():
    latest = message_to_latest(FakeMessage())
    assert latest.from_name == "Fulano"
    assert latest.from_addr == "fulano@cm.sp.gov.br"
    assert latest.subject == "Erro ao gerar relatório"
    assert latest.preview == "Bom dia, ao tentar gerar o relatório aparece erro."
    assert latest.body.startswith("Bom dia,\n\nao tentar")
    assert latest.date is not None and latest.date.tzinfo is None
    expected_local = datetime(2026, 9, 14, 18, 28, tzinfo=timezone.utc).astimezone().replace(tzinfo=None)
    assert latest.date == expected_local


def test_message_to_latest_falls_back_to_html_and_placeholders():
    msg = FakeMessage(from_values=None, subject="  ", text="", html="<p>Olá <b>mundo</b></p>")
    latest = message_to_latest(msg)
    assert latest.subject == "(sem assunto)"
    assert latest.from_name == ""
    assert latest.from_addr == "Fulano <fulano@cm.sp.gov.br>"
    assert latest.preview == "Olá mundo"


# --- coleta com mailbox falso ----------------------------------------------------


class FakeFolderManager:
    def __init__(self, mailbox, spam_count: int | None):
        self.mailbox = mailbox
        self.spam_count = spam_count
        self.selected: tuple[str, bool] | None = None

    def set(self, folder, readonly=False):
        self.selected = (folder, readonly)
        return ("OK", [])

    def status(self, folder=None, options=None):
        if self.spam_count is None:
            raise RuntimeError("NO folder not found")
        return {"MESSAGES": self.spam_count}


class FakeMailBox:
    def __init__(self, uids: list[str], unseen: list[str], spam_count: int | None = 3):
        self._uids = uids
        self._unseen = unseen
        self.folder = FakeFolderManager(self, spam_count)
        self.fetch_calls: list[dict] = []
        self.logged_out = False

    def uids(self, criteria="ALL", charset="US-ASCII", sort=None):
        return list(self._unseen if criteria == "UNSEEN" else self._uids)

    def fetch(self, criteria="ALL", charset="US-ASCII", **kwargs):
        self.fetch_calls.append(kwargs)
        yield FakeMessage(uid=kwargs["uid_list"][0])

    def logout(self):
        self.logged_out = True


def test_collect_state_uses_readonly_folder_and_newest_uid():
    mailbox = FakeMailBox(uids=["3", "10", "9"], unseen=["9", "10"])
    state = collect_state(mailbox, settings(), logging.getLogger("t"))
    assert mailbox.folder.selected == ("INBOX", True)
    assert state.total == 3
    assert state.unseen == 2
    assert state.spam == 3
    assert state.latest is not None and state.latest.subject == "Erro ao gerar relatório"
    assert mailbox.fetch_calls == [{"uid_list": ["10"], "mark_seen": False}]
    assert state.error is None


def test_collect_state_empty_inbox_and_missing_spam_folder():
    mailbox = FakeMailBox(uids=[], unseen=[], spam_count=None)
    state = collect_state(mailbox, settings(), logging.getLogger("t"))
    assert state.total == 0 and state.unseen == 0
    assert state.latest is None
    assert state.spam is None
    assert mailbox.fetch_calls == []


# --- conexão -----------------------------------------------------------------------


def test_plain_port_without_starttls_is_refused():
    source = EmailSource(settings(starttls=False, port=143))
    with pytest.raises(RuntimeError, match="texto puro"):
        source._connect()


def test_starttls_failure_falls_back_to_ssl_993(monkeypatch):
    calls: list[tuple[str, int]] = []

    class FakeSslBox:
        def __init__(self, host, port, timeout=None):
            calls.append(("ssl", port))
            self.login_args = None

        def login(self, user, password, initial_folder="INBOX"):
            self.login_args = (user, password, initial_folder)
            return self

    def failing_starttls(host, port, timeout=None):
        calls.append(("starttls", port))
        raise email_imap.MailboxStarttlsError(("NO", [b"not supported"]), "OK")

    monkeypatch.setattr(email_imap, "MailBoxStartTls", failing_starttls)
    monkeypatch.setattr(email_imap, "MailBox", FakeSslBox)

    source = EmailSource(settings())
    box = source._connect()
    assert calls == [("starttls", 143), ("ssl", 993)]
    assert box.login_args == ("suporte@example.com", "segredo", None)
    assert source._ssl_fallback is True

    # na reconexão seguinte vai direto para SSL, sem tentar STARTTLS de novo
    source._connect()
    assert calls[-1] == ("ssl", 993)
    assert calls.count(("starttls", 143)) == 1


async def test_fetch_drops_connection_on_failure_and_reconnects():
    source = EmailSource(settings())
    boxes: list[FakeMailBox] = []

    def connect():
        box = FakeMailBox(uids=["1"], unseen=[])
        box.client = type("C", (), {"noop": staticmethod(lambda: None)})()
        boxes.append(box)
        return box

    source._connect = connect  # type: ignore[method-assign]

    state = await source.fetch()
    assert state.total == 1 and len(boxes) == 1

    # segunda coleta reaproveita a conexão
    await source.fetch()
    assert len(boxes) == 1

    # falha na coleta derruba a conexão; a próxima reconecta
    boxes[0].uids = lambda *a, **k: (_ for _ in ()).throw(OSError("connection reset"))
    with pytest.raises(OSError):
        await source.fetch()
    assert boxes[0].logged_out is True
    await source.fetch()
    assert len(boxes) == 2

    await source.close()
    assert boxes[1].logged_out is True
