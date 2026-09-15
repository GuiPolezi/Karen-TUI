"""DataTable com linhas identificadas por chave.

`set_rows()` recebe a lista completa (chave, células) e aplica um diff: se o conjunto e a
ordem das chaves não mudaram, só as células diferentes são atualizadas; caso contrário a
tabela é remontada. Nos dois casos o cursor volta para a MESMA chave; se ela sumiu, vai
para o vizinho de índice mais próximo. Assim a seleção não "pula" quando o worker publica
um estado novo no meio da navegação.
"""

from __future__ import annotations

from typing import Any

from textual.binding import Binding
from textual.widgets import DataTable

ColumnSpec = tuple[str, str, int | None]  # (chave, rótulo, largura ou None = automática)
Row = tuple[str, list[Any]]               # (chave da linha, células)


class KeyedTable(DataTable):
    BINDINGS = [
        Binding("j", "cursor_down", "Baixo", show=False),
        Binding("k", "cursor_up", "Cima", show=False),
    ]

    def __init__(
        self, columns: list[ColumnSpec], *, id: str | None = None, classes: str | None = None,
        show_header: bool = False,
    ) -> None:
        super().__init__(id=id, classes=classes, cursor_type="row", show_header=show_header, zebra_stripes=False)
        self.column_specs = list(columns)
        self.keys: list[str] = []
        self._cells: dict[str, list[Any]] = {}

    def on_mount(self) -> None:
        self.rebuild_columns(self.column_specs)

    def rebuild_columns(self, columns: list[ColumnSpec]) -> None:
        """Troca o conjunto de colunas (ex.: terminal estreito) e remonta as linhas."""
        self.column_specs = list(columns)
        self.clear(columns=True)
        for key, label, width in self.column_specs:
            self.add_column(label, key=key, width=width)
        rows = [(key, self._cells[key]) for key in self.keys]
        self.keys, self._cells = [], {}
        self.set_rows(rows)

    @property
    def selected_key(self) -> str | None:
        if self.row_count == 0:
            return None
        try:
            return str(self.coordinate_to_cell_key(self.cursor_coordinate).row_key.value)
        except Exception:
            return None

    def set_rows(self, rows: list[Row]) -> None:
        new_keys = [key for key, _ in rows]
        selected = self.selected_key
        old_index = self.cursor_row if self.row_count else 0
        if new_keys == self.keys:
            for key, cells in rows:
                old = self._cells.get(key, [])
                for (column_key, _, _), value, previous in zip(self.column_specs, cells, old):
                    if value != previous:
                        self.update_cell(key, column_key, value)
                self._cells[key] = list(cells)
            return
        self.clear()
        for key, cells in rows:
            self.add_row(*cells, key=key)
            self._cells[key] = list(cells)
        self._cells = {key: self._cells[key] for key in new_keys}
        self.keys = new_keys
        if not new_keys:
            return
        if selected in new_keys:
            self.move_cursor(row=self.get_row_index(selected), animate=False)
        else:
            self.move_cursor(row=min(old_index, len(new_keys) - 1), animate=False)

    def select_key(self, key: str) -> None:
        if key in self.keys:
            self.move_cursor(row=self.get_row_index(key), animate=False)
