"""Parser do ChatPanel contra o HTML real e casos sintéticos; fonte com página falsa."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import ChatPanelSettings
from app.sources.chatpanel import (
    SESSION_EXPIRED,
    ChatPanelSource,
    SessionExpiredError,
    parse_chatpanel_html,
)

FIXTURE = Path(__file__).parent / "fixtures" / "chatpanel_chat.html"
HTML = FIXTURE.read_text(encoding="utf-8", errors="replace")


# --- fixture real ----------------------------------------------------------------


def test_fixture_sino_admin_has_two_chats():
    state = parse_chatpanel_html(HTML, "SINO Admin")
    assert [c.number for c in state.mine] == ["5511984568840", "5514988010122"]
    assert state.mine_unread == 1
    assert state.logged_user == "Guilherme"
    assert state.total_unread_tab == 1
    assert state.others_count == 1  # a conversa do Fabio
    assert state.error is None

    celso, diego = state.mine
    assert celso.name == "Celso - CM Itu"
    assert celso.time == "15:28"
    assert celso.last_message == "Só um momento"
    assert celso.unread == 1
    assert celso.tag == "Câmara"
    assert celso.department == "Suporte"
    assert celso.agent == "SINO Admin"
    assert celso.online is True

    assert diego.name == "Diego Leone - PM Iaras"
    assert diego.unread == 0
    assert diego.tag == "Prefeitura"
    assert diego.last_message.startswith("• Porta 21 (FTP) • Porta 3306")  # quebras colapsadas


def test_fixture_fabio_has_one_chat_with_prefixed_message():
    state = parse_chatpanel_html(HTML, "fabio")  # comparação sem acento/caixa
    assert [c.number for c in state.mine] == ["5516997484965"]
    assert state.mine[0].name == "Hércules - CM Tatui TI"
    assert state.mine[0].last_message.startswith("*Fabio:* Hércules")
    assert state.others_count == 2


def test_fixture_guilherme_has_no_chats():
    state = parse_chatpanel_html(HTML, "Guilherme")
    assert state.mine == []
    assert state.mine_unread == 0
    assert state.others_count == 3
    assert state.logged_user == "Guilherme"


# --- casos sintéticos --------------------------------------------------------------


def li(number: str, name: str, agent: str | None = None, unread: int = 0, extra_class: str = "") -> str:
    person = f'<span class="badge bg-success-transparent"><i class="bi bi-person"></i> {agent}</span>' if agent else ""
    badge = f'<span class="badge unread-count2" id="unreadchat_{number}">{unread}</span>' if unread else ""
    return f"""
    <li class="checkforactive {extra_class}" id="chat_{number}">
      <a onclick="x">
        <span class="avatar avatar-md me-2"><img src="p.png"></span>
        <p class="mb-0 fw-medium">{name} <span class="float-end text-muted fw-normal fs-11">10:00</span></p>
        <p class="fs-12 mb-0"><span class="chat-msg text-truncate">oi</span>{badge}</p>
        <p class="mb-0"><span class="badge"><i class="bi bi-tag"></i> Tag</span>{person}</p>
      </a>
    </li>"""


def page(mine_box: str = "", others_box: str = "", user: str | None = "Guilherme", total: str = "0") -> str:
    user_input = f'<input type="hidden" id="int_username" value="{user}">' if user is not None else ""
    return f"""<html><body>{user_input}
    <div id="atende-tab-pane">
      <span id="total-unread2" class="badge">{total}</span>
      <ul id="box-atende-chats"><li class="pb-0">SUAS CONVERSAS</li>{mine_box}</ul>
      <ul id="box-atendeothers-chats"><li class="pb-0">EM ATENDIMENTO</li>{others_box}</ul>
    </div></body></html>"""


def test_items_in_own_box_count_as_mine_even_without_badge():
    html = page(mine_box=li("551", "Alguém", agent=None, unread=2))
    state = parse_chatpanel_html(html, "Guilherme")
    assert [c.number for c in state.mine] == ["551"]
    assert state.mine_unread == 2
    assert state.mine[0].agent is None
    assert state.mine[0].online is False


def test_dedupes_same_number_across_boxes_and_ignores_headers_and_inactive():
    html = page(
        mine_box=li("551", "Dup", agent="Guilherme"),
        others_box=li("551", "Dup", agent="Guilherme") + li("552", "Outro", agent="Fabio")
        + li("553", "Encerrada", agent="Guilherme", extra_class="chat-inactive"),
        total="7",
    )
    state = parse_chatpanel_html(html, "Guilherme")
    assert [c.number for c in state.mine] == ["551"]
    assert state.others_count == 1
    assert state.total_unread_tab == 7


def test_missing_username_means_logged_out():
    state = parse_chatpanel_html(page(user=None), "Guilherme")
    assert state.logged_user is None
    assert state.mine == []


# --- fonte com navegador falso -------------------------------------------------------


class FakeSource(ChatPanelSource):
    def __init__(self, htmls: list[str]):
        super().__init__(
            ChatPanelSettings(url="https://x/chat.php", profile_dir=Path(".p"), refresh_seconds=15, headless=True),
            "Guilherme",
        )
        self.htmls = htmls
        self.calls: list[bool] = []
        self.torn_down = False

    async def _get_html(self, reload: bool = False) -> str:
        self.calls.append(reload)
        return self.htmls.pop(0)

    async def _teardown(self) -> None:
        self.torn_down = True


async def test_source_parses_page_without_reload():
    source = FakeSource([page(others_box=li("551", "X", agent="Guilherme"))])
    state = await source.fetch()
    assert len(state.mine) == 1
    assert source.calls == [False]


async def test_source_reloads_once_then_reports_expired_session():
    source = FakeSource([page(user=None), page(user=None)])
    with pytest.raises(SessionExpiredError, match="sessão expirada"):
        await source.fetch()
    assert source.calls == [False, True]
    assert source.torn_down is True
    assert SESSION_EXPIRED.startswith("sessão expirada")


async def test_source_recovers_after_reload():
    source = FakeSource([page(user=None), page(others_box=li("551", "X", agent="Guilherme"))])
    state = await source.fetch()
    assert len(state.mine) == 1
    assert source.calls == [False, True]
    assert source.torn_down is False


def test_always_configured_even_without_profile_dir(tmp_path: Path):
    """Sem perfil o 1º ciclo cai em "sessão expirada" e a TUI abre o login, que cria o perfil."""
    settings = ChatPanelSettings(url="https://x", profile_dir=tmp_path / "nao-existe", refresh_seconds=15, headless=True)
    assert ChatPanelSource(settings, "G").configured is True
    assert settings.prefill_login is False
    assert settings.login_on_start is True


def test_prefill_login_requires_user_and_password(tmp_path: Path):
    base = dict(url="https://x", profile_dir=tmp_path, refresh_seconds=15, headless=True)
    assert ChatPanelSettings(**base, user="g", password="").prefill_login is False
    assert ChatPanelSettings(**base, user="g", password="s").prefill_login is True


# --- ressincronização das listas ----------------------------------------------------


def test_resync_due_respects_interval_and_zero_disables():
    from app.sources.chatpanel import resync_due

    assert resync_due(None, 100.0, 60) is True
    assert resync_due(100.0, 159.9, 60) is False
    assert resync_due(100.0, 160.0, 60) is True
    assert resync_due(None, 100.0, 0) is False  # desligado


class FakePage:
    """Página falsa: evaluate() simula o RESYNC_JS trocando o HTML das listas."""

    def __init__(self, html_before: str, html_after: str, fail: bool = False):
        self.html = html_before
        self.html_after = html_after
        self.fail = fail
        self.evaluations = 0

    def is_closed(self) -> bool:
        return False

    async def evaluate(self, script: str):
        self.evaluations += 1
        assert "control-atende-on-us.php" in script and "control-atende-on-ot.php" in script
        if self.fail:
            raise RuntimeError("Execution context was destroyed")
        self.html = self.html_after
        return {"ok": 2, "failed": 0}

    async def content(self) -> str:
        return self.html


class ResyncSource(ChatPanelSource):
    def __init__(self, fake_page: FakePage, resync_seconds: int = 60):
        super().__init__(
            ChatPanelSettings(url="https://x/chat.php", profile_dir=Path(".p"), refresh_seconds=15,
                              headless=True, resync_seconds=resync_seconds),
            "Guilherme",
        )
        self.fake_page = fake_page

    async def _ensure_page(self):
        return self.fake_page


async def test_resync_replaces_stale_list_after_interval():
    stale = page(mine_box=li("551", "Transferida", agent="Guilherme"))
    fresh = page(others_box=li("551", "Transferida", agent="Fulano"))
    fake = FakePage(stale, fresh)
    source = ResyncSource(fake, resync_seconds=60)

    source._last_resync = 1000.0
    assert source._resync_due(now=1030.0) is False

    source._last_resync = None  # nunca ressincronizou: faz na primeira leitura
    state = await source.fetch()
    assert fake.evaluations == 1
    assert state.mine == []  # a conversa transferida saiu do meu nome
    assert state.others_count == 1
    assert source._last_resync is not None


async def test_resync_is_skipped_when_disabled_or_not_due():
    stale = page(mine_box=li("551", "X", agent="Guilherme"))
    fake = FakePage(stale, page())
    source = ResyncSource(fake, resync_seconds=0)
    state = await source.fetch()
    assert fake.evaluations == 0
    assert len(state.mine) == 1


async def test_resync_failure_keeps_reading_current_dom(caplog):
    stale = page(mine_box=li("551", "X", agent="Guilherme"))
    fake = FakePage(stale, page(), fail=True)
    source = ResyncSource(fake, resync_seconds=60)
    state = await source.fetch()
    assert fake.evaluations == 1
    assert len(state.mine) == 1  # falha na ressincronização não derruba a leitura
    assert any("ressincronização" in r.getMessage() for r in caplog.records)


def test_login_failure_messages_are_short():
    from app.sources.chatpanel import _describe_login_failure

    class TimeoutError_(Exception):
        pass

    class TargetClosedError(Exception):
        pass

    assert _describe_login_failure(TimeoutError_("x"), 300) == "tempo esgotado (300s) sem completar o login"
    assert "fechada" in _describe_login_failure(TargetClosedError("Target page, context or browser has been closed"), 300)
    assert _describe_login_failure(RuntimeError("boom\nmais"), 300) == "login não concluído: boom"
