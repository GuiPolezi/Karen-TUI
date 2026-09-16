"""Carrega o .env, valida e expõe as configurações da aplicação.

Regras:
- Variável AUSENTE do ambiente/.env → aborta com mensagem clara listando todas as faltantes.
- Segredo VAZIO (senha do e-mail, api_key do Milldesk) → a fonte correspondente fica
  marcada como "não configurada" e mostra isso no próprio painel, sem derrubar as outras.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from app.paths import BUNDLE_DIR, DATA_DIR, ENV_PATH, LOG_DIR

# mantido pelo que já importava daqui; é a pasta do código/pacote, não a do usuário
ROOT_DIR = BUNDLE_DIR


class ConfigError(Exception):
    """Configuração inválida ou incompleta."""


@dataclass(frozen=True)
class EmailSettings:
    host: str
    port: int
    starttls: bool
    user: str
    password: str
    inbox_folder: str
    spam_folder: str | None
    refresh_seconds: int
    list_size: int = 20  # quantos e-mails recentes listar (só cabeçalhos)

    @property
    def configured(self) -> bool:
        return bool(self.password)


@dataclass(frozen=True)
class MilldeskSettings:
    api_key: str
    base_url: str
    refresh_seconds: int
    agent_name: str = ""  # nome do técnico no Milldesk; vazio = usar TECH_NAME
    detail_ttl_seconds: int = 300  # cache do detalhe de um chamado (showTicket)

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    @property
    def masked_key(self) -> str:
        """Versão segura da chave para logs, no formato ****1776."""
        if not self.api_key:
            return "(vazia)"
        return "****" + self.api_key[-4:]


@dataclass(frozen=True)
class ChatPanelSettings:
    url: str
    profile_dir: Path
    refresh_seconds: int
    headless: bool
    user: str = ""               # opcional: pré-preenche o usuário na janela de login
    password: str = ""           # opcional: pré-preenche a senha; nunca aparece em log
    login_on_start: bool = True  # abre a janela de login sozinho (1x por execução) se a sessão expirou
    resync_seconds: int = 60     # recarrega as listas a cada N s (0 desliga); requer usuário dedicado
    read_conversations: bool = True  # Enter lê a conversa (inc_chat_view.php); medido como somente leitura

    @property
    def prefill_login(self) -> bool:
        return bool(self.user and self.password)


@dataclass(frozen=True)
class UrlSettings:
    """URLs abertas no navegador pela tecla `o` e pelo launcher. Vazio = "não configurado"."""

    webmail: str = ""
    milldesk: str = ""
    chatpanel: str = ""
    search: str = "https://www.google.com/search?q={q}"


@dataclass(frozen=True)
class Settings:
    tech_name: str
    email: EmailSettings
    milldesk: MilldeskSettings
    chatpanel: ChatPanelSettings
    notify_bell: bool
    log_level: str
    log_dir: Path
    urls: UrlSettings = UrlSettings()
    notify_toast: bool = False
    theme: str = "carbon"      # THEME: tema padrão (prefs.json tem prioridade)
    icons: str = "auto"        # ICONS: nerd | unicode | ascii | auto
    sla_blink: bool = True     # SLA_BLINK: SLA < 30 min pisca
    update_check: bool = True  # UPDATE_CHECK: ao abrir, git fetch e aviso se há commits novos


class _Env:
    """Leitor de variáveis que acumula as faltantes para reportar todas de uma vez."""

    def __init__(self) -> None:
        self.missing: list[str] = []
        self.invalid: list[str] = []

    def str(self, name: str, default: str | None = None, required: bool = True) -> str:
        """Ausente e em branco dão no mesmo.

        O `.env.example` é um modelo todo em branco: quem tem padrão cai no padrão, quem é
        obrigatória entra na lista do que falta preencher (em vez de virar valor vazio ou,
        pior, erro de "esperado inteiro" para um número em branco).
        """
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
        if default is not None:
            return default
        if required:
            self.missing.append(name)
        return ""

    def int(self, name: str, default: int) -> int:
        raw = self.str(name, str(default))
        try:
            return int(raw)
        except ValueError:
            self.invalid.append(f"{name}={raw!r} (esperado inteiro)")
            return default

    def bool(self, name: str, default: bool) -> bool:
        raw = self.str(name, "true" if default else "false").lower()
        if raw in {"1", "true", "yes", "sim", "on"}:
            return True
        if raw in {"0", "false", "no", "nao", "não", "off", ""}:
            return False
        self.invalid.append(f"{name}={raw!r} (esperado true/false)")
        return default


def load_settings(env_path: Path = ENV_PATH) -> Settings:
    """Lê o .env (se existir) e o ambiente, valida e devolve Settings."""
    if env_path.exists():
        load_dotenv(env_path, override=False)
    elif not os.environ.get("TECH_NAME"):
        raise ConfigError(
            f"Arquivo .env não encontrado em {env_path}.\n"
            "Copie .env.example para .env e preencha os valores."
        )

    env = _Env()

    tech_name = env.str("TECH_NAME")

    email = EmailSettings(
        host=env.str("EMAIL_IMAP_HOST"),
        port=env.int("EMAIL_IMAP_PORT", 143),
        starttls=env.bool("EMAIL_IMAP_STARTTLS", True),
        user=env.str("EMAIL_USER"),
        password=env.str("EMAIL_APP_PASSWORD", required=False),
        inbox_folder=env.str("EMAIL_INBOX_FOLDER", "INBOX"),
        spam_folder=env.str("EMAIL_SPAM_FOLDER", "", required=False) or None,
        refresh_seconds=env.int("EMAIL_REFRESH_SECONDS", 30),
        list_size=env.int("EMAIL_LIST_SIZE", 20),
    )

    milldesk = MilldeskSettings(
        api_key=env.str("MILLDESK_API_KEY", required=False),
        base_url=env.str("MILLDESK_BASE_URL", "https://v1.milldesk.com/api").rstrip("/"),
        refresh_seconds=env.int("MILLDESK_REFRESH_SECONDS", 60),
        agent_name=env.str("MILLDESK_AGENT_NAME", "", required=False) or tech_name,
        detail_ttl_seconds=env.int("MILLDESK_DETAIL_TTL_SECONDS", 300),
    )

    profile_dir = Path(env.str("CHATPANEL_PROFILE_DIR", ".chatpanel-profile"))
    if not profile_dir.is_absolute():
        profile_dir = DATA_DIR / profile_dir
    chatpanel = ChatPanelSettings(
        url=env.str("CHATPANEL_URL"),
        profile_dir=profile_dir,
        refresh_seconds=env.int("CHATPANEL_REFRESH_SECONDS", 15),
        headless=env.bool("CHATPANEL_HEADLESS", True),
        user=env.str("CHATPANEL_USER", "", required=False),
        password=env.str("CHATPANEL_PASSWORD", "", required=False),
        login_on_start=env.bool("CHATPANEL_LOGIN_ON_START", True),
        resync_seconds=env.int("CHATPANEL_RESYNC_SECONDS", 60),
        read_conversations=env.bool("CHATPANEL_READ_CONVERSATIONS", True),
    )

    notify_bell = env.bool("NOTIFY_BELL", True)
    notify_toast = env.bool("NOTIFY_TOAST", False)
    log_level = env.str("LOG_LEVEL", "INFO").upper()
    theme = env.str("THEME", "carbon") or "carbon"
    icons = env.str("ICONS", "auto").lower() or "auto"
    sla_blink = env.bool("SLA_BLINK", True)
    update_check = env.bool("UPDATE_CHECK", True)
    urls = UrlSettings(
        webmail=env.str("WEBMAIL_URL", "", required=False),
        milldesk=env.str("MILLDESK_WEB_URL", "", required=False),
        chatpanel=env.str("CHATPANEL_WEB_URL", "", required=False) or chatpanel.url,
        search=env.str("SEARCH_ENGINE_URL", "", required=False) or "https://www.google.com/search?q={q}",
    )

    problems: list[str] = []
    if env.missing:
        problems.append("Preencha estas variáveis obrigatórias: " + ", ".join(env.missing))
    if env.invalid:
        problems.append("Valores inválidos: " + "; ".join(env.invalid))
    for label, seconds in (
        ("EMAIL_REFRESH_SECONDS", email.refresh_seconds),
        ("MILLDESK_REFRESH_SECONDS", milldesk.refresh_seconds),
        ("CHATPANEL_REFRESH_SECONDS", chatpanel.refresh_seconds),
    ):
        if seconds < 5:
            problems.append(f"{label} deve ser >= 5 (recebido {seconds})")
    if chatpanel.resync_seconds != 0 and chatpanel.resync_seconds < 5:
        problems.append(
            f"CHATPANEL_RESYNC_SECONDS deve ser 0 (desligado) ou >= 5 (recebido {chatpanel.resync_seconds})"
        )
    if not 1 <= email.list_size <= 200:
        problems.append(f"EMAIL_LIST_SIZE deve estar entre 1 e 200 (recebido {email.list_size})")
    if problems:
        raise ConfigError("\n".join(problems) + f"\n\nArquivo lido: {env_path}")

    # segredos nunca aparecem em log, mesmo em mensagens de bibliotecas (URL do httpx etc.)
    from app.logging_setup import register_secret

    register_secret(milldesk.api_key, milldesk.masked_key)
    register_secret(email.password, "********")
    register_secret(chatpanel.password, "********")

    return Settings(
        tech_name=tech_name,
        email=email,
        milldesk=milldesk,
        chatpanel=chatpanel,
        notify_bell=notify_bell,
        log_level=log_level,
        log_dir=LOG_DIR,
        urls=urls,
        notify_toast=notify_toast,
        theme=theme,
        icons=icons,
        sla_blink=sla_blink,
        update_check=update_check,
    )
