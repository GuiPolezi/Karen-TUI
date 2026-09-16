"""Verificação de atualização pelo git (app/update.py) e o aviso na TUI.

Usa um repositório git de verdade em tmp_path (bare "GitHub" + clone "máquina"); pula
se o git não estiver no PATH."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from app.tui import demo
from app.update import UpdateStatus, check_updates
from tests.helpers import make_app, wait_until

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git não encontrado")


def git(*args: str, cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def repos(tmp_path: Path) -> tuple[Path, Path]:
    """(clone da máquina, clone de quem publica) apontando para o mesmo remoto bare."""
    remote = tmp_path / "remoto.git"
    git("init", "--bare", "-q", "-b", "main", str(remote), cwd=tmp_path)
    publisher = tmp_path / "publica"
    git("clone", "-q", str(remote), str(publisher), cwd=tmp_path)
    git("config", "user.email", "t@t", cwd=publisher)
    git("config", "user.name", "t", cwd=publisher)
    (publisher / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    git("add", ".", cwd=publisher)
    git("commit", "-q", "-m", "v1", cwd=publisher)
    git("push", "-q", "-u", "origin", "main", cwd=publisher)
    machine = tmp_path / "maquina"
    git("clone", "-q", str(remote), str(machine), cwd=tmp_path)
    return machine, publisher


def test_up_to_date_then_behind_then_ahead(repos: tuple[Path, Path]):
    machine, publisher = repos
    status = check_updates(machine)
    assert status.checked and status.behind == 0 and status.ahead == 0 and not status.error
    assert "mais recente" in status.summary()

    (publisher / "novo.txt").write_text("x", encoding="utf-8")
    git("add", ".", cwd=publisher)
    git("commit", "-q", "-m", "v2", cwd=publisher)
    git("push", "-q", cwd=publisher)
    status = check_updates(machine)
    assert status.available and status.behind == 1
    assert "1 commit(s) novos" in status.summary() and "atalho" in status.summary()
    # sem fetch: compara só com o que já foi baixado (já foi, no check anterior)
    assert check_updates(machine, fetch=False).behind == 1

    git("config", "user.email", "m@m", cwd=machine)
    git("config", "user.name", "m", cwd=machine)
    git("pull", "-q", "--ff-only", cwd=machine)
    (machine / "local.txt").write_text("y", encoding="utf-8")
    git("add", ".", cwd=machine)
    git("commit", "-q", "-m", "local", cwd=machine)
    status = check_updates(machine, fetch=False)
    assert status.ahead == 1 and status.behind == 0 and not status.available
    assert "à frente" in status.summary()


def test_errors_never_raise(tmp_path: Path, repos: tuple[Path, Path]):
    assert check_updates(tmp_path).error == "pasta sem repositório git"
    machine, _ = repos
    git("checkout", "-q", "-b", "sem-upstream", cwd=machine)
    status = check_updates(machine, fetch=False)
    assert status.checked and status.error == "branch sem upstream" and not status.available
    assert "não verificado" in status.summary()


async def test_app_shows_update_in_topbar_and_health():
    app = make_app(sources=demo.demo_sources())  # prefs_path=None: sem git fetch nos testes
    async with app.run_test(size=(120, 35)) as pilot:
        await wait_until(lambda: "milldesk" in app.states)
        assert app._update_enabled is False and app.topbar_extras() == []
        app.apply_update_status(UpdateStatus(checked=True, behind=2, local="abc1234", remote="def5678"))
        await pilot.pause()
        assert app.topbar_extras()[0] == ("⇡ 2", "accent")
        assert "atualização disponível: 2 commit(s)" in app.last_message
        app.apply_update_status(UpdateStatus(error="sem resposta do GitHub (timeout)"))
        assert app.topbar_extras() == []
