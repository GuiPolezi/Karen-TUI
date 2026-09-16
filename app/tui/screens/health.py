"""Tela Saúde (F8): estado de cada fonte, latência, próximo ciclo, chamadas do Milldesk no
último minuto, sessão do ChatPanel, tamanho do log e versões."""

from __future__ import annotations

import time
from datetime import datetime

from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static

from app import clock
from app.tui.screens.base import ModeScreen

REFRESH_SECONDS = 2.0
STATUS_TOKEN = {"ok": "ok", "erro": "danger", "não configurada": "text-faint", "aguardando": "text-muted"}


def _ago(stamp: float | None) -> str:
    if stamp is None:
        return "-"
    delta = int(clock.epoch() - stamp)
    return f"há {delta}s" if delta < 120 else f"há {delta // 60}min"


def _in(stamp: float | None) -> str:
    if stamp is None:
        return "-"
    delta = int(stamp - clock.epoch())
    return f"em {delta}s" if delta >= 0 else "agora"


class HealthScreen(ModeScreen):
    MODE = "health"
    TITLE_PT = "Saúde"
    FOOTER = [("r", "atualizar tudo"), ("{key_escape}", "dashboard")]

    def body(self) -> ComposeResult:
        with VerticalScroll(id="health"):
            yield Static("", id="health-sources")
            yield Static("", id="health-extra")

    def on_mount(self) -> None:
        super().on_mount()
        self.refresh_health()
        self.set_interval(REFRESH_SECONDS, self.refresh_health)

    def refresh_content(self) -> None:
        self.refresh_health()

    def refresh_health(self) -> None:
        tokens = self.app.tokens  # type: ignore[attr-defined]
        label = tokens.rich("text-muted")
        info = self.app.health()  # type: ignore[attr-defined]
        table = Table(title="Fontes", title_justify="left", title_style=tokens.rich("text", bold=True),
                      box=None, padding=(0, 2), header_style=tokens.rich("text-faint"))
        for column in ("Fonte", "Status", "Última coleta", "Duração", "Próximo ciclo", "Detalhe"):
            table.add_column(column)
        for row in info["sources"]:
            status = row["status"]
            token = STATUS_TOKEN.get(status.split(":")[0], "text")
            table.add_row(Text(row["label"], style=tokens.rich("text")), Text(status, style=tokens.rich(token)),
                          Text(_ago(row["last_ok"]), style=label),
                          Text(f"{row['duration']:.1f}s" if row["duration"] is not None else "-", style=label),
                          Text(_in(row["next_at"]), style=label), Text(row["detail"], style=label))
        self.query_one("#health-sources", Static).update(table)

        extra = Text()
        extra.append("Milldesk  ", style=label).append(f"{info['milldesk_calls_last_minute']} chamada(s) no último minuto")
        extra.append(f" · cooldown 429: {info['milldesk_cooldown']}\n")
        extra.append("ChatPanel  ", style=label).append(
            f"logado como {info['chatpanel_user'] or '-'} · ressincronização: {info['chatpanel_resync']}"
            f" · session.bin: {'existe' if info['chatpanel_session_file'] else 'ausente'}\n"
        )
        extra.append("Log  ", style=label).append(f"{info['log_path']} · {info['log_size_kb']:.0f} KB\n")
        extra.append("Eventos hoje  ", style=label).append(str(info["events_today"])).append("\n")
        extra.append("Versões  ", style=label).append(info["versions"]).append("\n")
        extra.append("Uptime  ", style=label).append(info["uptime"])
        extra.append(f"   ·   atualizado {clock.now():%H:%M:%S}", style=tokens.rich("text-faint"))
        self.query_one("#health-extra", Static).update(extra)
