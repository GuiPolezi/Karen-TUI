"""Logging em arquivo com rotação. Nada de print na TUI.

Todo handler recebe um SecretMaskFilter: qualquer segredo registrado via
register_secret() é trocado por sua versão mascarada antes de ir para o log.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FILE_NAME = "app.log"

_SECRETS: dict[str, str] = {}  # valor real -> versão mascarada


def register_secret(value: str, masked: str) -> None:
    """Registra um segredo para ser mascarado em todas as mensagens de log."""
    if value:
        _SECRETS[value] = masked


class SecretMaskFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if _SECRETS:
            message = record.getMessage()
            masked = message
            for value, replacement in _SECRETS.items():
                masked = masked.replace(value, replacement)
            if masked != message:
                record.msg = masked
                record.args = ()
        return True


def _quiet_noisy_libraries() -> None:
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def _install(handler: logging.Handler, level: str) -> None:
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    )
    handler.addFilter(SecretMaskFilter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level, logging.INFO))
    _quiet_noisy_libraries()


def setup_logging(log_dir: Path, level: str = "INFO") -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / LOG_FILE_NAME
    handler = RotatingFileHandler(
        log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    _install(handler, level)
    return log_path


def setup_debug_logging(level: str = "INFO") -> None:
    """Modo `python -m app.sources.<nome>`: log em stderr, mesmas regras de máscara."""
    _install(logging.StreamHandler(sys.stderr), level)
