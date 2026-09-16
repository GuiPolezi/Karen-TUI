"""Design tokens: o único lugar onde uma cor tem nome.

Um tema é um `Tokens`. Widgets e `styles.tcss` usam apenas os nomes semânticos
(`$accent`, `$text-muted`, `tokens.rich("danger")`...), nunca uma cor literal. Trocar de
tema não toca em widget: só as variáveis CSS mudam e os painéis re-renderizam as células.

Também vive aqui a função pura de contraste (WCAG 2.x), usada nos testes dos temas
embutidos e no aviso para temas do usuário.
"""

from __future__ import annotations

from dataclasses import dataclass, fields

# nome do token (com hífen, como no CSS) -> descrição curta, na ordem de exibição
TOKEN_NAMES: tuple[str, ...] = (
    "bg", "surface", "surface-raised", "border", "text", "text-muted", "text-faint",
    "accent", "accent-soft", "ok", "warn", "danger", "mine", "other",
)
MIN_CONTRAST_TEXT = 4.5
MIN_CONTRAST_MUTED = 3.0


@dataclass(frozen=True)
class Tokens:
    """Paleta semântica de um tema. Cores em `#rrggbb` ou, para temas ANSI, `ansi_<nome>`."""

    name: str
    bg: str
    surface: str
    surface_raised: str
    border: str
    text: str
    text_muted: str
    text_faint: str
    accent: str
    ok: str
    warn: str
    danger: str
    dark: bool = True
    ansi: bool = False
    accent_soft: str | None = None   # padrão: accent com 15% de opacidade
    mine: str | None = None          # padrão: accent
    other: str | None = None         # padrão: text-muted
    source: str = "embutido"         # embutido | textual | usuário (informativo)

    # --- leitura -------------------------------------------------------------------

    def value(self, token: str) -> str:
        """Valor CSS de um token pelo nome com hífen (`text-muted`)."""
        if token == "accent-soft":
            if self.accent_soft is not None:
                return self.accent_soft
            return self.accent if self.ansi else f"{self.accent} 15%"
        if token == "mine":
            return self.mine or self.accent
        if token == "other":
            return self.other or self.text_muted
        attr = token.replace("-", "_")
        if attr not in {f.name for f in fields(self)}:
            raise KeyError(token)
        return getattr(self, attr)

    def rich(self, token: str, *, bold: bool = False, dim: bool = False, italic: bool = False,
             on: str | None = None) -> str:
        """Estilo Rich (`bold <cor do token>`) para células e textos fora do CSS."""
        parts = []
        if bold:
            parts.append("bold")
        if dim:
            parts.append("dim")
        if italic:
            parts.append("italic")
        color = _rich_color(self.value(token))
        if color:
            parts.append(color)
        if on:
            background = _rich_color(self.value(on))
            if background:
                parts.append(f"on {background}")
        return " ".join(parts)

    def as_dict(self) -> dict[str, str]:
        return {token: self.value(token) for token in TOKEN_NAMES}

    # --- integração com o Textual --------------------------------------------------

    def css_variables(self) -> dict[str, str]:
        """Os tokens como variáveis CSS, mais as variáveis nativas do Textual que os widgets
        embutidos (Input, DataTable, OptionList, Tooltip, Toast, barra de rolagem...) usam,
        para que obedeçam à mesma paleta."""
        t = self.as_dict()
        raised = t["surface-raised"]
        return {
            **t,
            # cores base do Textual
            "background": t["bg"], "surface": t["surface"], "panel": raised, "boost": raised,
            "foreground": t["text"], "primary": t["accent"], "secondary": t["text-muted"],
            "accent": t["accent"], "success": t["ok"], "warning": t["warn"], "error": t["danger"],
            "text": t["text"], "text-muted": t["text-muted"], "text-disabled": t["text-faint"],
            "text-primary": t["accent"], "text-accent": t["accent"], "text-secondary": t["text-muted"],
            "text-success": t["ok"], "text-warning": t["warn"], "text-error": t["danger"],
            "border": t["border"], "border-blurred": t["border"],
            # usadas pelos widgets nativos no modo `:ansi` (tema `terminal`)
            "ansi-background": "ansi_default", "ansi-foreground": "ansi_default",
            # cursor de listas (DataTable, OptionList)
            "block-cursor-background": t["accent-soft"], "block-cursor-foreground": t["text"],
            "block-cursor-text-style": "none",
            "block-cursor-blurred-background": raised, "block-cursor-blurred-foreground": t["text"],
            "block-cursor-blurred-text-style": "none", "block-hover-background": raised,
            # inputs
            "input-cursor-background": t["accent"], "input-cursor-foreground": t["bg"],
            "input-cursor-text-style": "none",
            "input-selection-background": t["accent-soft"], "input-selection-foreground": t["text"],
            # rolagem: discreta, na cor da borda
            "scrollbar": t["border"], "scrollbar-hover": t["text-faint"], "scrollbar-active": t["text-muted"],
            "scrollbar-background": t["surface"], "scrollbar-background-hover": t["surface"],
            "scrollbar-background-active": t["surface"], "scrollbar-corner-color": t["surface"],
            # links (ajuda, launcher)
            "link-color": t["accent"], "link-style": "underline", "link-background": "transparent",
            "link-color-hover": t["accent"], "link-style-hover": "bold underline",
            "link-background-hover": t["accent-soft"],
            # Footer nativo não é usado, mas se aparecer segue a paleta
            "footer-background": t["surface"], "footer-foreground": t["text-muted"],
            "footer-key-foreground": t["accent"], "footer-key-background": t["surface"],
            "footer-description-foreground": t["text-muted"], "footer-description-background": t["surface"],
            "footer-item-background": t["surface"],
        }


def _rich_color(css_value: str) -> str:
    """`#rrggbb` fica como está; `ansi_cyan` vira `cyan`; `ansi_default` vira vazio."""
    value = css_value.split()[0] if css_value else ""
    if value.startswith("ansi_"):
        name = value[len("ansi_"):]
        return "" if name == "default" else name
    return value


# --- contraste (WCAG 2.x) ---------------------------------------------------------------


def relative_luminance(hex_color: str) -> float:
    """Luminância relativa de `#rrggbb` (0 = preto, 1 = branco)."""
    value = hex_color.strip().lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    if len(value) != 6:
        raise ValueError(f"cor inválida: {hex_color!r}")
    channels = []
    for i in (0, 2, 4):
        c = int(value[i:i + 2], 16) / 255
        channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(color_a: str, color_b: str) -> float:
    """Razão de contraste entre duas cores `#rrggbb` (1.0 a 21.0)."""
    la, lb = relative_luminance(color_a), relative_luminance(color_b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def ensure_contrast(color: str, background: str, towards: str, minimum: float = MIN_CONTRAST_MUTED) -> str:
    """Aproxima `color` de `towards` (5% por passo) até atingir o contraste mínimo com
    `background`. Usado ao mapear temas do Textual, cujo `primary` pode ser apagado."""
    from textual.color import Color

    current = Color.parse(color)
    target = Color.parse(towards)
    for _ in range(20):
        if contrast(current.hex, background) >= minimum:
            break
        current = current.blend(target, 0.05)
    return current.hex.lower()


def check_contrast(tokens: Tokens) -> list[str]:
    """Problemas de contraste (vazio = ok). Temas ANSI não são verificáveis (cores do
    terminal), então devolvem lista vazia."""
    if tokens.ansi:
        return []
    problems = []
    checks = (
        ("text", tokens.text, MIN_CONTRAST_TEXT),
        ("text-muted", tokens.text_muted, MIN_CONTRAST_MUTED),
        ("accent", tokens.accent, MIN_CONTRAST_MUTED),
        ("ok", tokens.ok, MIN_CONTRAST_MUTED),
        ("warn", tokens.warn, MIN_CONTRAST_MUTED),
        ("danger", tokens.danger, MIN_CONTRAST_MUTED),
    )
    for name, color, minimum in checks:
        try:
            ratio = contrast(color, tokens.bg)
        except ValueError as exc:
            problems.append(f"{name}: {exc}")
            continue
        if ratio < minimum:
            problems.append(f"{name}/bg = {ratio:.2f} (mínimo {minimum})")
    return problems
