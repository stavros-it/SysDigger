"""SysDigger — Windows System Information Viewer.

Gathers and displays Windows OS, hardware, network adapter, and external IP
information in a PySide6 (Qt) Fluent-design GUI.

Entry point: run ``python app.py`` or ``pythonw sysdigger.pyw``.
"""

from __future__ import annotations

import os

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app_logger import get_logger
from config import get_config
from paths import icon_path

logger = get_logger(__name__)

# AppID so Windows groups taskbar entries under a stable, branded identity
# (otherwise pythonw.exe shows a generic Python icon in the taskbar).
_APP_ID = "Stavros.SysDigger"


def _is_system_dark() -> bool:
    """Detect if Windows is using dark theme via registry."""
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        ) as key:
            val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return val == 0  # 0 = dark, 1 = light
    except Exception:
        return True  # Default to dark


def _resolve_theme() -> str:
    """Resolve the effective theme ('dark' or 'light')."""
    cfg = get_config()
    if cfg.theme == "system":
        return "dark" if _is_system_dark() else "light"
    return cfg.theme


def _is_elevated() -> bool:
    """Check if the current process has an elevated token.

    Uses IsUserAnAdmin() which correctly detects UAC elevation on Windows
    Vista+.  Returns True if the process is running with admin privileges.
    """
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def main() -> None:
    logger.info("Starting QApplication")

    # Warn (not block) if not elevated — sensor access will be limited.
    if not _is_elevated():
        logger.warning(
            "Process is NOT elevated — PawnIO driver (motherboard/CPU "
            "sensors) and some WMI namespaces will fail. Run via "
            "sysdigger.pyw for UAC elevation."
        )
    app = QApplication()
    app.setStyle("Fusion")

    # Set the app icon on the QApplication so it appears in the Windows
    # taskbar (grouping/tooltip) and on any top-level window/dialog.
    icon_path_str = icon_path()
    if os.path.exists(icon_path_str):
        app.setWindowIcon(QIcon(icon_path_str))

    # Register a stable AppUserModelID so the taskbar shows our icon and
    # groups the window under "SysDigger" instead of pythonw.exe.
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(_APP_ID)
    except Exception as e:
        logger.warning("Could not set AppUserModelID: %s", e)

    theme = _resolve_theme()
    logger.info("Using theme: %s", theme)

    # Set the palette BEFORE creating any widgets.  This serves two purposes:
    # 1. Windows uses the palette for WM_ERASEBKGND (system background fill)
    #    during ShowWindow(), before Qt's first WM_PAINT.
    # 2. Qt uses the palette for the initial widget backgrounds, so even
    #    before QSS is applied, widgets have the correct dark/light colors.
    # QSS is deferred to AFTER the window is shown (see below) to avoid
    # blocking startup for ~500ms while Qt parses the stylesheet.
    from PySide6.QtGui import QPalette, QColor
    if theme == "dark":
        pal = app.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor("#1c1c1c"))
        pal.setColor(QPalette.ColorRole.Base, QColor("#1c1c1c"))
        pal.setColor(QPalette.ColorRole.AlternateBase, QColor("#2d2d2d"))
        pal.setColor(QPalette.ColorRole.Text, QColor("#ffffff"))
        pal.setColor(QPalette.ColorRole.WindowText, QColor("#ffffff"))
        app.setPalette(pal)
    else:
        pal = app.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor("#f5f5f5"))
        pal.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
        pal.setColor(QPalette.ColorRole.AlternateBase, QColor("#f0f0f0"))
        pal.setColor(QPalette.ColorRole.Text, QColor("#1a1a1a"))
        pal.setColor(QPalette.ColorRole.WindowText, QColor("#1a1a1a"))
        app.setPalette(pal)

    font = app.font()
    cfg = get_config()
    if cfg.font_family:
        font.setFamily(cfg.font_family)
        logger.info("Using font: %s", cfg.font_family)
    app.setFont(font)

    # --- Launch mode picker -------------------------------------------------
    # Show the launch menu BEFORE importing collectors/gui — those modules
    # import sensors.py which loads pythonnet + .NET CLR at import time.
    # Fast mode sets SYSDIGGER_FAST_MODE=1 so sensors.py skips pythonnet,
    # saving ~3-6 seconds on startup (no .NET CLR init, no DLL loads,
    # no PawnIO driver install).
    from launch_menu import show_launch_menu, MODE_NORMAL, MODE_FAST, MODE_CANCEL
    mode = show_launch_menu(app)
    if mode == MODE_CANCEL:
        logger.info("User cancelled launch menu — exiting")
        return
    fast_mode = (mode == MODE_FAST)
    if fast_mode:
        os.environ["SYSDIGGER_FAST_MODE"] = "1"
        logger.info("Fast mode selected — skipping LHM / pythonnet / PawnIO")
    else:
        os.environ.pop("SYSDIGGER_FAST_MODE", None)
        logger.info("Normal mode selected — loading full sensor stack")

    # Now import collectors + gui (these trigger sensors.py, which checks
    # SYSDIGGER_FAST_MODE and skips pythonnet if set).
    from collectors import Collector
    from gui import InfoWindow, build_qss

    logger.info("Creating Collector")
    collector = Collector()

    # Install the PawnIO kernel driver in the background.  This gives
    # the DLL-based sensor collection access to motherboard SuperIO
    # sensors (fans, voltages, VRM temps) and AMD CPU MSR registers
    # (clock, power, voltage, temperature).  The driver is uninstalled
    # on close — nothing permanent is left behind (portable mode).
    # SKIPPED in fast mode — pythonnet/.NET/PawnIO not loaded.
    if not fast_mode:
        def _start_lhm_bridge() -> None:
            try:
                from lhm_process import LhmProcess
                proc = LhmProcess()
                # Attach to collector immediately so closeEvent can stop it
                # even if the app is closed during download/install.
                collector.set_lhm_process(proc)
                if not proc.ensure_downloaded():
                    logger.warning(
                        "PawnIO unavailable: %s", proc.download_error
                    )
                    return
                if proc.start():
                    proc.wait_for_driver(timeout=20.0)
                    # Re-attach to trigger Computer invalidation now that
                    # the driver is ready.
                    collector.set_lhm_process(proc)
            except Exception as e:
                logger.warning("PawnIO bridge failed: %s", e, exc_info=True)

        import threading as _threading
        _lhm_thread = _threading.Thread(target=_start_lhm_bridge, daemon=True)
        _lhm_thread.start()

    logger.info("Creating main window")
    window = InfoWindow(collector)
    # Prevent the white flash: Windows fills the window with white
    # (WM_ERASEBKGND + DWM compositor) during ShowWindow(), before Qt's
    # event loop can process the first WM_PAINT.  By setting opacity to 0
    # before show(), the window is invisible during this white period.
    window.setWindowOpacity(0.0)
    window.show()
    # Force a paint with the palette (dark) — this is ~6ms, vs ~340ms
    # if QSS is already applied (Qt resolves all widget styles on first paint).
    app.processEvents()
    # Now apply QSS while the window is still invisible.  This costs ~350ms
    # but the user doesn't see it — the window is opacity 0.
    app.setStyleSheet(build_qss(theme))
    app.processEvents()
    # Reveal the fully-styled dark window.
    window.setWindowOpacity(1.0)
    window._start_collection()
    logger.info("Entering Qt event loop")
    app.exec()
    logger.info("Qt event loop ended")


if __name__ == "__main__":
    main()
