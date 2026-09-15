"""Login humano no ChatPanel fora da TUI (a TUI faz o mesmo com a tecla `c`).

Abre um Chromium VISÍVEL com o perfil persistente configurado em CHATPANEL_PROFILE_DIR,
navega até CHATPANEL_URL e espera você fazer o login (usuário, senha e captcha). Se
CHATPANEL_USER e CHATPANEL_PASSWORD estiverem no .env, usuário e senha já vêm
preenchidos. Quando o painel carregar com o usuário logado (input#int_username no DOM),
fecha o navegador e a sessão fica salva.

Uso:
    python scripts/chatpanel_login.py

Importante: feche o app (python -m app) antes de rodar isto. O Chromium não abre o
mesmo perfil em dois processos ao mesmo tempo. Dentro da TUI, prefira a tecla `c`.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import ConfigError, load_settings  # noqa: E402
from app.logging_setup import setup_debug_logging  # noqa: E402
from app.main import force_utf8_console  # noqa: E402
from app.sources.chatpanel import ChatPanelSource, LoginNotCompletedError  # noqa: E402


def main() -> int:
    force_utf8_console()
    setup_debug_logging("WARNING")
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 2

    try:
        import playwright  # noqa: F401
    except ImportError:
        print("playwright não instalado. Rode: pip install playwright && playwright install chromium")
        return 2

    print(f"Perfil: {settings.chatpanel.profile_dir}")
    print(f"Abrindo {settings.chatpanel.url}")
    if settings.chatpanel.prefill_login:
        print("Usuário e senha vêm preenchidos do .env; responda o captcha e clique em Acessar Painel.")
    else:
        print("Faça o login no navegador que vai abrir. A janela fecha sozinha quando o painel carregar.")

    source = ChatPanelSource(settings.chatpanel, settings.tech_name)
    try:
        # sem headless: este script só confere as credenciais e salva os cookies
        user = asyncio.run(source.interactive_login(timeout=0, keep_headless=False))  # 0 = sem limite
    except LoginNotCompletedError as exc:
        print(f"Não foi possível confirmar o login: {exc}", file=sys.stderr)
        return 1

    print(f"Login OK. Usuário logado no ChatPanel: {user!r}")
    print("Atenção: o ChatPanel desloga o usuário quando o socket dele cai. Como esta janela")
    print("fechou, a sessão salva provavelmente já não vale: na TUI, use a tecla c (o app abre a")
    print("janela, sobe o headless e só então fecha a janela, mantendo a sessão).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
