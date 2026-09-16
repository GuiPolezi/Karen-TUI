r"""Primeira execução: preparar a pasta de dados antes de a TUI subir.

Quem instala o executável não tem `.env` nem o Chromium do Playwright. Este módulo cuida
das duas coisas, sempre de forma idempotente:

1. cria `%LOCALAPPDATA%\CMD-ALL-IN-ONE` (com `logs/` e `themes/`) e copia o `.env.example`
   embalado para `.env` quando ele ainda não existe;
2. baixa o Chromium (`playwright install chromium`, ~700 MB) na primeira execução e depois
   de uma atualização que troque a versão do Playwright; um marcador na pasta de dados
   evita repetir a checagem a cada abertura.

Roda antes da TUI, então aqui `print` é permitido: é a única saída que o usuário vê.
`PLAYWRIGHT_SKIP_INSTALL=1` pula o download (máquina sem internet, instalação manual).
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from app.paths import (
    BROWSERS_DIR,
    DATA_DIR,
    ENV_EXAMPLE_PATH,
    ENV_PATH,
    FROZEN,
    LOG_DIR,
    THEMES_DIR,
    configure_browsers_path,
    ensure_data_dir,
)

log = logging.getLogger("firstrun")

BROWSER_MARKER = ".navegador-ok"       # guarda a versão do Playwright já instalada
INSTALL_TIMEOUT = 30 * 60.0            # 700 MB em rede lenta
SKIP_INSTALL_ENV = "PLAYWRIGHT_SKIP_INSTALL"


@dataclass
class FirstRun:
    """O que a preparação fez; `main` decide o que mostrar a partir daqui."""

    data_dir: Path = field(default_factory=lambda: DATA_DIR)
    env_path: Path = field(default_factory=lambda: ENV_PATH)
    env_created: bool = False        # o .env acabou de ser criado a partir do exemplo
    browser_installed: bool = False  # o download do Chromium rodou agora
    problems: list[str] = field(default_factory=list)

    @property
    def needs_setup(self) -> bool:
        """O usuário precisa editar o .env antes de a TUI ter o que mostrar."""
        return self.env_created


# --- .env -------------------------------------------------------------------------------


def ensure_env(env_path: Path | None = None, example_path: Path | None = None) -> bool:
    """Cria o `.env` a partir do exemplo embalado. Devolve True se criou agora."""
    env_path = ENV_PATH if env_path is None else env_path
    example_path = ENV_EXAMPLE_PATH if example_path is None else example_path
    if env_path.exists():
        return False
    if not example_path.exists():
        raise FileNotFoundError(f"modelo de configuração não encontrado: {example_path}")
    env_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(example_path, env_path)
    log.info("`.env` criado a partir de %s", example_path)
    return True


def open_in_editor(path: Path) -> None:
    """Abre o arquivo no editor padrão do Windows. Falhar aqui não é problema."""
    try:
        opener = getattr(os, "startfile", None)
        if opener is not None:
            opener(str(path))  # type: ignore[operator]
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except OSError as exc:
        log.warning("não consegui abrir %s no editor: %s", path, exc)


# --- navegador do Playwright --------------------------------------------------------------


def probe_browser(timeout: float = 90.0) -> dict:
    """Abre o Chromium e fecha: prova que driver e navegador se encontram.

    É o teste que pega o erro clássico do executável ("Executable doesn't exist at ...");
    usado pelo `--verificar --navegador` e pelo build.
    """
    configure_browsers_path()
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            navegador = pw.chromium.launch(headless=True, timeout=timeout * 1000)
            versao = navegador.version
            navegador.close()
        return {"ok": True, "versao": versao, "pasta": str(browsers_dir())}
    except Exception as exc:
        primeira = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
        return {"ok": False, "erro": f"{type(exc).__name__}: {primeira[:200]}", "pasta": str(browsers_dir())}


def _playwright_version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("playwright")
    except PackageNotFoundError:  # pragma: no cover - só em ambiente quebrado
        return "desconhecida"


def browsers_dir() -> Path:
    """Onde o Playwright guarda os navegadores nesta máquina (e onde vamos baixá-los)."""
    return configure_browsers_path()


def installed_browsers(directory: Path | None = None) -> list[str]:
    """Pastas de Chromium já baixadas (para o diagnóstico do --verificar)."""
    directory = browsers_dir() if directory is None else directory
    if not directory.is_dir():
        return []
    return sorted(p.name for p in directory.glob("chromium*") if p.is_dir())


def browser_ready(data_dir: Path | None = None, expected: str | None = None) -> bool:
    """O Chromium desta versão do Playwright já está instalado nesta máquina?

    Marcador **e** navegador no disco: só o marcador mentiria se alguém limpasse a pasta
    do Playwright (ou se ele tivesse ido para o lugar errado, como acontecia quando o
    executável usava `.local-browsers`).
    """
    marker = (DATA_DIR if data_dir is None else data_dir) / BROWSER_MARKER
    try:
        carimbo = marker.read_text(encoding="utf-8").strip()
    except OSError:
        return False
    return carimbo == (expected or _playwright_version()) and bool(installed_browsers())


def install_browser(data_dir: Path | None = None, timeout: float = INSTALL_TIMEOUT) -> None:
    """Roda `playwright install chromium` usando o driver embalado.

    Escreve o marcador só no sucesso; o download em si é retomável pelo próprio Playwright
    e reexecutar é barato quando o navegador já está lá.
    """
    from playwright._impl._driver import compute_driver_executable, get_driver_env

    data_dir = DATA_DIR if data_dir is None else data_dir
    destino = configure_browsers_path()  # instalar e abrir têm de apontar para o mesmo lugar
    node, cli = compute_driver_executable()
    print(f"Baixando o navegador usado pelo ChatPanel (uma vez só, ~700 MB) em {destino}…", flush=True)
    result = subprocess.run([str(node), str(cli), "install", "chromium"],
                            env=get_driver_env(), timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(f"`playwright install chromium` terminou com código {result.returncode}")
    (data_dir / BROWSER_MARKER).write_text(_playwright_version(), encoding="utf-8")
    log.info("navegador do Playwright instalado")


def ensure_browser(data_dir: Path | None = None) -> bool:
    """Instala o navegador se preciso. Devolve True se rodou o download agora."""
    if os.environ.get(SKIP_INSTALL_ENV, "").strip() in {"1", "true", "yes", "sim"}:
        log.info("download do navegador pulado por %s", SKIP_INSTALL_ENV)
        return False
    data_dir = DATA_DIR if data_dir is None else data_dir
    if browser_ready(data_dir):
        return False
    install_browser(data_dir)
    return True


# --- orquestração --------------------------------------------------------------------------


def bootstrap(*, install_browser_if_needed: bool | None = None) -> FirstRun:
    """Prepara a pasta de dados. Nunca levanta exceção: problemas viram `FirstRun.problems`."""
    if install_browser_if_needed is None:
        install_browser_if_needed = FROZEN  # em desenvolvimento quem instala é o `pip`/`playwright`

    result = FirstRun(data_dir=DATA_DIR, env_path=ENV_PATH)
    configure_browsers_path()  # antes de qualquer uso do Playwright neste processo
    try:
        ensure_data_dir()
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        THEMES_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        result.problems.append(f"não consegui criar a pasta de dados {DATA_DIR}: {exc}")
        return result

    try:
        result.env_created = ensure_env(ENV_PATH, ENV_EXAMPLE_PATH)
    except (OSError, FileNotFoundError) as exc:
        result.problems.append(f"não consegui criar o .env: {exc}")

    if install_browser_if_needed and not result.env_created:
        try:
            result.browser_installed = ensure_browser(DATA_DIR)
        except (OSError, RuntimeError, subprocess.SubprocessError, ImportError) as exc:
            result.problems.append(
                f"não consegui instalar o navegador do ChatPanel: {exc}\n"
                "As outras fontes continuam funcionando; o painel do ChatPanel vai mostrar o erro."
            )
    return result


SETUP_MESSAGE = """\
Primeira execução: criei a configuração em
  {env_path}

O arquivo está abrindo no editor, todo em branco e com um comentário explicando cada
variável. Preencha as obrigatórias — TECH_NAME, EMAIL_IMAP_HOST, EMAIL_USER e
CHATPANEL_URL — mais EMAIL_APP_PASSWORD e MILLDESK_API_KEY, e abra o CMD ALL-IN-ONE de
novo. O que ficar em branco usa o padrão indicado no comentário.

Seus dados (configuração, logs, notas, preferências) ficam em
  {data_dir}
e sobrevivem a qualquer atualização do programa.
"""


if __name__ == "__main__":  # python -m app.firstrun
    import json

    state = bootstrap()
    print(json.dumps({
        "data_dir": str(state.data_dir), "env_path": str(state.env_path),
        "env_created": state.env_created, "browser_installed": state.browser_installed,
        "browser_ready": browser_ready(), "problems": state.problems,
    }, indent=2, ensure_ascii=False))
    sys.exit(1 if state.problems else 0)
