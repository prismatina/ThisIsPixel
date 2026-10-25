# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir build used by the Windows installer.

Build with::

    python -m PyInstaller --clean --noconfirm main_onedir.spec

The result is ``dist/ThisIsPixel/ThisIsPixel.exe`` plus its Qt libraries.
A onedir build starts faster than the single-file build and is far less likely
to be flagged by antivirus software, which makes it the right choice for the
installer handed to end users.
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
    [],
    exclude_binaries=True,
    name="ThisIsPixel",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON,
    version=VERSION,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ThisIsPixel",
)
