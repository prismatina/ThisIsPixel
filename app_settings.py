"""
ThisIsPixel - Settings Store
============================
Single place where :class:`QSettings` objects are created.

By default preferences live in the platform-native store (the Windows
registry, ``~/.config`` on Linux, a plist on macOS).

Two overrides keep the application portable and the test suite hermetic:

* ``THISISPIXEL_SETTINGS`` - path to an explicit INI file. The test suite
  points this at a throw-away temp file so it can never touch a real user
  profile. Shipping a launcher that sets the variable also turns the editor
  into a portable app.
* A file named ``thisispixel.ini`` placed next to the executable (or next to
  this module when running from source) is detected automatically, so the
  portable ZIP works with no configuration at all.

Note: ``QSettings(organization, application)`` always uses the *native*
format, which is why a plain ``setDefaultFormat``/``setPath`` is not enough to
redirect it.
"""

import os
import sys

from PyQt6.QtCore import QSettings

ORGANIZATION = "ThisIsPixel"
APPLICATION = "EditorSettings"
SETTINGS_ENV_VAR = "THISISPIXEL_SETTINGS"
PORTABLE_FILE_NAME = "thisispixel.ini"


def _portable_settings_path() -> str:
    """Returns the portable INI path when one sits next to the program."""
    if getattr(sys, "frozen", False):
        base = os.path.dirname(os.path.abspath(sys.executable))
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.join(base, PORTABLE_FILE_NAME)
    return candidate if os.path.isfile(candidate) else ""


def create_settings() -> QSettings:
    """Returns a QSettings object honouring the portable overrides."""
    override = os.environ.get(SETTINGS_ENV_VAR, "").strip()
    if not override:
        override = _portable_settings_path()
    if override:
        path = os.path.abspath(os.path.expanduser(override))
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        return QSettings(path, QSettings.Format.IniFormat)
    return QSettings(ORGANIZATION, APPLICATION)
