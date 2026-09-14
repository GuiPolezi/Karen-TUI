"""Loop de workers da TUI com fontes falsas: sucesso, erro isolado e refresh manual."""

from __future__ import annotations

import asyncio
from datetime import datetime

from textual.widgets import Static

from app.sources.base import Source
from app.state import EmailState, LatestEmail
from app.tui.app import CmdAllInOneApp
from tests.helpers import fake_settings, screen_text


class FakeEmailSource(Source[EmailState]):
    name = "email"
    config_hint = "preencha EMAIL_APP_PASSWORD no .env"

    def __init__(self, fail: bool = False, configured: bool = True):
        super().__init__(interval=60, timeout=1.0)
        self.fail = fail
        self._configured = configured
        self.calls = 0
        self.closed = False

    @property
    def configured(self) -> bool:
        return self._configured

    async def fetch(self) -> EmailState:
        self.calls += 1
        if self.fail:
            raise ConnectionError("servidor indisponível")
        return EmailState(
            total=142, unseen=7, spam=3,
            latest=LatestEmail(
                from_name="Fulano", from_addr="fulano@cm.sp.gov.br",
                subject="Erro ao gerar relatório", date=datetime(2026, 9, 14, 15, 28),
                preview="Bom dia, ao tentar gerar o relatório aparece erro.",
            ),
            updated_at=datetime(2026, 9, 14, 15, 31, 2),
        )

    async def close(self) -> None:
        self.closed = True


async def wait_until(predicate, timeout=3.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condição não atingida a tempo")
        await asyncio.sleep(0.02)


async def test_email_worker_renders_state_and_manual_refresh():
    source = FakeEmailSource()
    app = CmdAllInOneApp(fake_settings(), sources={"email": source})
    async with app.run_test(size=(120, 24)) as pilot:
        await wait_until(lambda: "email" in app.states)
        await pilot.pause()
        text = screen_text(app, 120, 24)
        assert "Inbox: 142" in text
        assert "Não lidos: 7" in text
        assert "Spam: 3" in text
        assert "Fulano <fulano@cm.sp.gov.br>" in text
        assert "Erro ao gerar relatório" in text
        assert "15:28 · Bom dia" in text  # data de hoje: só HH:MM
        assert "30s · 15:31:02" in text or "60s · 15:31:02" in text
        assert source.calls == 1

        await pilot.press("1")
        await wait_until(lambda: source.calls == 2)
        assert "atualizando e-mail" in str(app.query_one("#status-message", Static).content)
    assert source.closed is True


async def test_failing_source_marks_only_its_panel():
    source = FakeEmailSource(fail=True)
    source.timeout = 0.2
    app = CmdAllInOneApp(fake_settings(), sources={"email": source})
    # encurta o backoff para o teste não esperar 14 s
    import app.sources.base as base

    original = base.RETRY_DELAYS
    base.RETRY_DELAYS = (0.01, 0.01, 0.01)
    try:
        async with app.run_test(size=(120, 24)) as pilot:
            await wait_until(lambda: app.panel("email").has_class("error"))
            await pilot.pause()
            text = screen_text(app, 120, 24)
            assert "servidor indisponível" in text
            assert not app.panel("milldesk").has_class("error")
            assert "aguardando" in text  # os outros painéis seguem intactos
            assert source.calls == 4  # 1 + 3 retentativas
    finally:
        base.RETRY_DELAYS = original


async def test_unconfigured_source_does_not_start_worker():
    source = FakeEmailSource(configured=False)
    app = CmdAllInOneApp(fake_settings(), sources={"email": source})
    async with app.run_test(size=(120, 24)) as pilot:
        await pilot.pause()
        assert source.calls == 0
        assert app.panel("email").has_class("unconfigured")
        await pilot.press("1")
        assert "não configurado" in str(app.query_one("#status-message", Static).content)
        await pilot.press("2")
        assert "Fase 2" in str(app.query_one("#status-message", Static).content)
