"""Detalhe de uma conversa do ChatPanel ("ler conversa"): Enter na lista.

Abre com "carregando…" e é preenchida quando o worker do App traz o ConversationDetail
(POST inc_chat_view.php dentro da página; medido como somente leitura). Enquanto aberta,
o App recarrega quando a conversa ganha mensagem. `r` recarrega; `o` abre no navegador;
`y` copia o número; `Esc` volta.
"""

from __future__ import annotations

from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from app.state import ConversationDetail
from app.tui.icons import UNICODE, IconSet
from app.tui.themes import CARBON
from app.tui.tokens import Tokens


def header_text(number: str, item: Any, detail: ConversationDetail | None, *, tokens: Tokens = CARBON,
                icons: IconSet = UNICODE) -> Text:
    name = (detail.name if detail is not None and detail.name else getattr(item, "name", "")) or number
    muted, faint = tokens.rich("text-muted"), tokens.rich("text-faint")
    text = Text()
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


def messages_text(detail: ConversationDetail, *, tokens: Tokens = CARBON) -> Text:
    text = Text()
    faint = tokens.rich("text-faint")
    if detail.has_more:
        text.append("… mensagens mais antigas não carregadas (abra no navegador com o)\n\n", style=faint)
    if not detail.messages:
        text.append("(sem mensagens)", style=faint)
        return text
    for index, message in enumerate(detail.messages):
        if index:
            text.append("\n")
        if message.kind == "system":
            text.append(f"── {message.text} ──\n", style=faint)
            continue
        token = "accent" if message.mine else "text-muted"
        marker = "▐ " if message.mine else "▌ "
        author = "você/empresa" if message.mine and message.author == "técnico" else message.author
        text.append(marker, style=tokens.rich(token)).append(author, style=tokens.rich(token, bold=True))
        if message.when:
            text.append(f"  {message.when}", style=faint)
        text.append("\n")
        body = message.text or "(vazio)"
        for line in body.split("\n"):
            text.append("  " + line + "\n", style=tokens.rich("text", italic=message.kind == "media"))
    return text


class ConversationDetailScreen(ModalScreen[None]):
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

    @property
    def tokens(self) -> Tokens:
        return self.app.tokens  # type: ignore[attr-defined]

    def _header(self) -> Text:
        return header_text(self.number, self.item, self.detail, tokens=self.tokens,
                           icons=self.app.icons)  # type: ignore[attr-defined]

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="conversation"):
            yield Static("", id="conversation-header")
            yield Static("", id="conversation-messages")
            yield Static(Text("Esc voltar  r recarregar  o abrir no navegador  y copiar número",
                              style=self.tokens.rich("text-faint")), id="conversation-footer")

    def on_mount(self) -> None:
        if self._pending_error is not None:
            self.show_error(self._pending_error)
        elif self.detail is not None:
            self.show(self.detail)
        else:
            self.set_loading()

    def _ready(self) -> bool:
        return bool(self.query("#conversation-header"))

    def set_loading(self) -> None:
        if not self._ready():
            return
        self.query_one("#conversation-header", Static).update(self._header())
        if self.detail is None:
            self.query_one("#conversation-messages", Static).update(
                Text("carregando conversa…", style=self.tokens.rich("text-muted")))

    def show_error(self, message: str) -> None:
        if not self._ready():
            self._pending_error = message
            return
        self._pending_error = None
        icons = self.app.icons  # type: ignore[attr-defined]
        self.query_one("#conversation-header", Static).update(self._header())
        self.query_one("#conversation-messages", Static).update(
            Text(f"{icons.error} {message}", style=self.tokens.rich("danger", bold=True)))

    def show(self, detail: ConversationDetail) -> None:
        self.detail = detail
        self._pending_error = None
        if not self._ready():
            return
        self.query_one("#conversation-header", Static).update(self._header())
        self.query_one("#conversation-messages", Static).update(messages_text(detail, tokens=self.tokens))
        self.call_after_refresh(self.action_scroll_end)

    def action_scroll_end(self) -> None:
        self.query_one("#conversation", VerticalScroll).scroll_end(animate=False)

    def action_reload(self) -> None:
        self.app.open_conversation(self.number, force=True)  # type: ignore[attr-defined]

    def action_open_browser(self) -> None:
        self.app.copy_text(self.number, "número", quiet=True)  # type: ignore[attr-defined]
        self.app.open_url(self.app.settings.urls.chatpanel or None, "ChatPanel")  # type: ignore[attr-defined]

    def action_copy_number(self) -> None:
        self.app.copy_text(self.number, "número")  # type: ignore[attr-defined]
