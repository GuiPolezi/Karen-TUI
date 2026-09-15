"""Fonte 1: caixa de e-mail via IMAP (somente leitura).

- Conexão persistente entre ciclos; reconecta sozinha se cair.
- STARTTLS na porta 143 quando EMAIL_IMAP_STARTTLS=true; se o servidor recusar,
  cai para SSL direto na 993 e registra o aviso. Nunca envia senha em texto puro.
- Pasta selecionada em modo readonly: nada é marcado como lido.
- Contagens via SEARCH (ALL / UNSEEN) na pasta selecionada e STATUS na pasta de spam.

Modo debug: `python -m app.sources.email_imap` imprime o EmailState em JSON.
"""

from __future__ import annotations

import asyncio
import logging
import re
import ssl
import sys
from datetime import datetime
from typing import Any, Protocol

from bs4 import BeautifulSoup
from imap_tools import MailBox, MailBoxStartTls, MailboxStarttlsError

from app.config import EmailSettings
from app.sources.base import Source
from app.state import EmailState, EmailSummary, LatestEmail

PREVIEW_MAX_CHARS = 300
SSL_PORT = 993


class _AddressLike(Protocol):
    name: str
    email: str


class _MessageLike(Protocol):
    """Subconjunto de imap_tools.MailMessage que usamos (facilita testes com stubs)."""

    from_: str
    from_values: _AddressLike | None
    subject: str
    date: datetime | None
    text: str
    html: str


# --- funções puras (testáveis sem rede) ---------------------------------------


def collapse_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def html_to_text(html: str) -> str:
    """Remove tags, scripts e estilos; devolve texto com espaços colapsados."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "head", "title"]):
        tag.decompose()
    return collapse_whitespace(soup.get_text(" "))


def make_preview(text: str, max_chars: int = PREVIEW_MAX_CHARS) -> str:
    flat = collapse_whitespace(text)
    if len(flat) <= max_chars:
        return flat
    return flat[: max_chars - 1].rstrip() + "…"


def to_local(date: datetime | None) -> datetime | None:
    """Converte para o fuso local; datas sem fuso são mantidas como estão."""
    if date is None:
        return None
    if date.tzinfo is None:
        return date
    return date.astimezone().replace(tzinfo=None)


def message_to_latest(msg: _MessageLike) -> LatestEmail:
    address = msg.from_values
    from_name = (address.name if address else "").strip()
    from_addr = (address.email if address else msg.from_ or "").strip()
    body = (msg.text or "").strip()
    if not body:
        body = html_to_text(msg.html or "")
    return LatestEmail(
        from_name=from_name,
        from_addr=from_addr,
        subject=(msg.subject or "").strip() or "(sem assunto)",
        date=to_local(msg.date),
        preview=make_preview(body),
        body=body,
    )


def summary_from_message(msg: Any, unseen_uids: set[str]) -> EmailSummary:
    address = msg.from_values
    uid = str(getattr(msg, "uid", "") or "")
    return EmailSummary(
        uid=uid,
        from_name=(address.name if address else "").strip(),
        from_addr=(address.email if address else msg.from_ or "").strip(),
        subject=(msg.subject or "").strip() or "(sem assunto)",
        date=to_local(msg.date),
        unseen=uid in unseen_uids,
    )


def collect_state(mailbox: Any, settings: EmailSettings, log: logging.Logger) -> EmailState:
    """Lê contagens, os últimos N cabeçalhos e o e-mail mais recente (com corpo)."""
    mailbox.folder.set(settings.inbox_folder, readonly=True)
    all_uids: list[str] = mailbox.uids("ALL")
    unseen_uids: list[str] = mailbox.uids("UNSEEN")
    unseen_set = set(unseen_uids)

    latest: LatestEmail | None = None
    recent: list[EmailSummary] = []
    if all_uids:
        newest_first = sorted(all_uids, key=int, reverse=True)
        newest_uid = newest_first[0]
        messages = mailbox.fetch(uid_list=[newest_uid], mark_seen=False)
        msg = next(iter(messages), None)
        if msg is not None:
            latest = message_to_latest(msg)
        window = newest_first[: settings.list_size]
        headers = mailbox.fetch(uid_list=window, headers_only=True, mark_seen=False)
        recent = sorted(
            (summary_from_message(m, unseen_set) for m in headers),
            key=lambda item: int(item.uid or 0), reverse=True,
        )

    spam: int | None = None
    if settings.spam_folder:
        try:
            spam = int(mailbox.folder.status(settings.spam_folder, ["MESSAGES"])["MESSAGES"])
        except Exception as exc:  # pasta inexistente ou sem permissão: opcional
            log.info("pasta de spam %r indisponível: %s", settings.spam_folder, exc)

    return EmailState(
        total=len(all_uids),
        unseen=len(unseen_uids),
        spam=spam,
        latest=latest,
        recent=recent,
        updated_at=datetime.now(),
        error=None,
    )


def fetch_message(mailbox: Any, settings: EmailSettings, uid: str) -> LatestEmail | None:
    """Um e-mail completo por UID, em modo somente leitura (não marca como lido)."""
    mailbox.folder.set(settings.inbox_folder, readonly=True)
    messages = mailbox.fetch(uid_list=[uid], mark_seen=False)
    msg = next(iter(messages), None)
    return message_to_latest(msg) if msg is not None else None


# --- fonte -----------------------------------------------------------------------


class EmailSource(Source[EmailState]):
    name = "email"
    label = "e-mail"
    config_hint = "preencha EMAIL_APP_PASSWORD no .env"

    def __init__(self, settings: EmailSettings) -> None:
        super().__init__(interval=settings.refresh_seconds, timeout=20.0)
        self.settings = settings
        self._mailbox: Any = None
        self._ssl_fallback = False  # fica True após STARTTLS falhar e SSL/993 funcionar
        self._bodies: dict[str, LatestEmail] = {}  # cache de corpos por UID (tecla Enter)

    @property
    def configured(self) -> bool:
        return self.settings.configured

    async def fetch(self) -> EmailState:
        # imap-tools é síncrono: roda em thread para não travar a TUI
        return await asyncio.to_thread(self._fetch_sync)

    async def fetch_body(self, uid: str) -> LatestEmail | None:
        """Corpo completo de um e-mail da lista (tecla Enter). Cache por UID."""
        cached = self._bodies.get(uid)
        if cached is not None:
            return cached
        detail = await asyncio.to_thread(self._fetch_body_sync, uid)
        if detail is not None:
            self._bodies[uid] = detail
            if len(self._bodies) > 50:
                self._bodies.pop(next(iter(self._bodies)))
        return detail

    def _fetch_body_sync(self, uid: str) -> LatestEmail | None:
        try:
            return fetch_message(self._ensure_connected(), self.settings, uid)
        except Exception:
            self._drop_connection()
            raise

    async def close(self) -> None:
        await asyncio.to_thread(self._drop_connection)

    # --- síncrono ----------------------------------------------------------------

    def _fetch_sync(self) -> EmailState:
        try:
            mailbox = self._ensure_connected()
            return collect_state(mailbox, self.settings, self.log)
        except Exception:
            # qualquer falha derruba a conexão; a próxima tentativa reconecta
            self._drop_connection()
            raise

    def _ensure_connected(self) -> Any:
        if self._mailbox is not None:
            try:
                self._mailbox.client.noop()
                return self._mailbox
            except Exception as exc:
                self.log.info("conexão IMAP caiu (%s); reconectando", exc)
                self._drop_connection()
        self._mailbox = self._connect()
        return self._mailbox

    def _drop_connection(self) -> None:
        mailbox, self._mailbox = self._mailbox, None
        if mailbox is None:
            return
        try:
            mailbox.logout()
        except Exception:
            pass

    def _connect(self) -> Any:
        s = self.settings
        if s.starttls and not self._ssl_fallback:
            try:
                mailbox = MailBoxStartTls(s.host, s.port, timeout=self.timeout)
            except (MailboxStarttlsError, ssl.SSLError, OSError) as exc:
                self.log.warning(
                    "STARTTLS em %s:%s falhou (%s); tentando SSL direto na porta %s",
                    s.host, s.port, exc, SSL_PORT,
                )
                mailbox = MailBox(s.host, SSL_PORT, timeout=self.timeout)
                self._ssl_fallback = True
        elif s.starttls:
            mailbox = MailBox(s.host, SSL_PORT, timeout=self.timeout)
        else:
            if s.port != SSL_PORT:
                raise RuntimeError(
                    f"porta {s.port} sem STARTTLS enviaria a senha em texto puro; "
                    "use EMAIL_IMAP_STARTTLS=true ou EMAIL_IMAP_PORT=993"
                )
            mailbox = MailBox(s.host, s.port, timeout=self.timeout)

        self.log.info("conectando como %s em %s", s.user, s.host)
        mailbox.login(s.user, s.password, initial_folder=None)
        return mailbox


# --- modo debug --------------------------------------------------------------------


async def _debug_main() -> int:
    from app.config import ConfigError, load_settings
    from app.logging_setup import setup_debug_logging
    from app.main import force_utf8_console
    from app.state import to_json

    force_utf8_console()
    setup_debug_logging()
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 2
    source = EmailSource(settings.email)
    if not source.configured:
        print(source.config_hint, file=sys.stderr)
        return 2
    try:
        state = await source.fetch_with_retry()
    finally:
        await source.close()
    print(to_json(state))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_debug_main()))
