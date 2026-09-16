"""Primeira execução: pasta de dados, .env a partir do exemplo e navegador do Playwright."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app import firstrun


@pytest.fixture
def dados(tmp_path, monkeypatch):
    """Isola DATA_DIR/ENV_PATH num diretório temporário."""
    data_dir = tmp_path / "dados"
    exemplo = tmp_path / "pacote" / ".env.example"
    exemplo.parent.mkdir(parents=True)
    exemplo.write_text("TECH_NAME=Fulano\n", encoding="utf-8")
    monkeypatch.setattr(firstrun, "DATA_DIR", data_dir)
    monkeypatch.setattr(firstrun, "ENV_PATH", data_dir / ".env")
    monkeypatch.setattr(firstrun, "ENV_EXAMPLE_PATH", exemplo)
    monkeypatch.setattr(firstrun, "LOG_DIR", data_dir / "logs")
    monkeypatch.setattr(firstrun, "THEMES_DIR", data_dir / "themes")
    monkeypatch.setattr(firstrun, "ensure_data_dir", lambda: (data_dir.mkdir(parents=True, exist_ok=True), data_dir)[1])
    monkeypatch.delenv(firstrun.SKIP_INSTALL_ENV, raising=False)
    return data_dir


def test_cria_pastas_e_env_na_primeira_execucao(dados):
    result = firstrun.bootstrap(install_browser_if_needed=False)
    assert result.problems == []
    assert result.env_created and result.needs_setup
    assert (dados / ".env").read_text(encoding="utf-8") == "TECH_NAME=Fulano\n"
    assert (dados / "logs").is_dir() and (dados / "themes").is_dir()


def test_segunda_execucao_nao_mexe_no_env(dados):
    firstrun.bootstrap(install_browser_if_needed=False)
    (dados / ".env").write_text("TECH_NAME=Preenchido\n", encoding="utf-8")

    result = firstrun.bootstrap(install_browser_if_needed=False)
    assert not result.env_created and not result.needs_setup
    assert (dados / ".env").read_text(encoding="utf-8") == "TECH_NAME=Preenchido\n"


def test_sem_modelo_embalado_vira_problema(dados, monkeypatch):
    monkeypatch.setattr(firstrun, "ENV_EXAMPLE_PATH", dados / "nao-existe.example")
    result = firstrun.bootstrap(install_browser_if_needed=False)
    assert result.problems and "modelo de configuração" in result.problems[0]
    assert not result.env_created


def test_marcador_do_navegador(dados, monkeypatch):
    dados.mkdir(parents=True)
    monkeypatch.setattr(firstrun, "_playwright_version", lambda: "1.62.0")
    monkeypatch.setattr(firstrun, "installed_browsers", lambda *a, **k: ["chromium-1234"])
    assert not firstrun.browser_ready(dados)
    (dados / firstrun.BROWSER_MARKER).write_text("1.62.0", encoding="utf-8")
    assert firstrun.browser_ready(dados)
    (dados / firstrun.BROWSER_MARKER).write_text("1.50.0", encoding="utf-8")
    assert not firstrun.browser_ready(dados)  # atualização trocou a versão: baixa de novo


def test_marcador_sem_navegador_no_disco_nao_vale(dados, monkeypatch):
    """Marcador certo mas pasta do Playwright vazia (limpeza, ou navegador no lugar errado
    como acontecia com o .local-browsers do executável): tem de baixar de novo."""
    dados.mkdir(parents=True)
    monkeypatch.setattr(firstrun, "_playwright_version", lambda: "1.62.0")
    monkeypatch.setattr(firstrun, "installed_browsers", lambda *a, **k: [])
    (dados / firstrun.BROWSER_MARKER).write_text("1.62.0", encoding="utf-8")
    assert not firstrun.browser_ready(dados)


def test_install_browser_escreve_o_marcador(dados, monkeypatch):
    dados.mkdir(parents=True)
    chamadas: list[list[str]] = []
    monkeypatch.setattr(firstrun, "installed_browsers", lambda *a, **k: ["chromium-1234"])

    def fake_run(args, **kwargs):
        chamadas.append([str(a) for a in args])
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(firstrun, "_playwright_version", lambda: "1.62.0")
    monkeypatch.setattr(subprocess, "run", fake_run)
    firstrun.install_browser(dados)
    assert chamadas and chamadas[0][-2:] == ["install", "chromium"]
    assert (dados / firstrun.BROWSER_MARKER).read_text(encoding="utf-8") == "1.62.0"


def test_falha_no_download_vira_problema_sem_derrubar(dados, monkeypatch):
    monkeypatch.setattr(firstrun, "_playwright_version", lambda: "1.62.0")
    monkeypatch.setattr(subprocess, "run",
                        lambda args, **kwargs: subprocess.CompletedProcess(args, 1))
    firstrun.bootstrap(install_browser_if_needed=False)          # cria o .env
    (dados / ".env").write_text("TECH_NAME=Preenchido\n", encoding="utf-8")

    result = firstrun.bootstrap(install_browser_if_needed=True)
    assert result.problems and "navegador" in result.problems[0]
    assert not result.browser_installed
    assert not (dados / firstrun.BROWSER_MARKER).exists()


def test_install_aponta_para_a_pasta_compartilhada(dados, monkeypatch):
    """O download tem de ir para a mesma pasta que a abertura usa (o bug do .local-browsers)."""
    import os

    dados.mkdir(parents=True)
    monkeypatch.setattr(firstrun, "_playwright_version", lambda: "1.62.0")
    monkeypatch.delenv("PLAYWRIGHT_BROWSERS_PATH", raising=False)
    monkeypatch.setattr(subprocess, "run",
                        lambda args, **kwargs: subprocess.CompletedProcess(args, 0))
    firstrun.install_browser(dados)
    assert os.environ["PLAYWRIGHT_BROWSERS_PATH"] == str(firstrun.BROWSERS_DIR)
    assert "local-browsers" not in os.environ["PLAYWRIGHT_BROWSERS_PATH"]


def test_skip_install_pula_o_download(dados, monkeypatch):
    dados.mkdir(parents=True)
    monkeypatch.setenv(firstrun.SKIP_INSTALL_ENV, "1")
    monkeypatch.setattr(firstrun, "install_browser",
                        lambda *a, **k: pytest.fail("não deveria baixar nada"))
    assert firstrun.ensure_browser(dados) is False


def test_env_criado_adia_o_download(dados, monkeypatch):
    """Quem ainda vai preencher o .env não deve esperar 700 MB de download."""
    monkeypatch.setattr(firstrun, "ensure_browser",
                        lambda *a, **k: pytest.fail("não deveria baixar nada"))
    result = firstrun.bootstrap(install_browser_if_needed=True)
    assert result.env_created and not result.browser_installed
