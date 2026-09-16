"""Detalhe de uma conversa do ChatPanel ("ler conversa"): Enter na lista.

Abre com o indicador de carga e é preenchida quando o worker do App traz o
ConversationDetail (POST inc_chat_view.php dentro da página; medido como somente
leitura). Enquanto aberta, o App recarrega quando a conversa ganha mensagem.
`r` recarrega; `o` abre no navegador; `y` copia o número; `Esc` volta.

Mensagens: contato à esquerda em `text`, empresa à direita em `accent`, marcos
(transferências, encerramento) centrados em `text-faint`, hora em `text-faint`.
"""

from __future__ import annotations

from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Static

from app.state import ChatMessage, ConversationDetail
from app.tui.icons import UNICODE, IconSet
from app.tui.screens.detail import DetailScreen
from app.tui.themes import CARBON
from app.tui.tokens import Tokens


def header_text(number: str, item: Any, detail: ConversationDetail | None, *, tokens: Tokens = CARBON,
                icons: IconSet = UNICODE) -> Text:
    name = (detail.name if detail is not None and detail.name else getattr(item, "name", "")) or number
    muted, faint = tokens.rich("text-muted"), tokens.rich("text-faint")
    text = Text(no_wrap=True, overflow="ellipsis")
    text.append(name, style=tokens.rich("text", bold=True)).append(f"  {number}", style=faint)
    if item is not None:
        text.append("   ")
        if item.online:
            text.append(f"{icons.online} online", style=tokens.rich("text"))
        else:
            text.append(f"{icons.offline} offline", style=faint)
        if item.tag:
            text.append(f"   {item.tag}", style=muted)
        if item.department:
            text.append(f" {icons.arrow} {item.department}", style=muted)
        if item.agent:
            text.append(f"   atendente: {item.agent}", style=faint)
        if item.unread:
            text.append(f"   {item.unread} não lida(s)", style=tokens.rich("accent", bold=True))
    return text


def message_text(message: ChatMessage, *, tokens: Tokens = CARBON) -> Text:
    """Uma mensagem: autor + hora na primeira linha, corpo abaixo."""
    faint = tokens.rich("text-faint")
    if message.kind == "system":
        return Text(f"── {message.text} ──", style=faint)
    token = "accent" if message.mine else "text"
    author = "você/empresa" if message.mine and message.author == "técnico" else message.author
    text = Text()
    text.append(author, style=tokens.rich(token, bold=True))
    if message.when:
        text.append(f"  {message.when[-5:]}", style=faint)
    text.append("\n")
    text.append(message.text or "(vazio)", style=tokens.rich(token, italic=message.kind == "media"))
    return text


def messages_text(detail: ConversationDetail, *, tokens: Tokens = CARBON) -> Text:
    """Versão em texto corrido (para testes e para copiar)."""
    text = Text()
    if detail.has_more:
        text.append("… mensagens mais antigas não carregadas (abra no navegador com o)\n\n", style=tokens.rich("text-faint"))
    if not detail.messages:
        text.append("(sem mensagens)", style=tokens.rich("text-faint"))
        return text
    for index, message in enumerate(detail.messages):
        if index:
            text.append("\n\n")
        text.append_text(message_text(message, tokens=tokens))
    return text


class MessageRow(Vertical):
    """Uma mensagem alinhada à esquerda (contato), à direita (empresa) ou ao centro (marco)."""

    def __init__(self, message: ChatMessage, tokens: Tokens) -> None:
        side = "-system" if message.kind == "system" else "-mine" if message.mine else "-contact"
        super().__init__(classes=f"message-row {side}")
        self.message = message
        self._tokens = tokens

    def compose(self) -> ComposeResult:
        yield Static(message_text(self.message, tokens=self._tokens), classes="message")


class ConversationDetailScreen(DetailScreen):
    PREFIX = "conversation"
    FOOTER = [("{key_escape}", "voltar"), ("r", "recarregar"), ("o", "navegador"), ("y", "copiar número"), ("End", "fim")]
    BINDINGS = [
        Binding("escape", "dismiss", "Voltar"),
        Binding("q", "dismiss", "Voltar"),
        Binding("r", "reload", "Recarregar"),
        Binding("o", "open_browser", "Navegador"),
        Binding("y", "copy_number", "Copiar número"),
        Binding("end", "scroll_end", "Fim", show=False),
    ]

    def __init__(self, number: str, item: Any = None, detail: ConversationDetail | None = None) -> None:
        super().__init__()
        self.number = number
        self.item = item
        self.detail = detail
        self.snapshot = (getattr(item, "unread", 0), getattr(item, "last_message", ""), getattr(item, "time", ""))
        self._pending_error: str | None = None

    def body_widgets(self) -> ComposeResult:
        yield Static("", id="conversation-notice")
        yield Vertical(id="conversation-messages")

    def _header(self) -> Text:
        return header_text(self.number, self.item, self.detail, tokens=self.tokens, icons=self.icons)

    def on_mount(self) -> None:
        if self._pending_error is not None:
            self.show_error(self._pending_error)
        elif self.detail is not None:
            self.show(self.detail)
        else:
            self.set_loading()

    def _ready(self) -> bool:
        return bool(self.query("#conversation-header"))

    def refresh_content(self) -> None:
        if self.detail is not None:
            self.show(self.detail)

    def set_loading(self) -> None:
        if not self._ready():
            return
        self.query_one("#conversation-header", Static).update(self._header())
        if self.detail is None:
            self.set_busy(True)

    def show_error(self, message: str) -> None:
        if not self._ready():
            self._pending_error = message
            return
        self._pending_error = None
        self.set_busy(False)
        self.query_one("#conversation-header", Static).update(self._header())
        self.query_one("#conversation-notice", Static).update(self.error_text(message))
        self.query_one("#conversation-notice", Static).display = True

    def show(self, detail: ConversationDetail) -> None:
        self.detail = detail
        self._pending_error = None
        if not self._ready():
            return
        tokens = self.tokens
        self.set_busy(False)
        self.query_one("#conversation-header", Static).update(self._header())
        notice = self.query_one("#conversation-notice", Static)
        if detail.has_more:
            notice.update(Text("… mensagens mais antigas não carregadas (abra no navegador com o)",
                               style=tokens.rich("text-faint")))
            notice.display = True
        elif not detail.messages:
            notice.update(Text("(sem mensagens)", style=tokens.rich("text-faint")))
            notice.display = True
        else:
            notice.display = False
        self.call_later(self._fill_messages, [MessageRow(message, tokens) for message in detail.messages])

    async def _fill_messages(self, rows: list[MessageRow]) -> None:
        """Troca as mensagens e só então rola até o fim (a montagem é assíncrona)."""
        container = self.query_one("#conversation-messages", Vertical)
        await container.remove_children()
        await container.mount_all(rows)
        self.call_after_refresh(self.action_scroll_end)

    def action_scroll_end(self) -> None:
        self.query_one("#conversation-scroll", VerticalScroll).scroll_end(animate=False)

    def action_reload(self) -> None:
        self.app.open_conversation(self.number, force=True)  # type: ignore[attr-defined]

    def action_open_browser(self) -> None:
        self.app.copy_text(self.number, "número", quiet=True)  # type: ignore[attr-defined]
        self.app.open_url(self.app.settings.urls.chatpanel or None, "ChatPanel")  # type: ignore[attr-defined]

    def action_copy_number(self) -> None:
        self.app.copy_text(self.number, "número")  # type: ignore[attr-defined]
