#!/usr/bin/env python3
"""
ThisIsPixel - release builder
=============================
Builds everything an end user needs:

1. ``dist/ThisIsPixel/``                  onedir application (fast, AV friendly)
2. ``dist/ThisIsPixel-Setup-<ver>.exe``   Indonesian Windows installer
3. ``dist/ThisIsPixel-Portable-<ver>.zip`` portable copy (portable settings)

Usage::

    python build_release.py
    python build_release.py --nsis "C:\\Program Files (x86)\\NSIS\\makensis.exe"
    python build_release.py --skip-app          # only regenerate the installer

NSIS is looked up in ``--nsis``, ``$NSIS_HOME``, ``PATH`` and the usual
installation folders. If it is not available, the onedir build and the
portable ZIP are still produced and a hint is printed.
"""

import argparse
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
APP_DIR = DIST / "ThisIsPixel"
APP_EXE = APP_DIR / "ThisIsPixel.exe"
INSTALLER_DIR = ROOT / "installer"
NSI = INSTALLER_DIR / "ThisIsPixel.nsi"
GUIDE = INSTALLER_DIR / "Panduan Singkat.txt"

sys.path.insert(0, str(ROOT))
from version import APP_VERSION  # noqa: E402

PORTABLE_INI = """\
; ThisIsPixel portable settings.
; Hapus file ini jika ingin memakai pengaturan Windows biasa.
"""


def log(message: str) -> None:
    print(f"[release] {message}", flush=True)


def run(command: list[str], cwd: Path | None = None) -> None:
    log(" ".join(str(part) for part in command))
    result = subprocess.run(command, cwd=str(cwd or ROOT))
    if result.returncode != 0:
        raise SystemExit(f"Command failed with exit code {result.returncode}")


def find_makensis(explicit: str | None) -> str | None:
    candidates: list[str] = []
    if explicit:
        candidates.append(explicit)
    env_home = os.environ.get("NSIS_HOME", "").strip()
    if env_home:
        candidates.append(env_home)
        candidates.append(os.path.join(env_home, "makensis.exe"))
    candidates.extend(
        [
            "makensis.exe",
            r"C:\Program Files (x86)\NSIS\makensis.exe",
            r"C:\Program Files\NSIS\makensis.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\NSIS\makensis.exe"),
        ]
    )
    for candidate in candidates:
        resolved = shutil.which(candidate) if os.path.sep not in candidate else candidate
        if resolved and Path(resolved).is_file():
            return str(Path(resolved).resolve())
    return None


def build_app() -> None:
    log("building the onedir application with PyInstaller")
    run([sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", "main_onedir.spec"])
    if not APP_EXE.is_file():
        raise SystemExit(f"PyInstaller did not produce {APP_EXE}")
    log(f"application ready: {APP_EXE}")


def build_installer(makensis: str | None) -> Path | None:
    if makensis is None:
        log("NSIS not found; skipping installer creation")
        log("install NSIS 3.x or set NSIS_HOME to the folder containing makensis.exe")
        return None

    setup_path = DIST / f"ThisIsPixel-Setup-{APP_VERSION}.exe"
    if setup_path.exists():
        setup_path.unlink()

    log("building the Indonesian Windows installer with NSIS")
    run(
        [
            makensis,
            "/V2",
            f"/DAPPVERSION={APP_VERSION}",
            f"/DAPPDIR={APP_DIR}",
            str(NSI),
        ],
        cwd=INSTALLER_DIR,
    )
    if not setup_path.is_file():
        raise SystemExit(f"NSIS did not produce {setup_path}")
    size_mb = setup_path.stat().st_size / (1024 * 1024)
    log(f"installer ready: {setup_path} ({size_mb:.1f} MB)")
    return setup_path


def build_portable() -> Path:
    portable_name = f"ThisIsPixel-Portable-{APP_VERSION}"
    staging = DIST / portable_name
    archive = DIST / f"{portable_name}.zip"

    log("building the portable ZIP")
    if staging.exists():
        shutil.rmtree(staging)
    shutil.copytree(APP_DIR, staging)
    (staging / "thisispixel.ini").write_text(PORTABLE_INI, encoding="utf-8")
    shutil.copy2(GUIDE, staging / GUIDE.name)
    readme = ROOT / "README.md"
    if readme.is_file():
        shutil.copy2(readme, staging / "README.md")

    if archive.exists():
        archive.unlink()
    # Store paths relative to the staging folder, so extracting the ZIP with
    # Windows Explorer produces a single "ThisIsPixel-Portable-<ver>" folder
    # instead of a folder nested inside an identically named folder.
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for file_path in sorted(staging.rglob("*")):
            if file_path.is_file():
                bundle.write(file_path, file_path.relative_to(staging))
    shutil.rmtree(staging)

    size_mb = archive.stat().st_size / (1024 * 1024)
    log(f"portable ZIP ready: {archive} ({size_mb:.1f} MB)")
    return archive


def main() -> None:
    parser = argparse.ArgumentParser(description="Build ThisIsPixel release artifacts.")
    parser.add_argument("--nsis", help="path to makensis.exe (or set NSIS_HOME)")
    parser.add_argument("--skip-app", action="store_true", help="reuse dist/ThisIsPixel")
    parser.add_argument("--skip-installer", action="store_true")
    parser.add_argument("--skip-portable", action="store_true")
    args = parser.parse_args()

    DIST.mkdir(exist_ok=True)

    if args.skip_app:
        if not APP_EXE.is_file():
            raise SystemExit(f"{APP_EXE} is missing; run without --skip-app first")
    else:
        build_app()

    if not args.skip_installer:
        build_installer(find_makensis(args.nsis))
    if not args.skip_portable:
        build_portable()

    log(f"done - ThisIsPixel {APP_VERSION}")
    for artifact in (APP_DIR, DIST / f"ThisIsPixel-Setup-{APP_VERSION}.exe",
                     DIST / f"ThisIsPixel-Portable-{APP_VERSION}.zip"):
        if artifact.exists():
            log(f"  {artifact}")


if __name__ == "__main__":
    main()
