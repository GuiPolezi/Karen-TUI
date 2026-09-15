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


def header_text(number: str, item: Any, detail: ConversationDetail | None) -> Text:
    name = (detail.name if detail is not None and detail.name else getattr(item, "name", "")) or number
    text = Text()
    text.append(name, style="bold").append(f"  {number}", style="dim")
    if item is not None:
        text.append("   ")
        text.append("● online" if item.online else "○ offline", style="green" if item.online else "dim")
        if item.tag:
            text.append(f"   [{item.tag}]", style="cyan")
        if item.department:
            text.append(f"   {item.department}", style="dim")
        if item.agent:
            text.append(f"   atendente: {item.agent}", style="dim")
        if item.unread:
            text.append(f"   {item.unread} não lida(s)", style="bold yellow")
    return text


def messages_text(detail: ConversationDetail) -> Text:
    text = Text()
    if detail.has_more:
        text.append("… mensagens mais antigas não carregadas (abra no navegador com o)\n\n", style="dim")
    if not detail.messages:
        text.append("(sem mensagens)", style="dim")
        return text
    for index, message in enumerate(detail.messages):
        if index:
            text.append("\n")
        if message.kind == "system":
            text.append(f"── {message.text} ──\n", style="dim")
            continue
        style = "green" if message.mine else "cyan"
        marker = "▐ " if message.mine else "▌ "
        author = "você/empresa" if message.mine and message.author == "técnico" else message.author
        text.append(marker, style=style).append(author, style=f"bold {style}")
        if message.when:
            text.append(f"  {message.when}", style="dim")
        text.append("\n")
        body = message.text or "(vazio)"
        for line in body.split("\n"):
            text.append("  " + line + "\n", style="italic" if message.kind == "media" else "")
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

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="conversation"):
            yield Static("", id="conversation-header")
            yield Static("", id="conversation-messages")
            yield Static(Text("[Esc] voltar  [r] recarregar  [o] abrir no navegador  [y] copiar número", style="dim"),
                         id="conversation-footer")

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
        self.query_one("#conversation-header", Static).update(header_text(self.number, self.item, self.detail))
        if self.detail is None:
            self.query_one("#conversation-messages", Static).update(Text("carregando conversa…", style="dim"))

    def show_error(self, message: str) -> None:
        if not self._ready():
            self._pending_error = message
            return
        self._pending_error = None
        self.query_one("#conversation-header", Static).update(header_text(self.number, self.item, self.detail))
        self.query_one("#conversation-messages", Static).update(Text(f"✖ {message}", style="bold red"))

    def show(self, detail: ConversationDetail) -> None:
        self.detail = detail
        self._pending_error = None
        if not self._ready():
            return
        self.query_one("#conversation-header", Static).update(header_text(self.number, self.item, detail))
        self.query_one("#conversation-messages", Static).update(messages_text(detail))
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
