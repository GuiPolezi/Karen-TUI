"""Dados de exemplo da TUI, sem rede: usados pelas capturas de design
(`scripts/design_screenshots.py`), pelos testes de snapshot e pelo preview de temas.

Nada aqui lê `.env`, grava `prefs.json` ou toca a rede. Os horários são relativos a
`now` para que SLA, "há N min" e ordenação façam sentido em qualquer dia.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.config import ChatPanelSettings, EmailSettings, MilldeskSettings, Settings, UrlSettings
from app.events import Event
from app.sources.base import Source, SourceError
from app.state import (
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


class Clock:
    """Referência de tempo dos dados de exemplo (padrão: agora)."""

    def __init__(self, now: datetime | None = None) -> None:
        self.now = now or datetime.now()

    def at(self, hours: float = 0, minutes: float = 0, days: float = 0) -> datetime:
        return self.now + timedelta(hours=hours, minutes=minutes, days=days)

    def br(self, dt: datetime) -> tuple[str, str]:
        return dt.strftime("%d/%m/%Y"), dt.strftime("%H:%M")


def email_state(clock: Clock | None = None) -> EmailState:
    c = clock or Clock()
    recent = [
        EmailSummary("9012", "Fulano de Tal", "fulano@cm.sp.gov.br", "Erro ao gerar relatório de empenhos", c.at(minutes=-3), True),
        EmailSummary("9011", "Maria Souza", "maria@pmiaras.sp.gov.br", "RE: Acesso ao portal da transparência", c.at(minutes=-41), True),
        EmailSummary("9010", "Suporte Milldesk", "no-reply@milldesk.com", "[#4831] Novo chamado atribuído a você", c.at(hours=-1, minutes=-12)),
        EmailSummary("9009", "Hércules Andrade", "ti@camaratatui.sp.gov.br", "Certificado digital vencendo", c.at(hours=-3)),
        EmailSummary("9008", "Diego Leone", "diego@pmiaras.sp.gov.br", "Porta 21 continua fechada no firewall", c.at(hours=-5)),
        EmailSummary("9007", "Contabilidade", "contab@cmitu.sp.gov.br", "Fechamento do mês: relatório não abre", c.at(days=-1, hours=-2)),
        EmailSummary("9006", "Ana Paula", "ana@cmitu.sp.gov.br", "Solicitação de novo usuário", c.at(days=-1, hours=-6)),
        EmailSummary("9005", "GitHub", "noreply@github.com", "[cmd-all-in-one] Dependabot alert", c.at(days=-2)),
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
    return EmailState(total=142, unseen=7, spam=3, latest=latest, recent=recent, updated_at=c.at(minutes=-0.1))


def ticket(c: Clock, id: int, subject: str, status: str, opened: datetime, sla: datetime | str | None,
           requester: str = "") -> MilldeskTicket:
    day, time = c.br(opened)
    sla_text = sla.strftime("%d/%m/%Y %H:%M") if isinstance(sla, datetime) else sla
    return MilldeskTicket(id=id, subject=subject, status=status, stage="Atendimento", requester=requester,
                          start=day, starttime=time, sla_expiration=sla_text)


def milldesk_state(clock: Clock | None = None) -> MilldeskState:
    c = clock or Clock()
    tickets = [
        ticket(c, 4831, "Impressora fiscal não imprime cupom", "Em atendimento", c.at(minutes=-12), c.at(hours=6), "Ana Paula"),
        ticket(c, 4829, "Acesso ao sistema de RH bloqueado", "Aguardando cliente", c.at(hours=-1), c.at(days=1, hours=2), "Maria Souza"),
        ticket(c, 4821, "Backup noturno não executa desde sexta", "Em atendimento", c.at(hours=-3), c.at(hours=1, minutes=42), "TI Tatuí"),
        ticket(c, 4815, "Lentidão no portal da transparência", "Aguardando cliente", c.at(days=-1), c.at(days=2), "Diego Leone"),
        ticket(c, 4809, "Troca de toner — 2º andar", "Pausado", c.at(days=-2), "Em pausa", "Recepção"),
        ticket(c, 4802, "Certificado digital do prefeito vencendo", "Em atendimento", c.at(days=-3), c.at(hours=-1, minutes=-5), "Gabinete"),
        ticket(c, 4798, "Configurar VPN para home office", "Aguardando cliente", c.at(days=-4), c.at(days=5), "Jurídico"),
        ticket(c, 4790, "E-mail institucional não sincroniza no celular", "Aguardando cliente", c.at(days=-6), c.at(days=3), "Secretaria"),
        ticket(c, 4771, "Migração do servidor de arquivos", "Em atendimento", c.at(days=-9), c.at(days=12), "TI Itu"),
        ticket(c, 4750, "Atualização do sistema contábil", "Em atendimento", c.at(days=-14), c.at(days=20), "Contabilidade"),
        ticket(c, 4744, "Câmera do plenário sem imagem", "Aguardando cliente", c.at(days=-15), c.at(days=1), "Plenário"),
        ticket(c, 4731, "Licenças do Office vencidas", "Em atendimento", c.at(days=-20), c.at(days=30), "Compras"),
    ]
    return MilldeskState(
        my_tickets=len(tickets), my_open_by_status={"Em atendimento": 7, "Aguardando cliente": 4, "Pausado": 1},
        tickets=tickets, open_total=37, my_history=1184, my_percentage=23.4, total_all_agents=5061,
        updated_at=c.at(minutes=-0.45),
    )


def new_ticket(clock: Clock | None = None) -> MilldeskTicket:
    """Chamado que "chega" num segundo ciclo (para o destaque de mudança)."""
    c = clock or Clock()
    return ticket(c, 4833, "Novo: sistema de protocolo fora do ar", "Em atendimento", c.at(minutes=-1),
                  c.at(hours=4), "Protocolo")


def ticket_detail(clock: Clock | None = None) -> TicketDetail:
    c = clock or Clock()
    opened = c.at(hours=-3)
    day, time = c.br(opened)
    return TicketDetail(
        id=4821, subject="Backup noturno não executa desde sexta", requester="Hércules Andrade",
        agent="Guilherme", status="Em atendimento", stage="Atendimento", priority="Alta", urgency="Alta",
        category="Servidores", subcategory="Backup", department="TI", location="Câmara de Tatuí",
        group="Suporte N2", tickettype="Incidente", manner="E-mail", level="N2", impact="Alto",
        start=day, starttime=f"{day} {time}", end="", endtime="",
        sla_expiration=c.at(hours=1, minutes=42).strftime("%d/%m/%Y %H:%M"),
        description=(
            "O job de backup noturno (Veeam) não roda desde sexta-feira. O log mostra "
            "\"Unable to connect to repository\". O repositório é o NAS da sala do servidor; "
            "ping responde, mas o compartilhamento SMB não abre."
        ),
        resolution="",
        communications=[
            Communication(f"{day} {time}:00", "Hércules Andrade", "Abri o chamado; segue print do erro em anexo."),
            Communication(c.at(hours=-2).strftime("%d/%m/%Y %H:%M:%S"), "Guilherme", "Verificando credenciais do serviço no NAS. Retorno até as 16h."),
            Communication(c.at(minutes=-25).strftime("%d/%m/%Y %H:%M:%S"), "Hércules Andrade", "Ok, aguardo."),
        ],
        worked_hour="1,5000",
    )


def chatpanel_state(clock: Clock | None = None) -> ChatPanelState:
    c = clock or Clock()
    mine = [
        ChatItem("5515999990001", "Diego Leone · PM Iaras", c.at(minutes=-5).strftime("%H:%M"),
                 "Porta 21 continua fechada, consegue verificar hoje ainda?", unread=1, tag="Prefeitura",
                 department="Suporte", agent="Guilherme", online=True),
        ChatItem("5515999990002", "Hércules · CM Tatuí TI", c.at(minutes=-7).strftime("%H:%M"),
                 "Fabio: Hércules, consegue me mandar o print do erro do backup?", unread=0, tag="Câmara",
                 department="Suporte", agent="Guilherme", online=False),
        ChatItem("5515999990003", "Ana Paula · CM Itu", c.at(hours=-1).strftime("%H:%M"),
                 "Obrigada! Funcionou.", unread=0, tag="Câmara", department="Suporte", agent="Guilherme", online=False),
    ]
    others = [
        ChatItem("5515999990010", "Carla · CM Franca", c.at(minutes=-2).strftime("%H:%M"), "?", unread=3,
                 tag="Câmara", department="Comercial", agent="Fabio", online=True),
        ChatItem("5515999990011", "João · PM Cesário Lange", c.at(minutes=-30).strftime("%H:%M"),
                 "Vou verificar e retorno", unread=0, tag="Prefeitura", department="Suporte", agent="Rafael"),
    ]
    return ChatPanelState(mine=mine, mine_unread=1, others_count=4, others=others, total_unread_tab=6,
                          logged_user="User CMD", updated_at=c.at(minutes=-0.03))


def conversation_detail(clock: Clock | None = None) -> ConversationDetail:
    c = clock or Clock()

    def stamp(minutes: int) -> str:
        return c.at(minutes=minutes).strftime("%d/%m/%Y %H:%M")

    return ConversationDetail(
        number="5515999990001", name="Diego Leone · PM Iaras", has_more=True,
        messages=[
            ChatMessage(stamp(-95), "", "Conversa transferida para Guilherme", kind="system"),
            ChatMessage(stamp(-90), "Diego Leone", "Bom dia! O FTP da prefeitura parou de responder de novo."),
            ChatMessage(stamp(-80), "técnico", "Bom dia, Diego. Vou olhar o firewall agora.", mine=True),
            ChatMessage(stamp(-60), "técnico", "Liberei a porta 21 na regra de saída, testa aí por favor.", mine=True),
            ChatMessage(stamp(-30), "Diego Leone", "Ainda não conecta. Print:"),
            ChatMessage(stamp(-29), "Diego Leone", "[imagem]", kind="media"),
            ChatMessage(stamp(-5), "Diego Leone", "Porta 21 continua fechada, consegue verificar hoje ainda?"),
        ],
    )


def sample_events(clock: Clock | None = None) -> list[Event]:
    """Em ordem cronológica (como o EventLog guarda); a tela mostra o mais recente primeiro."""
    c = clock or Clock()
    events = [
        Event(c.at(minutes=-3), "email", "new_email", "e-mail novo de Fulano de Tal: Erro ao gerar relatório de empenhos", "9012"),
        Event(c.at(minutes=-5), "chatpanel", "chat_message", "Diego Leone · PM Iaras: 1 nova mensagem", "5515999990001"),
        Event(c.at(minutes=-12), "milldesk", "ticket_in", "chamado #4831 entrou: Impressora fiscal não imprime cupom", "4831"),
        Event(c.at(minutes=-41), "email", "new_email", "e-mail novo de Maria Souza: RE: Acesso ao portal da transparência", "9011"),
        Event(c.at(hours=-1), "milldesk", "ticket_status", "chamado #4829 mudou para Aguardando cliente", "4829"),
        Event(c.at(hours=-1, minutes=-30), "chatpanel", "chat_in", "conversa Ana Paula · CM Itu transferida para você", "5515999990003"),
        Event(c.at(hours=-2), "milldesk", "ticket_out", "chamado #4788 saiu do seu nome", "4788"),
        Event(c.at(hours=-2, minutes=-10), "chatpanel", "chat_out", "conversa Marcos · PM Boituva encerrada", "5515999990020"),
    ]
    return sorted(events, key=lambda e: e.when)


def sample_log(clock: Clock | None = None) -> list[str]:
    c = clock or Clock()
    entries = [
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
    return [f"{c.at(minutes=-m):%Y-%m-%d %H:%M:%S} {level} {name}: {text}" for m, level, name, text in entries]


SAMPLE_NOTES = """# Hoje

- [ ] ligar para Diego (PM Iaras) sobre a porta 21
- [x] renovar certificado CM Tatuí
- [ ] #4821 backup: testar credencial do serviço no NAS

## Senhas temporárias
(nunca aqui — usar o cofre)
"""


# --- fontes falsas ------------------------------------------------------------------------


class FakeSource(Source[Any]):
    """Fonte que publica um estado fixo (ou falha sempre) sem rede."""

    def __init__(self, name: str, state: Any, interval: int, *, configured: bool = True,
                 error: str | None = None, retry_after: float | None = 600.0,
                 hint: str = "verifique o .env", clock: Clock | None = None) -> None:
        self.name = name
        super().__init__(interval=interval, timeout=1.0)
        self._state = state
        self._configured = configured
        self._error = error
        self._retry_after = retry_after
        self.config_hint = hint
        self.clock = clock or Clock()
        self.calls = 0

    @property
    def configured(self) -> bool:
        return self._configured

    async def fetch(self) -> Any:
        self.calls += 1
        if self._error is not None:
            if "sessão expirada" in self._error:
                from app.sources.chatpanel import SessionExpiredError

                raise SessionExpiredError(self._error)  # como a fonte real: vira SourceError com esta causa
            # só limite de requisições (429) tem cooldown; timeout etc. são erro comum
            cooldown = any(word in self._error for word in ("429", "limite"))
            raise SourceError(self._error, retry_after=self._retry_after if cooldown else None)
        return self._state

    async def fetch_ticket(self, ticket_id: int, force: bool = False) -> TicketDetail:
        return ticket_detail(self.clock)

    async def fetch_conversation(self, number: str, name: str) -> ConversationDetail:
        return conversation_detail(self.clock)

    async def fetch_body(self, uid: str) -> LatestEmail | None:
        return email_state(self.clock).latest


def demo_settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = dict(
        tech_name="Guilherme",
        email=EmailSettings(host="imap.example.com", port=143, starttls=True, user="x@example.com",
                            password="x", inbox_folder="INBOX", spam_folder="Junk", refresh_seconds=30),
        milldesk=MilldeskSettings(api_key="x", base_url="https://example.com/api", refresh_seconds=60),
        chatpanel=ChatPanelSettings(url="https://example.com/chat.php", profile_dir=Path(".p"),
                                    refresh_seconds=15, headless=True),
        notify_bell=False, log_level="INFO", log_dir=Path("logs"),
        icons="unicode",  # determinístico em testes e capturas (auto depende do terminal)
        urls=UrlSettings(webmail="https://webmail.example.com", milldesk="https://md.example.com",
                         chatpanel="https://chat.example.com"),
    )
    base.update(overrides)
    return Settings(**base)


def empty_milldesk_state(clock: Clock | None = None) -> MilldeskState:
    """Nenhum chamado no meu nome (vazio é boa notícia)."""
    c = clock or Clock()
    return MilldeskState(my_tickets=0, tickets=[], open_total=37, my_history=1184, my_percentage=23.4,
                         total_all_agents=5061, updated_at=c.at(minutes=-0.45))


def demo_sources(clock: Clock | None = None, *, email_error: str | None = None,
                 milldesk_error: str | None = None, milldesk_retry_after: float | None = 600.0,
                 milldesk_empty: bool = False,
                 chat_unconfigured: bool = False, chat_expired: bool = False) -> dict[str, FakeSource]:
    c = clock or Clock()
    return {
        "email": FakeSource("email", email_state(c), 30, error=email_error, clock=c),
        "milldesk": FakeSource("milldesk", empty_milldesk_state(c) if milldesk_empty else milldesk_state(c), 60,
                               error=milldesk_error, retry_after=milldesk_retry_after, clock=c),
        "chatpanel": FakeSource("chatpanel", chatpanel_state(c), 15, configured=not chat_unconfigured,
                                error="sessão expirada: faça o login (c)" if chat_expired else None,
                                hint="CHATPANEL_URL vazio no .env", clock=c),
    }
