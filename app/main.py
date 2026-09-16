"""Entrypoint: python -m app, o executável instalado ou o script `app`.

Argumentos (úteis para suporte, já que a TUI toma a tela inteira):
  --versao      mostra a versão e sai
  --verificar   mostra caminhos, configuração e dependências em JSON e sai
"""

from __future__ import annotations

import logging
import sys

from app.config import ConfigError, load_settings
from app.firstrun import SETUP_MESSAGE, bootstrap, open_in_editor
from app.logging_setup import setup_logging
from app.paths import FROZEN, describe


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


def self_check() -> dict:
    """Diagnóstico rápido: onde estão os arquivos, o que está instalado, o que falta."""
    from app import __version__
    from app.firstrun import browser_ready, browsers_dir, installed_browsers
    from app.paths import ENV_PATH

    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as package_version

    versions = {}
    for nome, modulo in (("textual", "textual"), ("playwright", "playwright"),
                         ("httpx", "httpx"), ("imap-tools", "imap_tools")):
        try:
            versions[nome] = package_version(nome)
        except PackageNotFoundError:
            # no executável nem todo pacote leva o .dist-info junto; o que importa é importar
            try:
                __import__(modulo)
                versions[nome] = "instalado (sem metadados)"
            except ImportError:
                versions[nome] = "AUSENTE"
    try:
        settings = load_settings()
        config = {"ok": True, "tech_name": settings.tech_name,
                  "email": settings.email.configured, "milldesk": settings.milldesk.configured,
                  "milldesk_key": settings.milldesk.masked_key}
    except ConfigError as exc:
        config = {"ok": False, "erro": str(exc).splitlines()[0]}
    return {"versao": __version__, "caminhos": describe(), "env": str(ENV_PATH),
            "env_existe": ENV_PATH.exists(),
            "navegador": {"instalado_por_nos": browser_ready(), "pasta": str(browsers_dir()),
                          "baixados": installed_browsers()},
            "dependencias": versions, "configuracao": config}


def main(argv: list[str] | None = None) -> int:
    force_utf8_console()
    argv = sys.argv[1:] if argv is None else argv

    if "--versao" in argv or "--version" in argv:
        from app import __version__

        print(__version__)
        return 0

    if "--verificar" in argv or "--check" in argv:
        import json

        bootstrap(install_browser_if_needed=False)
        print(json.dumps(self_check(), indent=2, ensure_ascii=False))
        return 0  # sem pausa: é comando de terminal, roda no build e no CI

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
