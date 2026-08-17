"""LibreHardwareMonitorLib integration via pythonnet.

Loads the LHM .NET assembly at import time and provides sensor formatting
and hardware-type mapping helpers.
"""

from __future__ import annotations

import os

from app_logger import get_logger
from helpers import fmt_bytes
from paths import lib_dir

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
#  LHM assembly loading
# ---------------------------------------------------------------------------

_LHM_AVAILABLE = False
_LhmHardware = None

try:
    import clr as _clr
    from System import AppDomain as _AppDomain

    _lib_dir = lib_dir()
    if os.path.isdir(_lib_dir):
        logger.info("Loading LibreHardwareMonitorLib from %s", _lib_dir)
        # Swap in pending .new DLLs from a previous update (before loading)
        for _f in os.listdir(_lib_dir):
            if _f.endswith(".new"):
                _cur = os.path.join(_lib_dir, _f[:-4])
                _new = os.path.join(_lib_dir, _f)
                try:
                    os.replace(_new, _cur)
                    logger.info("Swapped updated DLL: %s", _f[:-4])
                except Exception as e:
                    logger.warning("Failed to swap DLL %s: %s", _f, e)
        if hasattr(os, "add_dll_directory"):
            os.add_dll_directory(_lib_dir)
        os.environ["PATH"] = _lib_dir + os.pathsep + os.environ.get("PATH", "")

        def _resolve_lib_assembly(sender, args):
            simple_name = args.Name.split(",")[0].strip()
            candidate = os.path.join(_lib_dir, simple_name + ".dll")
            if os.path.exists(candidate):
                from System.Reflection import Assembly
                return Assembly.LoadFrom(candidate)
            return None

        _AppDomain.CurrentDomain.AssemblyResolve += _resolve_lib_assembly

        _clr.AddReference("System")
        _hs_path = os.path.join(_lib_dir, "HidSharp.dll")
        if os.path.exists(_hs_path):
            _clr.AddReference(_hs_path)
        _lhm_path = os.path.join(_lib_dir, "LibreHardwareMonitorLib.dll")
        _clr.AddReference(_lhm_path)
        from LibreHardwareMonitor import Hardware as _LhmHardware
        _LHM_AVAILABLE = True
        logger.info("LibreHardwareMonitorLib loaded successfully")
    else:
        logger.warning("lib/ directory not found: %s", _lib_dir)
except Exception as e:
    _LHM_AVAILABLE = False
    logger.warning("LibreHardwareMonitorLib failed to load: %s", e, exc_info=True)


# ---------------------------------------------------------------------------
#  Sensor type metadata
# ---------------------------------------------------------------------------

SENSOR_TYPE_ORDER = {
    "Temperature": 0, "Fan": 1, "Power": 2, "Clock": 3,
    "Voltage": 4, "Load": 5, "Level": 6, "Data": 7,
    "Factor": 8, "Throughput": 9, "SmallData": 10, "Control": 11,
}

SENSOR_TYPE_UNIT = {
    "Temperature": "{:.1f} C",
    "Fan": "{:.0f} RPM",
    "Power": "{:.1f} W",
    "Clock": "{:.0f} MHz",
    "Voltage": "{:.3f} V",
    "Load": "{:.1f}%",
    "Level": "{:.1f}%",
    "Data": "{}",
    "Factor": "{:.0f}",
    "Throughput": "{}",
    "SmallData": "{}",
    "Control": "{:.1f}%",
}


def fmt_sensor_value(stype: str, val: float) -> str:
    """Format a sensor value with the appropriate unit based on its type."""
    if stype in ("Data", "SmallData"):
        return fmt_bytes(val * 1024 * 1024) if val < 100000 else f"{val:.0f} MB"
    if stype == "Throughput":
        return f"{fmt_bytes(val)}/s"
    try:
        fmt = SENSOR_TYPE_UNIT.get(stype, "{}")
        return fmt.format(val)
    except Exception:
        return str(val)


def hw_type_to_category(hw_type: str, hw_name: str) -> str:
    """Map a LibreHardwareMonitor HardwareType + name to a display category."""
    ht = hw_type.lower()
    if "cpu" in ht:
        return "CPU"
    if "gpu" in ht:
        return "GPU"
    if "motherboard" in ht or "superio" in ht:
        return "Motherboard"
    if "storage" in ht:
        name_lower = hw_name.lower()
        if "ssd" in name_lower or "nvme" in name_lower:
            return "SSD"
        if "hdd" in name_lower:
            return "Hard Disk"
        return "Disk"
    if "memory" in ht:
        return "Memory"
    if "network" in ht:
        return "Network"
    if "battery" in ht:
        return "Battery"
    if "psu" in ht:
        return "PSU"
    if "controller" in ht:
        return "Controller"
    return hw_name or "Other"
