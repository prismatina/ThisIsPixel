# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build definition for ThisIsPixel.

Build with::

    pyinstaller --clean --noconfirm main.spec

The executable is written to ``dist/ThisIsPixel.exe``.
"""

import os

ROOT = os.path.abspath(SPECPATH)
ICON_PATH = os.path.join(ROOT, "asset", "thisispixel.ico")
ICON = ICON_PATH if os.path.exists(ICON_PATH) else None
VERSION_FILE = os.path.join(ROOT, "installer", "version_info.txt")
VERSION = VERSION_FILE if os.path.exists(VERSION_FILE) else None
DATAS = [(ICON_PATH, "asset")] if ICON else []

a = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    binaries=[],
    datas=DATAS,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "numpy", "PIL"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ThisIsPixel",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON,
    version=VERSION,
)
