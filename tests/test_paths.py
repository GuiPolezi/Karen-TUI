"""Pasta do pacote x pasta do usuário, em desenvolvimento e no executável.

`app.paths` calcula tudo no import, então cada cenário recarrega o módulo com o ambiente
que se quer testar e o devolve ao estado normal no fim.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

import app.paths


@pytest.fixture
def reload_paths(monkeypatch):
    """Recarrega app.paths com o ambiente combinado e restaura o módulo ao final."""

    def load(*, frozen: bool = False, meipass: str | None = None, env: dict[str, str] | None = None):
        for name in ("CMD_DATA_DIR", "LOCALAPPDATA", "APPDATA"):
            monkeypatch.delenv(name, raising=False)
        for name, value in (env or {}).items():
            monkeypatch.setenv(name, value)
        if frozen:
            monkeypatch.setattr(sys, "frozen", True, raising=False)
        else:
            monkeypatch.delattr(sys, "frozen", raising=False)
        if meipass:
            monkeypatch.setattr(sys, "_MEIPASS", meipass, raising=False)
        else:
            monkeypatch.delattr(sys, "_MEIPASS", raising=False)
        return importlib.reload(app.paths)

    yield load
    importlib.reload(app.paths)


def test_desenvolvimento_usa_a_raiz_do_repositorio(reload_paths):
    paths = reload_paths()
    raiz = Path(__file__).resolve().parent.parent
    assert paths.BUNDLE_DIR == raiz
    assert paths.DATA_DIR == raiz          # em dev nada muda de lugar
    assert paths.ENV_PATH == raiz / ".env"
    assert paths.PREFS_PATH == raiz / "prefs.json"
    assert not paths.FROZEN


def test_executavel_separa_pacote_de_dados(reload_paths, tmp_path):
    extraido = tmp_path / "_MEI123"
    local = tmp_path / "LocalAppData"
    paths = reload_paths(frozen=True, meipass=str(extraido), env={"LOCALAPPDATA": str(local)})
    assert paths.BUNDLE_DIR == extraido                      # só leitura, some ao fechar
    assert paths.DATA_DIR == local / paths.APP_NAME          # sobrevive à atualização
    assert paths.ENV_PATH == local / paths.APP_NAME / ".env"
    assert paths.LOG_DIR == local / paths.APP_NAME / "logs"
    assert paths.ENV_EXAMPLE_PATH == extraido / ".env.example"
    assert paths.INSTALL_DIR == Path(sys.executable).resolve().parent
    assert paths.FROZEN


def test_cmd_data_dir_tem_prioridade(reload_paths, tmp_path):
    portatil = tmp_path / "pendrive"
    paths = reload_paths(frozen=True, meipass=str(tmp_path / "_MEI"),
                         env={"LOCALAPPDATA": str(tmp_path / "ignorado"), "CMD_DATA_DIR": str(portatil)})
    assert paths.DATA_DIR == portatil.resolve()


def test_sem_localappdata_cai_na_pasta_do_usuario(reload_paths, tmp_path):
    paths = reload_paths(frozen=True, meipass=str(tmp_path / "_MEI"))
    assert paths.DATA_DIR == Path.home() / paths.APP_NAME


def test_ensure_data_dir_cria_a_pasta(reload_paths, tmp_path):
    destino = tmp_path / "nova" / "pasta"
    paths = reload_paths(frozen=True, meipass=str(tmp_path / "_MEI"), env={"CMD_DATA_DIR": str(destino)})
    assert paths.ensure_data_dir() == destino.resolve()
    assert destino.is_dir()
    assert paths.ensure_data_dir() == destino.resolve()  # idempotente


def test_describe_mostra_os_caminhos(reload_paths):
    paths = reload_paths()
    dados = paths.describe()
    assert dados["modo"] == "desenvolvimento"
    assert dados["dados"] == str(paths.DATA_DIR)
