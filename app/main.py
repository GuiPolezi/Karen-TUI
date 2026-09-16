"""Entrypoint: python -m app (ou o script instalado app)."""

from __future__ import annotations

import logging
import sys

from app.config import ConfigError, load_settings
from app.firstrun import SETUP_MESSAGE, bootstrap, open_in_editor
from app.logging_setup import setup_logging
from app.paths import FROZEN


def force_utf8_console() -> None:
    """Consoles do Windows podem estar em cp1252; garante acentos legíveis nas mensagens."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def wait_before_closing() -> None:
    """No executável a janela fecha junto com o programa; segura para dar tempo de ler."""
    if not FROZEN:
        return
    try:
        input("\nPressione Enter para fechar…")
    except (EOFError, KeyboardInterrupt):
        pass


def main() -> int:
    force_utf8_console()

    first_run = bootstrap()
    for problem in first_run.problems:
        print(f"Aviso: {problem}\n", file=sys.stderr)
    if first_run.needs_setup:
        print(SETUP_MESSAGE.format(env_path=first_run.env_path, data_dir=first_run.data_dir))
        open_in_editor(first_run.env_path)
        wait_before_closing()
        return 3

    try:
        settings = load_settings()
    except ConfigError as exc:
        print("Erro de configuração:\n", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        wait_before_closing()
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
