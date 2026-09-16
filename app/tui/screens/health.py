"""Tela Saúde (F8): uma linha por fonte (ponto de status, última coleta, duração, próximo
ciclo, detalhe) com a latência dos últimos 30 ciclos em Sparkline; abaixo, Milldesk
(chamadas no último minuto, cooldown 429), sessão do ChatPanel, log, eventos, versões e
uptime."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Sparkline, Static

from app import clock
from app.tui.screens.base import ModeScreen
from app.tui.widgets.top_bar import DOT_STYLE

REFRESH_SECONDS = 2.0
STATUS_TOKEN = {"ok": "ok", "erro": "danger", "não configurada": "text-faint", "aguardando": "text-muted"}
STATUS_DOT = {"ok": "ok", "erro": "danger", "não configurada": "off", "aguardando": "wait"}


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


class HealthRow(Horizontal):
    """Uma fonte: ponto · nome · status · última · duração · próxima · sparkline · detalhe."""

    def __init__(self, name: str) -> None:
        super().__init__(classes="health-row")
        self.source = name

    def compose(self) -> ComposeResult:
        yield Static("", classes="health-dot")
        yield Static("", classes="health-name")
        yield Static("", classes="health-status")
        yield Static("", classes="health-last")
        yield Static("", classes="health-duration")
        yield Static("", classes="health-next")
        yield Sparkline([], classes="health-spark")
        yield Static("", classes="health-detail")

    def update_row(self, row: dict, latency: list[float]) -> None:  # noqa: ANN001
        tokens, icons = self.app.tokens, self.app.icons  # type: ignore[attr-defined]
        status = row["status"]
        key = status.split(":")[0]
        token = STATUS_TOKEN.get(key, "text")
        icon_name, _ = DOT_STYLE.get(STATUS_DOT.get(key, "wait"), DOT_STYLE["wait"])
        glyph = getattr(icons, icon_name or "online")
        muted = tokens.rich("text-muted")
        self.query_one(".health-dot", Static).update(Text(glyph, style=tokens.rich(token)))
        self.query_one(".health-name", Static).update(Text(row["label"], style=tokens.rich("text", bold=True)))
        self.query_one(".health-status", Static).update(Text(status, style=tokens.rich(token)))
        self.query_one(".health-last", Static).update(Text(_ago(row["last_ok"]), style=muted))
        duration = f"{row['duration']:.1f}s" if row["duration"] is not None else "-"
        self.query_one(".health-duration", Static).update(Text(duration, style=muted))
        self.query_one(".health-next", Static).update(Text(_in(row["next_at"]), style=muted))
        spark = self.query_one(Sparkline)
        spark.data = latency or [0.0]
        self.query_one(".health-detail", Static).update(Text(row["detail"], style=tokens.rich("text-faint")))


class HealthScreen(ModeScreen):
    MODE = "health"
    TITLE_PT = "Saúde"
    FOOTER = [("r", "atualizar tudo"), ("{key_escape}", "dashboard")]

    def body(self) -> ComposeResult:
        with VerticalScroll(id="health"):
            yield Static("", id="health-title")
            yield Static("", id="health-columns")
            with Vertical(id="health-sources"):
                for name in ("email", "milldesk", "chatpanel"):
                    yield HealthRow(name)
            yield Static("", id="health-extra")

    def on_mount(self) -> None:
        super().on_mount()
        self.refresh_health()
        self.set_interval(REFRESH_SECONDS, self.refresh_health)

    def refresh_content(self) -> None:
        self.refresh_health()

    def refresh_health(self) -> None:
        tokens, icons = self.app.tokens, self.app.icons  # type: ignore[attr-defined]
        label = tokens.rich("text-muted")
        info = self.app.health()  # type: ignore[attr-defined]
        self.query_one("#health-title", Static).update(Text("Fontes", style=tokens.rich("text", bold=True)))
        columns = Text(style=tokens.rich("text-faint"))
        columns.append("   FONTE        STATUS            ÚLTIMA       DURAÇÃO    PRÓXIMA    LATÊNCIA (30 CICLOS)")
        self.query_one("#health-columns", Static).update(columns)
        rows = {row["name"]: row for row in info["sources"]}
        latency = info.get("latency", {})
        for widget in self.query(HealthRow):
            row = rows.get(widget.source)
            if row is not None:
                widget.update_row(row, latency.get(widget.source, []))

        sep = f" {icons.sep} "
        extra = Text()
        extra.append("Milldesk  ", style=label).append(f"{info['milldesk_calls_last_minute']} chamada(s) no último minuto")
        extra.append(f"{sep}cooldown 429: {info['milldesk_cooldown']}\n")
        extra.append("ChatPanel  ", style=label).append(
            f"logado como {info['chatpanel_user'] or '-'}{sep}ressincronização: {info['chatpanel_resync']}"
            f"{sep}session.bin: {'existe' if info['chatpanel_session_file'] else 'ausente'}\n"
        )
        extra.append("Log  ", style=label).append(f"{info['log_path']}{sep}{info['log_size_kb']:.0f} KB\n")
        extra.append("Eventos hoje  ", style=label).append(str(info["events_today"])).append("\n")
        extra.append("Versões  ", style=label).append(info["versions"]).append("\n")
        extra.append("Terminal  ", style=label).append(info.get("terminal", "?")).append("\n")
        update = info.get("update", "")
        extra.append("Atualização  ", style=label).append(
            update, style=tokens.rich("accent") if "novos" in update else tokens.rich("text")).append("\n")
        extra.append("Uptime  ", style=label).append(info["uptime"])
        extra.append(f"   {icons.sep}   atualizado {clock.now():%H:%M:%S}", style=tokens.rich("text-faint"))
        self.query_one("#health-extra", Static).update(extra)
