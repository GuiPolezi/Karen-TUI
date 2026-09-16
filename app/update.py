"""Tem versão nova? E, se tiver, como instalar.

Duas estratégias, escolhidas pelo jeito que o programa está rodando:

- **release** (executável instalado): pergunta ao GitHub qual é o último release
  (`/releases/latest`, repositório público, sem token) e compara com `app.__version__`.
  Quando há novidade, baixa o instalador e o executa; ele fecha a TUI, troca os arquivos
  e a abre de novo.
- **git** (desenvolvimento, pasta com `.git`): `git fetch` + comparação de HEAD com o
  upstream, como sempre; quem atualiza continua sendo o `iniciar.cmd`.

Tudo com timeout, tudo somente leitura até o usuário pedir a instalação, e nada aqui pode
derrubar a TUI: falha vira `UpdateStatus.error`. O git nunca pede senha
(`GIT_TERMINAL_PROMPT=0`).
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app import __version__
from app.paths import BUNDLE_DIR, FROZEN, INSTALL_DIR

log = logging.getLogger("update")

FETCH_TIMEOUT = 15.0
QUERY_TIMEOUT = 5.0
API_TIMEOUT = 10.0
DOWNLOAD_TIMEOUT = 15 * 60.0

GITHUB_REPO = os.environ.get("UPDATE_REPO", "").strip() or "GuiPolezi/Karen-TUI"
RELEASES_API = "https://api.github.com/repos/{repo}/releases/latest"
RELEASES_PAGE = "https://github.com/{repo}/releases/latest"
INSTALLER_SUFFIX = ".exe"
EXE_NAME = "CMD-ALL-IN-ONE.exe"

CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008


@dataclass(frozen=True)
class UpdateStatus:
    """Resultado da verificação. `available` é o que a TopBar e a tela F8 olham."""

    checked: bool = False        # a verificação chegou ao fim (com ou sem novidade)
    mode: str = ""               # "release" | "git"
    current: str = ""            # versão em uso (0.1.0) ou hash curto local
    latest: str = ""             # versão disponível ou hash curto do upstream
    behind: int = 0              # commits que o GitHub tem e a máquina não (só no modo git)
    ahead: int = 0               # commits locais que o GitHub não tem (só no modo git)
    download_url: str = ""       # instalador anexado ao release
    asset_name: str = ""         # nome do arquivo do instalador
    page_url: str = ""           # página do release, para abrir no navegador
    error: str | None = None     # motivo de não ter conseguido verificar

    @property
    def available(self) -> bool:
        if not self.checked:
            return False
        if self.mode == "release":
            return bool(self.latest and self.latest != self.current)
        return self.behind > 0

    @property
    def can_install(self) -> bool:
        """Dá para atualizar sozinho, sem o usuário baixar nada na mão?"""
        return self.available and self.mode == "release" and bool(self.download_url)

    def badge(self) -> str:
        """Texto curto que aparece na TopBar ao lado do ícone."""
        if not self.available:
            return ""
        return self.latest if self.mode == "release" else str(self.behind)

    def summary(self) -> str:
        if self.error:
            return f"não verificado: {self.error}"
        if not self.checked:
            return "verificando…"
        if self.mode == "release":
            if not self.available:
                return f"na versão mais recente ({self.current})"
            como = "Ctrl+U baixa e instala" if self.can_install else f"baixe em github.com/{GITHUB_REPO}"
            return f"versão {self.latest} disponível (você está na {self.current}); {como}"
        if self.behind:
            return (f"{self.behind} commit(s) novos no GitHub ({self.current} → {self.latest}); "
                    "feche e abra pelo atalho")
        if self.ahead:
            return f"na versão {self.current} ({self.ahead} commit(s) locais à frente do GitHub)"
        return f"na versão mais recente ({self.current})"


# --- comparação de versões ------------------------------------------------------------------


def parse_version(text: str) -> tuple[int, ...]:
    """'v0.2.10' -> (0, 2, 10). Sem número nenhum devolve (0,)."""
    numbers = re.findall(r"\d+", text or "")
    return tuple(int(n) for n in numbers) or (0,)


def is_newer(latest: str, current: str) -> bool:
    """O release é mais novo do que a versão instalada?"""
    return parse_version(latest) > parse_version(current)


def normalize(tag: str) -> str:
    """'v0.2.0' -> '0.2.0' (nem o instalador nem o __version__ usam o 'v')."""
    return (tag or "").strip().lstrip("vV")


# --- modo release (executável instalado) ------------------------------------------------------


def check_release(repo: str = "", timeout: float = API_TIMEOUT, current: str = "") -> UpdateStatus:
    """Consulta o último release do GitHub. Nunca levanta exceção."""
    import httpx

    repo = repo or GITHUB_REPO
    current = current or __version__
    page = RELEASES_PAGE.format(repo=repo)
    try:
        response = httpx.get(
            RELEASES_API.format(repo=repo),
            timeout=timeout,
            follow_redirects=True,
            headers={"Accept": "application/vnd.github+json",
                     "User-Agent": f"cmd-all-in-one/{current}"},
        )
        if response.status_code == 404:
            return UpdateStatus(checked=True, mode="release", current=current, page_url=page,
                                error="nenhum release publicado ainda")
        response.raise_for_status()
        data = response.json()
    except Exception as exc:  # httpx tem muitas exceções e nenhuma pode derrubar a TUI
        message = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
        log.warning("verificação de atualização falhou: %s", message)
        return UpdateStatus(mode="release", current=current, page_url=page, error=message[:80])

    latest = normalize(data.get("tag_name") or data.get("name") or "")
    if not latest:
        return UpdateStatus(checked=True, mode="release", current=current, page_url=page,
                            error="release sem tag")
    asset = _pick_installer(data.get("assets") or [])
    return UpdateStatus(
        checked=True,
        mode="release",
        current=current,
        latest=latest if is_newer(latest, current) else current,
        download_url=str(asset.get("browser_download_url", "")) if asset else "",
        asset_name=str(asset.get("name", "")) if asset else "",
        page_url=str(data.get("html_url") or page),
    )


def _pick_installer(assets: list[dict]) -> dict | None:
    """O instalador do release é o primeiro .exe anexado."""
    for asset in assets:
        if str(asset.get("name", "")).lower().endswith(INSTALLER_SUFFIX):
            return asset
    return None


def download_installer(status: UpdateStatus, dest_dir: Path | None = None,
                       progress=None, timeout: float = DOWNLOAD_TIMEOUT) -> Path:
    """Baixa o instalador do release.

    `progress(baixado, total)` é chamado a cada pedaço; grava num `.parcial` e só renomeia
    no fim, para um download interrompido nunca virar um instalador quebrado.
    """
    import httpx

    if not status.download_url:
        raise RuntimeError("este release não tem instalador para baixar")
    dest_dir = Path(tempfile.gettempdir()) if dest_dir is None else dest_dir
    dest_dir.mkdir(parents=True, exist_ok=True)
    destino = dest_dir / (status.asset_name or "cmd-all-in-one-setup.exe")
    parcial = destino.with_name(destino.name + ".parcial")

    with httpx.stream("GET", status.download_url, timeout=timeout, follow_redirects=True) as response:
        response.raise_for_status()
        total = int(response.headers.get("Content-Length") or 0)
        with parcial.open("wb") as arquivo:
            for chunk in response.iter_bytes(256 * 1024):
                arquivo.write(chunk)
                if progress is not None:
                    progress(response.num_bytes_downloaded, total)
    parcial.replace(destino)
    log.info("instalador baixado em %s", destino)
    return destino


# --- instalação -------------------------------------------------------------------------------

# O instalador não consegue trocar um .exe que está aberto, então quem roda é este script:
# a TUI fecha, ele instala em silêncio (o Restart Manager encerra o que sobrar) e reabre.
UPDATE_SCRIPT = """@echo off
rem Gerado pelo CMD ALL-IN-ONE para instalar a atualizacao com a TUI fechada.
"{installer}" /SILENT /SUPPRESSMSGBOXES /NORESTART /FORCECLOSEAPPLICATIONS /RESTARTAPPLICATIONS
{relaunch}
del "%~f0"
"""


def relaunch_command(install_dir: Path | None = None, exe: Path | None = None) -> str:
    """Linha que reabre a TUI: Windows Terminal quando houver, senão o próprio executável."""
    install_dir = INSTALL_DIR if install_dir is None else install_dir
    if exe is None:
        exe = Path(sys.executable) if FROZEN else install_dir / EXE_NAME
    wt = shutil.which("wt.exe")
    if wt:
        return f'start "" "{wt}" -d "{install_dir}" "{exe}"'
    return f'start "" "{exe}"'


def write_update_script(installer: Path, dest_dir: Path | None = None,
                        relaunch: str | None = None) -> Path:
    """Grava o .cmd que instala e reabre. Devolve o caminho dele."""
    dest_dir = Path(tempfile.gettempdir()) if dest_dir is None else dest_dir
    dest_dir.mkdir(parents=True, exist_ok=True)
    script = dest_dir / "cmd-all-in-one-atualizar.cmd"
    script.write_text(
        UPDATE_SCRIPT.format(installer=installer,
                             relaunch=relaunch_command() if relaunch is None else relaunch),
        encoding="utf-8")
    return script


def run_installer(installer: Path, dest_dir: Path | None = None) -> Path:
    """Dispara o script de atualização; quem chama deve fechar a TUI em seguida."""
    script = write_update_script(installer, dest_dir)
    # DETACHED_PROCESS sozinho: o script sobrevive ao fim da TUI e não pisca janela nenhuma
    # (combinar com CREATE_NO_WINDOW não é documentado e pode falhar)
    flags = DETACHED_PROCESS if sys.platform == "win32" else 0
    subprocess.Popen(["cmd", "/c", str(script)], creationflags=flags, close_fds=True)
    log.info("atualização disparada: %s", script)
    return script


# --- modo git (desenvolvimento) -----------------------------------------------------------------


def _git(args: list[str], root: Path, timeout: float) -> str:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "Never"}
    flags = CREATE_NO_WINDOW if sys.platform == "win32" else 0
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=timeout,
                            env=env, creationflags=flags)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip() or f"git {' '.join(args)} falhou")
    return result.stdout.strip()


def check_git(root: Path = BUNDLE_DIR, *, fetch: bool = True,
              fetch_timeout: float = FETCH_TIMEOUT) -> UpdateStatus:
    """Compara HEAD com o upstream. `fetch=False` só compara com o que já foi baixado."""
    if not (root / ".git").exists():
        return UpdateStatus(mode="git", error="pasta sem repositório git")
    try:
        if fetch:
            _git(["fetch", "--quiet"], root, fetch_timeout)
        local = _git(["rev-parse", "--short", "HEAD"], root, QUERY_TIMEOUT)
        try:
            remote = _git(["rev-parse", "--short", "@{u}"], root, QUERY_TIMEOUT)
        except RuntimeError:
            return UpdateStatus(checked=True, mode="git", current=local, error="branch sem upstream")
        counts = _git(["rev-list", "--left-right", "--count", "HEAD...@{u}"], root, QUERY_TIMEOUT)
        ahead_text, behind_text = counts.split()
        return UpdateStatus(checked=True, mode="git", behind=int(behind_text), ahead=int(ahead_text),
                            current=local, latest=remote)
    except FileNotFoundError:
        return UpdateStatus(mode="git", error="git não encontrado")
    except subprocess.TimeoutExpired:
        return UpdateStatus(mode="git", error="sem resposta do GitHub (timeout)")
    except (RuntimeError, ValueError) as exc:
        message = str(exc).splitlines()[0] if str(exc) else "erro no git"
        log.warning("verificação de atualização falhou: %s", message)
        return UpdateStatus(mode="git", error=message[:80])


# --- porta de entrada -----------------------------------------------------------------------------


def check_updates(root: Path = BUNDLE_DIR, *, fetch: bool = True, mode: str = "",
                  fetch_timeout: float = FETCH_TIMEOUT) -> UpdateStatus:
    """Verifica atualização pela estratégia certa. `mode` força "git" ou "release"."""
    mode = mode or ("release" if FROZEN else "git")
    if mode == "release":
        return check_release()
    return check_git(root, fetch=fetch, fetch_timeout=fetch_timeout)


if __name__ == "__main__":  # python -m app.update [git|release]
    import json

    estado = check_updates(mode=sys.argv[1] if len(sys.argv) > 1 else "")
    print(json.dumps({**estado.__dict__, "available": estado.available,
                      "can_install": estado.can_install, "summary": estado.summary()},
                     indent=2, ensure_ascii=False))
