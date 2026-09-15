"""Fase 6.3: parser da conversa (fixture real anonimizada) e a tela de detalhe."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.sources.chatpanel import parse_conversation_html
from app.state import ChatItem, ChatPanelState, ConversationDetail
from app.tui.screens import ConversationDetailScreen
from tests.helpers import make_app, screen_text, wait_until
from tests.test_tui_lists import FakeChatSource as BaseFakeChatSource

FIXTURE = (Path(__file__).parent / "fixtures" / "chatpanel_conversation.html").read_text(encoding="utf-8")


def test_parse_conversation_fixture():
    detail = parse_conversation_html(FIXTURE, number="5519900000000")
    assert detail.number == "5519900000000"
    assert detail.has_more is True  # li#but-seemore
    kinds = [m.kind for m in detail.messages]
    assert kinds.count("system") == 2
    contact = [m for m in detail.messages if m.kind != "system" and not m.mine]
    mine = [m for m in detail.messages if m.mine]
    assert len(contact) == 5 and len(mine) == 4
    assert contact[0].author == "Contato Teste - CM Exemplo"
    assert contact[0].text == "Mensagem 1 do contato (anonimizada)."
    assert contact[0].when.startswith("03/09/2026 ")
    assert mine[0].author == "técnico"
    assert mine[1].text == "Resposta 2 do técnico (anonimizada).\nSegunda linha da resposta."
    system = [m for m in detail.messages if m.kind == "system"]
    assert all("transferida" in m.text.lower() for m in system)
    assert detail.messages[0].kind == "text" and not detail.messages[0].mine


def test_parse_conversation_media_and_empty():
    html = '''<div id="main-chat-content"><ul>
      <li class="chat-item-start"><div class="main-chat-msg"><div><img src="a.jpg"><p class="mb-0">olha</p></div></div>
        <span class="chatting-user-info"><span class="chatnameperson">Ana</span><span class="msg-sent-time">15/09/2026 10:00</span></span></li>
      <li class="chat-item-end"><div class="main-chat-msg"><div><a href="/files/doc.pdf">doc.pdf</a></div></div>
        <span class="msg-sent-time">15/09/2026 10:01</span></li>
    </ul></div>'''
    detail = parse_conversation_html(html, number="1", contact_name="Ana - CM")
    assert [m.kind for m in detail.messages] == ["media", "media"]
    assert detail.messages[0].text == "[imagem]\nolha"
    assert detail.messages[1].text == "[arquivo: doc.pdf]"
    assert detail.has_more is False
    empty = parse_conversation_html("<div id='main-chat-content'><ul></ul></div>", number="2")
    assert empty.messages == []


class FakeChatSource(BaseFakeChatSource):
    def __init__(self, fail: bool = False):
        super().__init__()
        self.fail = fail
        self.conversation_calls: list[str] = []
        self.unread = 2

    async def fetch(self) -> ChatPanelState:
        state = await super().fetch()
        state.mine[0].unread = self.unread
        return state

    async def fetch_conversation(self, number: str, contact_name: str = "") -> ConversationDetail:
        self.conversation_calls.append(number)
        if self.fail:
            raise RuntimeError("inc_chat_view.php: HTTP 500")
        return parse_conversation_html(FIXTURE, number=number, contact_name=contact_name)


async def test_enter_opens_conversation_and_state_change_reloads():
    source = FakeChatSource()
    app = make_app(sources={"chatpanel": source})
    async with app.run_test(size=(120, 36)) as pilot:
        await wait_until(lambda: "chatpanel" in app.states)
        await pilot.press("f4")
        await pilot.pause()
        await pilot.press("enter")
        await wait_until(lambda: source.conversation_calls == ["551"])
        await pilot.pause()
        assert isinstance(app.screen, ConversationDetailScreen)
        from textual.widgets import Static

        header = str(app.screen.query_one("#conversation-header", Static).content)
        assert "Ana - CM Itu" in header and "551" in header and "não lida(s)" in header
        text = screen_text(app, 120, 36)  # a tela rola até o fim: últimas mensagens visíveis
        assert "Resposta 4 do técnico" in text and "Conversa transferida 14:48" in text
        assert len(app.screen.detail.messages) == 11

        # mensagem nova na conversa aberta (não lidas mudam no estado) → recarrega sozinha
        source.unread = 3
        app.action_refresh("chatpanel")  # próximo ciclo da coleta (o "3" não atravessa um modal)
        await wait_until(lambda: len(source.conversation_calls) == 2)
        await pilot.press("r")
        await wait_until(lambda: len(source.conversation_calls) == 3)
        await pilot.press("y")
        assert "551" in app.last_message
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, ConversationDetailScreen)
        assert app.current_mode == "chatpanel"


async def test_conversation_error_is_shown_without_crashing():
    source = FakeChatSource(fail=True)
    app = make_app(sources={"chatpanel": source})
    async with app.run_test(size=(120, 36)) as pilot:
        await wait_until(lambda: "chatpanel" in app.states)
        await pilot.press("f4")
        await pilot.pause()
        await pilot.press("enter")
        await wait_until(lambda: source.conversation_calls == ["551"])
        await pilot.pause()
        assert "HTTP 500" in screen_text(app, 120, 36)
        await pilot.press("escape")
        await pilot.pause()
        assert app.current_mode == "chatpanel"
