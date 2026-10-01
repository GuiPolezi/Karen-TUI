"""Roda o RESYNC_JS real num DOM falso via Node (pulado se o node não estiver instalado)."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from app.sources.chatpanel import RESYNC_JS, parse_chatpanel_html

HARNESS = Path(__file__).parent / "resync_js_harness.js"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node não instalado")


def run_harness(tmp_path: Path, mode: str, scenario: str = "normal") -> dict:
    js_file = tmp_path / "resync.js"
    js_file.write_text(RESYNC_JS, encoding="utf-8")
    proc = subprocess.run(
        [NODE, str(HARNESS), str(js_file), mode, scenario], capture_output=True, text=True, timeout=30, check=True
    )
    return json.loads(proc.stdout.strip().splitlines()[-1])


def _numbers(html: str) -> list[str]:
    return re.findall(r'id="chat_(\d+)"', html)


def test_full_mode_reloads_first_page_and_follows_view_more(tmp_path: Path):
    out = run_harness(tmp_path, "full")
    assert out["result"]["failed"] == 0
    assert out["result"]["ok"] == 2
    assert out["result"]["pages"] == 2  # páginas 2 e 3 da lista "us"
    assert _numbers(out["boxes"]["box-atende-chats"]) == ["101", "102", "103", "104"]
    assert _numbers(out["boxes"]["box-atendeothers-chats"]) == ["201"]
    assert "box-bottom-activeus-services" not in out["boxes"]["box-atende-chats"]  # rodapé some no fim
    # as 1ªs páginas vêm antes de qualquer troca no DOM; com conversa na resposta, a sessão
    # está viva e a página não é consultada (nenhuma chamada com page 0)
    assert [(c["url"].split("-")[-1], c["page"]) for c in out["calls"]] == [
        ("us.php", 1), ("ot.php", 1), ("us.php", 2), ("us.php", 3),
    ]
    assert out["result"]["session"] == "alive"
    assert out["result"]["kept"] == 0


def test_full_mode_keeps_lists_when_server_session_is_dead(tmp_path: Path):
    """Sessão morta no servidor: os endpoints devolvem vazio e a página cai no login.
    Trocar o HTML apagaria as conversas que o socket mantém certas no DOM."""
    out = run_harness(tmp_path, "full", "dead")
    assert out["result"]["session"] == "dead"
    assert out["result"]["kept"] == 2
    assert out["result"]["ok"] == 0
    assert _numbers(out["boxes"]["box-atende-chats"]) == ["101", "102"]  # DOM intacto
    assert _numbers(out["boxes"]["box-atendeothers-chats"]) == ["201"]
    assert [c["page"] for c in out["calls"]] == [1, 1, 0]  # 2 listas + 1 consulta da sessão
    probe = out["calls"][-1]
    assert probe["url"] == "https://x/chat.php"  # a própria página
    assert probe["cache"] is False  # nunca a cópia em cache da carga (daria "viva" errado)


def test_full_mode_does_not_check_the_session_when_dom_has_nothing_to_lose(tmp_path: Path):
    out = run_harness(tmp_path, "full", "empty-dom")
    assert "session" not in out["result"]
    assert out["result"]["ok"] == 2 and out["result"]["kept"] == 0
    assert [c["page"] for c in out["calls"]] == [1, 1]  # nenhuma consulta da sessão


def test_full_mode_applies_empty_lists_when_session_is_alive(tmp_path: Path):
    """Lista vazia de verdade (a última conversa terminou): com a sessão confirmada, aplica."""
    out = run_harness(tmp_path, "full", "empty-alive")
    assert out["result"]["session"] == "alive"
    assert out["result"]["kept"] == 0
    assert out["result"]["ok"] == 2
    assert _numbers(out["boxes"]["box-atende-chats"]) == []
    assert _numbers(out["boxes"]["box-atendeothers-chats"]) == []


def test_full_mode_keeps_lists_when_session_cannot_be_checked(tmp_path: Path):
    """Sem resposta da consulta (rede), não dá para saber: na dúvida o DOM fica."""
    out = run_harness(tmp_path, "full", "probe-error")
    assert out["result"]["session"] == "unknown"
    assert out["result"]["kept"] == 2
    assert _numbers(out["boxes"]["box-atende-chats"]) == ["101", "102"]
    assert _numbers(out["boxes"]["box-atendeothers-chats"]) == ["201"]


def test_expand_mode_never_checks_the_session(tmp_path: Path):
    out = run_harness(tmp_path, "expand", "dead")
    assert "session" not in out["result"]
    assert all(c["page"] != 0 for c in out["calls"])
    assert _numbers(out["boxes"]["box-atendeothers-chats"]) == ["201"]


def test_expand_mode_only_loads_missing_pages(tmp_path: Path):
    out = run_harness(tmp_path, "expand")
    assert out["result"]["failed"] == 0
    assert out["result"]["ok"] == 0  # não recarrega a 1ª página
    assert out["result"]["pages"] == 2
    assert _numbers(out["boxes"]["box-atende-chats"]) == ["101", "102", "103", "104"]
    assert [c["page"] for c in out["calls"]] == [2, 3]


def test_parser_sees_every_page_after_expand(tmp_path: Path):
    out = run_harness(tmp_path, "expand")
    html = (
        '<input type="hidden" id="int_username" value="Guilherme">'
        f'<div id="box-atende-chats">{out["boxes"]["box-atende-chats"]}</div>'
        f'<div id="box-atendeothers-chats">{out["boxes"]["box-atendeothers-chats"]}</div>'
    )
    state = parse_chatpanel_html(html, "Guilherme")
    assert [c.number for c in state.mine] == ["101", "102", "103", "104"]
    assert state.others_count == 1
