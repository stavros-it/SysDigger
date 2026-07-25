"""Formatting and utility helpers."""

from __future__ import annotations

import datetime
import re
import winreg
from typing import Any

import psutil


def fmt_bytes(num: float) -> str:
    """Human-readable byte size."""
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(num) < 1024.0:
            return f"{num:.1f} {unit}"
        num /= 1024.0
    return f"{num:.1f} EB"


def vram_from_registry(pnp_device_id: str) -> int | None:
    """Read dedicated VRAM (bytes) from the registry.

    Win32_VideoController.AdapterRAM is a 32-bit uint that overflows for
    GPUs with 4 GB+ VRAM. The registry ``HardwareInformation.qwMemorySize``
    value (REG_QWORD) is a proper uint64 in bytes.
    """
    if not pnp_device_id:
        return None
    try:
        dp_path = rf"SYSTEM\CurrentControlSet\Enum\{pnp_device_id}\Device Parameters"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, dp_path) as key:
            video_id, _ = winreg.QueryValueEx(key, "VideoID")
    except Exception:
        return None

    if not video_id:
        return None

    vpath = rf"SYSTEM\CurrentControlSet\Control\Video\{video_id}\0000"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, vpath) as key:
            try:
                qw, _ = winreg.QueryValueEx(key, "HardwareInformation.qwMemorySize")
                if isinstance(qw, int) and qw > 0:
                    return qw
            except FileNotFoundError:
                pass
            try:
                ms, _ = winreg.QueryValueEx(key, "HardwareInformation.MemorySize")
                if isinstance(ms, int) and ms > 0:
                    return ms
            except FileNotFoundError:
                pass
    except Exception:
        pass
    return None


def fmt_speed(num: int | float) -> str:
    """Human-readable bits-per-second link speed."""
    n = float(num)
    for unit in ("bps", "Kbps", "Mbps", "Gbps"):
        if abs(n) < 1000.0:
            return f"{n:.0f} {unit}"
        n /= 1000.0
    return f"{n:.0f} Tbps"


def fmt_uptime(seconds: float) -> str:
    s = int(seconds)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    parts = []
    if d:
        parts.append(f"{d}d")
    if h or d:
        parts.append(f"{h}h")
    if m or h or d:
        parts.append(f"{m}m")
    parts.append(f"{s}s")
    return " ".join(parts)


def s(value: Any, default: str = "N/A") -> str:
    """Stringify a WMI value, treating None/empty as the default."""
    if value is None:
        return default
    s = str(value).strip()
    return s if s else default


def fmt_wmi_time(value: Any) -> str:
    """Convert a WMI date value to a readable string."""
    if value is None:
        return "N/A"
    if hasattr(value, "strftime"):
        try:
            return value.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return str(value)
    ts = str(value).strip()
    if not ts:
        return "N/A"
    m = re.match(r"/Date\((\d+)([+-]\d+)?\)/", ts)
    if m:
        try:
            epoch = int(m.group(1)) / 1000.0
            return datetime.datetime.fromtimestamp(epoch).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        except Exception:
            return ts
    m = re.match(
        r"(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})\.(\d+)([+-]\d{3})?", ts
    )
    if not m:
        return ts
    y, mo, d, h, mi, se = (int(x) for x in m.groups()[:6])
    try:
        return datetime.datetime(y, mo, d, h, mi, se).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ts


def reg_value(key_path: str, value_name: str, hive=winreg.HKEY_LOCAL_MACHINE) -> str:
    """Read a string value from the Windows registry. Returns '' if missing."""
    try:
        with winreg.OpenKey(hive, key_path) as key:
            val, _ = winreg.QueryValueEx(key, value_name)
            return str(val).strip()
    except Exception:
        return ""


def secsleft_is_valid(secs) -> bool:
    try:
        return secs is not None and secs >= 0 and secs != psutil.POWER_TIME_UNLIMITED
    except Exception:
        return False
