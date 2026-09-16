r"""Onde cada arquivo mora.

Em desenvolvimento (`python -m app`) tudo continua na raiz do repositório. Dentro do
executável as duas pastas se separam:

- `BUNDLE_DIR`: o que vem embalado e é **somente leitura** (`.env.example`, `themes/`,
  `docs/`). Em modo onefile é a pasta temporária de extração (`sys._MEIPASS`), que some
  quando o programa fecha — nada gravado ali sobrevive.
- `DATA_DIR`: o que é do usuário e precisa sobreviver a uma atualização (`.env`, `logs/`,
  `prefs.json`, `notes.md`, perfil do Chromium). Fica em
  `%LOCALAPPDATA%\CMD-ALL-IN-ONE`, fora da pasta que o instalador substitui.

`CMD_DATA_DIR` no ambiente força a pasta de dados (testes, ou uso portátil em pendrive).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "CMD-ALL-IN-ONE"
DATA_DIR_ENV = "CMD_DATA_DIR"

#: rodando a partir de um executável gerado pelo PyInstaller?
FROZEN = bool(getattr(sys, "frozen", False))


def _bundle_dir() -> Path:
    """Pasta com os recursos embalados (só leitura no executável)."""
    if FROZEN:
        meipass = getattr(sys, "_MEIPASS", None)  # onefile: pasta temporária de extração
        return Path(meipass) if meipass else Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _data_dir(bundle: Path) -> Path:
    """Pasta gravável do usuário. Em dev é a própria raiz do repositório."""
    override = os.environ.get(DATA_DIR_ENV, "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if not FROZEN:
        return bundle
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    return (Path(base) if base else Path.home()) / APP_NAME


BUNDLE_DIR = _bundle_dir()
DATA_DIR = _data_dir(BUNDLE_DIR)

#: pasta onde o executável está instalado (o instalador substitui só ela). Em dev, a raiz.
INSTALL_DIR = Path(sys.executable).resolve().parent if FROZEN else BUNDLE_DIR

ENV_PATH = DATA_DIR / ".env"
ENV_EXAMPLE_PATH = BUNDLE_DIR / ".env.example"
LOG_DIR = DATA_DIR / "logs"
PREFS_PATH = DATA_DIR / "prefs.json"
NOTES_PATH = DATA_DIR / "notes.md"
THEMES_DIR = DATA_DIR / "themes"
BUNDLED_THEMES_DIR = BUNDLE_DIR / "themes"
WT_SCHEMES_DIR = DATA_DIR / "docs" / "design" / "windows-terminal"

#: onde o Playwright guarda os navegadores. Fora da pasta do programa de propósito: o
#: instalador substitui a pasta do programa a cada atualização, e são ~700 MB.
BROWSERS_DIR = (Path(os.environ["LOCALAPPDATA"]) if os.environ.get("LOCALAPPDATA")
                else Path.home() / "AppData" / "Local") / "ms-playwright"

PLAYWRIGHT_BROWSERS_PATH = "PLAYWRIGHT_BROWSERS_PATH"


def configure_browsers_path() -> Path:
    """Aponta o Playwright para `BROWSERS_DIR` e devolve a pasta escolhida.

    Dentro de um executável o Playwright assume `PLAYWRIGHT_BROWSERS_PATH=0`
    (`playwright/_impl/_transport.py`), o que significa "o navegador está embalado junto,
    em `.local-browsers`" — e não está: são 700 MB que baixamos à parte. Sem isto, a
    instalação vai para um lugar e a abertura procura em outro
    ("Executable doesn't exist at ...local-browsers...").

    Respeita quem já definiu a variável na mão; idempotente.
    """
    atual = os.environ.get(PLAYWRIGHT_BROWSERS_PATH, "").strip()
    if atual and atual != "0":
        return Path(atual)
    os.environ[PLAYWRIGHT_BROWSERS_PATH] = str(BROWSERS_DIR)
    return BROWSERS_DIR


def ensure_data_dir() -> Path:
    """Cria a pasta de dados (e a de logs) na primeira execução. Idempotente."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR


def describe() -> dict[str, str]:
    """Caminhos em texto para a tela F8 e para o modo debug."""
    return {
        "modo": "executável" if FROZEN else "desenvolvimento",
        "navegadores": str(BROWSERS_DIR),
        "pacote": str(BUNDLE_DIR),
        "dados": str(DATA_DIR),
        "instalação": str(INSTALL_DIR),
    }


if __name__ == "__main__":  # python -m app.paths
    import json

    print(json.dumps(describe(), indent=2, ensure_ascii=False))
