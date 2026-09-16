"""Base das modais de detalhe (e-mail, chamado, conversa).

Caixa centrada com largura máxima 100, borda `round accent`, cabeçalho em duas colunas
(rótulo `text-faint` / valor `text`), corpo com rolagem e margem de 2, `LoadingIndicator`
enquanto o worker busca (a modal abre na hora, com o que a lista já sabe) e um
`FooterBar` com os atalhos da modal. `Esc` volta.
"""

from __future__ import annotations

from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import LoadingIndicator, Static

from app.tui.tokens import Tokens
from app.tui.widgets.footer_bar import FooterBar, FooterItem, format_items


def label_value_grid(pairs: list[tuple[str, Text | str]], tokens: Tokens, columns: int = 2) -> Table:
    """Grade rótulo/valor em N colunas (rótulo em text-faint, valor em text)."""
    grid = Table.grid(padding=(0, 2), expand=False)
    for _ in range(columns):
        grid.add_column(style=tokens.rich("text-faint"), no_wrap=True)
        grid.add_column(style=tokens.rich("text"))
    row: list[Text | str] = []
    for label, value in pairs:
        row.extend([label, value if isinstance(value, Text) else Text(str(value), style=tokens.rich("text"))])
        if len(row) == columns * 2:
            grid.add_row(*row)
            row = []
    if row:
        grid.add_row(*row, *[""] * (columns * 2 - len(row)))
    return grid


class DetailScreen(ModalScreen[None]):
    PREFIX = "detail"          # ids: {PREFIX}-header, {PREFIX}-scroll
    FOOTER: list[FooterItem] = [("{key_escape}", "voltar")]

    @property
    def tokens(self) -> Tokens:
        return self.app.tokens  # type: ignore[attr-defined]

    @property
    def icons(self):  # noqa: ANN201
        return self.app.icons  # type: ignore[attr-defined]

    def compose(self) -> ComposeResult:
        with Vertical(id="detail", classes="detail"):
            yield Static("", id=f"{self.PREFIX}-header", classes="detail-header")
            with VerticalScroll(id=f"{self.PREFIX}-scroll", classes="detail-body"):
                yield from self.body_widgets()
            yield LoadingIndicator(classes="detail-loading")
        yield FooterBar()

    def body_widgets(self) -> ComposeResult:
        yield from ()

    def footer_items(self) -> list[FooterItem]:
        return format_items(self.FOOTER, self.icons)

    def refresh_theme(self) -> None:
        for footer in self.query(FooterBar):
            footer.refresh_items()
        self.refresh_content()

    def refresh_content(self) -> None:
        """Subclasses re-renderizam os textos (estilos Rich carregam a cor)."""

    def set_busy(self, busy: bool) -> None:
        for indicator in self.query(LoadingIndicator):
            indicator.display = busy

    def error_text(self, message: str) -> Text:
        return Text(f"{self.icons.error} {message}", style=self.tokens.rich("danger", bold=True))
