"""Diagnóstico do ChatPanel (só leitura). FECHE A TUI ANTES: o Chromium não abre o
mesmo perfil em dois processos.

Uso:
    python scripts/chatpanel_diag.py            # carga + endpoints de lista
    python scripts/chatpanel_diag.py --watch 180  # idem + observa 180 s de eventos ao vivo

Saída em logs/chatpanel_diag/<hora>/:
    00_page_after_load.html         DOM completo logo após a carga
    01_box_atende_load.html         #box-atende-chats como a página montou
    02_box_atendeothers_load.html   #box-atendeothers-chats idem
    03_box_active_load.html         #box-active-chats (aba Todos) idem
    10_resp_on-us_qsearch.html      resposta crua de control-atende-on-us.php {qsearch: ""}
    11_resp_on-ot_qsearch.html      resposta crua de control-atende-on-ot.php {qsearch: ""}
    12_resp_on_qsearch.html         resposta crua de control-atende-on.php {qsearch: ""}
    20_summary.json                 contagens por caixa (li.checkforactive, ids, badges de pessoa)
    30_watch.json                   (--watch) frames do socket, mutações das caixas e console
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import ConfigError, load_settings  # noqa: E402
from app.main import force_utf8_console  # noqa: E402
from app.sources.chatpanel import LOGGED_OR_LOGIN_SELECTOR, ChatPanelSource  # noqa: E402

BOXES = ("box-atende-chats", "box-atendeothers-chats", "box-active-chats")

FETCH_JS = """
async (url) => new Promise((resolve) => $.ajax({
  type: "POST", url: url, data: {qsearch: ""}, timeout: 20000,
  success: (html) => resolve({ok: true, html: String(html)}),
  error: (xhr) => resolve({ok: false, status: xhr && xhr.status, html: xhr && xhr.responseText}),
}))
"""

BOX_JS = "(id) => { const el = document.getElementById(id); return el ? el.outerHTML : null; }"

# Instalado ANTES da página carregar: grava frames recebidos no WebSocket (socket.io),
# mutações nas caixas de lista (ids de chat por caixa) e a hora de cada evento.
INIT_JS = """
(() => {
  window.__cp = {frames: [], mutations: [], t0: Date.now()};
  const push = (arr, item) => { if (arr.length < 2000) arr.push(item); };
  const OrigWS = window.WebSocket;
  window.WebSocket = function (url, protocols) {
    const ws = protocols === undefined ? new OrigWS(url) : new OrigWS(url, protocols);
    ws.addEventListener("message", (ev) => {
      const data = typeof ev.data === "string" ? ev.data : "[binário]";
      if (data.length > 5) push(window.__cp.frames, {t: Date.now() - window.__cp.t0, data: data.slice(0, 3000)});
    });
    return ws;
  };
  window.WebSocket.prototype = OrigWS.prototype;
  Object.assign(window.WebSocket, OrigWS);
  const ids = (id) => {
    const el = document.getElementById(id);
    if (!el) return null;
    return Array.from(el.querySelectorAll("li.checkforactive")).map(li => li.id + (li.classList.contains("chat-inactive") ? "(inativa)" : ""));
  };
  const snapshot = (why) => push(window.__cp.mutations, {
    t: Date.now() - window.__cp.t0, why,
    atende: ids("box-atende-chats"), others: ids("box-atendeothers-chats"), active: ids("box-active-chats"),
    dup_atende: document.querySelectorAll("#box-atende-chats").length,
    dup_others: document.querySelectorAll("#box-atendeothers-chats").length,
  });
  window.__cp.snapshot = snapshot;
  document.addEventListener("DOMContentLoaded", () => {
    const obs = new MutationObserver(() => {
      clearTimeout(window.__cp._deb);
      window.__cp._deb = setTimeout(() => snapshot("mutation"), 300);
    });
    for (const id of ["box-atende-chats", "box-atendeothers-chats", "box-active-chats"]) {
      const el = document.getElementById(id);
      if (el) obs.observe(el.parentElement || el, {childList: true, subtree: true, attributes: true});
    }
    snapshot("load");
  });
})();
"""


def summarize(html: str | None) -> dict:
    if not html:
        return {"vazio": True}
    return {
        "chars": len(html),
        "li_checkforactive": len(re.findall(r'<li[^>]*class="[^"]*checkforactive', html)),
        "li_inativa": len(re.findall(r'<li[^>]*class="[^"]*chat-inactive', html)),
        "chat_ids": re.findall(r'id="chat_(\d+)"', html),
        "pessoas": re.findall(r'bi-person"></i>\s*([^<]{1,40})', html),
        "tem_wrapper_box": bool(re.search(r'id="box-atende(others)?-chats"', html)),
        "tem_rodape_ver_mais": "viewMoreActive" in html,
        "comeca_com": html.strip()[:100],
    }


async def main() -> int:
    force_utf8_console()
    parser = argparse.ArgumentParser()
    parser.add_argument("--watch", type=int, default=0, help="segundos observando eventos ao vivo")
    args = parser.parse_args()
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 2
    out = settings.log_dir / "chatpanel_diag" / datetime.now().strftime("%H%M%S")
    out.mkdir(parents=True, exist_ok=True)

    source = ChatPanelSource(settings.chatpanel, settings.tech_name)
    console: list[dict] = []
    try:
        page = await source._launch_context(headless=settings.chatpanel.headless)
        await page.context.add_init_script(INIT_JS)
        page.on("console", lambda msg: console.append({"type": msg.type, "text": msg.text[:500]}))
        await page.goto(settings.chatpanel.url, wait_until="domcontentloaded")
        await page.wait_for_selector(LOGGED_OR_LOGIN_SELECTOR, state="attached", timeout=15000)
        if not await page.query_selector("#int_username"):
            print("sessão expirada: faça o login (tecla c na TUI ou scripts/chatpanel_login.py)")
            return 1
        await page.wait_for_timeout(4000)
        (out / "00_page_after_load.html").write_text(await page.content(), encoding="utf-8")
        summary: dict = {}
        for n, box in zip(("01_box_atende_load", "02_box_atendeothers_load", "03_box_active_load"), BOXES):
            html = await page.evaluate(BOX_JS, box)
            (out / f"{n}.html").write_text(html or "", encoding="utf-8")
            summary[n] = summarize(html)
        for n, url in (("10_resp_on-us_qsearch", "control-atende-on-us.php"),
                       ("11_resp_on-ot_qsearch", "control-atende-on-ot.php"),
                       ("12_resp_on_qsearch", "control-atende-on.php")):
            resp = await page.evaluate(FETCH_JS, url)
            (out / f"{n}.html").write_text(str(resp.get("html") or ""), encoding="utf-8")
            summary[n] = {"ok": resp.get("ok"), "status": resp.get("status"), **summarize(resp.get("html"))}
        (out / "20_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2))

        if args.watch > 0:
            print(f"\nObservando {args.watch}s. Mande/receba mensagens e faça uma transferência agora...")
            await page.evaluate("() => window.__cp.snapshot('watch-start')")
            await page.wait_for_timeout(args.watch * 1000)
            await page.evaluate("() => window.__cp.snapshot('watch-end')")
            data = await page.evaluate("() => ({frames: window.__cp.frames, mutations: window.__cp.mutations})")
            data["console"] = console
            (out / "30_watch.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"frames de socket: {len(data['frames'])} · mutações: {len(data['mutations'])} · console: {len(console)}")
        print(f"\narquivos em {out}")
    finally:
        await source.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
