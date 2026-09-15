"""Preferências do usuário em prefs.json (raiz do projeto, gitignored). Nunca segredos.

Guarda coisas como a última tela aberta, ordenação escolhida, favoritos e histórico do
launcher. Leitura tolerante: arquivo ausente ou corrompido vira preferências padrão.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app.config import ROOT_DIR

PREFS_PATH = ROOT_DIR / "prefs.json"
MAX_HISTORY = 50

log = logging.getLogger("prefs")


@dataclass
class Prefs:
    last_screen: str = "dashboard"
    milldesk_sort: str = "sla"            # sla | data | status
    chatpanel_show_others: bool = False   # mostrar "com outros técnicos" na tela F4
    email_only_unseen: bool = False
    favorites: dict[str, str] = field(default_factory=dict)  # launcher: nome -> url
    history: list[str] = field(default_factory=list)          # launcher: últimos comandos
    silenced_until: float = 0.0                               # modo silêncio (epoch)

    def push_history(self, command: str) -> None:
        command = command.strip()
        if not command:
            return
        if command in self.history:
            self.history.remove(command)
        self.history.append(command)
        del self.history[:-MAX_HISTORY]


def load_prefs(path: Path = PREFS_PATH) -> Prefs:
    if not path.exists():
        return Prefs()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("prefs.json ilegível (%s); usando padrões", exc)
        return Prefs()
    prefs = Prefs()
    for key, value in (raw or {}).items():
        if hasattr(prefs, key) and isinstance(value, type(getattr(prefs, key))):
            setattr(prefs, key, value)
    return prefs


def save_prefs(prefs: Prefs, path: Path = PREFS_PATH) -> None:
    try:
        path.write_text(json.dumps(asdict(prefs), ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        log.warning("não consegui salvar %s: %s", path.name, exc)
