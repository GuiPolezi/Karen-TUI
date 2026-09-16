"""Verificação de atualização pelo git: há commits novos no GitHub que a máquina ainda
não tem? Só leitura (`git fetch` + comparação); quem atualiza é o `iniciar.cmd`.

Nunca pede senha (GIT_TERMINAL_PROMPT=0): sem credencial salva, o fetch falha e vira um
aviso no log. Tudo tem timeout; falha nunca derruba a TUI.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from app.config import ROOT_DIR

log = logging.getLogger("update")
FETCH_TIMEOUT = 15.0
QUERY_TIMEOUT = 5.0


@dataclass(frozen=True)
class UpdateStatus:
    checked: bool = False      # a verificação chegou ao fim (com ou sem novidade)
    behind: int = 0            # commits que o GitHub tem e a máquina não
    ahead: int = 0             # commits locais que o GitHub não tem
    local: str = ""            # hash curto local
    remote: str = ""           # hash curto do upstream
    error: str | None = None   # motivo de não ter conseguido verificar

    @property
    def available(self) -> bool:
        return self.checked and self.behind > 0

    def summary(self) -> str:
        if self.error:
            return f"não verificado: {self.error}"
        if not self.checked:
            return "verificando…"
        if self.behind:
            return f"{self.behind} commit(s) novos no GitHub ({self.local} → {self.remote}); feche e abra pelo atalho"
        if self.ahead:
            return f"na versão {self.local} ({self.ahead} commit(s) locais à frente do GitHub)"
        return f"na versão mais recente ({self.local})"


def _git(args: list[str], root: Path, timeout: float) -> str:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "Never"}
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0  # type: ignore[attr-defined]
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=timeout,
                            env=env, creationflags=flags)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip() or f"git {' '.join(args)} falhou")
    return result.stdout.strip()


def check_updates(root: Path = ROOT_DIR, *, fetch: bool = True, fetch_timeout: float = FETCH_TIMEOUT) -> UpdateStatus:
    """Compara HEAD com o upstream. `fetch=False` só compara com o que já foi baixado."""
    if not (root / ".git").exists():
        return UpdateStatus(error="pasta sem repositório git")
    try:
        if fetch:
            _git(["fetch", "--quiet"], root, fetch_timeout)
        local = _git(["rev-parse", "--short", "HEAD"], root, QUERY_TIMEOUT)
        try:
            remote = _git(["rev-parse", "--short", "@{u}"], root, QUERY_TIMEOUT)
        except RuntimeError:
            return UpdateStatus(checked=True, local=local, error="branch sem upstream")
        counts = _git(["rev-list", "--left-right", "--count", "HEAD...@{u}"], root, QUERY_TIMEOUT)
        ahead_text, behind_text = counts.split()
        return UpdateStatus(checked=True, behind=int(behind_text), ahead=int(ahead_text), local=local, remote=remote)
    except FileNotFoundError:
        return UpdateStatus(error="git não encontrado")
    except subprocess.TimeoutExpired:
        return UpdateStatus(error="sem resposta do GitHub (timeout)")
    except (RuntimeError, ValueError) as exc:
        message = str(exc).splitlines()[0] if str(exc) else "erro no git"
        log.warning("verificação de atualização falhou: %s", message)
        return UpdateStatus(error=message[:80])
