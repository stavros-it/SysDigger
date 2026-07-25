"""LibreHardwareMonitor.exe portable process manager.

The standalone LHM GUI loads a kernel driver (PawnIO) that gives access
to motherboard SuperIO sensors (fan speeds, voltages, temperatures).
Loading the DLL directly via pythonnet does NOT load this driver, so
motherboard sensors are missing.

This module launches the standalone ``LibreHardwareMonitor.exe`` hidden
in the background on startup.  Once the PawnIO driver is loaded, the
existing DLL-based sensor collection (``Collector._collect_sensors``)
automatically picks up motherboard sensors — no WMI bridge needed.

On close, the LHM.exe process is killed and the PawnIO driver service
is stopped and deleted, leaving no permanent installation.

First run: downloads the LHM release ZIP (~6.6 MB) and extracts it to
``lib/lhm_standalone/``.  Subsequent runs use the cached copy.
"""

from __future__ import annotations

import io
import os
import subprocess
import threading
import time
import zipfile

from app_logger import get_logger

logger = get_logger(__name__)

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_APP_DIR, "lib")
_LHM_STANDALONE_DIR = os.path.join(_LIB_DIR, "lhm_standalone")

LHM_RELEASE_URL = (
    "https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/"
    "releases/download/v0.9.6/LibreHardwareMonitor.zip"
)
LHM_EXE_NAME = "LibreHardwareMonitor.exe"
LHM_VERSION = "0.9.6"
LHM_VERSION_FILE = os.path.join(_LHM_STANDALONE_DIR, "version.txt")

# Driver service names that LHM may create (cleaned up on stop).
_DRIVER_SERVICES = ("PawnIO", "WinRing0_1_2_0", "WinRing0")


class LhmProcess:
    """Manages the lifecycle of a hidden LibreHardwareMonitor.exe process.

    The process loads the PawnIO kernel driver, which gives the DLL-based
    sensor collection access to motherboard SuperIO chips.  On stop, the
    process is killed and the driver service is removed.
    """

    def __init__(self) -> None:
        self._process: subprocess.Popen | None = None
        self._driver_ready = False
        self._lock = threading.Lock()
        self._downloaded = False
        self._download_error: str = ""

    @property
    def lhm_dir(self) -> str:
        return _LHM_STANDALONE_DIR

    @property
    def exe_path(self) -> str:
        return os.path.join(_LHM_STANDALONE_DIR, LHM_EXE_NAME)

    def is_downloaded(self) -> bool:
        """Return True if LHM.exe is cached and version matches."""
        if not os.path.exists(self.exe_path):
            return False
        try:
            with open(LHM_VERSION_FILE, "r") as f:
                return f.read().strip() == LHM_VERSION
        except Exception:
            return False

    def ensure_downloaded(self) -> bool:
        """Download and extract LHM.exe if not already cached.

        Returns True if the exe is ready (either was already cached or just
        downloaded).  Returns False on failure (network error, etc.).
        """
        if self.is_downloaded():
            self._downloaded = True
            return True

        try:
            import requests
        except ImportError:
            self._download_error = "requests library not available"
            logger.error(self._download_error)
            return False

        logger.info("Downloading LibreHardwareMonitor %s...", LHM_VERSION)
        try:
            resp = requests.get(LHM_RELEASE_URL, stream=True, timeout=120,
                                headers={"Accept": "application/octet-stream"})
            resp.raise_for_status()
        except Exception as e:
            self._download_error = f"Download failed: {e}"
            logger.error(self._download_error)
            return False

        buf = io.BytesIO()
        for chunk in resp.iter_content(chunk_size=65536):
            buf.write(chunk)
        buf.seek(0)

        os.makedirs(_LHM_STANDALONE_DIR, exist_ok=True)
        try:
            with zipfile.ZipFile(buf) as zf:
                for entry in zf.namelist():
                    base = os.path.basename(entry)
                    if not base:
                        continue
                    if base.endswith(".pdb") or base.endswith(".xml"):
                        continue
                    if "/" in entry and not entry.endswith(".dll") \
                            and not entry.endswith(".exe") \
                            and not entry.endswith(".config"):
                        continue
                    target = os.path.join(_LHM_STANDALONE_DIR, base)
                    with open(target, "wb") as f:
                        f.write(zf.read(entry))
        except Exception as e:
            self._download_error = f"Extraction failed: {e}"
            logger.error(self._download_error, exc_info=True)
            return False

        if not os.path.exists(self.exe_path):
            self._download_error = "Extraction complete but exe not found"
            logger.error(self._download_error)
            return False

        self._patch_config()

        logger.info("LHM.exe cached at %s", self.exe_path)
        self._downloaded = True
        return True

    def _patch_config(self) -> None:
        """Patch LibreHardwareMonitor.exe.config to enable the WMI provider.

        Although we don't use WMI directly, enabling it ensures LHM.exe
        fully initialises its sensor infrastructure (including driver load).
        """
        config_path = os.path.join(_LHM_STANDALONE_DIR,
                                   "LibreHardwareMonitor.exe.config")
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                content = f.read()
            if "wmiProvider" in content:
                return
            inject = (
                "  <userSettings>\n"
                "    <LibreHardwareMonitor.Properties.Settings>\n"
                "      <setting name=\"wmiProvider\" serializeAs=\"String\">\n"
                "        <value>True</value>\n"
                "      </setting>\n"
                "    </LibreHardwareMonitor.Properties.Settings>\n"
                "  </userSettings>\n"
            )
            content = content.replace("</configuration>",
                                      inject + "</configuration>")
            with open(config_path, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info("Patched LHM config: WMI provider enabled")
        except Exception as e:
            logger.warning("Failed to patch LHM config: %s", e)

    def start(self) -> bool:
        """Launch LHM.exe hidden.  Returns True if launched.

        Must be called after :meth:`ensure_downloaded`.  The process inherits
        admin from SysPeek (launched via UAC elevation), so the kernel driver
        can be loaded.
        """
        if not self.is_downloaded():
            logger.warning("LHM.exe not downloaded, skipping launch")
            return False

        self._patch_config()

        with self._lock:
            if self._process and self._process.poll() is None:
                logger.info("LHM.exe already running (PID %d)",
                            self._process.pid)
                return True

            try:
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = 0  # SW_HIDE
                creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                self._process = subprocess.Popen(
                    [self.exe_path],
                    startupinfo=si,
                    creationflags=creationflags,
                    cwd=_LHM_STANDALONE_DIR,
                )
                logger.info("LHM.exe launched (PID %d)", self._process.pid)
                return True
            except Exception as e:
                logger.error("Failed to launch LHM.exe: %s", e,
                             exc_info=True)
                self._process = None
                return False

    def wait_for_driver(self, timeout: float = 20.0) -> bool:
        """Poll until the PawnIO kernel driver is running.

        LHM.exe needs a few seconds to load the driver.  We poll every 500ms.
        """
        if self._driver_ready:
            return True
        proc = self._process
        if not proc or proc.poll() is not None:
            logger.warning("LHM.exe not running, cannot wait for driver")
            return False

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                logger.warning("LHM.exe exited during driver wait")
                return False
            if self._is_driver_running():
                self._driver_ready = True
                logger.info("PawnIO driver is running")
                return True
            time.sleep(0.5)

        logger.warning("PawnIO driver not running after %.1fs", timeout)
        return False

    def _is_driver_running(self) -> bool:
        """Check if any of the known driver services is running."""
        for svc in _DRIVER_SERVICES:
            try:
                r = subprocess.run(
                    ["sc", "query", svc],
                    capture_output=True, text=True,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    timeout=5,
                )
                if r.returncode == 0 and "RUNNING" in r.stdout:
                    return True
            except Exception:
                pass
        return False

    def is_driver_ready(self) -> bool:
        """Return True if the kernel driver is loaded."""
        if not self._driver_ready:
            return False
        proc = self._process
        if not proc or proc.poll() is not None:
            self._driver_ready = False
            return False
        return True

    def stop(self) -> None:
        """Kill LHM.exe and clean up driver services."""
        with self._lock:
            proc = self._process
            self._process = None
            self._driver_ready = False

        if proc and proc.poll() is None:
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    timeout=5,
                )
                logger.info("LHM.exe terminated (PID %d)", proc.pid)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

        self._cleanup_driver_services()

    def _cleanup_driver_services(self) -> None:
        """Stop and delete any kernel driver services LHM created.

        Kernel drivers may not support being stopped while loaded (the driver
        remains in kernel memory until reboot).  In that case, ``sc stop``
        fails silently but ``sc delete`` still marks the service as
        ``Disabled`` so it won't start on next boot and will be fully
        removed by Windows on reboot.
        """
        for svc in _DRIVER_SERVICES:
            try:
                r = subprocess.run(
                    ["sc", "query", svc],
                    capture_output=True, text=True,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    timeout=5,
                )
                if r.returncode != 0:
                    continue
                logger.info("Cleaning up driver service: %s", svc)
                subprocess.run(["sc", "stop", svc], capture_output=True,
                               creationflags=getattr(subprocess,
                                                    "CREATE_NO_WINDOW", 0),
                               timeout=5)
                time.sleep(0.5)
                r2 = subprocess.run(["sc", "delete", svc],
                                    capture_output=True, text=True,
                                    creationflags=getattr(subprocess,
                                                          "CREATE_NO_WINDOW",
                                                          0),
                                    timeout=5)
                if r2.returncode == 0:
                    logger.info("Driver service %s marked for deletion", svc)
                else:
                    logger.warning("Could not delete service %s: %s",
                                   svc, r2.stderr.strip())
            except Exception:
                pass

    @property
    def download_error(self) -> str:
        return self._download_error

    @property
    def is_running(self) -> bool:
        proc = self._process
        return proc is not None and proc.poll() is None
