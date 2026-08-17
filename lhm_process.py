"""PawnIO kernel driver installer (portable mode).

Installs the PawnIO kernel driver on app launch and uninstalls it on
close, giving access to motherboard SuperIO sensors (fan speeds,
voltages, temperatures) and AMD CPU MSR registers (clock, power,
voltage, temperature) without leaving a permanent installation.

Background:
    Starting with LHM 0.9.6 (Feb 2026), PawnIO is distributed as a
    separate installer (https://github.com/namazso/PawnIO.Setup) and is
    no longer bundled inside the LHM.exe release ZIP.  The DLL-based
    ``Computer.Open()`` expects PawnIO to already be installed.

Portable flow:
    1. ``ensure_downloaded()`` — download ``PawnIO_setup.exe`` v2.2.0
       to ``lib/pawnio/`` (cached, not re-downloaded on subsequent
       launches).
    2. ``start()`` — run ``PawnIO_setup.exe -install`` (silent, ~2.5s,
       idempotent — works whether the service is absent, stopped, or
       already running).  The installer places the driver in the Windows
       DriverStore and starts the service.
    3. ``wait_for_driver()`` — poll ``sc query PawnIO`` until RUNNING.
    4. ``stop()`` — run ``uninstall.exe -uninstall -silent`` (~0.1s).
       Removes ``C:\\Program Files\\PawnIO`` and stops the service.  The
       service entry may remain as STOPPED until the next reboot
       (Windows kernel driver limitation), but it is harmless and the
       installer handles re-install cleanly on next launch.
"""

from __future__ import annotations

import os
import subprocess
import threading
import time

from app_logger import get_logger
from paths import pawnio_dir

logger = get_logger(__name__)

_PAWNIO_DIR = pawnio_dir()

PAWNIO_SETUP_URL = (
    "https://github.com/namazso/PawnIO.Setup/releases/download/2.2.0/"
    "PawnIO_setup.exe"
)
PAWNIO_VERSION = "2.2.0"
PAWNIO_SETUP_NAME = "PawnIO_setup.exe"
PAWNIO_VERSION_FILE = os.path.join(_PAWNIO_DIR, "version.txt")

# Path to the uninstaller that the PawnIO installer places on disk.
_PAWNIO_UNINSTALLER = r"C:\Program Files\PawnIO\uninstall.exe"

# Legacy driver services that older LHM versions created (cleaned up
# on stop, but PawnIO itself is handled by the official uninstaller).
_LEGACY_DRIVER_SERVICES = ("WinRing0_1_2_0", "WinRing0")


class LhmProcess:
    """Manages the PawnIO kernel driver installation (portable mode).

    Despite the legacy name (kept to avoid breaking imports in app.py
    and collectors.py), this class installs/uninstalls the standalone
    PawnIO driver on each app run — no permanent installation left
    behind after the app closes.

    Lifecycle:
        1. ``ensure_downloaded()`` — download ``PawnIO_setup.exe`` if not
           cached.
        2. ``start()`` — run ``PawnIO_setup.exe -install`` (silent).
        3. ``wait_for_driver()`` — poll until the PawnIO service reports
           RUNNING.
        4. ``stop()`` — run ``uninstall.exe -uninstall -silent`` to
           remove the driver and clean up.
    """

    def __init__(self) -> None:
        self._driver_ready = False
        self._lock = threading.Lock()
        self._downloaded = False
        self._download_error: str = ""

    @property
    def installer_path(self) -> str:
        return os.path.join(_PAWNIO_DIR, PAWNIO_SETUP_NAME)

    def _is_pawnio_service_running(self) -> bool:
        """Check if the PawnIO service is in RUNNING state."""
        try:
            r = subprocess.run(
                ["sc", "query", "PawnIO"],
                capture_output=True, text=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                timeout=5,
            )
            return r.returncode == 0 and "RUNNING" in r.stdout
        except Exception:
            return False

    def is_downloaded(self) -> bool:
        """Return True if the installer is cached and version matches."""
        if not os.path.exists(self.installer_path):
            return False
        try:
            with open(PAWNIO_VERSION_FILE, "r", encoding="utf-8") as f:
                return f.read().strip() == PAWNIO_VERSION
        except Exception:
            return False

    def ensure_downloaded(self) -> bool:
        """Download PawnIO_setup.exe if not already cached.

        Returns True if the installer is ready.  Returns False on failure
        (network error, etc.).
        """
        if self.is_downloaded():
            self._downloaded = True
            logger.info("PawnIO installer already cached")
            return True

        try:
            import requests
        except ImportError:
            self._download_error = "requests library not available"
            logger.error(self._download_error)
            return False

        logger.info("Downloading PawnIO %s installer...", PAWNIO_VERSION)
        try:
            with requests.get(PAWNIO_SETUP_URL, stream=True, timeout=120,
                              headers={"Accept": "application/octet-stream"}) as resp:
                resp.raise_for_status()
                with open(self.installer_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=65536):
                        f.write(chunk)
        except Exception as e:
            self._download_error = f"Download failed: {e}"
            logger.error(self._download_error)
            return False

        try:
            with open(PAWNIO_VERSION_FILE, "w", encoding="utf-8") as f:
                f.write(PAWNIO_VERSION)
        except Exception as e:
            logger.warning("Failed to write PawnIO version file: %s", e)

        logger.info("PawnIO installer cached at %s", self.installer_path)
        self._downloaded = True
        return True

    def start(self) -> bool:
        """Run the PawnIO installer in silent mode.

        Uses the ``-install`` flag (the same flag LHM uses internally).
        The installer is idempotent — it succeeds (exit 0) whether the
        service is absent, stopped (marked for deletion from a previous
        run), or already running.
        """
        if self._is_pawnio_service_running():
            self._driver_ready = True
            logger.info("PawnIO service already running")
            return True

        if not os.path.exists(self.installer_path):
            logger.warning("PawnIO installer not downloaded, skipping")
            return False

        with self._lock:
            if self._is_pawnio_service_running():
                self._driver_ready = True
                return True

            logger.info("Installing PawnIO driver (silent)...")
            try:
                r = subprocess.run(
                    [self.installer_path, "-install"],
                    capture_output=True,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    timeout=60,
                )
                if r.returncode == 0:
                    logger.info("PawnIO installer completed (exit 0)")
                    return True
                elif r.returncode == 3010:
                    logger.info("PawnIO installed, reboot required")
                    return True
                else:
                    logger.error("PawnIO installer failed (exit %d)",
                                 r.returncode)
                    return False
            except subprocess.TimeoutExpired:
                logger.error("PawnIO installer timed out")
                return False
            except Exception as e:
                logger.error("Failed to run PawnIO installer: %s", e,
                             exc_info=True)
                return False

    def wait_for_driver(self, timeout: float = 20.0) -> bool:
        """Poll until the PawnIO kernel driver is running."""
        if self._driver_ready:
            return True

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._is_pawnio_service_running():
                self._driver_ready = True
                logger.info("PawnIO driver is running")
                return True
            time.sleep(0.5)

        logger.warning("PawnIO driver not running after %.1fs", timeout)
        return False

    def is_driver_ready(self) -> bool:
        """Return True if the kernel driver is loaded."""
        if not self._driver_ready:
            return False
        return self._is_pawnio_service_running()

    def stop(self) -> None:
        """Uninstall PawnIO and clean up legacy driver services.

        Runs the official uninstaller (``uninstall.exe -uninstall
        -silent``) which removes ``C:\\Program Files\\PawnIO``.  The
        uninstaller doesn't stop the running service, so we explicitly
        stop it via ``sc stop``.  The service entry may remain as
        STOPPED until the next reboot (Windows kernel driver
        limitation), but the installer handles re-install cleanly on
        next app launch.
        """
        self._driver_ready = False

        # Run the official uninstaller first (removes files).
        if os.path.exists(_PAWNIO_UNINSTALLER):
            try:
                r = subprocess.run(
                    [_PAWNIO_UNINSTALLER, "-uninstall", "-silent"],
                    capture_output=True,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    timeout=30,
                )
                if r.returncode == 0:
                    logger.info("PawnIO uninstalled (exit 0)")
                else:
                    logger.warning("PawnIO uninstaller exit %d",
                                   r.returncode)
            except Exception as e:
                logger.warning("PawnIO uninstall failed: %s", e)
        else:
            logger.info("PawnIO uninstaller not found (already removed)")

        # Stop the PawnIO service (the uninstaller doesn't do this).
        try:
            subprocess.run(
                ["sc", "stop", "PawnIO"],
                capture_output=True, text=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                timeout=10,
            )
        except Exception:
            pass

        # Clean up legacy WinRing0 services from older LHM versions.
        for svc in _LEGACY_DRIVER_SERVICES:
            try:
                r = subprocess.run(
                    ["sc", "query", svc],
                    capture_output=True, text=True,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    timeout=5,
                )
                if r.returncode != 0:
                    continue
                logger.info("Cleaning up legacy driver service: %s", svc)
                subprocess.run(["sc", "stop", svc], capture_output=True,
                               creationflags=getattr(subprocess,
                                                    "CREATE_NO_WINDOW", 0),
                               timeout=5)
                time.sleep(0.5)
                subprocess.run(["sc", "delete", svc],
                               capture_output=True, text=True,
                               creationflags=getattr(subprocess,
                                                    "CREATE_NO_WINDOW", 0),
                               timeout=5)
            except Exception:
                pass

    @property
    def download_error(self) -> str:
        return self._download_error

    @property
    def is_running(self) -> bool:
        return self._driver_ready
