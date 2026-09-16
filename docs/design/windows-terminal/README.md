# Esquemas de cores para o Windows Terminal

Um arquivo por tema embutido do CMD ALL-IN-ONE, no formato da lista `schemes` do
`settings.json` do Windows Terminal (`Ctrl+,` → "Abrir arquivo JSON").

## Como usar

1. Abra o `settings.json` e cole o conteúdo de `carbon.json` (ou outro) dentro da lista
   `"schemes": [ ... ]`.
2. No perfil que roda a TUI (`profiles.list[...]`), aponte `"colorScheme": "carbon"` e
   cole as chaves de `perfil-sugerido.json`:

```json
{
  "font": {
    "face": "Cascadia Code",
    "size": 11
  },
  "padding": "4",
  "useAcrylic": false,
  "cursorShape": "bar",
  "intenseTextStyle": "bold",
  "scrollbarState": "hidden",
  "colorScheme": "carbon"
}
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
