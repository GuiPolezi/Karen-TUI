"""Gera docs/design/windows-terminal/: um esquema de cores por tema embutido (formato
`schemes` do settings.json do Windows Terminal), o trecho de perfil sugerido e um README.

Uso: python scripts/export_wt_schemes.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.tui.themes import WT_DIR, WT_PROFILE_SNIPPET, all_tokens, write_windows_terminal_scheme  # noqa: E402

README = """# Esquemas de cores para o Windows Terminal

Um arquivo por tema embutido do CMD ALL-IN-ONE, no formato da lista `schemes` do
`settings.json` do Windows Terminal (`Ctrl+,` → "Abrir arquivo JSON").

## Como usar

1. Abra o `settings.json` e cole o conteúdo de `carbon.json` (ou outro) dentro da lista
   `"schemes": [ ... ]`.
2. No perfil que roda a TUI (`profiles.list[...]`), aponte `"colorScheme": "carbon"` e
   cole as chaves de `perfil-sugerido.json`:

```json
{profile}
```

- **Fonte:** `Cascadia Code` já vem com o Windows Terminal (sem instalar nada). Para os
  ícones Nerd Font (`ICONS=nerd`), instale `CaskaydiaCove Nerd Font Mono` e troque a
  `face`. Tamanho 11 equilibra densidade e legibilidade em 1080p; 12 em telas maiores.
- `useAcrylic: false`: o acrílico apaga o `dim` e o `text-faint` some.
- `intenseTextStyle: "bold"` (não `"bright"`): senão o `bold` vira outra cor.
- `scrollbarState: "hidden"`: a TUI tem a própria barra de rolagem.
- `padding: "4"` e `cursorShape: "bar"`.

Na TUI, `theme export wt` (no launcher `:`) regrava o esquema do tema atual nesta pasta e
copia o JSON para a área de transferência. O tema `terminal` (`THEME=terminal`) faz o
caminho inverso: usa as 16 cores do esquema que o Windows Terminal já tem.
"""


def main() -> None:
    written = []
    for tokens in all_tokens().values():
        if tokens.ansi or tokens.source != "embutido":
            continue
        written.append(write_windows_terminal_scheme(tokens, WT_DIR))
    (WT_DIR / "perfil-sugerido.json").write_text(json.dumps(WT_PROFILE_SNIPPET, indent=2, ensure_ascii=False) + "\n",
                                                 encoding="utf-8")
    (WT_DIR / "README.md").write_text(README.format(profile=json.dumps(WT_PROFILE_SNIPPET, indent=2, ensure_ascii=False)),
                                      encoding="utf-8")
    for path in written:
        print(path)
    print(WT_DIR / "perfil-sugerido.json")


if __name__ == "__main__":
    main()
