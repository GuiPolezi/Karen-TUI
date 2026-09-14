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

ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT_DIR / ".env"


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

    @property
    def configured(self) -> bool:
        return bool(self.password)


@dataclass(frozen=True)
class MilldeskSettings:
    api_key: str
    base_url: str
    refresh_seconds: int

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


@dataclass(frozen=True)
class Settings:
    tech_name: str
    email: EmailSettings
    milldesk: MilldeskSettings
    chatpanel: ChatPanelSettings
    notify_bell: bool
    log_level: str
    log_dir: Path


class _Env:
    """Leitor de variáveis que acumula as faltantes para reportar todas de uma vez."""

    def __init__(self) -> None:
        self.missing: list[str] = []
        self.invalid: list[str] = []

    def str(self, name: str, default: str | None = None, required: bool = True) -> str:
        value = os.environ.get(name)
        if value is None:
            if default is not None:
                return default
            if required:
                self.missing.append(name)
            return ""
        return value.strip()

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
    )

    milldesk = MilldeskSettings(
        api_key=env.str("MILLDESK_API_KEY", required=False),
        base_url=env.str("MILLDESK_BASE_URL", "https://v1.milldesk.com/api").rstrip("/"),
        refresh_seconds=env.int("MILLDESK_REFRESH_SECONDS", 60),
    )

    profile_dir = Path(env.str("CHATPANEL_PROFILE_DIR", ".chatpanel-profile"))
    if not profile_dir.is_absolute():
        profile_dir = ROOT_DIR / profile_dir
    chatpanel = ChatPanelSettings(
        url=env.str("CHATPANEL_URL"),
        profile_dir=profile_dir,
        refresh_seconds=env.int("CHATPANEL_REFRESH_SECONDS", 15),
        headless=env.bool("CHATPANEL_HEADLESS", True),
    )

    notify_bell = env.bool("NOTIFY_BELL", True)
    log_level = env.str("LOG_LEVEL", "INFO").upper()

    problems: list[str] = []
    if env.missing:
        problems.append("Variáveis obrigatórias ausentes: " + ", ".join(env.missing))
    if env.invalid:
        problems.append("Valores inválidos: " + "; ".join(env.invalid))
    if not tech_name:
        problems.append("TECH_NAME não pode ser vazio")
    for label, seconds in (
        ("EMAIL_REFRESH_SECONDS", email.refresh_seconds),
        ("MILLDESK_REFRESH_SECONDS", milldesk.refresh_seconds),
        ("CHATPANEL_REFRESH_SECONDS", chatpanel.refresh_seconds),
    ):
        if seconds < 5:
            problems.append(f"{label} deve ser >= 5 (recebido {seconds})")
    if problems:
        raise ConfigError("\n".join(problems) + f"\n\nArquivo lido: {env_path}")

    return Settings(
        tech_name=tech_name,
        email=email,
        milldesk=milldesk,
        chatpanel=chatpanel,
        notify_bell=notify_bell,
        log_level=log_level,
        log_dir=ROOT_DIR / "logs",
    )
