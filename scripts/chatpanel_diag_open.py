"""Medição da Fase 6.3: o que acontece no servidor quando o app carrega uma conversa.

Feche a TUI antes. Fluxo:
1. Janela de login (usuário dedicado; captcha humano) -> headless com os cookies, socket
   instrumentado, janela fechada (mesma passagem de bastão da TUI).
2. Espera a conversa do número informado aparecer nas listas com não lidas > 0
   (mande uma mensagem do celular de teste).
3. Carrega a conversa com `POST inc_chat_view.php {number}` dentro da página, SEM
   changeTheInfo (não mexe na lista nem no chat aberto).
4. Por N segundos, grava os frames de socket recebidos; depois pergunta ao servidor
   (control-atende-on-us/-ot.php) se a conversa continua com não lidas.
5. Salva tudo em logs/chatpanel_diag/open_<hora>/ (conversation.html é a base da fixture).

Uso:
    python scripts/chatpanel_diag_open.py 5519999999999 [--wait 180] [--watch 30]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.config import ConfigError, load_settings  # noqa: E402
from app.logging_setup import setup_debug_logging  # noqa: E402
from app.main import force_utf8_console  # noqa: E402
from app.sources.chatpanel import (  # noqa: E402
    LOGGED_OR_LOGIN_SELECTOR,
    LOGGED_SELECTOR,
    SOCKET_SETTLE_MS,
    ChatPanelSource,
)
from chatpanel_diag import FETCH_JS, INIT_JS  # noqa: E402

LI_JS = """
(number) => {
  const li = document.getElementById("chat_" + number);
  if (!li) return null;
  const badge = li.querySelector("span.unread-count2");
  const person = Array.from(li.querySelectorAll("span.badge")).find(b => b.querySelector("i.bi-person"));
  const box = li.closest("div") ? li.closest("div").id : "?";
  return {box, unread: badge ? badge.textContent.trim() : "0", agent: person ? person.textContent.trim() : null,
          active: li.classList.contains("active")};
}
"""

OPEN_JS = """
async (number) => new Promise((resolve) => $.ajax({
  type: "POST", url: "inc_chat_view.php", data: {number: number}, timeout: 20000,
  success: (html) => resolve({ok: true, html: String(html)}),
  error: (xhr) => resolve({ok: false, status: xhr && xhr.status, html: xhr && xhr.responseText}),
}))
"""


def unread_in_list(html: str, number: str) -> str | None:
    match = re.search(r'id="chat_%s".*?</li>' % number, html, re.S)
    if not match:
        return None
    badge = re.search(r'unread-count2"[^>]*>\s*(\d+)', match.group(0))
    return badge.group(1) if badge else "0"


async def main() -> int:
    force_utf8_console()
    setup_debug_logging("INFO")
    parser = argparse.ArgumentParser()
    parser.add_argument("number", help="número com DDI, ex.: 5519999999999")
    parser.add_argument("--wait", type=int, default=180, help="segundos esperando não lidas > 0")
    parser.add_argument("--watch", type=int, default=30, help="segundos observando o socket após abrir")
    args = parser.parse_args()
    number = re.sub(r"\D", "", args.number)
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 2
    out = settings.log_dir / "chatpanel_diag" / ("open_" + datetime.now().strftime("%H%M%S"))
    out.mkdir(parents=True, exist_ok=True)

    source = ChatPanelSource(settings.chatpanel, settings.tech_name)
    source.settings.profile_dir.mkdir(parents=True, exist_ok=True)
    source.login_profile_dir.mkdir(parents=True, exist_ok=True)
    from playwright.async_api import async_playwright

    source._playwright = await async_playwright().start()
    login_ctx = await source._playwright.chromium.launch_persistent_context(
        str(source.login_profile_dir), headless=False, viewport={"width": 1366, "height": 900},
        args=["--disable-blink-features=AutomationControlled"],
    )
    report: dict = {"number": number}
    try:
        page = login_ctx.pages[0] if login_ctx.pages else await login_ctx.new_page()
        await page.goto(settings.chatpanel.url, wait_until="domcontentloaded")
        await page.wait_for_selector(LOGGED_OR_LOGIN_SELECTOR, state="attached", timeout=15000)
        if not await page.query_selector(LOGGED_SELECTOR):
            await source._prefill_login_form(page)
            print("Faça o login na janela (captcha)...", flush=True)
            await page.wait_for_selector(LOGGED_SELECTOR, state="attached", timeout=0)
        user = await page.eval_on_selector(LOGGED_SELECTOR, "el => el.value")
        await page.wait_for_timeout(2000)
        await source._persist_session_cookies(login_ctx)

        # headless com o socket instrumentado, ANTES de fechar a janela
        headless = await source._launch_context(headless=True)
        await headless.context.add_init_script(INIT_JS)
        await source._open_panel(headless)
        await headless.wait_for_timeout(SOCKET_SETTLE_MS)
        await login_ctx.close()
        print(f"{time.strftime('%H:%M:%S')} logado como {user!r}; headless no ar, janela fechada", flush=True)
        report["logged_user"] = user

        # 2) espera não lidas > 0 na conversa do número
        print(f"Esperando até {args.wait}s por não lidas na conversa {number} (mande a mensagem do celular)...", flush=True)
        deadline = time.time() + args.wait
        info = None
        while time.time() < deadline:
            info = await headless.evaluate(LI_JS, number)
            if info and info["unread"] not in ("0", ""):
                break
            await asyncio.sleep(3)
        print(f"{time.strftime('%H:%M:%S')} conversa na lista: {info}", flush=True)
        report["before"] = info
        if not info:
            print("A conversa não está nas listas do usuário dedicado (departamento? número certo?)")
            return 1
        frames_before = await headless.evaluate("() => window.__cp.frames.length")

        # 3) carrega a conversa SEM changeTheInfo
        t_open = time.time()
        resp = await headless.evaluate(OPEN_JS, number)
        (out / "conversation.html").write_text(str(resp.get("html") or ""), encoding="utf-8")
        print(f"{time.strftime('%H:%M:%S')} inc_chat_view.php: ok={resp.get('ok')} chars={len(str(resp.get('html') or ''))}", flush=True)
        report["open"] = {"ok": resp.get("ok"), "chars": len(str(resp.get("html") or "")), "at": t_open}

        # 4) observa o socket
        await headless.wait_for_timeout(args.watch * 1000)
        frames = await headless.evaluate("() => window.__cp.frames")
        new_frames = frames[frames_before:]
        events = []
        for fr in new_frames:
            data = fr["data"]
            if data.startswith("42"):
                try:
                    ev = json.loads(data[2:])[1]
                    content = ev.get("content", {}) if isinstance(ev, dict) else {}
                    inner = content.get("content", {}) if isinstance(content, dict) else {}
                    events.append({"event": content.get("event"), "number": inner.get("number") if isinstance(inner, dict) else None})
                except Exception:
                    events.append({"raw": data[:120]})
        print(f"{time.strftime('%H:%M:%S')} frames de socket após abrir: {events}", flush=True)
        report["socket_events_after_open"] = events

        after_dom = await headless.evaluate(LI_JS, number)
        print(f"DOM local depois: {after_dom}", flush=True)
        report["after_dom"] = after_dom

        # servidor: a conversa ainda tem não lidas?
        server = {}
        for url in ("control-atende-on-us.php", "control-atende-on-ot.php"):
            r = await headless.evaluate(FETCH_JS, url)
            html = str(r.get("html") or "")
            (out / url.replace(".php", ".html")).write_text(html, encoding="utf-8")
            server[url] = unread_in_list(html, number)
        print(f"servidor (não lidas na lista por endpoint): {server}", flush=True)
        report["server_unread_after"] = server
        (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\narquivos em {out}")
    finally:
        try:
            await login_ctx.close()
        except Exception:
            pass
        await source.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
