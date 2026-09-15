"""Fonte 3: ChatPanel (WhatsApp) por scraping do painel web. Não existe API.

Estratégia A: Chromium headless (Playwright) com perfil persistente. A página fica aberta
entre ciclos (o socket.io do painel já atualiza o DOM) e a cada ciclo lemos o HTML e
parseamos com BeautifulSoup.

Login: a tela de login do ChatPanel tem um captcha, então o login é sempre humano.
`interactive_login()` abre um Chromium VISÍVEL no mesmo perfil, pré-preenche usuário e
senha (se CHATPANEL_USER/CHATPANEL_PASSWORD estiverem no .env) e espera a pessoa
responder o captcha e entrar. A TUI chama isso pela tecla `c` e, uma vez por execução,
sozinha quando detecta sessão expirada. `scripts/chatpanel_login.py` faz o mesmo fora da TUI.

Atenção: o ChatPanel aceita UMA sessão por usuário. Logar aqui derruba a sessão do
navegador normal (e vice-versa). Com o mesmo usuário do técnico isso vira pingue-pongue;
o ideal é um usuário dedicado ao dashboard.

Parser puro: `parse_chatpanel_html(html, tech_name) -> ChatPanelState`, testado contra
tests/fixtures/chatpanel_chat.html.

Modo debug: `python -m app.sources.chatpanel` imprime o ChatPanelState em JSON.
"""

from __future__ import annotations

import asyncio
import re
import sys
import unicodedata
from datetime import datetime
from typing import Any

from bs4 import BeautifulSoup, SoupStrainer, Tag

from app.config import ChatPanelSettings
from app.sources.base import Source, SourceError
from app.state import ChatItem, ChatPanelState

SESSION_EXPIRED = "sessão expirada — pressione c para fazer login (ou rode scripts/chatpanel_login.py)"
LOGIN_HINT = "pressione c (ou rode scripts/chatpanel_login.py) para salvar a sessão"
LOGIN_TIMEOUT = 300.0  # segundos que a janela de login fica aberta esperando a pessoa

# só estes trechos do HTML (≈780 KB) interessam; o SoupStrainer corta o parse de ~2 s para ~0,2 s
_INTERESTING_IDS = {
    "int_username",
    "chat_userid",
    "total-unread2",
    "box-atende-chats",
    "box-atendeothers-chats",
}


LOGIN_FORM_SELECTOR = "input[type='password']"
LOGGED_OR_LOGIN_SELECTOR = f"#int_username, {LOGIN_FORM_SELECTOR}"
LOGGED_SELECTOR = "#int_username"  # input hidden: esperar por presença, não por visibilidade
LOGIN_USER_SELECTOR = "#user"      # tela de login (index.php); o captcha (#captcha) fica com a pessoa
LOGIN_PASSWORD_SELECTOR = "#password"


class SessionExpiredError(Exception):
    """A página não tem o usuário logado (redirecionou para o login). Não é retentada."""

    retry_after = 120.0  # segundos até tentar de novo (dá tempo de fazer o login)


class LoginNotCompletedError(Exception):
    """A janela de login fechou ou o tempo acabou sem o usuário aparecer logado."""


# --- parser puro -------------------------------------------------------------------


def normalize_name(name: str) -> str:
    stripped = unicodedata.normalize("NFKD", name)
    without_accents = "".join(ch for ch in stripped if not unicodedata.combining(ch))
    return " ".join(without_accents.split()).casefold()


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _badge_text(li: Tag, icon_class: str) -> str | None:
    """Texto do badge que contém <i class="bi bi-tag">, <i class="bi bi-star"> etc."""
    for badge in li.select("span.badge"):
        icon = badge.find("i")
        if icon is not None and icon_class in (icon.get("class") or []):
            text = _collapse(badge.get_text(" "))
            return text or None
    return None


def parse_chat_item(li: Tag) -> ChatItem | None:
    raw_id = li.get("id") or ""
    if not isinstance(raw_id, str) or not raw_id.startswith("chat_"):
        return None
    number = raw_id.removeprefix("chat_")

    name = ""
    time_text = ""
    name_p = li.select_one("p.mb-0.fw-medium")
    if name_p is not None:
        time_span = name_p.select_one("span.float-end")
        if time_span is not None:
            time_text = _collapse(time_span.get_text(" "))
        name = _collapse(" ".join(str(t) for t in name_p.find_all(string=True, recursive=False)))

    message_span = li.select_one("span.chat-msg")
    last_message = _collapse(message_span.get_text(" ")) if message_span is not None else ""

    unread = 0
    unread_span = li.select_one("span.unread-count2")
    if unread_span is not None:
        digits = re.sub(r"\D", "", unread_span.get_text())
        unread = int(digits) if digits else 0

    avatar = li.select_one("span.avatar")
    online = avatar is not None and "online" in (avatar.get("class") or [])

    return ChatItem(
        number=number,
        name=name or number,
        time=time_text,
        last_message=last_message,
        unread=unread,
        tag=_badge_text(li, "bi-tag"),
        department=_badge_text(li, "bi-star"),
        agent=_badge_text(li, "bi-person"),
        online=online,
    )


def _active_items(box: Tag | None) -> list[Tag]:
    if box is None:
        return []
    return [
        li for li in box.select("li.checkforactive")
        if "pb-0" not in (li.get("class") or []) and "chat-inactive" not in (li.get("class") or [])
    ]


def parse_chatpanel_html(html: str, tech_name: str) -> ChatPanelState:
    soup = BeautifulSoup(
        html, "html.parser", parse_only=SoupStrainer(id=lambda value: value in _INTERESTING_IDS)
    )

    logged_user: str | None = None
    username_input = soup.find("input", id="int_username")
    if isinstance(username_input, Tag):
        logged_user = _collapse(str(username_input.get("value") or "")) or None

    wanted = normalize_name(tech_name)
    seen: set[str] = set()
    mine: list[ChatItem] = []
    others = 0

    # "SUAS CONVERSAS": tudo aqui é do usuário logado, com ou sem badge de pessoa
    for li in _active_items(soup.find(id="box-atende-chats")):
        item = parse_chat_item(li)
        if item is None or item.number in seen:
            continue
        seen.add(item.number)
        mine.append(item)

    # "EM ATENDIMENTO": filtra pelo badge de pessoa
    for li in _active_items(soup.find(id="box-atendeothers-chats")):
        item = parse_chat_item(li)
        if item is None or item.number in seen:
            continue
        seen.add(item.number)
        if item.agent is not None and normalize_name(item.agent) == wanted:
            mine.append(item)
        else:
            others += 1

    total_unread_tab = 0
    total_badge = soup.find(id="total-unread2")
    if isinstance(total_badge, Tag):
        digits = re.sub(r"\D", "", total_badge.get_text())
        total_unread_tab = int(digits) if digits else 0

    return ChatPanelState(
        mine=mine,
        mine_unread=sum(item.unread for item in mine),
        others_count=others,
        total_unread_tab=total_unread_tab,
        logged_user=logged_user,
        updated_at=datetime.now(),
        error=None,
    )


# --- fonte (Playwright) ------------------------------------------------------------


class ChatPanelSource(Source[ChatPanelState]):
    name = "chatpanel"
    label = "ChatPanel"
    config_hint = LOGIN_HINT

    def __init__(self, settings: ChatPanelSettings, tech_name: str) -> None:
        super().__init__(interval=settings.refresh_seconds, timeout=45.0)
        self.settings = settings
        self.tech_name = tech_name
        self._playwright: Any = None
        self._context: Any = None
        self._page: Any = None

    @property
    def configured(self) -> bool:
        """Sempre ativa: sem perfil salvo o primeiro ciclo cai em "sessão expirada" e a
        TUI abre a janela de login, que cria o perfil."""
        return True

    async def fetch(self) -> ChatPanelState:
        html = await self._get_html()
        state = parse_chatpanel_html(html, self.tech_name)
        if state.logged_user is None:
            # pode ser só um reload pendente; tenta uma vez antes de declarar sessão expirada
            self.log.info("usuário logado não encontrado no DOM; recarregando a página")
            html = await self._get_html(reload=True)
            state = parse_chatpanel_html(html, self.tech_name)
            if state.logged_user is None:
                await self._teardown()
                raise SessionExpiredError(SESSION_EXPIRED)
        if normalize_name(state.logged_user) != normalize_name(self.tech_name):
            self.log.warning(
                "usuário logado no ChatPanel é %r, mas TECH_NAME=%r", state.logged_user, self.tech_name
            )
        return state

    async def close(self) -> None:
        await self._teardown()

    # --- navegador -------------------------------------------------------------

    async def _get_html(self, reload: bool = False) -> str:
        page = await self._ensure_page()
        if reload:
            await self._open_panel(page)
        return await page.content()

    async def _ensure_page(self) -> Any:
        if self._page is not None and not self._page.is_closed():
            return self._page
        page = await self._launch_context(headless=self.settings.headless)
        await self._open_panel(page)
        self._page = page
        return page

    async def _launch_context(self, headless: bool) -> Any:
        """Abre o Chromium no perfil persistente e devolve a primeira página."""
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("playwright não instalado: pip install playwright") from exc

        if self._playwright is None:
            self._playwright = await async_playwright().start()
        self.log.info(
            "abrindo Chromium %s com perfil %s",
            "headless" if headless else "visível",
            self.settings.profile_dir,
        )
        self._context = await self._playwright.chromium.launch_persistent_context(
            str(self.settings.profile_dir),
            headless=headless,
            viewport={"width": 1366, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        return self._context.pages[0] if self._context.pages else await self._context.new_page()

    # --- login humano ------------------------------------------------------------

    async def interactive_login(self, timeout: float = LOGIN_TIMEOUT) -> str:
        """Abre um Chromium VISÍVEL no mesmo perfil e espera a pessoa fazer o login.

        Fecha o headless antes (o perfil não pode estar aberto em dois processos).
        Pré-preenche usuário e senha se estiverem no .env; o captcha e o botão ficam com a
        pessoa. `timeout=0` espera sem limite. Devolve o nome do usuário logado.
        """
        await self._teardown()
        self.settings.profile_dir.mkdir(parents=True, exist_ok=True)
        page = await self._launch_context(headless=False)
        try:
            await page.goto(self.settings.url, wait_until="domcontentloaded")
            try:
                await page.wait_for_selector(LOGGED_OR_LOGIN_SELECTOR, state="attached", timeout=15000)
            except Exception:
                self.log.warning("nem painel nem tela de login apareceram em 15 s (%s)", page.url)
            if not await page.query_selector(LOGGED_SELECTOR):
                await self._prefill_login_form(page)
                self.log.info("janela de login aberta; esperando o login humano (captcha)")
            await page.wait_for_selector(LOGGED_SELECTOR, state="attached", timeout=timeout * 1000)
            user = str(await page.eval_on_selector(LOGGED_SELECTOR, "el => el.value") or "").strip()
            await page.wait_for_timeout(2000)  # deixa cookies/localStorage assentarem
        except Exception as exc:
            raise LoginNotCompletedError(_describe_login_failure(exc, timeout)) from exc
        finally:
            await self._teardown()

        self.log.info("login concluído; usuário logado no ChatPanel: %r", user)
        if normalize_name(user) != normalize_name(self.tech_name):
            self.log.warning("usuário logado é %r, mas TECH_NAME=%r", user, self.tech_name)
        return user

    async def _prefill_login_form(self, page: Any) -> None:
        if not self.settings.prefill_login:
            return
        try:
            await page.fill(LOGIN_USER_SELECTOR, self.settings.user)
            await page.fill(LOGIN_PASSWORD_SELECTOR, self.settings.password)
            self.log.info("usuário e senha pré-preenchidos; falta o captcha")
        except Exception as exc:
            self.log.warning("não consegui pré-preencher o login: %s", exc)

    async def _open_panel(self, page: Any) -> None:
        """Navega até o painel e espera ou o usuário logado ou a tela de login."""
        await page.goto(self.settings.url, wait_until="domcontentloaded")
        try:
            await page.wait_for_selector(LOGGED_OR_LOGIN_SELECTOR, state="attached", timeout=15000)
        except Exception:
            self.log.warning("nem painel nem tela de login apareceram em 15 s (%s)", page.url)
        if await page.query_selector("#int_username"):
            await page.wait_for_timeout(2000)  # deixa o XHR/socket preencher as listas
            return
        # chat.php também tem um input de senha (modal); só é tela de login sem #int_username
        if await page.query_selector(LOGIN_FORM_SELECTOR):
            self.log.info("tela de login detectada em %s", page.url)

    async def _teardown(self) -> None:
        context, self._context = self._context, None
        playwright, self._playwright = self._playwright, None
        self._page = None
        for closer in (
            (context.close if context is not None else None),
            (playwright.stop if playwright is not None else None),
        ):
            if closer is None:
                continue
            try:
                await asyncio.wait_for(closer(), timeout=10)
            except Exception as exc:
                self.log.debug("erro ao fechar navegador: %s", exc)


def _describe_login_failure(exc: BaseException, timeout: float) -> str:
    name = type(exc).__name__
    if "Timeout" in name:
        return f"tempo esgotado ({int(timeout)}s) sem completar o login"
    if "TargetClosed" in name or "closed" in str(exc).lower():
        return "janela de login fechada antes de completar o login"
    text = str(exc).strip().splitlines()[0] if str(exc).strip() else name
    return f"login não concluído: {text}"


# --- modo debug ------------------------------------------------------------------------


async def _debug_main() -> int:
    from app.config import ConfigError, load_settings
    from app.logging_setup import setup_debug_logging
    from app.main import force_utf8_console
    from app.state import to_json

    force_utf8_console()
    setup_debug_logging()
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 2

    if len(sys.argv) > 1:  # modo offline: python -m app.sources.chatpanel arquivo.html
        html = open(sys.argv[1], encoding="utf-8", errors="replace").read()
        print(to_json(parse_chatpanel_html(html, settings.tech_name)))
        return 0

    source = ChatPanelSource(settings.chatpanel, settings.tech_name)
    try:
        state = await source.fetch_with_retry()
    except SourceError as exc:  # ex.: sessão expirada — mensagem limpa, sem traceback
        print(exc, file=sys.stderr)
        return 1
    finally:
        await source.close()
    print(to_json(state))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_debug_main()))
