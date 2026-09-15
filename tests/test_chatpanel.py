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


# --- ressincronização / páginas extras ---------------------------------------------


def test_resync_due_respects_interval_and_zero_disables():
    from app.sources.chatpanel import resync_due

    assert resync_due(None, 100.0, 60) is True
    assert resync_due(100.0, 159.9, 60) is False
    assert resync_due(100.0, 160.0, 60) is True
    assert resync_due(None, 100.0, 0) is False  # desligado


class FakePage:
    """Página falsa: evaluate() simula o RESYNC_JS trocando o HTML das listas."""

    def __init__(self, html_before: str, html_after: str = "", fail: bool = False, pages: int = 0):
        self.html = html_before
        self.html_after = html_after
        self.fail = fail
        self.pages = pages
        self.evaluations = 0
        self.modes: list[str] = []

    def is_closed(self) -> bool:
        return False

    async def evaluate(self, script: str, mode: str = "full"):
        self.evaluations += 1
        self.modes.append(mode)
        assert "control-atende-on-us.php" in script and "viewMoreActiveotChats" in script
        if self.fail:
            raise RuntimeError("Execution context was destroyed")
        if mode == "full":
            self.html = self.html_after
        return {"ok": 2 if mode == "full" else 0, "failed": 0, "pages": self.pages}

    async def content(self) -> str:
        return self.html


class ResyncSource(ChatPanelSource):
    def __init__(self, fake_page: FakePage, resync_seconds: int = 60, tech_name: str = "Guilherme"):
        super().__init__(
            ChatPanelSettings(url="https://x/chat.php", profile_dir=Path(".p"), refresh_seconds=15,
                              headless=True, resync_seconds=resync_seconds),
            tech_name,
        )
        self.fake_page = fake_page

    async def _ensure_page(self):
        return self.fake_page


async def test_resync_moves_transferred_chat_out_of_mine():
    # usuário dedicado "TUI" logado; a conversa está no meu nome no DOM antigo e no do Fulano no novo
    stale = page(others_box=li("551", "Transferida", agent="Guilherme"), user="TUI")
    fresh = page(others_box=li("551", "Transferida", agent="Fulano"), user="TUI")
    fake = FakePage(stale, fresh)
    source = ResyncSource(fake, resync_seconds=60)

    source._last_resync = 1000.0
    assert source._resync_due(now=1030.0) is False

    source._last_resync = None  # nunca ressincronizou: faz na primeira leitura
    state = await source.fetch()
    assert fake.modes == ["full"]
    assert state.mine == []  # saiu do meu nome
    assert state.others_count == 1
    assert source._last_resync is not None


async def test_resync_is_skipped_when_disabled():
    fake = FakePage(page(others_box=li("551", "X", agent="Guilherme"), user="TUI"))
    state = await ResyncSource(fake, resync_seconds=0).fetch()
    assert fake.evaluations == 0
    assert len(state.mine) == 1


async def test_resync_blocked_when_logged_as_the_technician(caplog):
    """Mesmo usuário do técnico: a sessão do app morre no servidor; ressincronizar apagaria tudo."""
    same = page(mine_box=li("551", "X", agent="Guilherme"), user="Guilherme")
    fake = FakePage(same, same)
    source = ResyncSource(fake, resync_seconds=60)
    state = await source.fetch()  # 1ª leitura ressincroniza (ainda não sabia quem estava logado)
    assert len(state.mine) == 1
    assert source._resync_blocked is True
    assert any("MESMO usuário" in r.getMessage() for r in caplog.records)
    source._last_resync = None
    await source.fetch()
    assert fake.modes == ["full"]  # não ressincronizou de novo


async def test_resync_failure_keeps_reading_current_dom(caplog):
    fake = FakePage(page(others_box=li("551", "X", agent="Guilherme"), user="TUI"), fail=True)
    state = await ResyncSource(fake, resync_seconds=60).fetch()
    assert fake.evaluations == 1
    assert len(state.mine) == 1  # falha na ressincronização não derruba a leitura
    assert any("ressincronização" in r.getMessage() for r in caplog.records)


async def test_resync_warns_when_page_limit_is_hit(caplog):
    from app.sources.chatpanel import RESYNC_MAX_PAGES

    fake = FakePage(page(user="TUI"), page(user="TUI"), pages=RESYNC_MAX_PAGES)
    await ResyncSource(fake)._resync_lists(fake, mode="expand")
    assert any("limite" in r.getMessage() for r in caplog.records)


# --- persistência dos cookies de sessão ------------------------------------------------


def test_persistable_cookies_selects_session_cookies_of_the_panel_host():
    from app.sources.chatpanel import persistable_cookies

    cookies = [
        {"name": "PHPSESSID", "domain": "srv.example.com", "expires": -1},
        {"name": "perm", "domain": "srv.example.com", "expires": 1_900_000_000},
        {"name": "outro", "domain": "outro.example.com", "expires": -1},
        {"name": "sub", "domain": ".example.com", "expires": 0},
    ]
    chosen = [c["name"] for c in persistable_cookies(cookies, "srv.example.com")]
    assert chosen == ["PHPSESSID", "sub"]


async def test_persist_session_cookies_rewrites_with_expiry(caplog):
    import logging
    import time

    caplog.set_level(logging.INFO, logger="source.chatpanel")

    class FakeContext:
        def __init__(self):
            self.added = None

        async def cookies(self):
            return [{"name": "PHPSESSID", "value": "x", "domain": "x", "path": "/", "expires": -1,
                     "httpOnly": True, "secure": True, "sameSite": "Lax"}]

        async def add_cookies(self, cookies):
            self.added = cookies

    source = ChatPanelSource(
        ChatPanelSettings(url="https://x/chat.php", profile_dir=Path(".p"), refresh_seconds=15, headless=True),
        "Guilherme",
    )
    ctx = FakeContext()
    await source._persist_session_cookies(ctx)
    assert ctx.added and ctx.added[0]["name"] == "PHPSESSID"
    assert ctx.added[0]["expires"] > time.time() + 29 * 86400
    assert ctx.added[0]["value"] == "x"  # valor intacto
    assert any("persistidos" in r.getMessage() for r in caplog.records)


def test_session_file_roundtrip_is_protected_on_disk(tmp_path: Path):
    import logging

    from app.sources.chatpanel import load_session_cookies, save_session_cookies

    log = logging.getLogger("test")
    path = tmp_path / "session.bin"
    cookies = [{"name": "PHPSESSID", "value": "segredo-123", "domain": "x", "path": "/", "expires": 4_000_000_000},
               {"name": "vencido", "value": "y", "domain": "x", "path": "/", "expires": 1}]
    save_session_cookies(path, cookies, log)
    assert b"segredo-123" not in path.read_bytes() or sys_is_not_windows()
    loaded = load_session_cookies(path, log)
    assert [c["name"] for c in loaded] == ["PHPSESSID"]  # o vencido é descartado
    assert loaded[0]["value"] == "segredo-123"
    assert load_session_cookies(tmp_path / "nao-existe.bin", log) == []
    (tmp_path / "lixo.bin").write_bytes(b"xx")
    assert load_session_cookies(tmp_path / "lixo.bin", log) == []


def sys_is_not_windows() -> bool:
    import sys

    return sys.platform != "win32"


async def test_launch_restores_saved_session_cookies(tmp_path: Path, caplog):
    import logging

    from app.sources.chatpanel import save_session_cookies

    caplog.set_level(logging.INFO, logger="source.chatpanel")

    class FakeContext:
        pages = []

        def __init__(self):
            self.added = None

        async def add_cookies(self, cookies):
            self.added = cookies

        async def new_page(self):
            return "page"

    source = ChatPanelSource(
        ChatPanelSettings(url="https://x/chat.php", profile_dir=tmp_path, refresh_seconds=15, headless=True),
        "Guilherme",
    )
    save_session_cookies(source.session_file, [{"name": "PHPSESSID", "value": "v", "domain": "x", "path": "/", "expires": 4_000_000_000}], logging.getLogger("t"))
    ctx = FakeContext()
    await source._restore_session(ctx)
    assert ctx.added and ctx.added[0]["name"] == "PHPSESSID"
    assert any("reinjetados" in r.getMessage() for r in caplog.records)
    assert not any("v" == r.getMessage() for r in caplog.records)


def test_login_failure_messages_are_short():
    from app.sources.chatpanel import _describe_login_failure

    class TimeoutError_(Exception):
        pass

    class TargetClosedError(Exception):
        pass

    assert _describe_login_failure(TimeoutError_("x"), 300) == "tempo esgotado (300s) sem completar o login"
    assert "fechada" in _describe_login_failure(TargetClosedError("Target page, context or browser has been closed"), 300)
    assert _describe_login_failure(RuntimeError("boom\nmais"), 300) == "login não concluído: boom"
