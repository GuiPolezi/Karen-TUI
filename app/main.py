"""Entrypoint: python -m app (ou o script instalado app)."""

from __future__ import annotations

import logging
import sys

from app.config import ConfigError, load_settings
from app.logging_setup import setup_logging


def _force_utf8_console() -> None:
    """Consoles do Windows podem estar em cp1252; garante acentos legíveis nas mensagens."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def main() -> int:
    _force_utf8_console()
    try:
        settings = load_settings()
    except ConfigError as exc:
        print("Erro de configuração:\n", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 2

    log_path = setup_logging(settings.log_dir, settings.log_level)
    logging.getLogger("app").info(
        "iniciando: técnico=%s milldesk_key=%s log=%s",
        settings.tech_name,
        settings.milldesk.masked_key,
        log_path,
    )

    from app.tui.app import CmdAllInOneApp  # import tardio: textual é pesado

    CmdAllInOneApp(settings).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
