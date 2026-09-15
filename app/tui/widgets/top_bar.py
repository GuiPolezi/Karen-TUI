"""Barra superior de toda tela: título do app, nome da tela, técnico e relógio."""

from __future__ import annotations

from datetime import datetime

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static

APP_TITLE = "CMD ALL-IN-ONE"


class TopBar(Horizontal):
    def __init__(self, screen_name: str, tech_name: str) -> None:
        super().__init__(id="header")
        self.screen_name = screen_name
        self.tech_name = tech_name

    def compose(self) -> ComposeResult:
        yield Static(f"{APP_TITLE}  ·  {self.screen_name}", id="title")
        yield Static("", id="clock")

    def on_mount(self) -> None:
        self.tick()
        self.set_interval(1.0, self.tick)

    def tick(self) -> None:
        now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        extra = getattr(self.app, "header_extra", "")
        self.query_one("#clock", Static).update(f"{extra}{self.tech_name} · {now}")
