from pathlib import Path

import pytest

from app.config import ConfigError, load_settings

MINIMAL_ENV = {
    "TECH_NAME": "Guilherme",
    "EMAIL_IMAP_HOST": "imap.example.com",
    "EMAIL_USER": "suporte@example.com",
    "CHATPANEL_URL": "https://example.com/chat.php",
}


@pytest.fixture
def clean_env(monkeypatch):
    """Remove qualquer variável do projeto do ambiente para o teste ser determinístico."""
    import os

    for key in list(os.environ):
        if key.startswith(("TECH_", "EMAIL_", "MILLDESK_", "CHATPANEL_", "NOTIFY_", "LOG_")):
            monkeypatch.delenv(key, raising=False)
    return monkeypatch


def test_missing_required_variables_are_all_reported(clean_env, tmp_path: Path):
    clean_env.setenv("TECH_NAME", "Guilherme")
    with pytest.raises(ConfigError) as info:
        load_settings(tmp_path / ".env")
    message = str(info.value)
    assert "EMAIL_IMAP_HOST" in message
    assert "EMAIL_USER" in message
    assert "CHATPANEL_URL" in message


def test_missing_env_file_without_environment_aborts(clean_env, tmp_path: Path):
    with pytest.raises(ConfigError, match="\\.env não encontrado"):
        load_settings(tmp_path / ".env")


def test_empty_secrets_mark_sources_as_not_configured(clean_env):
    for key, value in MINIMAL_ENV.items():
        clean_env.setenv(key, value)
    settings = load_settings(Path("nao-existe.env"))
    assert settings.tech_name == "Guilherme"
    assert settings.email.configured is False
    assert settings.milldesk.configured is False
    assert settings.milldesk.masked_key == "(vazia)"
    assert settings.email.port == 143
    assert settings.email.starttls is True
    assert settings.chatpanel.profile_dir.is_absolute()
    assert settings.chatpanel.prefill_login is False  # sem usuário/senha: só login manual
    assert settings.chatpanel.login_on_start is True


def test_reads_dotenv_file_and_masks_api_key(clean_env, tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                *(f"{k}={v}" for k, v in MINIMAL_ENV.items()),
                "MILLDESK_API_KEY=abcdef1776",
                "EMAIL_APP_PASSWORD='se#nha*'",
                "EMAIL_IMAP_PORT=993",
                "EMAIL_IMAP_STARTTLS=false",
                "EMAIL_SPAM_FOLDER=Junk E-Mail",
                "CHATPANEL_USER=guilherme",
                "CHATPANEL_PASSWORD='cp#senha'",
                "CHATPANEL_LOGIN_ON_START=false",
                "CHATPANEL_RESYNC_SECONDS=0",
            ]
        ),
        encoding="utf-8",
    )
    settings = load_settings(env_file)
    assert settings.chatpanel.user == "guilherme"
    assert settings.chatpanel.password == "cp#senha"
    assert settings.chatpanel.prefill_login is True
    assert settings.chatpanel.login_on_start is False
    assert settings.chatpanel.resync_seconds == 0
    assert settings.milldesk.configured is True
    assert settings.milldesk.masked_key == "****1776"
    assert settings.email.password == "se#nha*"
    assert settings.email.port == 993
    assert settings.email.starttls is False
    assert settings.email.spam_folder == "Junk E-Mail"


def test_invalid_values_are_reported(clean_env):
    for key, value in MINIMAL_ENV.items():
        clean_env.setenv(key, value)
    clean_env.setenv("EMAIL_IMAP_PORT", "abc")
    clean_env.setenv("EMAIL_REFRESH_SECONDS", "1")
    clean_env.setenv("CHATPANEL_RESYNC_SECONDS", "3")
    with pytest.raises(ConfigError) as info:
        load_settings(Path("nao-existe.env"))
    message = str(info.value)
    assert "EMAIL_IMAP_PORT" in message
    assert "EMAIL_REFRESH_SECONDS" in message
    assert "CHATPANEL_RESYNC_SECONDS" in message


def test_secrets_are_masked_in_logs(clean_env, tmp_path: Path, caplog):
    import logging

    from app.logging_setup import SecretMaskFilter

    for key, value in MINIMAL_ENV.items():
        clean_env.setenv(key, value)
    clean_env.setenv("MILLDESK_API_KEY", "abcdef1776")
    clean_env.setenv("EMAIL_APP_PASSWORD", "senha-secreta")
    clean_env.setenv("CHATPANEL_PASSWORD", "senha-do-chat")
    load_settings(Path("nao-existe.env"))

    record = logging.LogRecord("httpx", logging.INFO, __file__, 1,
                               "GET https://x/api/%s/ticketsByAgent senha=%s chat=%s",
                               ("abcdef1776", "senha-secreta", "senha-do-chat"), None)
    assert SecretMaskFilter().filter(record) is True
    assert record.getMessage() == "GET https://x/api/****1776/ticketsByAgent senha=******** chat=********"
