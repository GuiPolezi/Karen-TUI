"""Capturas SVG (e texto) de todas as telas da TUI com dados de fixture, sem rede.

Uso: python scripts/design_screenshots.py [pasta de saída]   (padrão: docs/design/antes)

Gera, para cada tela/estado, um `.svg` (cores) e um `.txt` (texto puro, útil para diff
e para ler no terminal) em dois tamanhos: 120x35 e 90x30. As fontes são falsas
(`FakeSource`) e publicam um estado fixo; Log e Notas leem linhas de exemplo em vez
dos arquivos reais. Nada aqui toca `.env`, rede ou `prefs.json`.
"""

from __future__ import annotations

import asyncio
import io
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console  # noqa: E402

from app.config import ChatPanelSettings, EmailSettings, MilldeskSettings, Settings, UrlSettings  # noqa: E402
from app.events import Event  # noqa: E402
from app.prefs import Prefs  # noqa: E402
from app.sources.base import Source  # noqa: E402
from app.state import (  # noqa: E402
    ChatItem,
    ChatMessage,
    ChatPanelState,
    Communication,
    ConversationDetail,
    EmailState,
    EmailSummary,
    LatestEmail,
    MilldeskState,
    MilldeskTicket,
    TicketDetail,
)
from app.tui.app import CmdAllInOneApp  # noqa: E402
from app.tui.screens import ConversationDetailScreen, EmailDetailScreen, TicketDetailScreen  # noqa: E402
from app.tui.screens import log as log_screen  # noqa: E402
from app.tui.screens import notes as notes_screen  # noqa: E402

SIZES = ((120, 35), (90, 30))
NOW = datetime.now()


def _at(hours: float = 0, minutes: float = 0, days: float = 0) -> datetime:
    return NOW + timedelta(hours=hours, minutes=minutes, days=days)


def _br(dt: datetime) -> tuple[str, str]:
    return dt.strftime("%d/%m/%Y"), dt.strftime("%H:%M")


# --- fixtures ------------------------------------------------------------------------------


def email_state() -> EmailState:
    recent = [
        EmailSummary("9012", "Fulano de Tal", "fulano@cm.sp.gov.br", "Erro ao gerar relatório de empenhos", _at(minutes=-3), True),
        EmailSummary("9011", "Maria Souza", "maria@pmiaras.sp.gov.br", "RE: Acesso ao portal da transparência", _at(minutes=-41), True),
        EmailSummary("9010", "Suporte Milldesk", "no-reply@milldesk.com", "[#4831] Novo chamado atribuído a você", _at(hours=-1, minutes=-12)),
        EmailSummary("9009", "Hércules Andrade", "ti@camaratatui.sp.gov.br", "Certificado digital vencendo", _at(hours=-3)),
        EmailSummary("9008", "Diego Leone", "diego@pmiaras.sp.gov.br", "Porta 21 continua fechada no firewall", _at(hours=-5)),
        EmailSummary("9007", "Contabilidade", "contab@cmitu.sp.gov.br", "Fechamento do mês: relatório não abre", _at(days=-1, hours=-2)),
        EmailSummary("9006", "Ana Paula", "ana@cmitu.sp.gov.br", "Solicitação de novo usuário", _at(days=-1, hours=-6)),
        EmailSummary("9005", "GitHub", "noreply@github.com", "[cmd-all-in-one] Dependabot alert", _at(days=-2)),
    ]
    latest = LatestEmail(
        from_name=recent[0].from_name, from_addr=recent[0].from_addr, subject=recent[0].subject,
        date=recent[0].date,
        preview="Bom dia, ao tentar gerar o relatório de empenhos do mês o sistema apresenta a mensagem…",
        body=(
            "Bom dia,\n\nAo tentar gerar o relatório de empenhos do mês o sistema apresenta a mensagem "
            "\"Erro interno (500)\" e não gera o PDF. Já tentei em outro navegador.\n\n"
            "Podem verificar?\n\nAtenciosamente,\nFulano de Tal\nContabilidade — Câmara Municipal"
        ),
    )
    return EmailState(total=142, unseen=7, spam=3, latest=latest, recent=recent, updated_at=_at(minutes=-0.1))


def _ticket(id: int, subject: str, status: str, opened: datetime, sla: datetime | str | None,
            requester: str = "") -> MilldeskTicket:
    day, time = _br(opened)
    if isinstance(sla, datetime):
        sla_text: str | None = sla.strftime("%d/%m/%Y %H:%M")
    else:
        sla_text = sla
    return MilldeskTicket(id=id, subject=subject, status=status, stage="Atendimento", requester=requester,
                          start=day, starttime=time, sla_expiration=sla_text)


def milldesk_state() -> MilldeskState:
    tickets = [
        _ticket(4831, "Impressora fiscal não imprime cupom", "Em atendimento", _at(minutes=-12), _at(hours=6), "Ana Paula"),
        _ticket(4829, "Acesso ao sistema de RH bloqueado", "Aguardando cliente", _at(hours=-1), _at(days=1, hours=2), "Maria Souza"),
        _ticket(4821, "Backup noturno não executa desde sexta", "Em atendimento", _at(hours=-3), _at(hours=1, minutes=42), "TI Tatuí"),
        _ticket(4815, "Lentidão no portal da transparência", "Aguardando cliente", _at(days=-1), _at(days=2), "Diego Leone"),
        _ticket(4809, "Troca de toner — 2º andar", "Pausado", _at(days=-2), "Em pausa", "Recepção"),
        _ticket(4802, "Certificado digital do prefeito vencendo", "Em atendimento", _at(days=-3), _at(hours=-1, minutes=-5), "Gabinete"),
        _ticket(4798, "Configurar VPN para home office", "Aguardando cliente", _at(days=-4), _at(days=5), "Jurídico"),
        _ticket(4790, "E-mail institucional não sincroniza no celular", "Aguardando cliente", _at(days=-6), _at(days=3), "Secretaria"),
        _ticket(4771, "Migração do servidor de arquivos", "Em atendimento", _at(days=-9), _at(days=12), "TI Itu"),
        _ticket(4750, "Atualização do sistema contábil", "Em atendimento", _at(days=-14), _at(days=20), "Contabilidade"),
        _ticket(4744, "Câmera do plenário sem imagem", "Aguardando cliente", _at(days=-15), _at(days=1), "Plenário"),
        _ticket(4731, "Licenças do Office vencidas", "Em atendimento", _at(days=-20), _at(days=30), "Compras"),
    ]
    return MilldeskState(
        my_tickets=len(tickets), my_open_by_status={"Em atendimento": 7, "Aguardando cliente": 4, "Pausado": 1},
        tickets=tickets, open_total=37, my_history=1184, my_percentage=23.4, total_all_agents=5061,
        updated_at=_at(minutes=-0.45),
    )


def ticket_detail() -> TicketDetail:
    opened = _at(hours=-3)
    day, time = _br(opened)
    return TicketDetail(
        id=4821, subject="Backup noturno não executa desde sexta", requester="Hércules Andrade",
        agent="Guilherme", status="Em atendimento", stage="Atendimento", priority="Alta", urgency="Alta",
        category="Servidores", subcategory="Backup", department="TI", location="Câmara de Tatuí",
        group="Suporte N2", tickettype="Incidente", manner="E-mail", level="N2", impact="Alto",
        start=day, starttime=f"{day} {time}", end="", endtime="",
        sla_expiration=_at(hours=1, minutes=42).strftime("%d/%m/%Y %H:%M"),
        description=(
            "O job de backup noturno (Veeam) não roda desde sexta-feira. O log mostra "
            "\"Unable to connect to repository\". O repositório é o NAS da sala do servidor; "
            "ping responde, mas o compartilhamento SMB não abre."
        ),
        resolution="",
        communications=[
            Communication(f"{day} {time}:00", "Hércules Andrade", "Abri o chamado; segue print do erro em anexo."),
            Communication(_at(hours=-2).strftime("%d/%m/%Y %H:%M:%S"), "Guilherme", "Verificando credenciais do serviço no NAS. Retorno até as 16h."),
            Communication(_at(minutes=-25).strftime("%d/%m/%Y %H:%M:%S"), "Hércules Andrade", "Ok, aguardo."),
        ],
        worked_hour="1,5000",
    )


def chatpanel_state() -> ChatPanelState:
    mine = [
        ChatItem("5515999990001", "Diego Leone · PM Iaras", _at(minutes=-5).strftime("%H:%M"),
                 "Porta 21 continua fechada, consegue verificar hoje ainda?", unread=1, tag="Prefeitura",
                 department="Suporte", agent="Guilherme", online=True),
        ChatItem("5515999990002", "Hércules · CM Tatuí TI", _at(minutes=-7).strftime("%H:%M"),
                 "Fabio: Hércules, consegue me mandar o print do erro do backup?", unread=0, tag="Câmara",
                 department="Suporte", agent="Guilherme", online=False),
        ChatItem("5515999990003", "Ana Paula · CM Itu", _at(hours=-1).strftime("%H:%M"),
                 "Obrigada! Funcionou.", unread=0, tag="Câmara", department="Suporte", agent="Guilherme", online=False),
    ]
    others = [
        ChatItem("5515999990010", "Carla · CM Franca", _at(minutes=-2).strftime("%H:%M"), "?", unread=3,
                 tag="Câmara", department="Comercial", agent="Fabio", online=True),
        ChatItem("5515999990011", "João · PM Cesário Lange", _at(minutes=-30).strftime("%H:%M"),
                 "Vou verificar e retorno", unread=0, tag="Prefeitura", department="Suporte", agent="Rafael"),
    ]
    return ChatPanelState(mine=mine, mine_unread=1, others_count=4, others=others, total_unread_tab=6,
                          logged_user="User CMD", updated_at=_at(minutes=-0.03))


def conversation_detail() -> ConversationDetail:
    stamp = lambda m: _at(minutes=m).strftime("%d/%m/%Y %H:%M")  # noqa: E731
    return ConversationDetail(
        number="5515999990001", name="Diego Leone · PM Iaras", has_more=True,
        messages=[
            ChatMessage(stamp(-95), "", "Conversa transferida para Guilherme", kind="system"),
            ChatMessage(stamp(-90), "Diego Leone", "Bom dia! O FTP da prefeitura parou de responder de novo."),
            ChatMessage(stamp(-80), "técnico", "Bom dia, Diego. Vou olhar o firewall agora.", mine=True),
            ChatMessage(stamp(-60), "técnico", "Liberei a porta 21 na regra de saída, testa aí por favor.", mine=True),
            ChatMessage(stamp(-30), "Diego Leone", "Ainda não conecta. Print:", ),
            ChatMessage(stamp(-29), "Diego Leone", "[imagem]", kind="media"),
            ChatMessage(stamp(-5), "Diego Leone", "Porta 21 continua fechada, consegue verificar hoje ainda?"),
        ],
    )


def sample_events() -> list[Event]:
    """Em ordem cronológica (como o EventLog guarda); a tela mostra o mais recente primeiro."""
    return sorted(_sample_events(), key=lambda e: e.when)


def _sample_events() -> list[Event]:
    return [
        Event(_at(minutes=-3), "email", "new_email", "e-mail novo de Fulano de Tal: Erro ao gerar relatório de empenhos", "9012"),
        Event(_at(minutes=-5), "chatpanel", "chat_message", "Diego Leone · PM Iaras: 1 nova mensagem", "5515999990001"),
        Event(_at(minutes=-12), "milldesk", "ticket_in", "chamado #4831 entrou: Impressora fiscal não imprime cupom", "4831"),
        Event(_at(minutes=-41), "email", "new_email", "e-mail novo de Maria Souza: RE: Acesso ao portal da transparência", "9011"),
        Event(_at(hours=-1), "milldesk", "ticket_status", "chamado #4829 mudou para Aguardando cliente", "4829"),
        Event(_at(hours=-1, minutes=-30), "chatpanel", "chat_in", "conversa Ana Paula · CM Itu transferida para você", "5515999990003"),
        Event(_at(hours=-2), "milldesk", "ticket_out", "chamado #4788 saiu do seu nome", "4788"),
        Event(_at(hours=-2, minutes=-10), "chatpanel", "chat_out", "conversa Marcos · PM Boituva encerrada", "5515999990020"),
    ]


SAMPLE_LOG = [
    f"{_at(minutes=-m):%Y-%m-%d %H:%M:%S} {level} {name}: {text}"
    for m, level, name, text in [
        (30, "INFO", "app", "CMD ALL-IN-ONE iniciado (textual 8.2.8)"),
        (30, "INFO", "source.email", "conectado a imap.example.com:143 (STARTTLS, readonly)"),
        (29, "INFO", "source.milldesk", "ticketsByStatus: 37 abertos, 12 no meu nome"),
        (29, "INFO", "source.chatpanel", "sessão restaurada de session.bin (User CMD)"),
        (12, "INFO", "tui", "aumentou em Milldesk: abertos"),
        (12, "INFO", "tui", "evento: chamado #4831 entrou: Impressora fiscal não imprime cupom"),
        (8, "WARNING", "source.milldesk", "tentativa 1 falhou: timeout"),
        (8, "INFO", "source.milldesk", "tentativa 2 ok (2,1 s)"),
        (5, "INFO", "tui", "evento: Diego Leone · PM Iaras: 1 nova mensagem"),
        (3, "INFO", "tui", "aumentou em e-mail: não lidos"),
        (0, "INFO", "source.email", "142 na caixa, 7 não lidos, 3 spam"),
    ]
]

SAMPLE_NOTES = """# Hoje

- [ ] ligar para Diego (PM Iaras) sobre a porta 21
- [x] renovar certificado CM Tatuí
- [ ] #4821 backup: testar credencial do serviço no NAS

## Senhas temporárias
(nunca aqui — usar o cofre)
"""


# --- fontes falsas --------------------------------------------------------------------------


class FakeSource(Source[Any]):
    """Fonte que publica um estado fixo (ou falha) sem rede."""

    def __init__(self, name: str, state: Any, interval: int, *, configured: bool = True,
                 error: str | None = None, hint: str = "verifique o .env") -> None:
        self.name = name
        super().__init__(interval=interval, timeout=1.0)
        self._state = state
        self._configured = configured
        self._error = error
        self.config_hint = hint
        self.calls = 0

    @property
    def configured(self) -> bool:
        return self._configured

    async def fetch(self) -> Any:
        self.calls += 1
        if self._error is not None:
            from app.sources.base import SourceError

            raise SourceError(self._error, retry_after=600)
        return self._state

    async def fetch_ticket(self, ticket_id: int, force: bool = False) -> TicketDetail:
        return ticket_detail()

    async def fetch_conversation(self, number: str, name: str) -> ConversationDetail:
        return conversation_detail()

    async def fetch_body(self, uid: str) -> LatestEmail | None:
        return email_state().latest


def settings() -> Settings:
    return Settings(
        tech_name="Guilherme",
        email=EmailSettings(host="imap.example.com", port=143, starttls=True, user="x@example.com",
                            password="x", inbox_folder="INBOX", spam_folder="Junk", refresh_seconds=30),
        milldesk=MilldeskSettings(api_key="x", base_url="https://example.com/api", refresh_seconds=60),
        chatpanel=ChatPanelSettings(url="https://example.com/chat.php", profile_dir=Path(".p"),
                                    refresh_seconds=15, headless=True),
        notify_bell=False, log_level="INFO", log_dir=Path("logs"),
        urls=UrlSettings(webmail="https://webmail.example.com", milldesk="https://md.example.com",
                         chatpanel="https://chat.example.com"),
    )


def make_app(*, email_error: str | None = None, chat_unconfigured: bool = False, chat_expired: bool = False,
             prefs: Prefs | None = None) -> CmdAllInOneApp:
    sources = {
        "email": FakeSource("email", email_state(), 30, error=email_error),
        "milldesk": FakeSource("milldesk", milldesk_state(), 60),
        "chatpanel": FakeSource("chatpanel", chatpanel_state(), 15, configured=not chat_unconfigured,
                                error="sessão expirada: faça o login (c)" if chat_expired else None,
                                hint="CHATPANEL_URL vazio no .env"),
    }
    app = CmdAllInOneApp(settings(), sources=sources, prefs=prefs or Prefs(), prefs_path=None)
    app.event_log.events.extend(sample_events())
    return app


# --- captura ---------------------------------------------------------------------------------


def _text(app: CmdAllInOneApp, width: int, height: int) -> str:
    console = Console(width=width, height=height, record=True, file=io.StringIO(), force_terminal=True,
                      color_system="truecolor", legacy_windows=False)
    console.print(app.screen._compositor)
    return console.export_text()


async def _wait_states(app: CmdAllInOneApp, names: tuple[str, ...] = ("email", "milldesk", "chatpanel")) -> None:
    for _ in range(200):
        if all(n in app.states or app.errors.get(n) for n in names):
            return
        await asyncio.sleep(0.02)


def _save(app: CmdAllInOneApp, out: Path, name: str, width: int, height: int) -> None:
    stem = f"{name}_{width}x{height}"
    (out / f"{stem}.svg").write_text(app.export_screenshot(title=f"{name} {width}x{height}"), encoding="utf-8")
    (out / f"{stem}.txt").write_text(_text(app, width, height), encoding="utf-8")
    print(f"  {stem}")


async def capture_all(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    log_screen.tail = lambda path, lines=300: list(SAMPLE_LOG)  # type: ignore[assignment]
    notes_screen.load_notes = lambda path=None: SAMPLE_NOTES  # type: ignore[assignment]

    for width, height in SIZES:
        print(f"-- {width}x{height}")
        app = make_app()
        async with app.run_test(size=(width, height)) as pilot:
            await _wait_states(app)
            await pilot.pause()
            _save(app, out, "dashboard", width, height)

            # destaque de mudança (borda amarela grossa) e marcador ● na linha nova
            new_state = milldesk_state()
            new_state.tickets.insert(0, _ticket(4833, "Novo: sistema de protocolo fora do ar", "Em atendimento",
                                                _at(minutes=-1), _at(hours=4), "Protocolo"))
            new_state.my_tickets += 1
            app._publish("milldesk", new_state)
            await pilot.pause()
            _save(app, out, "dashboard_mudanca", width, height)

            for key, mode in (("f2", "email"), ("f3", "milldesk"), ("f4", "chatpanel"), ("f5", "log"),
                              ("f6", "notes"), ("f7", "events"), ("f8", "health")):
                await pilot.press(key)
                await pilot.pause()
                _save(app, out, mode, width, height)

            await pilot.press("f3")
            await pilot.pause()
            await pilot.press("slash")
            await pilot.press("b", "a", "c")
            await pilot.pause()
            _save(app, out, "milldesk_filtro", width, height)
            await pilot.press("escape")
            await pilot.pause()

            await pilot.press("f1")
            await pilot.pause()
            app.push_screen(EmailDetailScreen(email_state().latest))
            await pilot.pause()
            _save(app, out, "detalhe_email", width, height)
            await pilot.press("escape")
            await pilot.pause()

            app.push_screen(TicketDetailScreen(4821, ticket_detail()))
            await pilot.pause()
            _save(app, out, "detalhe_chamado", width, height)
            await pilot.press("escape")
            await pilot.pause()

            item = chatpanel_state().mine[0]
            app.push_screen(ConversationDetailScreen(item.number, item, conversation_detail()))
            await pilot.pause()
            _save(app, out, "detalhe_conversa", width, height)
            await pilot.press("escape")
            await pilot.pause()

            await pilot.press("colon")
            await pilot.pause()
            await pilot.press("m", "d", " ", "4", "8")
            await pilot.pause()
            _save(app, out, "launcher", width, height)
            await pilot.press("escape")
            await pilot.pause()

            await pilot.press("question_mark")
            await pilot.pause()
            _save(app, out, "ajuda", width, height)
            await pilot.press("escape")
            await pilot.pause()

            app.notify("Milldesk: abertos")
            app.notify("e-mail: não lidos", severity="warning")
            await pilot.pause()
            _save(app, out, "dashboard_notify", width, height)

        # estados: erro com dados antigos (e-mail), sessão expirada (ChatPanel)
        app = make_app(email_error="timeout", chat_expired=True)
        async with app.run_test(size=(width, height)) as pilot:
            await _wait_states(app)
            await pilot.pause()
            _save(app, out, "dashboard_erros", width, height)

        # estados: não configurado (ChatPanel) + aguardando primeira coleta
        app = make_app(chat_unconfigured=True)
        async with app.run_test(size=(width, height)) as pilot:
            await pilot.pause()
            _save(app, out, "dashboard_inicio", width, height)

        # silêncio ligado (ícone na TopBar)
        app = make_app(prefs=Prefs(silenced_until=NOW.timestamp() + 1800))
        async with app.run_test(size=(width, height)) as pilot:
            await _wait_states(app)
            await pilot.pause()
            _save(app, out, "dashboard_silencio", width, height)

    # terminal muito baixo e terminal estreito extra
    for width, height in ((120, 22), (80, 24)):
        print(f"-- {width}x{height}")
        app = make_app()
        async with app.run_test(size=(width, height)) as pilot:
            await _wait_states(app)
            await pilot.pause()
            _save(app, out, "dashboard", width, height)


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("docs/design/antes")
    asyncio.run(capture_all(target))
    print(f"capturas em {target}")
