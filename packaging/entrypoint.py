"""Ponto de entrada do executável (PyInstaller).

Um arquivo só para o PyInstaller ter um script de entrada previsível; toda a lógica está
em `app.main`, igual ao `python -m app`.
"""

from __future__ import annotations

import sys

from app.main import main

if __name__ == "__main__":
    sys.exit(main())
