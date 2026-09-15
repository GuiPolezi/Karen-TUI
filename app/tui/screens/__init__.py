"""Telas da TUI: uma por modo (Dashboard, E-mail, Milldesk, ChatPanel, Log, Notas) e as
modais de detalhe. Os workers de coleta vivem no App; as telas só leem o estado publicado."""

from __future__ import annotations

from app.tui.screens.base import ModeScreen
from app.tui.screens.chatpanel import ChatPanelScreen
from app.tui.screens.dashboard import DashboardScreen
from app.tui.screens.email import EmailScreen
from app.tui.screens.email_detail import EmailDetailScreen
from app.tui.screens.log import LogScreen
from app.tui.screens.milldesk import MilldeskScreen
from app.tui.screens.notes import NotesScreen
from app.tui.screens.ticket_detail import TicketDetailScreen

MODE_SCREENS: dict[str, type[ModeScreen]] = {
    "dashboard": DashboardScreen,
    "email": EmailScreen,
    "milldesk": MilldeskScreen,
    "chatpanel": ChatPanelScreen,
    "log": LogScreen,
    "notes": NotesScreen,
}

__all__ = [
    "MODE_SCREENS", "ModeScreen", "DashboardScreen", "EmailScreen", "MilldeskScreen",
    "ChatPanelScreen", "LogScreen", "NotesScreen", "EmailDetailScreen", "TicketDetailScreen",
]
