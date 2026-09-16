"""Verificação de atualização (app/update.py) nos dois modos e o aviso na TUI.

O modo git usa um repositório de verdade em tmp_path (bare "GitHub" + clone "máquina") e
pula se o git não estiver no PATH. O modo release usa um `httpx` falso: nenhum teste toca
a rede.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import types
from pathlib import Path

import pytest

from app import update as update_mod
from app.tui import demo
from app.update import (
    UpdateStatus,
    check_git,
    check_release,
    check_updates,
    download_installer,
    is_newer,
    parse_version,
    write_update_script,
)
from tests.helpers import make_app, wait_until

requer_git = pytest.mark.skipif(shutil.which("git") is None, reason="git não encontrado")


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


# --- comparação de versões ------------------------------------------------------------


@pytest.mark.parametrize("texto, esperado", [
    ("v0.2.10", (0, 2, 10)), ("0.1.0", (0, 1, 0)), ("v1", (1,)), ("", (0,)), ("beta", (0,)),
])
def test_parse_version(texto, esperado):
    assert parse_version(texto) == esperado


def test_is_newer_compara_numero_e_nao_texto():
    assert is_newer("v0.2.0", "0.1.9")
    assert is_newer("0.1.10", "0.1.9")      # texto diria o contrário
    assert not is_newer("v0.1.0", "0.1.0")
    assert not is_newer("0.0.9", "0.1.0")


# --- modo git -------------------------------------------------------------------------


@requer_git
def test_git_atualizado_depois_atras_depois_a_frente(repos: tuple[Path, Path]):
    machine, publisher = repos
    status = check_updates(machine, mode="git")
    assert status.checked and status.behind == 0 and status.ahead == 0 and not status.error
    assert "mais recente" in status.summary()

    (publisher / "novo.txt").write_text("x", encoding="utf-8")
    git("add", ".", cwd=publisher)
    git("commit", "-q", "-m", "v2", cwd=publisher)
    git("push", "-q", cwd=publisher)
    status = check_updates(machine, mode="git")
    assert status.available and status.behind == 1 and status.badge() == "1"
    assert "1 commit(s) novos" in status.summary() and "atalho" in status.summary()
    # sem fetch: compara só com o que já foi baixado (já foi, no check anterior)
    assert check_updates(machine, mode="git", fetch=False).behind == 1

    git("config", "user.email", "m@m", cwd=machine)
    git("config", "user.name", "m", cwd=machine)
    git("pull", "-q", "--ff-only", cwd=machine)
    (machine / "local.txt").write_text("y", encoding="utf-8")
    git("add", ".", cwd=machine)
    git("commit", "-q", "-m", "local", cwd=machine)
    status = check_updates(machine, mode="git", fetch=False)
    assert status.ahead == 1 and status.behind == 0 and not status.available
    assert "à frente" in status.summary()


@requer_git
def test_git_erros_nunca_levantam(tmp_path: Path, repos: tuple[Path, Path]):
    assert check_git(tmp_path).error == "pasta sem repositório git"
    machine, _ = repos
    git("checkout", "-q", "-b", "sem-upstream", cwd=machine)
    status = check_git(machine, fetch=False)
    assert status.checked and status.error == "branch sem upstream" and not status.available
    assert "não verificado" in status.summary()


# --- modo release -----------------------------------------------------------------------


class RespostaFalsa:
    def __init__(self, dados: dict, status_code: int = 200):
        self._dados = dados
        self.status_code = status_code
        self.headers: dict[str, str] = {}

    def json(self) -> dict:
        return self._dados

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def httpx_falso(monkeypatch, resposta=None, erro: Exception | None = None, stream=None):
    """Troca o módulo httpx que `app.update` importa dentro das funções."""
    modulo = types.SimpleNamespace()

    def get(url, **kwargs):
        if erro is not None:
            raise erro
        modulo.ultima_url = url
        modulo.ultimos_headers = kwargs.get("headers", {})
        return resposta

    modulo.get = get
    modulo.stream = stream
    monkeypatch.setitem(sys.modules, "httpx", modulo)
    return modulo


RELEASE = {
    "tag_name": "v0.3.0",
    "html_url": "https://github.com/dono/repo/releases/tag/v0.3.0",
    "assets": [
        {"name": "notas.txt", "browser_download_url": "https://exemplo/notas.txt"},
        {"name": "CMD-ALL-IN-ONE-Setup-0.3.0.exe", "browser_download_url": "https://exemplo/setup.exe"},
    ],
}


def test_release_com_versao_nova(monkeypatch):
    httpx_falso(monkeypatch, RespostaFalsa(RELEASE))
    status = check_release(repo="dono/repo", current="0.1.0")
    assert status.checked and status.mode == "release"
    assert status.latest == "0.3.0" and status.available and status.can_install
    assert status.download_url == "https://exemplo/setup.exe"
    assert status.asset_name == "CMD-ALL-IN-ONE-Setup-0.3.0.exe"
    assert status.badge() == "0.3.0"
    assert "0.3.0 disponível" in status.summary() and "Ctrl+U" in status.summary()


def test_release_igual_ou_mais_velho_nao_avisa(monkeypatch):
    httpx_falso(monkeypatch, RespostaFalsa(RELEASE))
    status = check_release(repo="dono/repo", current="0.3.0")
    assert status.checked and not status.available and status.badge() == ""
    assert "mais recente" in status.summary()

    httpx_falso(monkeypatch, RespostaFalsa({**RELEASE, "tag_name": "v0.2.0"}))
    assert not check_release(repo="dono/repo", current="0.9.0").available


def test_release_sem_instalador_so_aponta_a_pagina(monkeypatch):
    httpx_falso(monkeypatch, RespostaFalsa({**RELEASE, "assets": []}))
    status = check_release(repo="dono/repo", current="0.1.0")
    assert status.available and not status.can_install
    assert status.page_url.endswith("/releases/tag/v0.3.0")
    assert "baixe em github.com" in status.summary()


def test_release_sem_nenhuma_publicacao(monkeypatch):
    httpx_falso(monkeypatch, RespostaFalsa({}, status_code=404))
    status = check_release(repo="dono/repo", current="0.1.0")
    assert status.error == "nenhum release publicado ainda" and not status.available
    assert status.page_url == "https://github.com/dono/repo/releases/latest"


def test_release_sem_internet_vira_aviso(monkeypatch):
    httpx_falso(monkeypatch, erro=OSError("getaddrinfo failed"))
    status = check_release(repo="dono/repo", current="0.1.0")
    assert not status.checked and status.error and "getaddrinfo" in status.error
    assert not status.available and "não verificado" in status.summary()


def test_release_manda_user_agent(monkeypatch):
    modulo = httpx_falso(monkeypatch, RespostaFalsa(RELEASE))
    check_release(repo="dono/repo", current="0.1.0")
    assert modulo.ultima_url == "https://api.github.com/repos/dono/repo/releases/latest"
    assert modulo.ultimos_headers["User-Agent"] == "cmd-all-in-one/0.1.0"


# --- download e instalação -----------------------------------------------------------------


class StreamFalso:
    """Contexto que imita `httpx.stream`, entregando o conteúdo em dois pedaços."""

    def __init__(self, pedacos: list[bytes]):
        self.pedacos = pedacos
        self.headers = {"Content-Length": str(sum(len(p) for p in pedacos))}
        self.num_bytes_downloaded = 0

    def __call__(self, method, url, **kwargs):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def raise_for_status(self) -> None:
        return None

    def iter_bytes(self, tamanho: int):
        for pedaco in self.pedacos:
            self.num_bytes_downloaded += len(pedaco)
            yield pedaco


def test_download_grava_o_instalador_e_relata_progresso(monkeypatch, tmp_path):
    httpx_falso(monkeypatch, stream=StreamFalso([b"MZ" * 10, b"resto"]))
    status = UpdateStatus(checked=True, mode="release", current="0.1.0", latest="0.3.0",
                          download_url="https://exemplo/setup.exe", asset_name="Setup.exe")
    vistos: list[tuple[int, int]] = []
    destino = download_installer(status, dest_dir=tmp_path, progress=lambda b, t: vistos.append((b, t)))
    assert destino == tmp_path / "Setup.exe"
    assert destino.read_bytes() == b"MZ" * 10 + b"resto"
    assert vistos[-1] == (25, 25)
    assert not list(tmp_path.glob("*.parcial"))  # o parcial vira o arquivo final


def test_download_sem_url_recusa(tmp_path):
    with pytest.raises(RuntimeError, match="instalador"):
        download_installer(UpdateStatus(checked=True, mode="release"), dest_dir=tmp_path)


def test_script_de_atualizacao_instala_em_silencio_e_reabre(tmp_path):
    script = write_update_script(tmp_path / "Setup.exe", dest_dir=tmp_path, relaunch='start "" "tui.exe"')
    texto = script.read_text(encoding="utf-8")
    assert script.suffix == ".cmd"
    assert "Setup.exe" in texto and "/SILENT" in texto and "/CLOSEAPPLICATIONS" in texto
    assert 'start "" "tui.exe"' in texto
    assert "del " in texto  # o script se apaga no fim


def test_relaunch_usa_o_windows_terminal_quando_existe(monkeypatch, tmp_path):
    monkeypatch.setattr(update_mod.shutil, "which", lambda nome: "C:/wt/wt.exe")
    linha = update_mod.relaunch_command(install_dir=tmp_path, exe=tmp_path / "tui.exe")
    assert "wt.exe" in linha and str(tmp_path) in linha

    monkeypatch.setattr(update_mod.shutil, "which", lambda nome: None)
    linha = update_mod.relaunch_command(install_dir=tmp_path, exe=tmp_path / "tui.exe")
    assert "wt.exe" not in linha and "tui.exe" in linha


# --- integração com a TUI ---------------------------------------------------------------------


async def test_app_mostra_atualizacao_na_topbar_e_no_f8():
    app = make_app(sources=demo.demo_sources())  # prefs_path=None: sem verificação nos testes
    async with app.run_test(size=(120, 35)) as pilot:
        await wait_until(lambda: "milldesk" in app.states)
        assert app._update_enabled is False and app.topbar_extras() == []

        app.apply_update_status(UpdateStatus(checked=True, mode="git", behind=2,
                                             current="abc1234", latest="def5678"))
        await pilot.pause()
        assert app.topbar_extras()[0] == ("⇡ 2", "accent")
        assert "2 commit(s) novos" in app.last_message

        app.apply_update_status(UpdateStatus(checked=True, mode="release", current="0.1.0",
                                             latest="0.3.0", download_url="https://exemplo/setup.exe",
                                             asset_name="Setup.exe"))
        await pilot.pause()
        assert app.topbar_extras()[0] == ("⇡ 0.3.0", "accent")
        assert "0.3.0 disponível" in app.last_message

        app.apply_update_status(UpdateStatus(error="sem resposta do GitHub (timeout)"))
        assert app.topbar_extras() == []


async def test_ctrl_u_sem_atualizacao_so_avisa():
    app = make_app(sources=demo.demo_sources())
    async with app.run_test(size=(120, 35)) as pilot:
        await wait_until(lambda: "milldesk" in app.states)
        app.apply_update_status(UpdateStatus(checked=True, mode="release", current="0.1.0"))
        await pilot.press("ctrl+u")
        await pilot.pause()
        assert "mais recente" in app.last_message
        assert app._updating is False


async def test_ctrl_u_baixa_e_dispara_o_instalador(monkeypatch, tmp_path):
    """Com release instalável, Ctrl+U baixa, chama o instalador e fecha a TUI."""
    baixados: list[UpdateStatus] = []
    disparados: list[Path] = []
    monkeypatch.setattr("app.tui.app.download_installer",
                        lambda status, progress=None: (baixados.append(status), tmp_path / "Setup.exe")[1])
    monkeypatch.setattr("app.tui.app.run_installer",
                        lambda instalador: (disparados.append(instalador), instalador)[1])

    app = make_app(sources=demo.demo_sources())
    async with app.run_test(size=(120, 35)) as pilot:
        await wait_until(lambda: "milldesk" in app.states)
        app.apply_update_status(UpdateStatus(checked=True, mode="release", current="0.1.0",
                                             latest="0.3.0", download_url="https://exemplo/setup.exe",
                                             asset_name="Setup.exe"))
        await pilot.press("ctrl+u")
        await wait_until(lambda: bool(disparados))
    assert baixados and baixados[0].latest == "0.3.0"
    assert disparados == [tmp_path / "Setup.exe"]


async def test_ctrl_u_sem_instalador_abre_a_pagina(monkeypatch):
    abertas: list[str] = []
    monkeypatch.setattr("app.tui.app.webbrowser.open_new_tab", lambda url: abertas.append(url) or True)
    app = make_app(sources=demo.demo_sources())
    async with app.run_test(size=(120, 35)) as pilot:
        await wait_until(lambda: "milldesk" in app.states)
        app.apply_update_status(UpdateStatus(checked=True, mode="release", current="0.1.0", latest="0.3.0",
                                             page_url="https://github.com/dono/repo/releases/tag/v0.3.0"))
        await pilot.press("ctrl+u")
        await pilot.pause()
    assert abertas == ["https://github.com/dono/repo/releases/tag/v0.3.0"]
