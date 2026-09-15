"""Mede QUANDO a sessão do ChatPanel morre. Faz o login (janela visível, captcha humano),
mantém a janela aberta e recarrega a página em intervalos; depois fecha, reabre e testa
de novo. Só leitura. Feche a TUI antes.

Uso:
    python scripts/chatpanel_session_probe.py [--checks 30,60,120]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import ConfigError, load_settings  # noqa: E402
from app.logging_setup import setup_debug_logging  # noqa: E402
from app.main import force_utf8_console  # noqa: E402
from app.sources.chatpanel import (  # noqa: E402
    LOGGED_OR_LOGIN_SELECTOR,
    LOGGED_SELECTOR,
    ChatPanelSource,
)


async def logged_in(page) -> str:
    await page.goto(page.url if "chat.php" in page.url else page.url, wait_until="domcontentloaded")
    try:
        await page.wait_for_selector(LOGGED_OR_LOGIN_SELECTOR, state="attached", timeout=15000)
    except Exception:
        return "indefinido"
    el = await page.query_selector(LOGGED_SELECTOR)
    return f"LOGADO ({await el.get_attribute('value')})" if el else "DESLOGADO (tela de login)"


async def main() -> int:
    force_utf8_console()
    setup_debug_logging("INFO")
    parser = argparse.ArgumentParser()
    parser.add_argument("--checks", default="30,60,120", help="segundos após o login em que recarrega")
    args = parser.parse_args()
    checks = [int(x) for x in args.checks.split(",") if x.strip()]
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 2

    source = ChatPanelSource(settings.chatpanel, settings.tech_name)
    source.settings.profile_dir.mkdir(parents=True, exist_ok=True)
    page = await source._launch_context(headless=False)
    try:
        await page.goto(settings.chatpanel.url, wait_until="domcontentloaded")
        if not await page.query_selector(LOGGED_SELECTOR):
            await source._prefill_login_form(page)
            print("Faça o login na janela (captcha)...")
            await page.wait_for_selector(LOGGED_SELECTOR, state="attached", timeout=0)
        user = await page.eval_on_selector(LOGGED_SELECTOR, "el => el.value")
        t0 = time.time()
        print(f"{time.strftime('%H:%M:%S')} login OK como {user!r}; janela fica ABERTA")
        await page.wait_for_timeout(2000)
        await source._persist_session_cookies(source._context)
        for sec in checks:
            wait = t0 + sec - time.time()
            if wait > 0:
                await asyncio.sleep(wait)
            print(f"{time.strftime('%H:%M:%S')} +{sec:>4}s recarga com a janela aberta: {await logged_in(page)}")
        await source._teardown()
        print(f"{time.strftime('%H:%M:%S')} janela fechada; reabrindo headless em 5 s...")
        await asyncio.sleep(5)
        page = await source._launch_context(headless=True)
        await page.goto(settings.chatpanel.url, wait_until="domcontentloaded")
        print(f"{time.strftime('%H:%M:%S')} após reabrir: {await logged_in(page)}")
    finally:
        await source.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
