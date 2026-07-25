"""Portable path resolution for SysPeek.

Distinguishes read-only resources (icons, bundled DLLs, PowerShell lib)
from writable data (config.json, app.log, cache/, lib/lhm_standalone/).

When running as a script, both resolve to the script directory.
When packaged as a frozen exe (PyInstaller):
  - ``resource_dir()`` returns ``sys._MEIPASS`` (bundled read-only assets)
  - ``data_dir()`` returns the exe directory if writable, else
    ``%LOCALAPPDATA%\\SysPeek`` (per-user writable fallback)
"""

from __future__ import annotations

import os
import sys

_FROZEN = getattr(sys, "frozen", False)


def resource_dir() -> str:
    """Directory containing read-only bundled resources (icons, DLLs, .ps1).

    When frozen with PyInstaller ``--onefile``, this is ``sys._MEIPASS``
    (a temp extraction dir).  When frozen with ``--onedir``, it's the
    ``_internal`` subdirectory.  When running as a script, it's the script
    directory.
    """
    if _FROZEN:
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return meipass
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def data_dir() -> str:
    """Directory for writable per-user data (config, logs, cache, downloads).

    Prefers the exe/script directory (portable mode).  Falls back to
    ``%LOCALAPPDATA%\\SysPeek`` when the primary location is read-only
    (e.g. Program Files, CD-ROM, network share).
    """
    if _FROZEN:
        primary = os.path.dirname(sys.executable)
    else:
        primary = os.path.dirname(os.path.abspath(__file__))
    if os.access(primary, os.W_OK):
        return primary
    fallback = os.path.join(os.environ.get("LOCALAPPDATA", ""), "SysPeek")
    try:
        os.makedirs(fallback, exist_ok=True)
        if os.access(fallback, os.W_OK):
            return fallback
    except OSError:
        pass
    return primary


def cache_dir() -> str:
    """Directory for static data cache files."""
    d = os.path.join(data_dir(), "cache")
    os.makedirs(d, exist_ok=True)
    return d


def lib_dir() -> str:
    """Directory for LHM DLLs and standalone LHM.exe."""
    return os.path.join(resource_dir(), "lib")


def lhm_standalone_dir() -> str:
    """Directory for the portable LHM.exe download (writable)."""
    return os.path.join(data_dir(), "lib", "lhm_standalone")


def icon_path(name: str = "app.ico") -> str:
    """Full path to an icon file."""
    return os.path.join(resource_dir(), name)


def icons_dir() -> str:
    """Directory containing nav/category icon PNGs."""
    return os.path.join(resource_dir(), "icons")
