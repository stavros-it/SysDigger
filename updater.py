"""LibreHardwareMonitorLib GitHub release updater.

Downloads the latest release ZIP, extracts needed DLLs, and writes them
as ``.new`` files that are swapped in on next app restart.
"""

from __future__ import annotations

import io
import os
import threading
import zipfile

import requests
from PySide6.QtCore import Signal, QObject

from app_logger import get_logger

logger = get_logger(__name__)

GH_RELEASES_API = "https://api.github.com/repos/LibreHardwareMonitor/LibreHardwareMonitor/releases/latest"

LHM_NEEDED_DLLS = (
    "LibreHardwareMonitorLib.dll",
    "HidSharp.dll",
    "System.Memory.dll",
    "System.Runtime.CompilerServices.Unsafe.dll",
    "RAMSPDToolkit-NDD.dll",
    "System.Buffers.dll",
    "System.Numerics.Vectors.dll",
    "System.Threading.Tasks.Extensions.dll",
    "Microsoft.Bcl.AsyncInterfaces.dll",
    "Microsoft.Bcl.HashCode.dll",
    "DiskInfoToolkit.dll",
    "BlackSharp.Core.dll",
    # The following DLLs are transitive dependencies of
    # LibreHardwareMonitorLib.dll.  Without them, Computer.Open() fails
    # to load or silently skips sensors.
    "System.Security.AccessControl.dll",
    "System.Security.Principal.Windows.dll",
    "System.Threading.AccessControl.dll",
    "System.Reflection.Metadata.dll",
    "System.Collections.Immutable.dll",
    "System.Resources.Extensions.dll",
    "System.CodeDom.dll",
    "System.Formats.Nrbf.dll",
    "System.IO.Pipelines.dll",
    "System.Text.Encodings.Web.dll",
    "System.Text.Json.dll",
)


class UpdateSignals(QObject):
    status = Signal(str, str)      # (message, kind: "info"|"success"|"error")
    finished = Signal(bool, str)   # (success, message)


class LibraryUpdater:
    """Downloads and installs the latest LibreHardwareMonitorLib from GitHub.

    Uses the full release ZIP (self-contained with all dependencies) rather
    than the NuGet package, which has transitive dependency issues when
    loading DLLs directly via pythonnet.
    """

    def __init__(self, lib_dir: str) -> None:
        self.lib_dir = lib_dir
        self.signals = UpdateSignals()

    def get_installed_version(self) -> str:
        """Read the version from a version.txt file in lib/, or 'unknown'."""
        vf = os.path.join(self.lib_dir, "version.txt")
        try:
            with open(vf, "r", encoding="utf-8") as f:
                return f.read().strip() or "unknown"
        except Exception:
            return "unknown"

    def _get_latest_release(self) -> dict:
        resp = requests.get(GH_RELEASES_API, timeout=15, headers={
            "Accept": "application/vnd.github+json"
        })
        resp.raise_for_status()
        return resp.json()

    def _find_release_zip(self, release: dict) -> str:
        for asset in release.get("assets", []):
            name = asset.get("name", "")
            if name == "LibreHardwareMonitor.zip":
                return asset.get("browser_download_url", "")
        return ""

    def _download_zip(self, url: str) -> bytes:
        # 'with' ensures the streaming response is always closed so the
        # connection returns to the pool (H-1 pattern, applied here too).
        with requests.get(url, timeout=120, stream=True) as resp:
            resp.raise_for_status()
            buf = io.BytesIO()
            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            for chunk in resp.iter_content(chunk_size=65536):
                buf.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    pct = downloaded * 100 // total
                    self.signals.status.emit(
                        f"Downloading... {pct}% ({downloaded // 1024} KB)", "info"
                    )
            return buf.getvalue()

    def _extract_dlls(self, zip_bytes: bytes) -> dict[str, bytes]:
        result: dict[str, bytes] = {}
        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                names = zf.namelist()
                for dll_name in LHM_NEEDED_DLLS:
                    for entry in names:
                        base = os.path.basename(entry)
                        if base.lower() == dll_name.lower() and entry.endswith(".dll"):
                            result[dll_name] = zf.read(entry)
                            break
        except Exception:
            pass
        return result

    def run_update(self) -> None:
        threading.Thread(target=self._update_worker, daemon=True).start()

    def _update_worker(self) -> None:
        try:
            current = self.get_installed_version()
            logger.info("Checking for library updates (current: v%s)", current)
            self.signals.status.emit(
                f"Current version: {current}. Checking GitHub for updates...", "info"
            )

            release = self._get_latest_release()
            tag = release.get("tag_name", "")
            latest_version = tag.lstrip("v") if tag else ""

            if not latest_version:
                self.signals.finished.emit(False, "Could not determine latest version from GitHub.")
                return

            if current == latest_version:
                self.signals.finished.emit(True, f"Already up to date (v{latest_version}).")
                return

            zip_url = self._find_release_zip(release)
            if not zip_url:
                self.signals.finished.emit(False, "Could not find release ZIP on GitHub.")
                return

            self.signals.status.emit(
                f"Downloading LibreHardwareMonitor v{latest_version} release...", "info"
            )
            zip_bytes = self._download_zip(zip_url)

            self.signals.status.emit("Extracting libraries...", "info")
            dlls = self._extract_dlls(zip_bytes)

            if "LibreHardwareMonitorLib.dll" not in dlls:
                self.signals.finished.emit(
                    False, "Failed to extract LibreHardwareMonitorLib.dll from release ZIP."
                )
                return

            self.signals.status.emit(
                f"Installing {len(dlls)} libraries...", "info"
            )
            os.makedirs(self.lib_dir, exist_ok=True)

            written = 0
            for dll_name, dll_data in dlls.items():
                new_path = os.path.join(self.lib_dir, dll_name + ".new")
                try:
                    with open(new_path, "wb") as f:
                        f.write(dll_data)
                    written += 1
                except Exception as e:
                    self.signals.status.emit(
                        f"Warning: could not write {dll_name}: {e}", "error"
                    )

            # Only persist the version marker if at least one DLL was
            # actually written.  Otherwise is_up_to_date() would report
            # "already up to date" on the next launch even though the DLLs
            # on disk are stale.
            if written > 0:
                with open(os.path.join(self.lib_dir, "version.txt"),
                          "w", encoding="utf-8") as f:
                    f.write(latest_version)

            logger.info("Library update complete: v%s (%d DLLs)", latest_version, written)
            self.signals.finished.emit(
                True,
                f"Updated to v{latest_version} ({written} DLLs). "
                f"Restart the app to apply."
            )

        except Exception as e:
            logger.error("Library update failed: %s", e, exc_info=True)
            self.signals.finished.emit(False, f"Update failed: {e}")
