"""Launcher for the SysDigger app.

Run this file (double-click or `pythonw sysdigger.pyw`) to start the GUI
without a console window. The app self-elevates to admin for sensor access
(temperatures, fan speeds). Any uncaught errors are logged to app.log
next to this file.

When packaged as a frozen exe (PyInstaller), UAC elevation is handled by
the exe manifest (uac_admin=True in the spec), so the self-elevation code
below is skipped.
"""

import os
import sys
import traceback

_FROZEN = getattr(sys, "frozen", False)

if not _FROZEN:
    _here = os.path.dirname(os.path.abspath(__file__))
    if _here not in sys.path:
        sys.path.insert(0, _here)


def is_admin() -> bool:
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def elevate() -> bool:
    """Re-launch with admin privileges via UAC. Returns True on success."""
    import ctypes
    # Pass the working directory explicitly — elevated processes default
    # to C:\Windows\System32, which would break relative path resolution.
    work_dir = os.path.dirname(os.path.abspath(__file__))
    if _FROZEN:
        exe = sys.executable
        params = " ".join(f'"{a}"' for a in sys.argv[1:])
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", exe, params, work_dir, 1
        )
    else:
        exe = sys.executable
        params = " ".join(f'"{a}"' for a in sys.argv[1:])
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", exe,
            f'"{os.path.abspath(__file__)}" {params}', work_dir, 1
        )
    return ret > 32


def main() -> int:
    from app_logger import get_logger, log_startup, log_exception
    log_startup()
    logger = get_logger("launcher")

    # Verify elevation status and log it so we can diagnose UAC issues.
    _admin = is_admin()
    logger.info("Elevation check: is_admin=%s, frozen=%s", _admin, _FROZEN)
    if not _admin:
        logger.warning("Process is NOT elevated — attempting UAC elevation")
        if not elevate():
            # ShellExecuteW returns <= 32 on failure (user declined UAC,
            # or UAC is disabled and the user is not an admin).
            import ctypes
            err = ctypes.get_last_error()
            logger.error(
                "UAC elevation failed (ShellExecuteW returned error, "
                "GetLastError=%d). The user may have declined the UAC "
                "prompt or UAC may be disabled.", err
            )
            try:
                ctypes.windll.user32.MessageBoxW(
                    0,
                    "SysDigger requires administrator privileges for sensor "
                    "access (temperatures, fan speeds, motherboard voltages). "
                    "Please run as administrator or enable UAC prompts.",
                    "SysDigger - Elevation Required",
                    0x30,  # MB_ICONWARNING
                )
            except Exception:
                pass
            return 0
        # Elevation accepted — this (non-elevated) process exits.
        # The elevated process will write its own log entries.
        logger.info("UAC elevation accepted — non-elevated process exiting")
        return 0
    logger.info("Process is elevated — proceeding with launch")

    # Redirect stderr to the log (no console under pythonw)
    class _StderrToLogger:
        def write(self, msg):
            msg = msg.rstrip()
            if msg:
                logger.error(msg)
        def flush(self):
            pass
    sys.stderr = _StderrToLogger()

    try:
        logger.info("Launching application")
        import app  # the main application module
        app.main()
        logger.info("Application exited normally")
        return 0
    except Exception as exc:
        log_exception(logger, "Unhandled exception in application", exc)
        err = traceback.format_exc()
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0,
                f"The application crashed. See app.log for details.\n\n{err[:1000]}",
                "SysDigger - Error",
                0x10,  # MB_ICONERROR
            )
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
