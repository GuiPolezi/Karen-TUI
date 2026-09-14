"""Login manual no ChatPanel, uma única vez.

Abre um Chromium VISÍVEL com o perfil persistente configurado em CHATPANEL_PROFILE_DIR,
navega até CHATPANEL_URL e espera você fazer login. Quando o painel carregar com o
usuário logado (input#int_username no DOM), fecha o navegador e a sessão fica salva.

Uso:
    python scripts/chatpanel_login.py

Importante: feche o app (python -m app) antes de rodar isto. O Chromium não abre o
mesmo perfil em dois processos ao mesmo tempo.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import ConfigError, load_settings  # noqa: E402
from app.main import force_utf8_console  # noqa: E402


def main() -> int:
    force_utf8_console()
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 2

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright não instalado. Rode: pip install playwright && playwright install chromium")
        return 2

    profile_dir = settings.chatpanel.profile_dir
    profile_dir.mkdir(parents=True, exist_ok=True)
    print(f"Perfil: {profile_dir}")
    print(f"Abrindo {settings.chatpanel.url}")
    print("Faça o login no navegador que vai abrir. Esta janela fecha sozinha quando o painel carregar.")

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(profile_dir),
            headless=False,
            viewport={"width": 1366, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(settings.chatpanel.url, wait_until="domcontentloaded")
        try:
            page.wait_for_selector("#int_username", timeout=0)  # espera indefinidamente
        except Exception as exc:  # navegador fechado pelo usuário, por exemplo
            print(f"Não foi possível confirmar o login: {exc}", file=sys.stderr)
            return 1
        user = page.eval_on_selector("#int_username", "el => el.value")
        page.wait_for_timeout(2000)  # deixa cookies/localStorage assentarem
        context.close()

    print(f"Sessão salva. Usuário logado no ChatPanel: {user!r}")
    if user.strip().casefold() != settings.tech_name.strip().casefold():
        print(f"Atenção: TECH_NAME={settings.tech_name!r} é diferente do usuário logado {user!r}.")
    print("Agora rode: python -m app.sources.chatpanel   (teste)  ou  python -m app   (TUI)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
