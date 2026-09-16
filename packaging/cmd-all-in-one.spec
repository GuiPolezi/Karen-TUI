# -*- mode: python ; coding: utf-8 -*-
"""Receita do PyInstaller para o CMD ALL-IN-ONE (onedir + console).

Console de verdade porque a TUI é Textual: o atalho abre isto dentro do Windows Terminal.
O Chromium do Playwright NÃO entra aqui (são 700 MB): quem baixa é `app/firstrun.py`, na
primeira execução, para `%LOCALAPPDATA%/ms-playwright`. O driver (node) vem junto pelos
hooks do próprio Playwright.

Uso: .venv/Scripts/python -m PyInstaller packaging/cmd-all-in-one.spec --noconfirm
"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

RAIZ = Path(SPECPATH).resolve().parent
sys.path.insert(0, str(RAIZ))
from app import __version__  # noqa: E402  (precisa da raiz no sys.path)

NOME = "CMD-ALL-IN-ONE"

# recursos só de leitura que o app procura em BUNDLE_DIR (ver app/paths.py)
datas = [
    (str(RAIZ / ".env.example"), "."),
    (str(RAIZ / "themes" / "exemplo.json"), "themes"),
    (str(RAIZ / "app" / "tui" / "styles.tcss"), "app/tui"),
    (str(RAIZ / "README.md"), "."),
]
binaries = []
hiddenimports = ["imap_tools", "pyperclip", "playwright.async_api"]

# textual carrega .tcss e temas por arquivo; playwright carrega o driver node
for pacote in ("textual", "playwright"):
    pacote_datas, pacote_binaries, pacote_hidden = collect_all(pacote)
    datas += pacote_datas
    binaries += pacote_binaries
    hiddenimports += pacote_hidden

versao_numerica = tuple(int(n) for n in (__version__.split(".") + ["0", "0", "0"])[:3]) + (0,)
try:
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo,
        StringFileInfo,
        StringStruct,
        StringTable,
        VarFileInfo,
        VarStruct,
        VSVersionInfo,
    )

    version_info = VSVersionInfo(
        ffi=FixedFileInfo(filevers=versao_numerica, prodvers=versao_numerica),
        kids=[
            StringFileInfo([StringTable("040904B0", [
                StringStruct("CompanyName", "Sino Informática"),
                StringStruct("FileDescription", "CMD ALL-IN-ONE - dashboard de suporte"),
                StringStruct("FileVersion", __version__),
                StringStruct("InternalName", NOME),
                StringStruct("OriginalFilename", f"{NOME}.exe"),
                StringStruct("ProductName", "CMD ALL-IN-ONE"),
                StringStruct("ProductVersion", __version__),
            ])]),
            VarFileInfo([VarStruct("Translation", [0x0409, 1200])]),
        ],
    )
except ImportError:  # fora do Windows o recurso de versão nem existe
    version_info = None

a = Analysis(
    [str(RAIZ / "packaging" / "entrypoint.py")],
    pathex=[str(RAIZ)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "_pytest", "IPython", "matplotlib", "numpy", "PIL"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,      # onedir: mais rápido para abrir e para o instalador trocar
    name=NOME,
    console=True,               # a TUI precisa de um terminal de verdade
    icon=str(RAIZ / "packaging" / "cmd-all-in-one.ico"),
    version=version_info,
    debug=False,
    strip=False,
    upx=False,                  # UPX incomoda antivírus e ganha pouco aqui
)

coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name=NOME)
