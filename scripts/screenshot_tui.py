"""Gera uma captura SVG da TUI sem terminal real (útil para revisar o layout).

Uso: python scripts/screenshot_tui.py [largura] [altura]
Saída: logs/screenshot.svg
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import ConfigError, load_settings  # noqa: E402
from app.tui.app import CmdAllInOneApp  # noqa: E402


async def main(width: int, height: int) -> None:
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        sys.exit(2)
    app = CmdAllInOneApp(settings)
    async with app.run_test(size=(width, height)) as pilot:
        await pilot.pause()
        out = settings.log_dir / "screenshot.svg"
        out.parent.mkdir(parents=True, exist_ok=True)
        app.save_screenshot(str(out))
        print(f"captura salva em {out}")


if __name__ == "__main__":
    w = int(sys.argv[1]) if len(sys.argv) > 1 else 120
    h = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    asyncio.run(main(w, h))
