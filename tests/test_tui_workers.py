"""Loop de workers da TUI com fontes falsas: sucesso, erro isolado e refresh manual."""

from __future__ import annotations

from datetime import datetime

from app.sources.base import Source
from app.state import EmailState, EmailSummary, LatestEmail
from tests.helpers import fake_settings, make_app, screen_text, wait_until


def sample_email_state(unseen: int = 7) -> EmailState:
    latest = LatestEmail(
        from_name="Fulano", from_addr="fulano@cm.sp.gov.br",
        subject="Erro ao gerar relatório", date=datetime(2026, 9, 14, 15, 28),
        preview="Bom dia, ao tentar gerar o relatório aparece erro.",
        body="Bom dia,\n\nao tentar gerar o relatório aparece erro.",
    )
    recent = [
        EmailSummary(uid="10", from_name="Fulano", from_addr="fulano@cm.sp.gov.br",
                     subject="Erro ao gerar relatório", date=datetime(2026, 9, 14, 15, 28), unseen=True),
        EmailSummary(uid="9", from_name="Beltrano", from_addr="b@x.br",
                     subject="Nota fiscal", date=datetime(2026, 9, 14, 11, 2), unseen=False),
    ]
    return EmailState(total=142, unseen=unseen, spam=3, latest=latest, recent=recent,
                      updated_at=datetime(2026, 9, 14, 15, 31, 2))


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
        return sample_email_state()

    async def close(self) -> None:
        self.closed = True


async def test_email_worker_renders_state_and_manual_refresh():
    source = FakeEmailSource()
    app = make_app(sources={"email": source})
    async with app.run_test(size=(120, 30)) as pilot:
        await wait_until(lambda: "email" in app.states)
        await pilot.pause()
        text = screen_text(app, 120, 30)
        assert "Inbox 142" in text  # rótulo em text-muted, número em bold (sem dois-pontos)
        assert "Não lidos 7" in text
        assert "Spam 3" in text
        assert "Fulano" in text
        assert "Erro ao gerar" in text  # o assunto é cortado na largura do painel compacto
        assert "Beltrano" in text
        assert "60s · 15:31:02" in text
        assert source.calls == 1
        assert app.panel("email").table.keys == ["10", "9"]

        await pilot.press("1")
        await wait_until(lambda: source.calls == 2)
        assert "atualizando e-mail" in app.last_message
    assert source.closed is True


async def test_failing_source_marks_only_its_panel():
    source = FakeEmailSource(fail=True)
    source.timeout = 0.2
    app = make_app(sources={"email": source})
    import app.sources.base as base

    original = base.RETRY_DELAYS
    base.RETRY_DELAYS = (0.01, 0.01, 0.01)
    try:
        async with app.run_test(size=(120, 24)) as pilot:
            await wait_until(lambda: app.errors.get("email") is not None)
            await pilot.pause()
            text = screen_text(app, 120, 24)
            assert "servidor indisponível" in text
            assert app.panel("email").has_class("error")
            assert not app.panel("milldesk").has_class("error")
            assert "aguardando" in text  # os outros painéis seguem intactos
            assert source.calls == 4  # 1 + 3 retentativas
    finally:
        base.RETRY_DELAYS = original


async def test_unconfigured_source_does_not_start_worker():
    source = FakeEmailSource(configured=False)
    app = make_app(sources={"email": source})
    async with app.run_test(size=(120, 24)) as pilot:
        await pilot.pause()
        assert source.calls == 0
        assert app.panel("email").has_class("unconfigured")
        await pilot.press("1")
        assert "não configurado" in app.last_message
        await pilot.press("2")
        assert "Fase 2" in app.last_message


async def test_full_email_screen_shares_state_and_opens_detail_on_enter():
    source = FakeEmailSource()
    app = make_app(sources={"email": source})
    async with app.run_test(size=(120, 30)) as pilot:
        await wait_until(lambda: "email" in app.states)
        await pilot.press("f2")
        await pilot.pause()
        panel = app.mode_screens["email"].query_one("#email-full")
        assert panel.table.keys == ["10", "9"]
        assert panel.table.selected_key == "10"
        await pilot.press("down")
        await pilot.pause()
        assert panel.table.selected_key == "9"
        await pilot.press("enter")
        await pilot.pause()
        from app.tui.screens import EmailDetailScreen

        assert isinstance(app.screen, EmailDetailScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, EmailDetailScreen)
        assert app.current_mode == "email"
