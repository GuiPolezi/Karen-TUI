"""Rodapé próprio (1 linha, sem borda): só os atalhos da tela atual.

Tecla em `accent`, descrição em `text-muted`, dois espaços entre itens. Nunca passa de
uma linha: o que não cabe some, da direita para a esquerda, mas `? ajuda` (o último
item) cabe sempre. A tela informa os itens via `footer_items()` e chama
`refresh_items()` quando eles mudam (ex.: rótulo da ordenação).
"""

from __future__ import annotations

from rich.cells import cell_len
from rich.text import Text
from textual.widgets import Static

FooterItem = tuple[str, str]  # (tecla como aparece, descrição)
GAP = "  "


def fit_items(items: list[FooterItem], width: int, keep_last: bool = True) -> list[FooterItem]:
    """Subconjunto dos itens que cabe em `width` células: remove do fim, preservando o
    último item (ajuda) quando `keep_last`."""
    if not items:
        return []
    last = items[-1] if keep_last else None
    candidates = items[:-1] if keep_last else list(items)

    def total(selection: list[FooterItem]) -> int:
        parts = [f"{key} {label}" for key, label in selection]
        return cell_len(GAP.join(parts)) + 1  # margem esquerda de 1 célula

    while candidates:
        chosen = [*candidates, last] if last else candidates
        if total(chosen) <= width:
            return chosen
        candidates.pop()
    if last and total([last]) <= width:
        return [last]
    return []


class FooterBar(Static):
    def __init__(self) -> None:
        super().__init__("", id="footer")
        self._items: list[FooterItem] = []

    def on_mount(self) -> None:
        self.refresh_items()

    def on_resize(self) -> None:
        self._render_items()

    def refresh_items(self) -> None:
        provider = getattr(self.screen, "footer_items", None)
        self._items = list(provider()) if provider is not None else []
        self._render_items()

    def _render_items(self) -> None:
        tokens = self.app.tokens  # type: ignore[attr-defined]
        width = self.size.width or self.app.size.width
        text = Text(no_wrap=True, overflow="ellipsis")
        text.append(" ")
        for index, (key, label) in enumerate(fit_items(self._items, width)):
            if index:
                text.append(GAP)
            text.append(key, style=tokens.rich("accent", bold=True))
            text.append(f" {label}", style=tokens.rich("text-muted"))
        self.update(text)
