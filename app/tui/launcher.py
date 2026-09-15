"""Parser puro do launcher (`:`): texto -> ação. Sem UI, sem rede; testável offline.

Sintaxe `prefixo argumento`; sem prefixo = pesquisa no motor padrão. As URLs base vêm do
`.env` (UrlSettings); favoritos vêm de prefs.json. Nunca "chuta" URL: quando uma base não
está configurada, a ação é um erro com a mensagem "não configurado".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote_plus

from app.config import UrlSettings

SEARCH_ENGINES = {
    "g": ("Google", None),  # None = motor padrão do .env
    "ddg": ("DuckDuckGo", "https://duckduckgo.com/?q={q}"),
    "yt": ("YouTube", "https://www.youtube.com/results?search_query={q}"),
}
MODE_ALIASES = {
    "dash": "dashboard", "dashboard": "dashboard", "email": "email", "mail": "email",
    "tickets": "milldesk", "md": "milldesk", "chats": "chatpanel", "cp": "chatpanel",
    "log": "log", "notes": "notes", "notas": "notes",
}
REFRESH_ALIASES = {"md": "milldesk", "milldesk": "milldesk", "email": "email", "mail": "email",
                   "cp": "chatpanel", "chat": "chatpanel", "chatpanel": "chatpanel"}

HELP_LINES = [
    ("termo  /  g termo", "pesquisa no motor padrão (Google)"),
    ("ddg termo · yt termo", "DuckDuckGo · YouTube"),
    ("md 1234", "abre o detalhe do chamado na TUI"),
    ("md! 1234", "abre o Milldesk no navegador e copia o ID"),
    ("wa 5511999999999", "abre wa.me com o número"),
    ("cp · mail · mdweb", "abre ChatPanel · webmail · Milldesk no navegador"),
    ("open url", "abre uma URL qualquer"),
    ("fav nome", "abre um favorito"),
    ("fav add nome url · fav rm nome · fav", "gerencia/lista favoritos (prefs.json)"),
    ("email · tickets · chats · log · notes · dash", "troca de tela"),
    ("refresh  /  refresh md|email|cp", "atualiza tudo / uma fonte"),
    ("help", "esta lista"),
]


@dataclass
class Action:
    kind: str            # search | open | ticket | goto | refresh | fav_add | fav_rm | fav_list | help | error | empty
    arg: str = ""        # url, id, modo, nome da fonte, mensagem de erro...
    label: str = ""      # texto para o aviso ("Google: termo")
    copy: str = ""       # valor a copiar junto (ex.: ID do chamado no md!)


def _with_scheme(url: str) -> str:
    return url if re.match(r"^[a-z][a-z0-9+.-]*://", url, re.I) else "https://" + url


def parse_command(text: str, favorites: dict[str, str], urls: UrlSettings) -> Action:
    text = text.strip()
    if not text:
        return Action("empty")
    head, _, rest = text.partition(" ")
    head, rest = head.lower(), rest.strip()

    if head in ("help", "?", "ajuda"):
        return Action("help")

    if head in SEARCH_ENGINES:
        if not rest:
            return Action("error", "", f"uso: {head} termo")
        name, template = SEARCH_ENGINES[head]
        template = template or urls.search
        return Action("search", template.replace("{q}", quote_plus(rest)), f"{name}: {rest}")

    if head in ("md", "md!"):
        digits = re.sub(r"\D", "", rest)
        if not digits:
            return Action("error", "", "uso: md 1234 (detalhe na TUI) ou md! 1234 (navegador)")
        if head == "md":
            return Action("ticket", digits, f"chamado #{digits}")
        if not urls.milldesk:
            return Action("error", "", "MILLDESK_WEB_URL não configurada no .env")
        return Action("open", urls.milldesk, f"Milldesk (ID #{digits} copiado)", copy=digits)

    if head == "wa":
        digits = re.sub(r"\D", "", rest)
        if not digits:
            return Action("error", "", "uso: wa 5511999999999")
        return Action("open", f"https://wa.me/{digits}", f"WhatsApp {digits}")

    if head in ("cp", "mail", "mdweb") and not rest:
        url = {"cp": urls.chatpanel, "mail": urls.webmail, "mdweb": urls.milldesk}[head]
        label = {"cp": "ChatPanel", "mail": "webmail", "mdweb": "Milldesk"}[head]
        var = {"cp": "CHATPANEL_WEB_URL", "mail": "WEBMAIL_URL", "mdweb": "MILLDESK_WEB_URL"}[head]
        if not url:
            return Action("error", "", f"{var} não configurada no .env")
        return Action("open", url, label)

    if head == "open":
        if not rest:
            return Action("error", "", "uso: open url")
        return Action("open", _with_scheme(rest), rest)

    if head == "fav":
        parts = rest.split(None, 2)
        if not parts:
            return Action("fav_list")
        sub = parts[0].lower()
        if sub == "add":
            if len(parts) < 3:
                return Action("error", "", "uso: fav add nome url")
            return Action("fav_add", parts[1], _with_scheme(parts[2].strip()))  # label = url
        if sub == "rm":
            if len(parts) < 2:
                return Action("error", "", "uso: fav rm nome")
            return Action("fav_rm", parts[1])
        url = favorites.get(parts[0])
        if url is None:
            return Action("error", "", f"favorito '{parts[0]}' não existe (fav add nome url)")
        return Action("open", url, f"favorito {parts[0]}")

    if head in MODE_ALIASES and not rest:
        return Action("goto", MODE_ALIASES[head], MODE_ALIASES[head])

    if head == "refresh":
        if not rest:
            return Action("refresh", "", "tudo")
        source = REFRESH_ALIASES.get(rest.lower())
        if source is None:
            return Action("error", "", "uso: refresh [md|email|cp]")
        return Action("refresh", source, source)

    # sem prefixo conhecido: pesquisa com o texto inteiro
    return Action("search", urls.search.replace("{q}", quote_plus(text)), f"Google: {text}")
