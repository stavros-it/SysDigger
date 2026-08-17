"""System data collection: OS, hardware, network, external IP, sensors."""

from __future__ import annotations

import datetime
import getpass
import json
import os
import platform
import re
import socket
import subprocess
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

import psutil
import requests

from app_logger import get_logger
from paths import cache_dir
logger = get_logger(__name__)

try:
    import wmi as _wmi_mod
    _WMI_AVAILABLE = True
except Exception as _e:
    _WMI_AVAILABLE = False
    logger.warning("WMI module not available: %s", _e)

try:
    import pythoncom
    _PYTHONCOM_AVAILABLE = True
except Exception as _e:
    _PYTHONCOM_AVAILABLE = False
    logger.debug("pythoncom not available: %s", _e)


@contextmanager
def _com_context() -> Iterator[None]:
    """Context manager that initializes COM on entry and uninitializes on exit.

    COM is apartment-threaded; each thread that touches WMI/COM objects must
    call ``CoInitialize`` before and ``CoUninitialize`` after.  Wrapping the
    work in this context manager guarantees the uninit runs even on exceptions,
    fixing the long-standing leak (B-21) where ``CoUninitialize`` was never
    called across 13 sites.
    """
    if not _PYTHONCOM_AVAILABLE:
        yield
        return
    try:
        pythoncom.CoInitialize()
    except Exception:
        yield
        return
    try:
        yield
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass

from config import get_config
from helpers import (
    fmt_bytes, fmt_speed, fmt_uptime, fmt_wmi_time, s, reg_value,
    vram_from_registry, secsleft_is_valid,
)
from sensors import (
    _LHM_AVAILABLE, _LhmHardware,
    fmt_sensor_value, hw_type_to_category,
)


# Cloudflare data center IATA codes → city names.
# Source: https://www.cloudflare.com/en-gb/network/
_CLOUDFLARE_COLOS = {
    "AMS": "Amsterdam, Netherlands", "ARN": "Stockholm, Sweden",
    "ATH": "Athens, Greece", "ATL": "Atlanta, GA, USA",
    "AUS": "Austin, TX, USA", "BEG": "Belgrade, Serbia",
    "BOM": "Mumbai, India", "BOS": "Boston, MA, USA",
    "BRU": "Brussels, Belgium", "BUD": "Budapest, Hungary",
    "BUF": "Buffalo, NY, USA", "CPH": "Copenhagen, Denmark",
    "CLE": "Cleveland, OH, USA", "CLT": "Charlotte, NC, USA",
    "CMH": "Columbus, OH, USA", "DEL": "Delhi, India",
    "DEN": "Denver, CO, USA", "DFW": "Dallas-Fort Worth, TX, USA",
    "DME": "Moscow, Russia", "DUB": "Dublin, Ireland",
    "DUS": "Dusseldorf, Germany", "EWR": "Newark, NJ, USA",
    "EZE": "Buenos Aires, Argentina", "FRA": "Frankfurt, Germany",
    "GRU": "Sao Paulo, Brazil", "GVA": "Geneva, Switzerland",
    "HAM": "Hamburg, Germany", "HEL": "Helsinki, Finland",
    "HKG": "Hong Kong", "IAD": "Washington, DC, USA",
    "IAH": "Houston, TX, USA",
    "JNB": "Johannesburg, South Africa", "KIX": "Osaka, Japan",
    "KUL": "Kuala Lumpur, Malaysia", "LAS": "Las Vegas, NV, USA",
    "LAX": "Los Angeles, CA, USA", "LHR": "London, United Kingdom",
    "LIS": "Lisbon, Portugal", "MAD": "Madrid, Spain",
    "MEL": "Melbourne, Australia", "MIA": "Miami, FL, USA",
    "MIL": "Milan, Italy", "MIN": "Minneapolis, MN, USA",
    "MRS": "Marseille, France", "MUC": "Munich, Germany",
    "NBO": "Nairobi, Kenya", "NRT": "Tokyo, Japan",
    "ORD": "Chicago, IL, USA", "OTP": "Bucharest, Romania",
    "PHL": "Philadelphia, PA, USA", "PHX": "Phoenix, AZ, USA",
    "PRG": "Prague, Czech Republic", "QRO": "Queretaro, Mexico",
    "RDU": "Raleigh, NC, USA", "RIX": "Riga, Latvia",
    "SCL": "Santiago, Chile", "SEA": "Seattle, WA, USA",
    "SIN": "Singapore", "SJC": "San Jose, CA, USA",
    "SOF": "Sofia, Bulgaria", "STO": "Stockholm, Sweden",
    "SYD": "Sydney, Australia", "TPE": "Taipei, Taiwan",
    "TLS": "Toulouse, France", "TOR": "Toronto, Canada",
    "TTL": "Tallinn, Estonia", "VIE": "Vienna, Austria",
    "WAW": "Warsaw, Poland", "ZAG": "Zagreb, Croatia",
    "ZRH": "Zurich, Switzerland",
}


@dataclass
class SystemData:
    """Container for all gathered data (refreshed in-place)."""
    os_info: dict[str, str] = field(default_factory=dict)
    hw_info: dict[str, Any] = field(default_factory=dict)
    net_info: list[dict[str, Any]] = field(default_factory=list)
    ext_ip_info: dict[str, str] = field(default_factory=dict)
    ext_ip_error: str = ""
    ext_ip_time: str = ""
    processes: list[dict[str, Any]] = field(default_factory=list)
    startup_programs: list[dict[str, Any]] = field(default_factory=list)
    installed_programs: list[dict[str, Any]] = field(default_factory=list)
    update_history: list[dict[str, Any]] = field(default_factory=list)
    health_info: dict[str, Any] = field(default_factory=dict)
    speed_test_result: dict[str, Any] = field(default_factory=dict)
    bufferbloat_result: dict[str, Any] = field(default_factory=dict)
    devices_info: dict[str, Any] = field(default_factory=dict)
    diagnostics_info: dict[str, Any] = field(default_factory=dict)
    gpu_details: list[dict[str, Any]] = field(default_factory=list)
    vpn_status: dict[str, Any] = field(default_factory=dict)
    services_info: list[dict[str, str]] = field(default_factory=list)
    drivers_info: list[dict[str, str]] = field(default_factory=list)
    restore_points: list[dict[str, str]] = field(default_factory=list)
    environment_info: dict[str, str] = field(default_factory=dict)
    active_connections: list[dict[str, str]] = field(default_factory=list)
    wifi_info: dict[str, str] = field(default_factory=dict)
    dns_cache: list[dict[str, str]] = field(default_factory=list)
    disk_benchmark: dict[str, Any] = field(default_factory=dict)
    startup_impact: dict[str, Any] = field(default_factory=dict)


class Collector:
    """Collects system data. Static info loaded once; dynamic info refreshed."""

    def __init__(self) -> None:
        self.data = SystemData()
        self._lhm_computer = None
        self._cache_dir = cache_dir()
        self._wmi_local = threading.local()
        self._process_cpu_primed = False
        self._process_io_prev: dict[int, tuple[int, int]] = {}
        self._process_io_time: float = 0.0
        # Shared caches between collect_processes() and
        # collect_active_connections() to avoid duplicating expensive
        # psutil.process_iter and psutil.net_connections syscalls (each
        # ~50-200ms on a busy system) on every 5s refresh.
        self._pid_name_cache: dict[int, str] = {}
        self._net_conns_cache: list = []
        self._lhm_lock = threading.Lock()
        self._sensor_read_lock = threading.Lock()
        self._kb_title_cache: dict[str, tuple[float, str]] = {}
        # PDH query cache for AMD per-core frequency (opened lazily by
        # _read_amd_per_core_freqs, reused on every 2s refresh).
        self._pdh_query = None
        self._pdh_perf_counters: list = []
        self._pdh_base_freq: float = 0.0
        self._pdh_lock = threading.Lock()
        self._kb_title_ttl = 7 * 24 * 3600  # 7 days
        self._lhm_process = None

    def _init_wmi(self) -> None:
        """Create a WMI connection for the current thread. COM is
        apartment-threaded, so each thread needs its own connection.

        Note: ``CoInitialize`` is called but ``CoUninitialize`` is
        intentionally NOT called here — the thread-local WMI connection
        needs COM to stay initialized for the thread's lifetime.  This
        is one ``CoInitialize`` per collection thread (4 total) and is
        cleaned up automatically by Windows when each thread exits.
        Short-lived COM usage (ad-hoc WMI namespaces, firewall COM
        dispatch) uses the ``_com_context()`` / ``_wmi_namespace()``
        helpers which properly pair init/uninit.
        """
        if getattr(self._wmi_local, "wmi", None) is not None:
            return
        if _WMI_AVAILABLE and _PYTHONCOM_AVAILABLE:
            try:
                pythoncom.CoInitialize()
            except Exception:
                pass
            try:
                self._wmi_local.wmi = _wmi_mod.WMI()
            except Exception:
                self._wmi_local.wmi = None

    @property
    def _wmi_conn(self):
        """Get the WMI connection for the current thread.

        Returns ``None`` if the current thread has not called
        ``_init_wmi()``.  Callers that need WMI must call ``_init_wmi()``
        at thread entry — never fall back to another thread's connection
        (B-11: cross-thread COM violation).
        """
        return getattr(self._wmi_local, "wmi", None)

    @contextmanager
    def _wmi_namespace(self, namespace: str = "root/cimv2") -> Iterator[Any]:
        """Context manager that creates a short-lived WMI connection to the
        given namespace, paired with proper COM init/uninit.

        Use for ad-hoc namespace queries (root/WMI, root/Storage, etc.)
        instead of bare ``_wmi_mod.WMI(namespace=...)`` calls, which leaked
        the COM apartment (I-02).  The connection goes out of scope (and is
        garbage-collected) before ``CoUninitialize`` runs.
        """
        if not _WMI_AVAILABLE:
            yield None
            return
        with _com_context():
            conn = None
            try:
                conn = _wmi_mod.WMI(namespace=namespace)
                yield conn
            finally:
                # The caller's `as` variable still holds a reference; this
                # only clears the local alias.  Callers must not retain the
                # connection past the `with` block so COM pointers are
                # released before CoUninitialize runs in _com_context's
                # __exit__.
                conn = None

    # -- Disk cache for static data ----------------------------------------- #
    def clear_cache(self) -> None:
        """Clear the static data cache so the next collection fetches fresh data."""
        try:
            import shutil
            if os.path.isdir(self._cache_dir):
                shutil.rmtree(self._cache_dir)
        except Exception:
            pass

    def _cache_read(self, name: str) -> Any | None:
        path = os.path.join(self._cache_dir, f"{name}.json")
        try:
            with open(path, "r") as f:
                data = json.load(f)
            ts = data.get("_ts", 0)
            if time.time() - ts > get_config().cache_ttl_seconds:
                return None
            return data.get("value")
        except Exception:
            return None

    def _cache_write(self, name: str, value: Any) -> None:
        try:
            os.makedirs(self._cache_dir, exist_ok=True)
            path = os.path.join(self._cache_dir, f"{name}.json")
            with open(path, "w") as f:
                json.dump({"_ts": time.time(), "value": value}, f)
        except Exception:
            pass

    # -- OS ----------------------------------------------------------------- #
    def collect_os(self) -> None:
        logger.info("Collecting OS info")
        d: dict[str, str] = {}
        try:
            d["Computer Name"] = socket.gethostname()
        except Exception:
            d["Computer Name"] = platform.node()
        try:
            d["Logged-on User"] = f"{d['Computer Name']}\\{getpass.getuser()}"
        except Exception:
            d["Logged-on User"] = "N/A"
        d["Operating System"] = "Unknown"
        d["OS Edition"] = "N/A"
        d["Version"] = "N/A"
        d["Build Number"] = "N/A"
        d["Release ID"] = "N/A"
        d["Architecture (OS)"] = f"{platform.architecture()[0]}"
        d["Domain / Workgroup"] = "N/A"
        d["Install Date"] = "N/A"
        d["Last Boot Time"] = "N/A"
        d["Uptime"] = "N/A"

        cached_os = self._cache_read("os_static")
        if cached_os:
            d.update(cached_os)
        else:
            if self._wmi_conn:
                try:
                    for os_obj in self._wmi_conn.Win32_OperatingSystem():
                        d["Operating System"] = s(os_obj.Caption, d["Operating System"])
                        d["Version"] = s(os_obj.Version)
                        d["Build Number"] = s(os_obj.BuildNumber)
                        d["Architecture (OS)"] = s(os_obj.OSArchitecture, d["Architecture (OS)"])
                        if os_obj.InstallDate is not None:
                            d["Install Date"] = fmt_wmi_time(os_obj.InstallDate)
                        if os_obj.LastBootUpTime is not None:
                            d["Last Boot Time"] = fmt_wmi_time(os_obj.LastBootUpTime)
                        break
                except Exception as e:
                    logger.error("OS WMI query failed: %s", e, exc_info=True)
                try:
                    for cs in self._wmi_conn.Win32_ComputerSystem():
                        domain = s(cs.Domain)
                        part = getattr(cs, "PartOfDomain", False)
                        if part:
                            d["Domain / Workgroup"] = f"Domain: {domain}"
                        else:
                            d["Domain / Workgroup"] = f"Workgroup: {domain}"
                        break
                except Exception as e:
                    logger.error("ComputerSystem WMI query failed: %s", e,
                                exc_info=True)

            reg_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
            dv = reg_value(reg_path, "DisplayVersion")
            if dv:
                d["Release ID"] = dv
            ed = reg_value(reg_path, "EditionID")
            if ed:
                d["OS Edition"] = ed

            static_fields = {k: v for k, v in d.items()
                            if k not in ("Uptime", "Last Boot Time")}
            self._cache_write("os_static", static_fields)

        try:
            d["Architecture (Processor)"] = platform.machine()
        except Exception:
            d["Architecture (Processor)"] = "N/A"

        self.data.os_info = d

    # -- Hardware ----------------------------------------------------------- #
    def collect_hardware(self) -> None:
        logger.info("Collecting hardware info")
        hw: dict[str, Any] = {}

        cached_hw = self._cache_read("hw_static")
        if cached_hw:
            hw.update(cached_hw)
        else:
            static: dict[str, Any] = {}
            self._collect_hardware_static(static)
            self._cache_write("hw_static", static)
            hw.update(static)

        # Add dynamic placeholders (filled by refresh_dynamic)
        hw.setdefault("cpu", {})["Usage"] = "0.0%"
        hw.setdefault("cpu", {})["Per-core Usage"] = ""
        hw.setdefault("cpu", {})["Current Freq"] = "N/A"
        hw.setdefault("ram", {})["Total"] = "N/A"
        hw.setdefault("ram", {})["Used"] = "N/A"
        hw.setdefault("ram", {})["Available"] = "N/A"
        hw.setdefault("ram", {})["Usage %"] = "0.0%"
        for d in hw.get("disks", []):
            d["Free"] = "N/A"
            d["Usage %"] = "N/A"

        bat: dict[str, Any] = {"Present": False}
        if hasattr(psutil, "sensors_battery"):
            try:
                b = psutil.sensors_battery()
                if b is not None:
                    bat["Present"] = True
                    bat["Percent"] = f"{b.percent:.0f}%"
                    bat["Plugged In"] = "Yes" if b.power_plugged else "No"
                    bat["Charging"] = "Yes" if b.power_plugged and b.percent < 100 else "No"
                    secs = b.secsleft
                    if secsleft_is_valid(secs):
                        bat["Time Left"] = fmt_uptime(secs)
                    else:
                        bat["Time Left"] = "N/A"
            except Exception as e:
                logger.error("Battery info collection failed: %s", e,
                            exc_info=True)

        # Battery health & wear via WMI root/WMI namespace
        if bat.get("Present"):
            with self._wmi_namespace("root/WMI") as bat_wmi:
                if bat_wmi is not None:
                    try:
                        design_cap = None
                        full_cap = None
                        cycle_count = None
                        try:
                            for bd in bat_wmi.BatteryStaticData():
                                design_cap = getattr(bd, "DesignedCapacity", None)
                                break
                        except Exception:
                            pass
                        try:
                            for bf in bat_wmi.BatteryFullChargedCapacity():
                                full_cap = getattr(bf, "FullChargedCapacity", None)
                                break
                        except Exception:
                            pass
                        try:
                            for bc in bat_wmi.BatteryCycleCount():
                                cycle_count = getattr(bc, "CycleCount", None)
                                break
                        except Exception:
                            pass
                        if design_cap and design_cap > 0:
                            bat["Design Capacity"] = f"{design_cap} mWh"
                        if full_cap and full_cap > 0:
                            bat["Full Charge Capacity"] = f"{full_cap} mWh"
                        if design_cap and full_cap and design_cap > 0:
                            wear = max(0, (1 - full_cap / design_cap) * 100)
                            bat["Wear %"] = f"{wear:.1f}%"
                        if cycle_count is not None:
                            bat["Cycle Count"] = str(cycle_count)
                    except Exception as e:
                        logger.debug("Battery WMI health query failed: %s", e)

        hw["battery"] = bat

        # Set hw_info BEFORE collecting sensors so that
        # _apply_amd_cpu_fallbacks() can read the CPU name to detect AMD.
        self.data.hw_info = hw

        try:
            hw["sensors"] = self._collect_sensors()
        except Exception as e:
            logger.error("Sensor collection failed: %s", e, exc_info=True)
            hw["sensors"] = {"available": False, "source": "None",
                             "hint": f"Sensor collection error: {e}",
                             "temperatures": [], "fans": [], "powers": [],
                             "clocks": [], "voltages": [], "loads": [],
                             "levels": [], "data": [], "factors": [],
                             "throughputs": [], "smalldata": [],
                             "controls": []}

    def _collect_hardware_static(self, static: dict[str, Any]) -> None:
        """Collect static hardware info, with per-section error boundaries.

        Each section (CPU, RAM, motherboard, BIOS, GPU, disks) is wrapped in
        its own try/except so a failure in one doesn't break the others.
        """
        # -- CPU ---------------------------------------------------------- #
        try:
            cpu: dict[str, Any] = {}
            cpu["Name"] = platform.processor() or "N/A"
            cpu["Max Clock"] = "N/A"
            phys = log = 0
            if self._wmi_conn:
                try:
                    for p in self._wmi_conn.Win32_Processor():
                        cpu["Name"] = s(p.Name, cpu["Name"])
                        try:
                            phys = int(getattr(p, "NumberOfCores", 0) or 0)
                        except Exception:
                            phys = 0
                        try:
                            log = int(getattr(p, "NumberOfLogicalProcessors", 0) or 0)
                        except Exception:
                            log = 0
                        try:
                            mcs = int(getattr(p, "MaxClockSpeed", 0) or 0)
                            if mcs:
                                cpu["Max Clock"] = f"{mcs} MHz"
                        except Exception:
                            pass
                        break
                except Exception as e:
                    logger.error("CPU WMI query failed: %s", e, exc_info=True)
            cpu["Physical Cores"] = str(phys or psutil.cpu_count(logical=False) or "N/A")
            cpu["Logical Cores"] = str(log or psutil.cpu_count(logical=True) or "N/A")
            cpu["Threads"] = cpu["Logical Cores"]
            static["cpu"] = cpu
        except Exception as e:
            logger.error("CPU info collection failed: %s", e, exc_info=True)
            static["cpu"] = {"Name": "N/A", "Max Clock": "N/A",
                             "Physical Cores": "N/A", "Logical Cores": "N/A",
                             "Threads": "N/A"}

        # -- RAM ---------------------------------------------------------- #
        try:
            ram: dict[str, Any] = {}
            slots = []
            total = 0
            if self._wmi_conn:
                try:
                    for mem in self._wmi_conn.Win32_PhysicalMemory():
                        try:
                            cap = int(getattr(mem, "Capacity", 0) or 0)
                        except Exception:
                            cap = 0
                        total += cap
                        speed = getattr(mem, "Speed", None)
                        conf = getattr(mem, "ConfiguredClockSpeed", None)
                        if speed:
                            speed_str = f"{int(speed)} MT/s"
                        else:
                            speed_str = "N/A"
                        if conf:
                            try:
                                speed_str += f" (configured {int(conf)} MHz)"
                            except Exception:
                                pass
                        slots.append({
                            "Slot": len(slots) + 1,
                            "Manufacturer": s(getattr(mem, "Manufacturer", None)),
                            "Part Number": s(getattr(mem, "PartNumber", None)),
                            "Capacity": fmt_bytes(cap) if cap else "N/A",
                            "Speed": speed_str,
                            "Serial": s(getattr(mem, "SerialNumber", None)),
                        })
                except Exception as e:
                    logger.error("RAM WMI query failed: %s", e, exc_info=True)
            ram["Slots"] = slots
            ram["Total Installed"] = fmt_bytes(total) if total else "N/A"
            static["ram"] = ram
        except Exception as e:
            logger.error("RAM info collection failed: %s", e, exc_info=True)
            static["ram"] = {"Slots": [], "Total Installed": "N/A"}

        # -- Motherboard ------------------------------------------------- #
        try:
            mb: dict[str, str] = {}
            if self._wmi_conn:
                try:
                    for bb in self._wmi_conn.Win32_BaseBoard():
                        mb["Manufacturer"] = s(getattr(bb, "Manufacturer", None))
                        mb["Model"] = s(getattr(bb, "Product", None))
                        mb["Version"] = s(getattr(bb, "Version", None))
                        mb["Serial Number"] = s(getattr(bb, "SerialNumber", None))
                        break
                except Exception as e:
                    logger.error("Motherboard WMI query failed: %s", e,
                                exc_info=True)
            static["motherboard"] = mb
        except Exception as e:
            logger.error("Motherboard info collection failed: %s", e,
                        exc_info=True)
            static["motherboard"] = {}

        # -- BIOS --------------------------------------------------------- #
        try:
            bios: dict[str, str] = {}
            if self._wmi_conn:
                try:
                    for b in self._wmi_conn.Win32_BIOS():
                        bios["Manufacturer"] = s(getattr(b, "Manufacturer", None))
                        bios["Name"] = s(getattr(b, "Name", None))
                        bios["Version"] = s(getattr(b, "Version", None))
                        bios["Release Date"] = fmt_wmi_time(getattr(b, "ReleaseDate", None))
                        bios["Serial Number"] = s(getattr(b, "SerialNumber", None))
                        break
                except Exception as e:
                    logger.error("BIOS WMI query failed: %s", e, exc_info=True)
            # Add UEFI / Secure Boot / TPM info
            try:
                uefi = self._collect_uefi_info()
                bios.update(uefi)
            except Exception as e:
                logger.debug("UEFI info collection failed: %s", e)
            static["bios"] = bios
        except Exception as e:
            logger.error("BIOS info collection failed: %s", e, exc_info=True)
            static["bios"] = {}

        # -- GPU(s) ------------------------------------------------------- #
        try:
            gpus = []
            if self._wmi_conn:
                try:
                    for vc in self._wmi_conn.Win32_VideoController():
                        vram_str = "N/A"
                        pnp_id = s(getattr(vc, "PNPDeviceID", None)) or ""
                        reg_vram = vram_from_registry(pnp_id)
                        if reg_vram and reg_vram > 0:
                            vram_str = fmt_bytes(reg_vram)
                        else:
                            vram = getattr(vc, "AdapterRAM", None)
                            try:
                                if vram and int(vram) > 0:
                                    vram_str = fmt_bytes(int(vram))
                            except Exception:
                                pass
                        res = ""
                        hr = getattr(vc, "CurrentHorizontalResolution", None)
                        vr = getattr(vc, "CurrentVerticalResolution", None)
                        if hr and vr:
                            res = f"{int(hr)} x {int(vr)}"
                            rr = getattr(vc, "CurrentRefreshRate", None)
                            if rr:
                                try:
                                    res += f" @ {int(rr)} Hz"
                                except Exception:
                                    pass

                        # Max supported resolution
                        max_res = ""
                        mhr = getattr(vc, "MaxHorizontalResolution", None)
                        mvr = getattr(vc, "MaxVerticalResolution", None)
                        if mhr and mvr:
                            max_res = f"{int(mhr)} x {int(mvr)}"
                            mrr = getattr(vc, "MaxRefreshRate", None)
                            if mrr:
                                try:
                                    max_res += f" @ {int(mrr)} Hz"
                                except Exception:
                                    pass

                        # Color depth
                        bpp = getattr(vc, "CurrentBitsPerPixel", None)
                        color_depth = f"{int(bpp)}-bit" if bpp else "N/A"

                        # Video memory type
                        _mem_types = {
                            1: "VRAM (dedicated)",
                            2: "UMA (unified)",
                            3: "Shared memory",
                            4: "AGP memory",
                        }
                        mem_type_code = getattr(vc, "VideoMemoryType", None)
                        mem_type = _mem_types.get(
                            mem_type_code, f"Unknown ({mem_type_code})") if mem_type_code else "N/A"

                        # Scan mode
                        _scan_modes = {1: "Non-Interlaced", 2: "Interlaced"}
                        scan_code = getattr(vc, "CurrentScanMode", None)
                        scan_mode = _scan_modes.get(
                            scan_code, f"Unknown ({scan_code})") if scan_code else "N/A"

                        # DAC type
                        dac = s(getattr(vc, "AdapterDACType", None)) or "N/A"

                        # Adapter compatibility (vendor)
                        vendor = s(getattr(vc, "AdapterCompatibility", None)) or "N/A"

                        # Video architecture
                        _arch = {
                            1: "Other", 2: "Unknown", 3: "CGA",
                            4: "EGA", 5: "VGA", 6: "SVGA",
                            7: "MDA", 8: "HGC", 9: "MCGA",
                            10: "8514A", 11: "XGA", 12: "Linear Frame Buffer",
                            13: "PC-98",
                        }
                        arch_code = getattr(vc, "VideoArchitecture", None)
                        arch = _arch.get(
                            arch_code, f"Unknown ({arch_code})") if arch_code else "N/A"

                        gpus.append({
                            "Name": s(getattr(vc, "Name", None)),
                            "Video Processor": s(getattr(vc, "VideoProcessor", None)),
                            "Driver Version": s(getattr(vc, "DriverVersion", None)),
                            "Driver Date": fmt_wmi_time(getattr(vc, "DriverDate", None)),
                            "VRAM": vram_str,
                            "Resolution": res or "N/A",
                            "Max Resolution": max_res or "N/A",
                            "Color Depth": color_depth,
                            "Max Refresh Rate": f"{int(getattr(vc, 'MaxRefreshRate', 0) or 0)} Hz" if getattr(vc, "MaxRefreshRate", None) else "N/A",
                            "Memory Type": mem_type,
                            "Scan Mode": scan_mode,
                            "DAC Type": dac,
                            "Vendor": vendor,
                            "Architecture": arch,
                        })
                except Exception as e:
                    logger.error("GPU WMI query failed: %s", e, exc_info=True)
            static["gpus"] = gpus
        except Exception as e:
            logger.error("GPU info collection failed: %s", e, exc_info=True)
            static["gpus"] = []

        # -- Disks -------------------------------------------------------- #
        try:
            disks = []
            bus_by_index, bus_by_serial = self._get_disk_bus_types()
            if self._wmi_conn:
                try:
                    for dd in self._wmi_conn.Win32_DiskDrive():
                        try:
                            size = int(getattr(dd, "Size", 0) or 0)
                        except Exception:
                            size = 0
                        try:
                            disk_idx = int(getattr(dd, "Index", -1))
                        except Exception:
                            disk_idx = -1
                        pnp_id = s(getattr(dd, "PNPDeviceID", None)) or ""
                        model = s(getattr(dd, "Model", None))
                        serial = s(getattr(dd, "SerialNumber", None))

                        interface, media_type = "", ""
                        if disk_idx in bus_by_index:
                            interface, media_type = bus_by_index[disk_idx]
                        elif serial and serial in bus_by_serial:
                            interface, media_type = bus_by_serial[serial]
                        if not interface:
                            interface = self._infer_interface_from_pnp(
                                pnp_id, model
                            ) or s(getattr(dd, "InterfaceType", None))
                        if not media_type:
                            media_type = s(getattr(dd, "MediaType", None))

                        link_speed = self._get_disk_link_speed(
                            disk_idx, interface, pnp_id
                        )
                        disks.append({
                            "Index": disk_idx if disk_idx >= 0 else len(disks),
                            "Model": model,
                            "Size": fmt_bytes(size) if size else "N/A",
                            "Interface": interface,
                            "Link Speed": link_speed,
                            "Media Type": media_type,
                            "Serial": serial,
                            "Firmware": s(getattr(dd, "FirmwareRevision", None)),
                        })
                except Exception as e:
                    logger.error("Disk WMI query failed: %s", e, exc_info=True)
            static["disks"] = disks
        except Exception as e:
            logger.error("Disk info collection failed: %s", e, exc_info=True)
            static["disks"] = []

    def refresh_sensors(self) -> None:
        """Re-collect only sensor data (for live refresh).

        Also updates hw_info cpu Usage/Per-core from LHM Load sensors
        so the Hardware page stays in sync with the 2s sensor refresh.
        """
        try:
            self.data.hw_info["sensors"] = self._collect_sensors()
        except Exception as e:
            logger.error("Sensor refresh failed: %s", e, exc_info=True)
            return

        # Update CPU Usage and Per-core from LHM Load sensors
        loads = self.data.hw_info.get("sensors", {}).get("loads", [])
        cpu_total = None
        per_core: list[tuple[int, float]] = []
        for entry in loads:
            if entry.get("Category") != "CPU":
                continue
            name = entry.get("Name", "")
            val = entry.get("Value", 0.0)
            if name == "CPU Total":
                cpu_total = val
            elif name.startswith("CPU Core #") and name != "CPU Core Max":
                try:
                    core_num = int(name.replace("CPU Core #", ""))
                    per_core.append((core_num, val))
                except ValueError:
                    pass
        if cpu_total is not None:
            self.data.hw_info["cpu"]["Usage"] = f"{cpu_total:.1f}%"
        if per_core:
            per_core.sort()
            self.data.hw_info["cpu"]["Per-core Usage"] = "  ".join(
                f"{v:5.1f}%" for _, v in per_core)

        # Update Current Freq from LHM Clock sensors (fall back to psutil)
        clocks = self.data.hw_info.get("sensors", {}).get("clocks", [])
        cpu_clock = None
        for entry in clocks:
            if entry.get("Category") != "CPU":
                continue
            name = entry.get("Name", "")
            val = entry.get("Value", 0.0)
            if name == "Cores (Average)" and val > 0:
                cpu_clock = val
                break
        if cpu_clock is not None:
            self.data.hw_info["cpu"]["Current Freq"] = f"{cpu_clock:.0f} MHz"
        else:
            try:
                freq = psutil.cpu_freq()
                if freq:
                    self.data.hw_info["cpu"]["Current Freq"] = (
                        f"{freq.current:.0f} MHz")
            except Exception:
                pass

        # Update RAM usage from psutil
        try:
            vm = psutil.virtual_memory()
            self.data.hw_info["ram"]["Total"] = fmt_bytes(vm.total)
            self.data.hw_info["ram"]["Used"] = fmt_bytes(vm.used)
            self.data.hw_info["ram"]["Available"] = fmt_bytes(vm.available)
            self.data.hw_info["ram"]["Usage %"] = f"{vm.percent:.1f}%"
        except Exception:
            pass

    # -- Sensors (temperatures & fans) -------------------------------------- #
    def set_lhm_process(self, proc) -> None:
        """Attach a PawnIO driver manager for kernel-driver-assisted reads.

        When the PawnIO driver is installed (via the standalone installer),
        the existing DLL-based sensor collection automatically picks up
        motherboard SuperIO sensors and AMD CPU MSR registers.  We
        invalidate the cached Computer so the next _collect_sensors call
        recreates it with the driver now available.
        """
        self._lhm_process = proc
        if proc and proc.is_driver_ready():
            with self._lhm_lock:
                old = self._lhm_computer
                self._lhm_computer = None
            if old is not None:
                # Close under _sensor_read_lock too: the 2s refresh timer
                # may be iterating old.Hardware at this moment. Without
                # this lock, old.Close() can race with the iteration and
                # crash or return empty results for one refresh cycle.
                with self._sensor_read_lock:
                    try:
                        old.Close()
                    except Exception:
                        pass

    def close(self) -> None:
        """Release cached resources (PDH query, etc.).  Called on app exit."""
        with self._pdh_lock:
            if self._pdh_query is not None:
                try:
                    import win32pdh
                    win32pdh.CloseQuery(self._pdh_query)
                except Exception:
                    pass
                self._pdh_query = None
                self._pdh_perf_counters = []

    def _get_lhm_computer(self):
        """Get or create the persistent LHM Computer object."""
        if self._lhm_computer is not None:
            return self._lhm_computer
        if not _LHM_AVAILABLE:
            return None
        with self._lhm_lock:
            if self._lhm_computer is not None:
                return self._lhm_computer
            try:
                computer = _LhmHardware.Computer()
                lhm_settings = get_config().get_lhm_computer_settings()
                for prop_name, enabled in lhm_settings.items():
                    setattr(computer, prop_name, enabled)
                computer.Open()
                self._lhm_computer = computer
                return computer
            except Exception as e:
                logger.error("Failed to initialize LHM Computer: %s", e,
                            exc_info=True)
                return None

    def _collect_sensors(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "available": False,
            "source": "None",
            "temperatures": [], "fans": [], "powers": [], "clocks": [],
            "voltages": [], "loads": [], "levels": [], "data": [],
            "factors": [], "throughputs": [], "smalldata": [],
            "controls": [], "hint": "",
        }

        if not _LHM_AVAILABLE:
            result["hint"] = (
                "Install pythonnet (pip install pythonnet) and ensure the "
                "lib/ folder contains LibreHardwareMonitorLib.dll + HidSharp.dll "
                "for sensor data."
            )
            return self._collect_sensors_wmi_fallback(result)

        computer = self._get_lhm_computer()
        if computer is None:
            result["hint"] = "Failed to initialize LibreHardwareMonitor."
            return result

        try:
            with self._sensor_read_lock:
                for hw_obj in computer.Hardware:
                    hw_name = str(hw_obj.Name)
                    hw_type = str(hw_obj.HardwareType)
                    hw_obj.Update()
                    self._read_sensors(hw_obj, hw_name, hw_type, result)
                    for sub in hw_obj.SubHardware:
                        sub.Update()
                        sub_name = str(sub.Name)
                        sub_type = str(sub.HardwareType)
                        self._read_sensors(sub, sub_name, sub_type, result)

            if (result["temperatures"] or result["fans"] or result["powers"]
                    or result["clocks"] or result["voltages"] or result["loads"]
                    or result["levels"] or result["data"] or result["factors"]
                    or result["throughputs"] or result["smalldata"]
                    or result["controls"]):
                result["available"] = True
                result["source"] = "LibreHardwareMonitor"
            else:
                result["hint"] = "No sensor data returned. Try running as administrator."
        except Exception as e:
            result["hint"] = f"Sensor error: {e}"

        self._apply_amd_cpu_fallbacks(result)
        return result

    def _read_sensors(self, hw_obj, hw_name: str, hw_type: str,
                      result: dict[str, Any]) -> None:
        import math
        category = hw_type_to_category(hw_type, hw_name)
        cfg = get_config()
        for sensor in hw_obj.Sensors:
            stype = str(sensor.SensorType)
            if not cfg.is_sensor_type_enabled(stype):
                continue
            name = str(sensor.Name)
            val = sensor.Value
            if val is None:
                continue
            try:
                fval = float(val)
            except (TypeError, ValueError):
                continue
            if math.isnan(fval) or math.isinf(fval):
                continue
            entry = {
                "Name": name, "Value": fval, "Source": hw_name,
                "Type": stype, "Category": category,
            }
            if stype == "Temperature":
                result["temperatures"].append(entry)
            elif stype == "Fan":
                result["fans"].append(entry)
            elif stype == "Power":
                result["powers"].append(entry)
            elif stype == "Clock":
                result["clocks"].append(entry)
            elif stype == "Voltage":
                result["voltages"].append(entry)
            elif stype == "Load":
                result["loads"].append(entry)
            elif stype == "Level":
                result["levels"].append(entry)
            elif stype == "Data":
                result["data"].append(entry)
            elif stype == "Factor":
                result["factors"].append(entry)
            elif stype == "Throughput":
                result["throughputs"].append(entry)
            elif stype == "SmallData":
                result["smalldata"].append(entry)
            elif stype == "Control":
                result["controls"].append(entry)

    def _read_amd_per_core_freqs(self) -> list[float]:
        """Read live per-core effective frequencies on AMD via Windows PDH.

        Uses the ``% Processor Performance`` performance counter per logical
        core, multiplied by the base frequency from ``psutil.cpu_freq()``.
        On AMD Zen, this counter tracks boost/throttle events correctly
        (>100% = boost above base, <100% = throttle below base).

        The PDH query + counters are cached on the instance so the 2s
        refresh timer doesn't re-open them every cycle.
        """
        try:
            import win32pdh
        except ImportError:
            return []
        # PDH query handles are not thread-safe — CollectQueryData and
        # GetFormattedCounterValue on the same query from two threads
        # (collect_hardware thread + 2s refresh_sensors timer) can corrupt
        # internal state.  Guard with a lock.
        try:
            with self._pdh_lock:
                # Reuse the cached PDH query if available (opened on first call).
                query = self._pdh_query
                counters = self._pdh_perf_counters
                base_freq = self._pdh_base_freq
                if query is None:
                    base_freq_info = psutil.cpu_freq()
                    if not base_freq_info or base_freq_info.current <= 0:
                        return []
                    base_freq = float(base_freq_info.current)
                    self._pdh_base_freq = base_freq

                    query = win32pdh.OpenQuery()
                    self._pdh_query = query
                    counters = []
                    n_logical = psutil.cpu_count(logical=True) or 1
                    n_physical = psutil.cpu_count(logical=False) or 1
                    # PDH instance format is "NUMA,Logical" — e.g. "0,0" through
                    # "0,15" for a 16-thread CPU.  We read one counter per
                    # PHYSICAL core (the first N logical threads map 1:1 to
                    # physical cores on AMD Zen SMT).
                    for i in range(n_physical):
                        inst = f"0,{i}"
                        path = (rf"\Processor Information({inst})"
                                r"\% Processor Performance")
                        try:
                            c = win32pdh.AddEnglishCounter(query, path, 0)
                            counters.append(c)
                        except Exception:
                            pass
                    self._pdh_perf_counters = counters
                    # Prime the counter with a first sample (rate-based counters
                    # need two samples before they return data).
                    win32pdh.CollectQueryData(query)
                # Second sample — this returns the actual value.
                win32pdh.CollectQueryData(query)
                freqs: list[float] = []
                for c in counters:
                    try:
                        val = win32pdh.GetFormattedCounterValue(
                            c, win32pdh.PDH_FMT_DOUBLE)
                        perf_pct = val[1]
                        if perf_pct > 0:
                            freqs.append(base_freq * perf_pct / 100.0)
                        else:
                            freqs.append(base_freq)
                    except Exception:
                        freqs.append(base_freq)
                return freqs
        except Exception as e:
            logger.debug("PDH per-core freq read failed: %s", e)
            return []

    def _apply_amd_cpu_fallbacks(self, result: dict[str, Any]) -> None:
        """Replace zero-value CPU Clock/Power sensors with live fallbacks.

        LHM 0.9.6 cannot read Clock and Power telemetry from the AMD SMU
        on Zen 2/3/4 CPUs (returns 0 MHz / 0 W).  This method detects that
        condition and replaces the zero-value Clock entries with real
        **effective** per-core frequencies read from the Windows PDH
        (Performance Data Helper) API:

        ``% Processor Performance`` counter reports the ratio of actual
        frequency to the advertised base frequency.  On AMD Zen this
        correctly tracks boost/throttle events (>100% = boost, <100% =
        throttle).  Multiplying by the base frequency yields the live
        effective frequency per core — no kernel driver needed.

        Zero-value CPU Power entries are removed entirely since there is
        no portable Python-side equivalent.  On Intel CPUs LHM reads
        Clock/Power/Voltage correctly, so this method is a no-op (guarded
        by the AMD vendor check).
        """
        cpu_name = self.data.hw_info.get("cpu", {}).get("Name", "CPU")
        if "AMD" not in cpu_name.upper():
            return

        # --- Clocks: replace 0-value CPU clocks with live PDH freqs -- #
        cpu_clocks = [e for e in result["clocks"]
                      if e.get("Category") == "CPU"]
        has_zero_cpu_clocks = any(
            e.get("Value", 0.0) == 0.0 for e in cpu_clocks)
        if cpu_clocks and has_zero_cpu_clocks:
            # Capture the LHM hardware Source name from existing CPU
            # entries so the psutil fallback clocks land on the SAME
            # Sensors tab as the CPU temperatures/loads/voltages.
            cpu_source = cpu_clocks[0].get("Source", cpu_name)
            live_freqs = self._read_amd_per_core_freqs()
            if live_freqs:
                # Remove the zero-value CPU clock entries from LHM.
                result["clocks"] = [e for e in result["clocks"]
                                     if e.get("Category") != "CPU"
                                     or e.get("Value", 0.0) != 0.0]
                # Add live per-core clocks.
                for i, freq in enumerate(live_freqs):
                    if freq > 0:
                        result["clocks"].append({
                            "Name": f"Core #{i + 1}",
                            "Value": float(freq),
                            "Source": cpu_source,
                            "Type": "Clock",
                            "Category": "CPU",
                        })
                avg = sum(live_freqs) / len(live_freqs)
                if avg > 0:
                    result["clocks"].append({
                        "Name": "Cores (Average)",
                        "Value": float(avg),
                        "Source": cpu_source,
                        "Type": "Clock",
                        "Category": "CPU",
                    })

        # --- Power: remove 0-value CPU power entries (no portable source) -- #
        result["powers"] = [e for e in result["powers"]
                            if e.get("Category") != "CPU"
                            or e.get("Value", 0.0) != 0.0]

    def _collect_sensors_wmi_fallback(self, result: dict[str, Any]) -> dict[str, Any]:
        with self._wmi_namespace("root/WMI") as acpi:
            if acpi is not None:
                try:
                    for tz in acpi.MSAcpi_ThermalZoneTemperature():
                        raw = getattr(tz, "CurrentTemperature", None)
                        if raw:
                            celsius = raw / 10.0 - 273.15
                            result["temperatures"].append({
                                "Name": "ACPI Thermal Zone",
                                "Value": celsius,
                                "Source": str(getattr(tz, "InstanceName", "")).strip(),
                                "Type": "Temperature",
                                "Category": "Motherboard",
                            })
                except Exception:
                    pass
        if self._wmi_conn:
            try:
                for p in self._wmi_conn.Win32_TemperatureProbe():
                    raw = getattr(p, "CurrentReading", None)
                    if raw:
                        celsius = raw / 10.0 - 273.15
                        result["temperatures"].append({
                            "Name": "Temperature Probe",
                            "Value": celsius,
                            "Source": str(getattr(p, "Description", "")).strip(),
                            "Type": "Temperature",
                            "Category": "Motherboard",
                        })
            except Exception:
                pass
            try:
                for f in self._wmi_conn.Win32_Fan():
                    speed = getattr(f, "DesiredSpeed", None)
                    if speed:
                        result["fans"].append({
                            "Name": "System Fan",
                            "Value": float(speed),
                            "Source": str(getattr(f, "Description", "")).strip(),
                            "Type": "Fan",
                            "Category": "Motherboard",
                        })
            except Exception:
                pass
        if result["temperatures"] or result["fans"]:
            result["available"] = True
            result["source"] = "WMI"
        return result

    # -- Disk interface detection ------------------------------------------- #
    _BUS_TYPE_MAP = {
        0: "Unknown", 1: "SCSI", 2: "ATAPI", 3: "ATA/PATA",
        4: "IEEE 1394", 5: "SSA", 6: "Fibre Channel",
        7: "USB", 8: "RAID", 9: "iSCSI", 10: "SAS",
        11: "SATA", 12: "SD", 13: "MMC", 14: "Max",
        15: "File-Backed Virtual", 16: "Storage Spaces",
        17: "NVMe",
    }

    _MEDIA_TYPE_MAP = {
        0: "Unspecified", 3: "HDD", 4: "SSD", 5: "SCM",
    }

    def _get_disk_bus_types(self) -> tuple[dict[int, tuple[str, str]], dict[str, tuple[str, str]]]:
        """Query MSFT_PhysicalDisk for bus type and media type.

        Returns a tuple of two dicts:
        - First: keyed by disk index (int) -> (bus_type, media_type)
        - Second: keyed by serial number (str) -> (bus_type, media_type)
        Falls back to empty dicts if the storage namespace is unavailable.
        """
        by_index: dict[int, tuple[str, str]] = {}
        by_serial: dict[str, tuple[str, str]] = {}
        if not _WMI_AVAILABLE:
            return by_index, by_serial
        with self._wmi_namespace("root/Microsoft/Windows/Storage") as storage_wmi:
            if storage_wmi is None:
                return by_index, by_serial
            try:
                for pd in storage_wmi.MSFT_PhysicalDisk():
                    try:
                        bus = int(getattr(pd, "BusType", 0))
                        media = int(getattr(pd, "MediaType", 0))
                        entry = (
                            self._BUS_TYPE_MAP.get(bus, f"Unknown ({bus})"),
                            self._MEDIA_TYPE_MAP.get(media, f"Unknown ({media})"),
                        )
                        dev_id = getattr(pd, "DeviceId", None)
                        if dev_id is not None:
                            try:
                                by_index[int(dev_id)] = entry
                            except (ValueError, TypeError):
                                pass
                        serial = str(getattr(pd, "SerialNumber", "")).strip()
                        if serial:
                            by_serial[serial] = entry
                    except Exception:
                        pass
            except Exception:
                pass
        return by_index, by_serial

    def _get_disk_link_speed(self, disk_index: int, interface: str,
                             pnp_id: str) -> str:
        """Determine the link speed/generation for a disk.

        SATA: sends IDENTIFY DEVICE via IOCTL_ATA_PASS_THROUGH and reads
              word 76 (SATA Capabilities) for the highest supported generation.
        NVMe: reads PCIe Link Status from PCI config space via SetupAPI.
        Other: returns the interface name as-is.
        """
        if interface == "SATA":
            gen = self._get_sata_generation(disk_index)
            return gen or "SATA"
        if interface == "NVMe":
            return self._get_nvme_pcie_link(pnp_id) or "PCIe"
        if interface == "SAS":
            return "SAS"
        return interface or "N/A"

    def _get_sata_generation(self, disk_index: int) -> str:
        """Query SATA generation supported by a disk via ATA IDENTIFY.

        Reads word 76 (SATA Capabilities) from IDENTIFY DEVICE data:
          bit 0 = 1.5 Gbps (Gen1), bit 1 = 3.0 Gbps (Gen2),
          bit 2 = 6.0 Gbps (Gen3)

        Two methods are tried in order:
        1. IOCTL_ATA_PASS_THROUGH (0x0004D02C) — modern, preferred
        2. DFP_RECEIVE_DRIVE_DATA (0x0007C088) — classic SMART IOCTL,
           broader compatibility with AHCI/storport drivers
        """
        import ctypes
        from ctypes import wintypes

        INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
        GENERIC_READ = 0x80000000
        GENERIC_WRITE = 0x40000000
        FILE_SHARE_READ = 0x00000001
        FILE_SHARE_WRITE = 0x00000002
        OPEN_EXISTING = 3

        k32 = ctypes.windll.kernel32
        k32.CreateFileW.restype = ctypes.c_void_p
        k32.CreateFileW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
            ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE
        ]
        k32.DeviceIoControl.argtypes = [
            wintypes.HANDLE, wintypes.DWORD,
            ctypes.c_void_p, wintypes.DWORD,
            ctypes.c_void_p, wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p
        ]
        k32.DeviceIoControl.restype = wintypes.BOOL
        k32.CloseHandle.argtypes = [wintypes.HANDLE]

        if disk_index < 0:
            return ""

        path = f"\\\\.\\PhysicalDrive{disk_index}"
        handle = k32.CreateFileW(
            path, GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None, OPEN_EXISTING, 0, None
        )
        if not handle or handle == INVALID_HANDLE_VALUE:
            handle = k32.CreateFileW(
                path, GENERIC_READ,
                FILE_SHARE_READ | FILE_SHARE_WRITE,
                None, OPEN_EXISTING, 0, None
            )
            if not handle or handle == INVALID_HANDLE_VALUE:
                return ""

        try:
            identify_data = self._identify_via_ata_pass_through(k32, handle)
            if identify_data is None:
                identify_data = self._identify_via_dfp(k32, handle, disk_index)
            if identify_data is None:
                return ""

            word0 = identify_data[0] | (identify_data[1] << 8)
            if word0 == 0 or word0 == 0xFFFF:
                return ""

            word76 = identify_data[152] | (identify_data[153] << 8)
            if word76 == 0 or word76 == 0xFFFF:
                return ""
            if word76 & 0x04:
                return "SATA 3.0 (6 Gbps)"
            if word76 & 0x02:
                return "SATA 2.0 (3 Gbps)"
            if word76 & 0x01:
                return "SATA 1.0 (1.5 Gbps)"
            return ""
        except Exception:
            return ""
        finally:
            k32.CloseHandle(handle)

    @staticmethod
    def _identify_via_ata_pass_through(k32, handle) -> bytearray | None:
        """IDENTIFY DEVICE via IOCTL_ATA_PASS_THROUGH (0x0004D02C).

        Uses ATA_PASS_THROUGH_EX with correct 64-bit layout (DWORD_PTR
        DataBufferOffset). Matches CrystalDiskInfo's struct which adds
        explicit padding on _WIN64.
        """
        import ctypes
        from ctypes import wintypes

        IOCTL_ATA_PASS_THROUGH = 0x0004D02C
        ATA_FLAGS_DATA_IN = 0x02

        class IDEREGS(ctypes.Structure):
            _pack_ = 1
            _fields_ = [
                ("bFeaturesReg", ctypes.c_uint8),
                ("bSectorCountReg", ctypes.c_uint8),
                ("bSectorNumberReg", ctypes.c_uint8),
                ("bCylLowReg", ctypes.c_uint8),
                ("bCylHighReg", ctypes.c_uint8),
                ("bDriveHeadReg", ctypes.c_uint8),
                ("bCommandReg", ctypes.c_uint8),
                ("bReserved", ctypes.c_uint8),
            ]

        class ATA_PASS_THROUGH_EX(ctypes.Structure):
            _fields_ = [
                ("Length", wintypes.USHORT),
                ("AtaFlags", wintypes.USHORT),
                ("PathId", ctypes.c_uint8),
                ("TargetId", ctypes.c_uint8),
                ("Lun", ctypes.c_uint8),
                ("ReservedAsUchar", ctypes.c_uint8),
                ("DataTransferLength", wintypes.ULONG),
                ("TimeOutValue", wintypes.ULONG),
                ("ReservedAsUlong", wintypes.ULONG),
                ("DataBufferOffset", ctypes.c_size_t),
                ("PreviousTaskFile", IDEREGS),
                ("CurrentTaskFile", IDEREGS),
            ]

        struct_size = ctypes.sizeof(ATA_PASS_THROUGH_EX)
        total_size = struct_size + 512
        combined = (ctypes.c_ubyte * total_size)()
        aptd = ATA_PASS_THROUGH_EX.from_buffer(combined)

        aptd.Length = struct_size
        aptd.AtaFlags = ATA_FLAGS_DATA_IN
        aptd.DataTransferLength = 512
        aptd.TimeOutValue = 5
        aptd.DataBufferOffset = struct_size
        aptd.CurrentTaskFile.bDriveHeadReg = 0xA0
        aptd.CurrentTaskFile.bCommandReg = 0xEC

        bytes_returned = wintypes.DWORD(0)
        buf_ptr = ctypes.cast(combined, ctypes.c_void_p)
        ok = k32.DeviceIoControl(
            handle, IOCTL_ATA_PASS_THROUGH,
            buf_ptr, total_size,
            buf_ptr, total_size,
            ctypes.byref(bytes_returned), None
        )
        if not ok:
            return None

        return bytearray(combined[struct_size:struct_size + 512])

    @staticmethod
    def _identify_via_dfp(k32, handle, disk_index: int) -> bytearray | None:
        """IDENTIFY DEVICE via DFP_RECEIVE_DRIVE_DATA (0x0007C088).

        Classic SMART IOCTL using SENDCMDINPARAMS/SENDCMDOUTPARAMS.
        Broader compatibility — works even when ATA_PASS_THROUGH is
        rejected by storport drivers.
        """
        import ctypes
        from ctypes import wintypes

        DFP_RECEIVE_DRIVE_DATA = 0x0007C088

        class IDEREGS(ctypes.Structure):
            _pack_ = 1
            _fields_ = [
                ("bFeaturesReg", ctypes.c_uint8),
                ("bSectorCountReg", ctypes.c_uint8),
                ("bSectorNumberReg", ctypes.c_uint8),
                ("bCylLowReg", ctypes.c_uint8),
                ("bCylHighReg", ctypes.c_uint8),
                ("bDriveHeadReg", ctypes.c_uint8),
                ("bCommandReg", ctypes.c_uint8),
                ("bReserved", ctypes.c_uint8),
            ]

        class DRIVERSTATUS(ctypes.Structure):
            _pack_ = 1
            _fields_ = [
                ("bDriverError", ctypes.c_uint8),
                ("bIDEError", ctypes.c_uint8),
                ("bReserved", ctypes.c_uint8 * 2),
                ("dwReserved", wintypes.DWORD * 4),
            ]

        class SENDCMDINPARAMS(ctypes.Structure):
            _pack_ = 1
            _fields_ = [
                ("cBufferSize", wintypes.DWORD),
                ("irDriveRegs", IDEREGS),
                ("bDriveNumber", ctypes.c_uint8),
                ("bReserved", ctypes.c_uint8 * 3),
                ("dwReserved", wintypes.DWORD * 4),
                ("bBuffer", ctypes.c_uint8 * 1),
            ]

        class SENDCMDOUTPARAMS(ctypes.Structure):
            _pack_ = 1
            _fields_ = [
                ("cBufferSize", wintypes.DWORD),
                ("DriverStatus", DRIVERSTATUS),
                ("bBuffer", ctypes.c_uint8 * 512),
            ]

        in_params = SENDCMDINPARAMS()
        in_params.cBufferSize = 512
        in_params.irDriveRegs.bFeaturesReg = 0
        in_params.irDriveRegs.bSectorCountReg = 0
        in_params.irDriveRegs.bSectorNumberReg = 0
        in_params.irDriveRegs.bCylLowReg = 0
        in_params.irDriveRegs.bCylHighReg = 0
        in_params.irDriveRegs.bDriveHeadReg = 0xA0 | ((disk_index & 1) << 4)
        in_params.irDriveRegs.bCommandReg = 0xEC
        in_params.bDriveNumber = disk_index & 1

        out_params = SENDCMDOUTPARAMS()
        bytes_returned = wintypes.DWORD(0)

        ok = k32.DeviceIoControl(
            handle, DFP_RECEIVE_DRIVE_DATA,
            ctypes.byref(in_params), ctypes.sizeof(in_params),
            ctypes.byref(out_params), ctypes.sizeof(out_params),
            ctypes.byref(bytes_returned), None
        )
        if not ok:
            return None
        if out_params.DriverStatus.bDriverError != 0:
            return None

        return bytearray(out_params.bBuffer)

    def _get_nvme_pcie_link(self, pnp_id: str) -> str:
        """Read PCIe link speed for an NVMe drive from PCI config space.

        Walks up the device tree from the disk's PNPDeviceID to find the
        parent PCI device, then reads its configuration space to locate
        the PCI Express Capability and extract the Link Status register
        (negotiated link speed + width).
        """
        if not pnp_id:
            return ""
        try:
            import ctypes
            from ctypes import wintypes

            CR_SUCCESS = 0x00
            CM_DRP_DEVICEDESC = 0x00000002
            CM_DRP_DEVICE_PCICONFIG = 0x0000001C

            _PCIE_SPEEDS = {
                1: "2.5 GT/s (Gen1)",
                2: "5 GT/s (Gen2)",
                3: "8 GT/s (Gen3)",
                4: "16 GT/s (Gen4)",
                5: "32 GT/s (Gen5)",
            }

            cfgapi = ctypes.windll.cfgmgr32
            cfgapi.CM_Locate_DevNodeW.argtypes = [
                ctypes.POINTER(wintypes.DWORD), wintypes.LPCWSTR, wintypes.ULONG
            ]
            cfgapi.CM_Locate_DevNodeW.restype = wintypes.DWORD
            cfgapi.CM_Get_Parent.argtypes = [
                ctypes.POINTER(wintypes.DWORD), wintypes.DWORD, wintypes.ULONG
            ]
            cfgapi.CM_Get_Parent.restype = wintypes.DWORD
            cfgapi.CM_Get_Device_IDW.argtypes = [
                wintypes.DWORD, wintypes.LPWSTR, wintypes.ULONG, wintypes.ULONG
            ]
            cfgapi.CM_Get_Device_IDW.restype = wintypes.DWORD
            cfgapi.CM_Get_DevNode_Registry_PropertyW.argtypes = [
                wintypes.DWORD, wintypes.ULONG, ctypes.POINTER(wintypes.ULONG),
                ctypes.c_void_p, ctypes.POINTER(wintypes.ULONG), wintypes.ULONG
            ]
            cfgapi.CM_Get_DevNode_Registry_PropertyW.restype = wintypes.DWORD

            def _get_dev_node(device_id: str) -> int | None:
                dev_node = wintypes.DWORD(0)
                ret = cfgapi.CM_Locate_DevNodeW(
                    ctypes.byref(dev_node), device_id, 0
                )
                if ret != CR_SUCCESS:
                    return None
                return dev_node.value

            def _get_device_id(dev_node: int) -> str:
                buf = ctypes.create_unicode_buffer(1024)
                ret = cfgapi.CM_Get_Device_IDW(dev_node, buf, 1024, 0)
                if ret != CR_SUCCESS:
                    return ""
                return buf.value

            def _get_parent(dev_node: int) -> int | None:
                parent = wintypes.DWORD(0)
                ret = cfgapi.CM_Get_Parent(
                    ctypes.byref(parent), dev_node, 0
                )
                if ret != CR_SUCCESS:
                    return None
                return parent.value

            def _read_pci_link_status(dev_node: int) -> str:
                buf = (wintypes.BYTE * 4096)()
                length = wintypes.ULONG(4096)
                ret = cfgapi.CM_Get_DevNode_Registry_PropertyW(
                    dev_node, CM_DRP_DEVICE_PCICONFIG, None,
                    buf, ctypes.byref(length), 0
                )
                if ret != CR_SUCCESS or length.value < 0x100:
                    return ""
                cap_ptr = buf[0x34]
                while cap_ptr != 0 and cap_ptr + 1 < length.value:
                    cap_id = buf[cap_ptr]
                    if cap_id == 0x10:
                        ls_off = cap_ptr + 0x12
                        if ls_off + 1 < length.value:
                            raw = buf[ls_off] | (buf[ls_off + 1] << 8)
                            speed_code = raw & 0x0F
                            width = (raw >> 4) & 0x3F
                            speed_str = _PCIE_SPEEDS.get(
                                speed_code, f"Unknown ({speed_code})"
                            )
                            if width:
                                return f"PCIe {speed_str} x{width}"
                            return f"PCIe {speed_str}"
                        break
                    next_ptr_off = cap_ptr + 1
                    if next_ptr_off < length.value:
                        cap_ptr = buf[next_ptr_off]
                    else:
                        break
                return ""

            dev_node = _get_dev_node(pnp_id)
            if dev_node is None:
                return ""

            for _ in range(3):
                parent = _get_parent(dev_node)
                if parent is None:
                    break
                dev_id = _get_device_id(parent)
                if dev_id.upper().startswith("PCI"):
                    result = _read_pci_link_status(parent)
                    if result:
                        return result
                dev_node = parent
            return ""
        except Exception:
            return ""

    @staticmethod
    def _infer_interface_from_pnp(pnp_id: str, model: str) -> str:
        """Infer the interface type from the PNPDeviceID prefix and model.

        Used as a fallback when MSFT_PhysicalDisk is unavailable.
        SATA AHCI disks often report as SCSI\\ in PNPDeviceID, so we check
        for NVMe first (in both PNP ID and model) before falling back to
        SATA for generic SCSI devices.
        """
        pnp_lower = pnp_id.lower()
        model_lower = model.lower()
        if "nvme" in pnp_lower or "nvme" in model_lower:
            return "NVMe"
        if pnp_lower.startswith("usbstor"):
            return "USB"
        if pnp_lower.startswith("ide"):
            return "IDE/PATA"
        if "sas" in pnp_lower and "sata" not in pnp_lower:
            return "SAS"
        if pnp_lower.startswith("scsi") or pnp_lower.startswith("pci"):
            return "SATA"
        return ""

    # -- Network ------------------------------------------------------------ #
    def collect_network(self) -> None:
        logger.info("Collecting network adapter info")

        cached = self._cache_read("net_static")
        if cached:
            self.data.net_info = cached
            return

        nets: list[dict[str, Any]] = []
        try:
            addrs = psutil.net_if_addrs()
            stats = psutil.net_if_stats()
            io = psutil.net_io_counters(pernic=True)

            for name, addr_list in addrs.items():
                if name.lower() == "loopback pseudo-interface 1":
                    continue
                st = stats.get(name)
                is_up = bool(st and st.isup)
                has_ip = any(a.family in (socket.AF_INET, socket.AF_INET6) for a in addr_list)
                if not is_up and not has_ip:
                    continue

                adapter: dict[str, Any] = {
                    "Name": name,
                    "Description": "N/A",
                    "MAC": "N/A",
                    "Status": "Up" if is_up else "Down",
                    "Link Speed": "N/A",
                    "IPv4": [], "IPv6": [],
                    "Gateway": "N/A",
                    "DNS Servers": "N/A",
                    "Bytes Sent": "N/A",
                    "Bytes Received": "N/A",
                }
                for a in addr_list:
                    if a.family == socket.AF_INET:
                        adapter["IPv4"].append(a.address)
                    elif a.family == socket.AF_INET6:
                        if not a.address.lower().startswith("fe80"):
                            adapter["IPv6"].append(a.address)
                    elif a.family == psutil.AF_LINK:
                        mac = a.address
                        if mac and mac != "00-00-00-00-00-00":
                            adapter["MAC"] = mac
                if st:
                    adapter["Link Speed"] = fmt_speed(st.speed) if st.speed else "N/A"
                nio = io.get(name)
                if nio:
                    adapter["Bytes Sent"] = fmt_bytes(nio.bytes_sent)
                    adapter["Bytes Received"] = fmt_bytes(nio.bytes_recv)
                nets.append(adapter)

            if self._wmi_conn:
                try:
                    for cfg in self._wmi_conn.Win32_NetworkAdapterConfiguration(IPEnabled=True):
                        desc = (cfg.Description or "").strip()
                        ips = cfg.IPAddress or []
                        for adapter in nets:
                            match = False
                            for ip in ips:
                                if ip in adapter["IPv4"] or ip in adapter["IPv6"]:
                                    match = True
                                    break
                            if match:
                                adapter["Description"] = desc or adapter["Description"]
                                gw = cfg.DefaultIPGateway
                                if gw:
                                    adapter["Gateway"] = ", ".join(gw)
                                dns = cfg.DNSServerSearchOrder
                                if dns:
                                    adapter["DNS Servers"] = ", ".join(dns)
                                break
                except Exception as e:
                    logger.error("Network adapter WMI query failed: %s", e,
                                exc_info=True)
        except Exception as e:
            logger.error("Network info collection failed: %s", e, exc_info=True)

        self.data.net_info = nets

        # Only cache if we got results
        if nets:
            self._cache_write("net_static", nets)
        else:
            logger.warning("Network collection returned empty results, "
                          "not caching")

    # -- Active connections ------------------------------------------------- #
    def collect_active_connections(self) -> None:
        """Collect active TCP/UDP connections via psutil."""
        logger.info("Collecting active connections")
        results: list[dict[str, str]] = []
        try:
            # Reuse the pid→name cache populated by collect_processes() if
            # available; fall back to a fresh process_iter only if the cache
            # is empty (e.g., collect_active_connections called standalone).
            pid_to_name = self._pid_name_cache
            if not pid_to_name:
                try:
                    for p in psutil.process_iter(["pid", "name"]):
                        pid = p.info.get("pid", 0)
                        name = p.info.get("name", "")
                        if pid and name:
                            pid_to_name[pid] = name
                except Exception:
                    pass

            _proto_map = {
                1: "TCP", 2: "TCP", 5: "TCP", 6: "TCP",
                17: "UDP", 18: "UDP",
            }
            # Reuse the net_connections cache from collect_processes() if
            # available; otherwise make a fresh call.
            conns = self._net_conns_cache or psutil.net_connections(kind="inet")
            # Clear the cache so we don't accidentally reuse stale data on
            # the next standalone call (without a preceding collect_processes).
            self._net_conns_cache = []
            for c in conns:
                proto = "TCP" if c.type == socket.SOCK_STREAM else "UDP"
                laddr = ""
                if c.laddr:
                    laddr = f"{c.laddr.ip}:{c.laddr.port}"
                raddr = ""
                if c.raddr:
                    raddr = f"{c.raddr.ip}:{c.raddr.port}"
                pid = c.pid or 0
                proc = pid_to_name.get(pid, "N/A")
                results.append({
                    "Protocol": proto,
                    "Local Address": laddr or "N/A",
                    "Remote Address": raddr or "N/A",
                    "State": c.status or "N/A",
                    "PID": str(pid) if pid else "N/A",
                    "Process": proc,
                })
            results.sort(key=lambda x: (x["Process"].lower(),
                                       x["Local Address"]))
        except psutil.AccessDenied:
            logger.warning("Active connections: access denied (need admin)")
        except Exception as e:
            logger.error("Active connections collection failed: %s", e,
                        exc_info=True)
        self.data.active_connections = results
        logger.info("Active connections: %d collected", len(results))

    # -- Wi-Fi info --------------------------------------------------------- #
    def collect_wifi_info(self) -> None:
        """Collect Wi-Fi adapter signal/SSID info via ``netsh wlan show interfaces``."""
        logger.info("Collecting Wi-Fi info")
        result: dict[str, str] = {}
        try:
            out = subprocess.run(
                ["netsh", "wlan", "show", "interfaces"],
                capture_output=True, text=True, timeout=15,
                creationflags=0x08000000,  # CREATE_NO_WINDOW
            ).stdout
            if out:
                field_order = [
                    "Name", "Description", "_GUID", "MAC", "State",
                    "SSID", "BSSID", "Network type", "Standard",
                    "Authentication", "Cipher", "Connection mode",
                    "Channel", "Band", "Receive Rate", "Transmit Rate",
                    "Signal", "_Profile",
                ]
                pos = 0
                for line in out.splitlines():
                    if ":" not in line:
                        continue
                    if not (line.startswith(" ") or line.startswith("\t")):
                        continue
                    _, _, val = line.partition(":")
                    val = val.strip()
                    if pos < len(field_order):
                        name = field_order[pos]
                        if not name.startswith("_") and val:
                            result[name] = val
                    pos += 1
                if "Channel" in result and "Band" not in result:
                    try:
                        ch = int(result["Channel"])
                        result["Band"] = "5 GHz" if ch >= 36 else "2.4 GHz"
                    except ValueError:
                        pass
        except FileNotFoundError:
            logger.debug("netsh not available for Wi-Fi info")
        except subprocess.TimeoutExpired:
            logger.warning("netsh wlan timed out")
        except Exception as e:
            logger.error("Wi-Fi info collection failed: %s", e, exc_info=True)
        self.data.wifi_info = result
        logger.info("Wi-Fi info: %s",
                    "collected" if result else "not available")

    # -- DNS cache ---------------------------------------------------------- #
    def collect_dns_cache(self) -> None:
        """Collect DNS resolver cache via ``ipconfig /displaydns``."""
        logger.info("Collecting DNS cache")
        results: list[dict[str, str]] = []
        try:
            out = subprocess.run(
                ["ipconfig", "/displaydns"],
                capture_output=True, text=True, timeout=30,
                creationflags=0x08000000,  # CREATE_NO_WINDOW
            ).stdout
            if out:
                cur: dict[str, str] = {}
                for line in out.splitlines():
                    line = line.strip()
                    if not line:
                        if cur:
                            results.append(cur)
                            cur = {}
                        continue
                    if ":" not in line:
                        continue
                    key, _, val = line.partition(":")
                    key = key.strip()
                    val = val.strip()
                    if not val:
                        continue
                    kl = key.lower()
                    if kl.startswith("record name"):
                        cur["Record Name"] = val
                    elif kl.startswith("record type"):
                        cur["Type"] = val
                    elif kl.startswith("time to live"):
                        cur["TTL"] = val
                    elif kl.startswith("data length"):
                        cur["Data Length"] = val
                    elif kl.startswith("section"):
                        cur["Section"] = val
                    elif "record" in kl and ("host" in kl or "cname" in kl
                                              or "ptr" in kl or "a " in kl):
                        cur["Address"] = val
                if cur:
                    results.append(cur)
            results.sort(key=lambda x: x.get("Record Name", "").lower())
        except FileNotFoundError:
            logger.debug("ipconfig not available for DNS cache")
        except subprocess.TimeoutExpired:
            logger.warning("ipconfig /displaydns timed out")
        except Exception as e:
            logger.error("DNS cache collection failed: %s", e, exc_info=True)
        self.data.dns_cache = results
        logger.info("DNS cache: %d entries", len(results))

    # -- External IP -------------------------------------------------------- #
    def collect_ext_ip(self) -> None:
        logger.info("Collecting external IP info")
        try:
            with requests.get("https://api.ipify.org?format=text", timeout=10) as resp:
                if resp.status_code != 200:
                    self.data.ext_ip_error = f"ipify returned HTTP {resp.status_code}"
                    return
                ip = resp.text.strip()
            self.data.ext_ip_info = {"IP": ip}
            self.data.ext_ip_error = ""
            try:
                with requests.get(f"https://ipinfo.io/{ip}/json", timeout=10) as geo_resp:
                    geo = geo_resp.json()
                self.data.ext_ip_info.update({
                    "ISP / Organization": geo.get("org", "N/A"),
                    "Country": geo.get("country", "N/A"),
                    "Region": geo.get("region", "N/A"),
                    "City": geo.get("city", "N/A"),
                    "Timezone": geo.get("timezone", "N/A"),
                    "Hostname": geo.get("hostname", "N/A"),
                    "Coordinates": geo.get("loc", "N/A"),
                })
            except Exception:
                pass
            self.data.ext_ip_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        except Exception as e:
            logger.error("External IP lookup failed: %s", e)
            self.data.ext_ip_info = {}
            self.data.ext_ip_error = str(e)
            self.data.ext_ip_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # -- Dynamic refresh (CPU/RAM/disk/uptime) ------------------------------ #
    def refresh_dynamic(self) -> None:
        try:
            self.data.hw_info["cpu"]["Usage"] = f"{psutil.cpu_percent(interval=None):.1f}%"
        except Exception as e:
            logger.debug("CPU usage refresh failed: %s", e)
            self.data.hw_info["cpu"]["Usage"] = "N/A"
        try:
            per = psutil.cpu_percent(interval=None, percpu=True)
            self.data.hw_info["cpu"]["Per-core Usage"] = "  ".join(f"{p:5.1f}%" for p in per)
        except Exception:
            self.data.hw_info["cpu"]["Per-core Usage"] = "N/A"
        try:
            freq = psutil.cpu_freq()
            if freq:
                self.data.hw_info["cpu"]["Current Freq"] = f"{freq.current:.0f} MHz"
        except Exception:
            pass

        try:
            vm = psutil.virtual_memory()
            self.data.hw_info["ram"]["Total"] = fmt_bytes(vm.total)
            self.data.hw_info["ram"]["Used"] = fmt_bytes(vm.used)
            self.data.hw_info["ram"]["Available"] = fmt_bytes(vm.available)
            self.data.hw_info["ram"]["Usage %"] = f"{vm.percent:.1f}%"
        except Exception:
            pass

        try:
            for disk in self.data.hw_info["disks"]:
                disk["Free"] = "N/A"
                disk["Usage %"] = "N/A"
                disk["_partitions"] = []
            all_parts = list(psutil.disk_partitions(all=False))
            n_disks = len(self.data.hw_info["disks"])
            for i, part in enumerate(all_parts):
                try:
                    u = psutil.disk_usage(part.mountpoint)
                except Exception:
                    continue
                if n_disks <= 0:
                    break
                idx = min(i, n_disks - 1)
                disk = self.data.hw_info["disks"][idx]
                disk["_partitions"].append({
                    "mountpoint": part.mountpoint,
                    "free": u.free,
                    "percent": u.percent,
                })
            for disk in self.data.hw_info["disks"]:
                dparts = disk.get("_partitions", [])
                if dparts:
                    disk["Free"] = "; ".join(
                        f"{fmt_bytes(p['free'])} ({p['mountpoint']})"
                        for p in dparts)
                    if len(dparts) > 1:
                        avg = sum(p["percent"] for p in dparts) / len(dparts)
                        disk["Usage %"] = (
                            f"{avg:.1f}% (avg across "
                            f"{len(dparts)} partitions)")
                    else:
                        disk["Usage %"] = f"{dparts[0]['percent']:.1f}%"
                disk.pop("_partitions", None)
        except Exception:
            pass

        try:
            self.data.os_info["Uptime"] = fmt_uptime(
                time.time() - psutil.boot_time()
            )
        except Exception:
            pass

        try:
            io = psutil.net_io_counters(pernic=True)
            for adapter in self.data.net_info:
                nio = io.get(adapter["Name"])
                if nio:
                    adapter["Bytes Sent"] = fmt_bytes(nio.bytes_sent)
                    adapter["Bytes Received"] = fmt_bytes(nio.bytes_recv)
        except Exception:
            pass

    # -- Autopilot hardware hash -------------------------------------------- #
    # -- Processes ---------------------------------------------------------- #
    def collect_processes(self) -> None:
        """Collect running processes with CPU/RAM/Disk/Network usage.

        Uses a two-pass approach: first call to cpu_percent() primes the
        internal state, then after a sleep the second call returns actual
        CPU usage. Disk I/O rate is computed from io_counters() deltas
        (cumulative read_bytes + write_bytes between collections, divided
        by elapsed time). Network shows count of active TCP/UDP connections
        per PID via psutil.net_connections(). Results are sorted by CPU%
        descending, top 200. The sleep is skipped on subsequent calls
        (timer-based refresh) since baselines are already set.
        """
        logger.info("Collecting processes")
        procs: list[dict[str, Any]] = []
        try:
            num_cores = psutil.cpu_count(logical=True) or 1

            # Pass 1: prime cpu_percent and io_counters (only needed on first call)
            if not self._process_cpu_primed:
                for p in psutil.process_iter(["pid"]):
                    try:
                        p.cpu_percent()
                        io = p.io_counters()
                        self._process_io_prev[p.info["pid"]] = (
                            io.read_bytes, io.write_bytes)
                    except (psutil.NoSuchProcess, psutil.AccessDenied,
                            AttributeError):
                        pass
                self._process_io_time = time.time()
                time.sleep(0.5)
                self._process_cpu_primed = True

            # Build network connection count per PID
            net_by_pid: dict[int, int] = {}
            try:
                net_conns = psutil.net_connections(kind="inet")
                # Cache for reuse by collect_active_connections() (saves
                # a duplicate ~50-200ms syscall on every 5s refresh).
                self._net_conns_cache = net_conns
                for conn in net_conns:
                    pid = getattr(conn, "pid", None)
                    if pid:
                        net_by_pid[pid] = net_by_pid.get(pid, 0) + 1
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                pass

            now = time.time()
            time_delta = (now - self._process_io_time
                          if self._process_io_time else 1.0)
            self._process_io_time = now

            # Pass 2: collect actual values
            for p in psutil.process_iter(["pid", "name", "memory_info",
                                           "username", "ppid"]):
                try:
                    cpu_raw = p.cpu_percent()
                    mem_info = p.info.get("memory_info")
                    mem_bytes = mem_info.rss if mem_info else 0
                    pid = p.info["pid"]

                    # Disk I/O rate (KB/s) from cumulative io_counters delta
                    disk_rate_kb = 0.0
                    try:
                        io = p.io_counters()
                        prev = self._process_io_prev.get(pid)
                        if prev and time_delta > 0:
                            delta = ((io.read_bytes + io.write_bytes) -
                                     (prev[0] + prev[1]))
                            if delta > 0:
                                disk_rate_kb = delta / time_delta / 1024
                        self._process_io_prev[pid] = (
                            io.read_bytes, io.write_bytes)
                    except (psutil.NoSuchProcess, psutil.AccessDenied,
                            AttributeError):
                        pass

                    procs.append({
                        "PID": pid,
                        "PPID": p.info.get("ppid"),
                        "Name": p.info["name"] or "N/A",
                        "CPU %": round(cpu_raw / num_cores, 1),
                        "Memory": mem_bytes,
                        "Memory (MB)": round(mem_bytes / (1024 * 1024), 1),
                        "Disk (KB/s)": round(disk_rate_kb, 1),
                        "Network": net_by_pid.get(pid, 0),
                        "User": p.info.get("username") or "N/A",
                    })
                    # Cache pid→name for reuse by collect_active_connections
                    # (saves a duplicate psutil.process_iter syscall).
                    name = p.info.get("name") or ""
                    if name:
                        self._pid_name_cache[pid] = name
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            procs.sort(key=lambda x: x["CPU %"], reverse=True)
            # Capture current PIDs from the FULL process list BEFORE slicing
            # to top-N.  Otherwise we'd prune every PID not in the top-N,
            # which then re-appears with prev=None on the next refresh and
            # always reports 0 KB/s disk I/O (B-15/I-19 regression).
            current_pids = {p["PID"] for p in procs}
            procs = procs[:get_config().process_top_n]
            stale = [pid for pid in self._process_io_prev if pid not in current_pids]
            for pid in stale:
                del self._process_io_prev[pid]
        except Exception as e:
            logger.error("Process collection failed: %s", e, exc_info=True)

        self.data.processes = procs

    # -- Disk benchmark ----------------------------------------------------- #
    def run_disk_benchmark(self, drive: str, size_mb: int = 256) -> dict[str, Any]:
        """Quick sequential read/write benchmark for a disk.

        Writes a temporary file of ``size_mb`` MB, then reads it back,
        measuring throughput.  Returns a dict with read/write speeds (MB/s),
        test size, and timestamps.  Runs in the calling thread — should be
        invoked from a background worker.
        """
        logger.info("Disk benchmark on %s (%d MB)", drive, size_mb)
        result: dict[str, Any] = {
            "Drive": drive,
            "Test Size (MB)": size_mb,
            "Write Speed (MB/s)": 0.0,
            "Read Speed (MB/s)": 0.0,
            "Status": "Running",
        }
        # os.path.join("C:", "file") yields "C:file" — a path RELATIVE to
        # the current directory on drive C, NOT the drive root.  Append a
        # backslash so the temp file lands at the root of the chosen drive.
        test_file = os.path.join(drive + os.sep, "_SysDigger_bench.tmp")
        data_block = b"\x00" * (1024 * 1024)  # 1 MB block
        try:
            # Write phase
            t0 = time.perf_counter()
            with open(test_file, "wb") as f:
                for _ in range(size_mb):
                    f.write(data_block)
                f.flush()
                os.fsync(f.fileno())
            t_write = time.perf_counter() - t0
            write_speed = size_mb / t_write if t_write > 0 else 0.0
            result["Write Speed (MB/s)"] = round(write_speed, 1)

            # Read phase
            t0 = time.perf_counter()
            with open(test_file, "rb") as f:
                while f.read(1024 * 1024):
                    pass
            t_read = time.perf_counter() - t0
            read_speed = size_mb / t_read if t_read > 0 else 0.0
            result["Read Speed (MB/s)"] = round(read_speed, 1)

            result["Status"] = "Completed"
            result["Timestamp"] = datetime.datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S")
        except PermissionError:
            result["Status"] = "Access denied (need admin?)"
        except OSError as e:
            result["Status"] = f"Error: {e}"
        except Exception as e:
            result["Status"] = f"Error: {e}"
            logger.error("Disk benchmark failed: %s", e, exc_info=True)
        finally:
            try:
                if os.path.exists(test_file):
                    os.remove(test_file)
            except Exception:
                pass
        self.data.disk_benchmark = result
        return result

    # -- Startup impact analysis -------------------------------------------- #
    def collect_startup_impact(self) -> None:
        """Analyse boot duration from Event log and correlate with startup programs.

        Reads Event ID 12 (boot) and Event ID 13 (shutdown) from the System
        event log, computes the last few boot durations, and lists startup
        programs (from ``startup_programs`` if already collected) alongside
        the boot time for context.
        """
        logger.info("Collecting startup impact")
        result: dict[str, Any] = {
            "Last Boot Duration (s)": "N/A",
            "Boot History": [],
            "Startup Programs Count": 0,
            "Top Startup Programs": [],
        }
        try:
            import win32evtlog
            raw_boots: list = []
            raw_shutdowns: list = []
            try:
                hand = win32evtlog.OpenEventLog(None, "System")
                try:
                    flags = (win32evtlog.EVENTLOG_BACKWARDS_READ |
                             win32evtlog.EVENTLOG_SEQUENTIAL_READ)
                    count = 0
                    while count < 1000:
                        batch = win32evtlog.ReadEventLog(hand, flags, 0)
                        if not batch:
                            break
                        for e in batch:
                            eid = e.EventID
                            if eid == 12:
                                raw_boots.append(e.TimeGenerated)
                            elif eid == 13:
                                raw_shutdowns.append(e.TimeGenerated)
                            count += 1
                finally:
                    win32evtlog.CloseEventLog(hand)
            except Exception as e:
                logger.debug("Event log read for startup impact failed: %s", e)

            raw_boots.sort(reverse=True)
            raw_shutdowns.sort(reverse=True)

            # Deduplicate: Event ID 12 fires multiple times per boot —
            # group events within 60s of each other as one boot
            boots: list = []
            for t in raw_boots:
                if boots and (boots[-1] - t).total_seconds() < 60:
                    continue
                boots.append(t)

            shutdowns: list = []
            for t in raw_shutdowns:
                if shutdowns and (shutdowns[-1] - t).total_seconds() < 60:
                    continue
                shutdowns.append(t)

            boot_history: list[dict[str, str]] = []
            for boot_time in boots[:10]:
                prev_shutdown = None
                for sd in shutdowns:
                    if sd < boot_time:
                        prev_shutdown = sd
                        break
                if prev_shutdown:
                    duration = (boot_time - prev_shutdown).total_seconds()
                    if duration > 3600:
                        continue
                    boot_history.append({
                        "Boot Time": boot_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "Duration (s)": f"{duration:.1f}",
                    })
            if boot_history:
                result["Last Boot Duration (s)"] = boot_history[0].get(
                    "Duration (s)", "N/A")
            result["Boot History"] = boot_history

            startups = self.data.startup_programs
            result["Startup Programs Count"] = len(startups)
            result["Top Startup Programs"] = startups[:20]
        except Exception as e:
            logger.error("Startup impact collection failed: %s", e,
                        exc_info=True)
        self.data.startup_impact = result
        logger.info("Startup impact: %d boot entries, %d startup programs",
                    len(result.get("Boot History", [])),
                    result.get("Startup Programs Count", 0))

    # -- Software (startup + installed) ------------------------------------- #
    def collect_software(self) -> None:
        """Collect startup programs and installed programs from registry."""
        logger.info("Collecting software info")

        cached = self._cache_read("software_static")
        if cached:
            self.data.startup_programs = cached.get("startup", [])
            self.data.installed_programs = cached.get("installed", [])
            return

        startup = self._collect_startup_programs()
        installed = self._collect_installed_programs()

        self.data.startup_programs = startup
        self.data.installed_programs = installed

        # Only cache if we actually got results (don't cache failures)
        if startup or installed:
            self._cache_write("software_static", {
                "startup": startup,
                "installed": installed,
            })
        else:
            logger.warning("Software collection returned empty results, "
                          "not caching")

    def collect_services(self) -> None:
        """Collect Windows services list via WMI Win32_Service."""
        logger.info("Collecting services info")
        cached = self._cache_read("services_static")
        if cached:
            self.data.services_info = cached
            return
        results: list[dict[str, str]] = []
        if not self._wmi_conn:
            self.data.services_info = results
            return
        try:
            _start_map = {
                "Auto": "Automatic",
                "Manual": "Manual",
                "Disabled": "Disabled",
            }
            for svc in self._wmi_conn.Win32_Service():
                name = s(getattr(svc, "Name", "N/A"))
                display = s(getattr(svc, "DisplayName", name))
                state = s(getattr(svc, "State", "N/A"))
                start_mode = s(getattr(svc, "StartMode", "N/A"))
                start_name = s(getattr(svc, "StartName", "N/A"))
                results.append({
                    "Name": name,
                    "Display Name": display,
                    "State": state,
                    "Start Type": _start_map.get(start_mode, start_mode),
                    "Log On As": start_name,
                })
            results.sort(key=lambda x: x["Name"].lower())
        except Exception as e:
            logger.error("Services collection failed: %s", e, exc_info=True)
        self.data.services_info = results
        if results:
            self._cache_write("services_static", results)
        logger.info("Services: %d collected", len(results))

    def _collect_startup_programs(self) -> list[dict[str, Any]]:
        """Read startup programs from registry Run keys and Startup folders."""
        import winreg
        programs: list[dict[str, Any]] = []

        reg_paths = [
            (winreg.HKEY_LOCAL_MACHINE,
             r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run", "HKLM"),
            (winreg.HKEY_CURRENT_USER,
             r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run", "HKCU"),
            (winreg.HKEY_LOCAL_MACHINE,
             r"SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce", "HKLM RunOnce"),
            (winreg.HKEY_CURRENT_USER,
             r"SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce", "HKCU RunOnce"),
            (winreg.HKEY_LOCAL_MACHINE,
             r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run",
             "HKLM WOW64"),
        ]

        for hive, path, source in reg_paths:
            try:
                with winreg.OpenKey(hive, path) as key:
                    num_values = winreg.QueryInfoKey(key)[1]
                    for i in range(num_values):
                        try:
                            name, value, _ = winreg.EnumValue(key, i)
                            programs.append({
                                "Name": name,
                                "Command": str(value),
                                "Source": source,
                            })
                        except Exception:
                            pass
            except FileNotFoundError:
                pass
            except Exception as e:
                logger.error("Startup registry read failed (%s): %s", source, e)

        startup_folders = [
            (os.path.join(os.environ.get("APPDATA", ""),
                          r"Microsoft\Windows\Start Menu\Programs\Startup"),
             "Startup (User)"),
            (os.path.join(os.environ.get("ProgramData", ""),
                          r"Microsoft\Windows\Start Menu\Programs\Startup"),
             "Startup (All Users)"),
        ]

        for folder, source in startup_folders:
            if not os.path.isdir(folder):
                continue
            try:
                for item in os.listdir(folder):
                    full_path = os.path.join(folder, item)
                    if os.path.isfile(full_path):
                        programs.append({
                            "Name": item,
                            "Command": full_path,
                            "Source": source,
                        })
            except Exception as e:
                logger.error("Startup folder read failed (%s): %s", source, e)

        return programs

    def _collect_installed_programs(self) -> list[dict[str, Any]]:
        """Read installed programs from registry uninstall keys."""
        import winreg
        programs: list[dict[str, Any]] = []

        uninstall_paths = [
            (winreg.HKEY_LOCAL_MACHINE,
             r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
             "HKLM 64-bit"),
            (winreg.HKEY_LOCAL_MACHINE,
             r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
             "HKLM 32-bit (WOW64)"),
            (winreg.HKEY_CURRENT_USER,
             r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
             "HKCU"),
        ]

        for hive, base_path, label in uninstall_paths:
            try:
                with winreg.OpenKey(hive, base_path) as key:
                    num_subkeys = winreg.QueryInfoKey(key)[0]
                    found = 0
                    skipped = 0
                    for i in range(num_subkeys):
                        try:
                            subkey_name = winreg.EnumKey(key, i)
                            sub_path = f"{base_path}\\{subkey_name}"
                            with winreg.OpenKey(hive, sub_path) as subkey:
                                def _q(value_name):
                                    try:
                                        v, _ = winreg.QueryValueEx(
                                            subkey, value_name)
                                        return str(v).strip()
                                    except Exception:
                                        return ""
                                name = _q("DisplayName")
                                if not name:
                                    skipped += 1
                                    continue
                                version = _q("DisplayVersion")
                                publisher = _q("Publisher")
                                install_date = _q("InstallDate")
                                programs.append({
                                    "Name": name,
                                    "Version": version or "N/A",
                                    "Publisher": publisher or "N/A",
                                    "Install Date": install_date or "N/A",
                                })
                                found += 1
                        except Exception as e:
                            logger.debug(
                                "Installed programs: subkey %d enum failed "
                                "(%s): %s", i, label, e)
                    logger.info("Installed programs [%s]: %d subkeys, "
                                "%d found, %d skipped (no DisplayName)",
                                label, num_subkeys, found, skipped)
            except FileNotFoundError:
                logger.debug("Installed programs: %s path not found", label)
            except Exception as e:
                logger.error("Installed programs read failed (%s): %s",
                            label, e, exc_info=True)

        programs.sort(key=lambda x: x["Name"].lower())
        logger.info("Total installed programs found: %d", len(programs))
        return programs

    # -- Windows Updates ---------------------------------------------------- #
    def collect_updates(self) -> None:
        """Collect Windows Update history via WMI QuickFixEngineering.

        For each KB, fetches the real description from the Microsoft Support
        page (support.microsoft.com/help/KBnumber). Falls back to the WMI
        Description ("Update") if the fetch fails. Results are cached.
        """
        logger.info("Collecting Windows Update history")
        updates: list[dict[str, Any]] = []

        cached = self._cache_read("updates_static")
        if cached:
            self.data.update_history = cached
            return

        if self._wmi_conn:
            try:
                for qfe in self._wmi_conn.Win32_QuickFixEngineering():
                    try:
                        kb = s(getattr(qfe, "HotFixID", ""))
                        if not kb or kb == "N/A":
                            continue
                        desc = s(getattr(qfe, "Description", ""))
                        installed_on = s(getattr(qfe, "InstalledOn", ""))
                        installed_by = s(getattr(qfe, "InstalledBy", ""))

                        updates.append({
                            "KB": kb,
                            "Description": desc,
                            "Installed On": installed_on,
                            "Installed By": installed_by,
                        })
                    except Exception:
                        pass
            except Exception as e:
                logger.error("QuickFix WMI query failed: %s", e, exc_info=True)

        def _parse_date(s: str):
            """Parse a locale-formatted date string for chronological sorting."""
            for fmt in ("%m/%d/%Y %H:%M", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S",
                        "%Y-%m-%d", "%d/%m/%Y"):
                try:
                    return datetime.datetime.strptime(s, fmt)
                except ValueError:
                    continue
            return datetime.datetime.min

        updates.sort(
            key=lambda x: _parse_date(x.get("Installed On", "")),
            reverse=True,
        )
        self.data.update_history = updates
        self._cache_write("updates_static", updates)

    @staticmethod
    def _fetch_kb_title(kb: str) -> str:
        """Fetch the real KB title from Microsoft Support website.

        Returns empty string on failure. Each request has a 5s timeout.
        """
        kb_num = kb.replace("KB", "").replace("kb", "")
        if not kb_num:
            return ""
        try:
            url = f"https://support.microsoft.com/en-us/help/{kb_num}"
            with requests.get(url, timeout=5, allow_redirects=True) as r:
                if r.status_code != 200:
                    return ""
                m = re.search(r"<title>(.*?)</title>", r.text,
                              re.IGNORECASE | re.DOTALL)
            if m:
                title = m.group(1).strip()
                # Decode HTML entities
                title = (title.replace("&#x2014;", "\u2014")
                               .replace("&#x2013;", "\u2013")
                               .replace("&amp;", "&")
                               .replace("&#39;", "'")
                               .replace("&quot;", '"')
                               .replace("&nbsp;", " "))
                # Clean up common suffixes
                for suffix in (" - Microsoft Support",
                               " - Office.com", "Microsoft Support"):
                    if title.endswith(suffix):
                        title = title[: -len(suffix)].strip()
                # Skip error pages
                if "error" in title.lower() or "office.com" in title.lower():
                    return ""
                # Strip redundant "KBxxxxx: " prefix if present
                title = re.sub(r'^KB\d+\s*:\s*', '', title)
                return title
        except Exception as e:
            logger.debug("KB title fetch failed for %s: %s", kb, e)
        return ""

    def get_kb_title(self, kb: str) -> str:
        """Return cached KB title, or fetch on demand. Thread-safe."""
        now = time.time()
        cached = self._kb_title_cache.get(kb)
        if cached and (now - cached[0]) < self._kb_title_ttl:
            return cached[1]
        title = self._fetch_kb_title(kb)
        self._kb_title_cache[kb] = (now, title)
        return title

    # -- System Health ------------------------------------------------------ #
    def collect_health(self) -> None:
        """Collect system health status: SMART, Defender, Firewall."""
        logger.info("Collecting system health")

        cached = self._cache_read("health_static")
        if cached:
            self.data.health_info = cached
            return

        health: dict[str, Any] = {}

        try:
            health["disk_smart"] = self._collect_disk_smart()
        except Exception as e:
            logger.error("Disk SMART collection failed: %s", e, exc_info=True)
            health["disk_smart"] = []

        try:
            health["defender"] = self._collect_defender_status()
        except Exception as e:
            logger.error("Defender status collection failed: %s", e, exc_info=True)
            health["defender"] = {"Available": False}

        try:
            health["firewall"] = self._collect_firewall_status()
        except Exception as e:
            logger.error("Firewall status collection failed: %s", e,
                        exc_info=True)
            health["firewall"] = []

        try:
            health["activation"] = self._collect_activation_status()
        except Exception as e:
            logger.error("Activation status collection failed: %s", e,
                        exc_info=True)
            health["activation"] = {"Available": False}

        self.data.health_info = health

        # Only cache if we got at least some data
        if health.get("disk_smart") or health.get("defender", {}).get("Available") or health.get("firewall") or health.get("activation", {}).get("Available"):
            self._cache_write("health_static", health)
        else:
            logger.warning("Health collection returned empty results, "
                          "not caching")

    def _collect_disk_smart(self) -> list[dict[str, Any]]:
        """Collect SMART health status for each disk."""
        results: list[dict[str, Any]] = []
        if self._wmi_conn:
            try:
                for dd in self._wmi_conn.Win32_DiskDrive():
                    model = s(getattr(dd, "Model", "N/A"))
                    status = s(getattr(dd, "Status", "N/A"))
                    try:
                        size = int(getattr(dd, "Size", 0) or 0)
                    except Exception:
                        size = 0
                    results.append({
                        "Model": model,
                        "Status": status,
                        "Health": "OK" if status == "OK" else "Warning",
                        "Size": fmt_bytes(size) if size else "N/A",
                    })
            except Exception as e:
                logger.error("Disk SMART WMI query failed: %s", e, exc_info=True)
        return results

    def _collect_defender_status(self) -> dict[str, Any]:
        """Collect Windows Defender status from WMI."""
        result: dict[str, Any] = {"Available": False}

        if not _WMI_AVAILABLE:
            return result

        with self._wmi_namespace("root/Microsoft/Windows/Defender") as def_ns:
            if def_ns is not None:
                try:
                    for ms in def_ns.MSFT_MpComputerStatus():
                        result["Available"] = True
                        result["Product"] = "Windows Defender"
                        result["Real-time Protection"] = (
                            "Enabled"
                            if getattr(ms, "RealTimeProtectionEnabled", False)
                            else "Disabled")
                        result["Antivirus Enabled"] = (
                            "Enabled"
                            if getattr(ms, "AntivirusEnabled", False)
                            else "Disabled")
                        result["Antispyware Enabled"] = (
                            "Enabled"
                            if getattr(ms, "AntispywareEnabled", False)
                            else "Disabled")
                        result["Signature Age"] = (
                            f"{getattr(ms, 'AntivirusSignatureAge', '?')} days")
                        # Fall back to start time if end time is None
                        quick_scan = (getattr(ms, "LastQuickScanEndTime", None)
                                      or getattr(ms, "QuickScanStartTime", None))
                        result["Last Quick Scan"] = (
                            fmt_wmi_time(quick_scan) if quick_scan else "Never")
                        full_scan = (getattr(ms, "LastFullScanEndTime", None)
                                     or getattr(ms, "FullScanStartTime", None))
                        result["Last Full Scan"] = (
                            fmt_wmi_time(full_scan) if full_scan else "Never")
                        break
                except Exception as e:
                    logger.debug("Defender WMI namespace query failed: %s", e)

        if not result["Available"]:
            with self._wmi_namespace("root/SecurityCenter2") as sec:
                if sec is not None:
                    try:
                        for av in sec.AntiVirusProduct():
                            result["Available"] = True
                            result["Product"] = s(getattr(av, "displayName", "N/A"))
                            result["Enabled"] = (
                                "Yes"
                                if getattr(av, "productEnabled", False)
                                else "No")
                            break
                    except Exception as e:
                        logger.debug("SecurityCenter2 query failed: %s", e)

        return result

    def _collect_firewall_status(self) -> list[dict[str, Any]]:
        """Collect firewall status for each network profile via COM."""
        results: list[dict[str, Any]] = []
        with _com_context():
            try:
                import win32com.client
                fw = win32com.client.Dispatch("HNetCfg.FwPolicy2")
                # NET_FW_PROFILE_TYPE2 enum: 0=Domain, 1=Private, 2=Public
                profiles = {0: "Domain", 1: "Private", 2: "Public"}
                for enum_val, name in profiles.items():
                    try:
                        enabled = bool(fw.FirewallEnabled(enum_val))
                    except Exception:
                        # Domain profile may not exist on non-domain machines
                        enabled = False
                    results.append({
                        "Profile": name,
                        "Status": "Enabled" if enabled else "Disabled",
                    })
            except ImportError:
                logger.debug("pywin32 not available for firewall status")
                results.append({
                    "Profile": "All",
                    "Status": "N/A (pywin32 required)",
                })
            except Exception as e:
                logger.error("Firewall COM query failed: %s", e, exc_info=True)
                results.append({
                    "Profile": "All",
                    "Status": f"Error: {e}",
                })
        return results

    def _collect_activation_status(self) -> dict[str, Any]:
        """Collect Windows activation status via WMI
        SoftwareLicensingProduct.

        Returns a dict with keys: Available, Status, Edition, Product Key
        (last 5 chars), Grace Period (days), Activation Type.
        """
        result: dict[str, Any] = {"Available": False}
        if not self._wmi_conn:
            return result
        try:
            # LicenseStatus enum values
            _LIC = {
                0: "Unlicensed",
                1: "Licensed (Activated)",
                2: "OOB Grace",
                3: "OOT Grace",
                4: "Non-Genuine Grace",
                5: "Notification",
                6: "Extended Grace",
            }
            for prod in self._wmi_conn.query(
                "SELECT * FROM SoftwareLicensingProduct "
                "WHERE PartialProductKey IS NOT NULL"):
                partial = getattr(prod, "PartialProductKey", None)
                if not partial:
                    continue
                # Only the Windows product has ApplicationId =
                # 55c92734-d682-4d71-983e-d6ec3f16059f
                app_id = s(getattr(prod, "ApplicationId", ""))
                if "55c92734" not in app_id.lower():
                    continue
                status_code = int(getattr(prod, "LicenseStatus", 0))
                grace_min = int(getattr(prod, "GracePeriodRemaining", 0))
                name = s(getattr(prod, "Name", ""))
                desc = s(getattr(prod, "Description", ""))
                result = {
                    "Available": True,
                    "Status": _LIC.get(status_code, f"Unknown ({status_code})"),
                    "Activated": status_code == 1,
                    "Edition": name,
                    "Description": desc,
                    "Product Key": f"XXXXX-XXXXX-XXXXX-XXXXX-{partial}",
                    "Grace Period (days)": (
                        f"{grace_min // 1440}"
                        if grace_min and grace_min > 0 else "N/A"
                    ),
                }
                break
        except Exception as e:
            logger.error("Activation status query failed: %s", e,
                        exc_info=True)
            result = {"Available": False,
                      "Status": f"Error: {e}"}
        return result

    # -- Network Speed Test ------------------------------------------------- #
    def run_speed_test(self) -> dict[str, Any]:
        """Run a network speed test (download + upload) via Cloudflare.

        Queries Cloudflare's speed test endpoint to find the closest colo
        (data center), then downloads/uploads 25 MB measuring throughput.
        Uses the user's external IP geo info to report the user's location.
        Returns a result dict with speeds in Mbps, server colo, and locations.
        """
        result: dict[str, Any] = {
            "download_mbps": 0.0,
            "upload_mbps": 0.0,
            "download_time_s": 0.0,
            "upload_time_s": 0.0,
            "download_bytes": 0,
            "upload_bytes": 0,
            "server_colo": "",
            "server_location": "",
            "user_location": "",
            "user_ip": "",
            "error": "",
            "timestamp": datetime.datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"),
        }

        # User location from previously-collected external IP info
        ip_info = self.data.ext_ip_info
        if ip_info:
            parts = []
            if ip_info.get("City"):
                parts.append(ip_info["City"])
            if ip_info.get("Region"):
                parts.append(ip_info["Region"])
            if ip_info.get("Country"):
                parts.append(ip_info["Country"])
            result["user_location"] = ", ".join(parts) if parts else "Unknown"
            result["user_ip"] = ip_info.get("IP", "")

        # Cloudflare colo lookup — the response includes the closest data
        # center (IATA code + city name) in its headers/body.
        # A browser User-Agent is required — Cloudflare blocks the default
        # python-requests UA with HTTP 403 on larger downloads.
        _cf_headers = {
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/120.0.0.0 Safari/537.36"),
        }
        colo = ""
        colo_location = ""
        try:
            with requests.get(
                "https://speed.cloudflare.com/meta", timeout=10,
                headers=_cf_headers) as meta_resp:
                if meta_resp.status_code == 200:
                    meta = meta_resp.json()
                    colo = meta.get("colo", "")
                    if colo:
                        result["server_colo"] = colo
                        # Look up colo IATA code → city name
                        colo_location = _CLOUDFLARE_COLOS.get(colo, colo)
                        result["server_location"] = colo_location
                        logger.info("Speed test: Cloudflare colo=%s (%s)",
                                    colo, colo_location)
        except Exception as e:
            logger.debug("Cloudflare meta lookup failed: %s", e)

        # If meta failed, try the CF-Connecting-IP / server header on download
        _cfg = get_config()
        _dl_bytes = _cfg.speed_test_download_mb * 1_000_000
        _ul_bytes = _cfg.speed_test_upload_mb * 1_000_000
        _timeout = _cfg.speed_test_timeout_s
        download_url = f"https://speed.cloudflare.com/__down?bytes={_dl_bytes}"
        try:
            start = time.time()
            with requests.get(download_url, timeout=_timeout,
                              stream=True, headers=_cf_headers) as response:
                if not colo:
                    cf_ray = response.headers.get("CF-RAY", "")
                    if "-" in cf_ray:
                        colo = cf_ray.rsplit("-", 1)[-1]
                        result["server_colo"] = colo
                        colo_location = _CLOUDFLARE_COLOS.get(colo, colo)
                        result["server_location"] = colo_location
                        logger.info("Speed test: Cloudflare colo=%s (from CF-RAY)",
                                    colo)
                total = 0
                for chunk in response.iter_content(chunk_size=65536):
                    total += len(chunk)
            elapsed = time.time() - start
            if elapsed > 0 and total > 0:
                result["download_mbps"] = round(
                    (total * 8) / elapsed / 1_000_000, 2)
                result["download_time_s"] = round(elapsed, 2)
                result["download_bytes"] = total
        except Exception as e:
            result["error"] = f"Download: {e}"
            logger.error("Speed test download failed: %s", e, exc_info=True)

        upload_url = "https://speed.cloudflare.com/__up"
        try:
            data = b"0" * _ul_bytes
            start = time.time()
            with requests.post(upload_url, data=data, timeout=_timeout,
                               headers=_cf_headers):
                pass
            elapsed = time.time() - start
            if elapsed > 0:
                result["upload_mbps"] = round(
                    (len(data) * 8) / elapsed / 1_000_000, 2)
                result["upload_time_s"] = round(elapsed, 2)
                result["upload_bytes"] = len(data)
        except Exception as e:
            if result["error"]:
                result["error"] += f" | Upload: {e}"
            else:
                result["error"] = f"Upload: {e}"
            logger.error("Speed test upload failed: %s", e, exc_info=True)

        self.data.speed_test_result = result
        return result

    def run_bufferbloat_test(self) -> dict[str, Any]:
        """Run a bufferbloat test measuring latency under load.

        Bufferbloat is the increase in latency when the connection is
        saturated. We measure:
          1. Baseline ping latency (no load)
          2. Latency during a sustained download
          3. Latency during a sustained upload
        The difference (loaded - baseline) is the "bloat" in each direction.

        Uses the Windows ``ping`` command via subprocess (no external deps)
        and Cloudflare's speed endpoints for load generation.

        Returns a result dict with baseline/download/upload latencies,
        bloat values in ms, and a letter grade (A-F).
        """
        # Browser User-Agent — Cloudflare blocks default python-requests UA
        # on larger downloads with HTTP 403.
        _cf_headers = {
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/120.0.0.0 Safari/537.36"),
        }

        result: dict[str, Any] = {
            "baseline_latency_ms": 0.0,
            "download_latency_ms": 0.0,
            "download_bloat_ms": 0.0,
            "upload_latency_ms": 0.0,
            "upload_bloat_ms": 0.0,
            "grade": "",
            "error": "",
            "timestamp": datetime.datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"),
        }

        def _ping_latency(host: str = "1.1.1.1",
                          count: int = 10) -> float | None:
            """Run Windows ping and return average latency in ms, or None."""
            try:
                # Windows ping: -n count, -w timeout_ms
                proc = subprocess.run(
                    ["ping", "-n", str(count), "-w", "2000", host],
                    capture_output=True, text=True, timeout=30,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                # Parse "Minimum = 5ms, Maximum = 15ms, Average = 10ms"
                output = proc.stdout
                m = re.search(r"Average\s*=\s*(\d+)\s*ms", output)
                if m:
                    return float(m.group(1))
            except Exception as e:
                logger.debug("Ping failed: %s", e)
            return None

        def _ping_in_background(host: str = "1.1.1.1",
                                duration_s: float = 10.0) -> list[float]:
            """Run many pings for a duration, return list of per-ping latencies."""
            latencies: list[float] = []
            deadline = time.time() + duration_s
            while time.time() < deadline:
                try:
                    proc = subprocess.run(
                        ["ping", "-n", "1", "-w", "2000", host],
                        capture_output=True, text=True, timeout=5,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                    # Parse "Reply from 1.1.1.1: bytes=32 time=5ms TTL=57"
                    m = re.search(r"time[=<](\d+)ms", proc.stdout)
                    if m:
                        latencies.append(float(m.group(1)))
                except Exception:
                    pass
            return latencies

        try:
            # 1. Baseline latency (10 pings, take average)
            baseline = _ping_latency(count=10)
            if baseline is None:
                result["error"] = "Could not measure baseline ping latency"
                self.data.bufferbloat_result = result
                return result
            result["baseline_latency_ms"] = round(baseline, 1)
            logger.info("Bufferbloat: baseline latency = %.1f ms", baseline)

            # 2. Download under load — spawn ping thread, run download in main
            dl_latencies: list[float] = []
            _cfg = get_config()
            _dl_bytes = _cfg.speed_test_download_mb * 1_000_000
            _ul_bytes = _cfg.speed_test_upload_mb * 1_000_000
            _timeout = _cfg.speed_test_timeout_s
            download_url = f"https://speed.cloudflare.com/__down?bytes={_dl_bytes}"
            dl_thread = threading.Thread(
                target=lambda: dl_latencies.extend(
                    _ping_in_background(duration_s=12.0)),
                daemon=True,
            )
            dl_thread.start()
            try:
                with requests.get(download_url, timeout=_timeout, stream=True,
                                   headers=_cf_headers) as resp:
                    for _ in resp.iter_content(chunk_size=65536):
                        pass
            except Exception as e:
                logger.debug("Bufferbloat download load failed: %s", e)
            dl_thread.join(timeout=15)

            if dl_latencies:
                import statistics
                dl_avg = statistics.mean(dl_latencies)
                result["download_latency_ms"] = round(dl_avg, 1)
                result["download_bloat_ms"] = round(
                    max(0, dl_avg - baseline), 1)
                logger.info("Bufferbloat: download latency = %.1f ms "
                            "(bloat %.1f ms)", dl_avg,
                            result["download_bloat_ms"])
            else:
                result["download_latency_ms"] = 0.0
                result["download_bloat_ms"] = 0.0

            # 3. Upload under load
            ul_latencies: list[float] = []
            upload_url = "https://speed.cloudflare.com/__up"
            ul_thread = threading.Thread(
                target=lambda: ul_latencies.extend(
                    _ping_in_background(duration_s=12.0)),
                daemon=True,
            )
            ul_thread.start()
            try:
                data = b"0" * _ul_bytes
                with requests.post(upload_url, data=data, timeout=_timeout,
                                   headers=_cf_headers):
                    pass
            except Exception as e:
                logger.debug("Bufferbloat upload load failed: %s", e)
            ul_thread.join(timeout=15)

            if ul_latencies:
                import statistics
                ul_avg = statistics.mean(ul_latencies)
                result["upload_latency_ms"] = round(ul_avg, 1)
                result["upload_bloat_ms"] = round(
                    max(0, ul_avg - baseline), 1)
                logger.info("Bufferbloat: upload latency = %.1f ms "
                            "(bloat %.1f ms)", ul_avg,
                            result["upload_bloat_ms"])
            else:
                result["upload_latency_ms"] = 0.0
                result["upload_bloat_ms"] = 0.0

            # 4. Grade based on worst bloat (download or upload)
            worst_bloat = max(result["download_bloat_ms"],
                              result["upload_bloat_ms"])
            if worst_bloat < 30:
                result["grade"] = "A"
            elif worst_bloat < 60:
                result["grade"] = "B"
            elif worst_bloat < 100:
                result["grade"] = "C"
            elif worst_bloat < 200:
                result["grade"] = "D"
            else:
                result["grade"] = "F"
            logger.info("Bufferbloat: grade = %s (worst bloat %.1f ms)",
                        result["grade"], worst_bloat)

        except Exception as e:
            result["error"] = str(e)
            logger.error("Bufferbloat test failed: %s", e, exc_info=True)

        self.data.bufferbloat_result = result
        return result

    # ------------------------------------------------------------------ #
    #  GPU details (NVML for NVIDIA, ADL stub for AMD)
    # ------------------------------------------------------------------ #

    def collect_gpu_details(self) -> None:
        """Collect detailed GPU metrics via NVML (NVIDIA) or WMI fallback."""
        results: list[dict[str, Any]] = []
        try:
            results = self._collect_nvml_gpus()
        except Exception as e:
            logger.debug("NVML GPU details failed: %s", e)

        if not results:
            # Fallback: use existing WMI GPU info with what we have
            for g in self.data.hw_info.get("gpus", []):
                results.append({
                    "Name": g.get("Name", "N/A"),
                    "Driver Version": g.get("Driver Version", "N/A"),
                    "VRAM": g.get("VRAM", "N/A"),
                    "API": "WMI (no vendor SDK)",
                })

        self.data.gpu_details = results
        logger.info("GPU details: %d GPU(s) collected", len(results))

    @staticmethod
    def _collect_nvml_gpus() -> list[dict[str, Any]]:
        """Query NVIDIA NVML for detailed GPU metrics. Returns [] if no NVIDIA GPU."""
        import ctypes
        import ctypes.wintypes

        # NVML struct definitions
        class NvmlUtilization(ctypes.Structure):
            _fields_ = [
                ("gpu", ctypes.c_uint),
                ("memory", ctypes.c_uint),
            ]

        class NvmlMemory(ctypes.Structure):
            _fields_ = [
                ("total", ctypes.c_ulonglong),
                ("used", ctypes.c_ulonglong),
                ("free", ctypes.c_ulonglong),
            ]

        # Try loading nvml.dll (ships with NVIDIA drivers)
        try:
            nvml = ctypes.windll.LoadLibrary("nvml.dll")
        except OSError:
            try:
                nvml = ctypes.windll.LoadLibrary(
                    r"C:\Windows\System32\nvml.dll")
            except OSError:
                logger.debug("nvml.dll not found — no NVIDIA GPU or driver")
                return []

        # NVML constants
        NVML_TEMPERATURE_GPU = 0
        NVML_CLOCK_GRAPHICS = 0
        NVML_CLOCK_MEM = 2
        NVML_SUCCESS = 0

        # Set return types
        nvml.nvmlInit_v2.restype = ctypes.c_int
        nvml.nvmlDeviceGetCount_v2.restype = ctypes.c_int
        nvml.nvmlDeviceGetCount_v2.argtypes = [ctypes.POINTER(ctypes.c_uint)]
        nvml.nvmlDeviceGetHandleByIndex_v2.restype = ctypes.c_int
        nvml.nvmlDeviceGetHandleByIndex_v2.argtypes = [
            ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p)]
        nvml.nvmlDeviceGetName.restype = ctypes.c_int
        nvml.nvmlDeviceGetName.argtypes = [
            ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint]
        nvml.nvmlDeviceGetTemperature.restype = ctypes.c_int
        nvml.nvmlDeviceGetTemperature.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_uint)]
        nvml.nvmlDeviceGetUtilizationRates.restype = ctypes.c_int
        nvml.nvmlDeviceGetUtilizationRates.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(NvmlUtilization)]
        nvml.nvmlDeviceGetMemoryInfo.restype = ctypes.c_int
        nvml.nvmlDeviceGetMemoryInfo.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(NvmlMemory)]
        nvml.nvmlDeviceGetPowerUsage.restype = ctypes.c_int
        nvml.nvmlDeviceGetPowerUsage.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint)]
        nvml.nvmlDeviceGetFanSpeed.restype = ctypes.c_int
        nvml.nvmlDeviceGetFanSpeed.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint)]
        nvml.nvmlDeviceGetClockInfo.restype = ctypes.c_int
        nvml.nvmlDeviceGetClockInfo.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_uint)]
        nvml.nvmlDeviceGetMaxClockInfo.restype = ctypes.c_int
        nvml.nvmlDeviceGetMaxClockInfo.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_uint)]
        nvml.nvmlDeviceGetDriverVersion.restype = ctypes.c_int
        nvml.nvmlDeviceGetDriverVersion.argtypes = [
            ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint]
        nvml.nvmlShutdown.restype = ctypes.c_int

        if nvml.nvmlInit_v2() != NVML_SUCCESS:
            logger.debug("NVML init failed")
            return []

        results: list[dict[str, Any]] = []
        try:
            count = ctypes.c_uint(0)
            if nvml.nvmlDeviceGetCount_v2(ctypes.byref(count)) != NVML_SUCCESS:
                return []

            for i in range(count.value):
                handle = ctypes.c_void_p()
                if nvml.nvmlDeviceGetHandleByIndex_v2(
                        i, ctypes.byref(handle)) != NVML_SUCCESS:
                    continue

                info: dict[str, Any] = {"API": "NVIDIA NVML"}

                # Name
                buf = ctypes.create_string_buffer(256)
                if nvml.nvmlDeviceGetName(handle, buf, 256) == NVML_SUCCESS:
                    info["Name"] = buf.value.decode("utf-8", errors="replace")

                # Driver version
                drv = ctypes.create_string_buffer(256)
                if nvml.nvmlDeviceGetDriverVersion(
                        handle, drv, 256) == NVML_SUCCESS:
                    info["Driver Version"] = drv.value.decode(
                        "utf-8", errors="replace")

                # Temperature
                temp = ctypes.c_uint(0)
                if nvml.nvmlDeviceGetTemperature(
                        handle, NVML_TEMPERATURE_GPU,
                        ctypes.byref(temp)) == NVML_SUCCESS:
                    info["Temperature"] = f"{temp.value} C"

                # Utilization
                util = NvmlUtilization()
                if nvml.nvmlDeviceGetUtilizationRates(
                        handle, ctypes.byref(util)) == NVML_SUCCESS:
                    info["GPU Utilization"] = f"{util.gpu}%"
                    info["Memory Utilization"] = f"{util.memory}%"

                # Memory
                mem = NvmlMemory()
                if nvml.nvmlDeviceGetMemoryInfo(
                        handle, ctypes.byref(mem)) == NVML_SUCCESS:
                    info["VRAM Total"] = fmt_bytes(mem.total)
                    info["VRAM Used"] = fmt_bytes(mem.used)
                    info["VRAM Free"] = fmt_bytes(mem.free)
                    if mem.total > 0:
                        info["VRAM Usage %"] = (
                            f"{mem.used * 100 / mem.total:.1f}%")

                # Power
                power = ctypes.c_uint(0)
                if nvml.nvmlDeviceGetPowerUsage(
                        handle, ctypes.byref(power)) == NVML_SUCCESS:
                    info["Power Draw"] = f"{power.value / 1000:.1f} W"

                # Fan speed
                fan = ctypes.c_uint(0)
                if nvml.nvmlDeviceGetFanSpeed(
                        handle, ctypes.byref(fan)) == NVML_SUCCESS:
                    info["Fan Speed"] = f"{fan.value}%"

                # Clocks
                clk = ctypes.c_uint(0)
                if nvml.nvmlDeviceGetClockInfo(
                        handle, NVML_CLOCK_GRAPHICS,
                        ctypes.byref(clk)) == NVML_SUCCESS:
                    info["GPU Clock"] = f"{clk.value} MHz"
                if nvml.nvmlDeviceGetClockInfo(
                        handle, NVML_CLOCK_MEM,
                        ctypes.byref(clk)) == NVML_SUCCESS:
                    info["Memory Clock"] = f"{clk.value} MHz"

                # Max clocks
                if nvml.nvmlDeviceGetMaxClockInfo(
                        handle, NVML_CLOCK_GRAPHICS,
                        ctypes.byref(clk)) == NVML_SUCCESS:
                    info["Max GPU Clock"] = f"{clk.value} MHz"

                results.append(info)
        finally:
            nvml.nvmlShutdown()

        return results

    # ------------------------------------------------------------------ #
    #  Devices: USB, Bluetooth, Printers, Audio
    # ------------------------------------------------------------------ #

    def collect_devices(self) -> None:
        """Collect USB, Bluetooth, printer, and audio device info (cached)."""
        cached = self._cache_read("devices_static")
        if cached is not None:
            self.data.devices_info = cached
            logger.info("Devices info loaded from cache")
            return

        result: dict[str, Any] = {
            "usb": [],
            "bluetooth": [],
            "printers": [],
            "audio": [],
        }

        try:
            result["usb"] = self._collect_usb_devices()
        except Exception as e:
            logger.error("USB devices collection failed: %s", e, exc_info=True)

        try:
            result["bluetooth"] = self._collect_bluetooth_devices()
        except Exception as e:
            logger.error("Bluetooth devices collection failed: %s", e,
                        exc_info=True)

        try:
            result["printers"] = self._collect_printers()
        except Exception as e:
            logger.error("Printers collection failed: %s", e, exc_info=True)

        try:
            result["audio"] = self._collect_audio_devices()
        except Exception as e:
            logger.error("Audio devices collection failed: %s", e,
                        exc_info=True)

        self.data.devices_info = result
        if any(result.values()):
            self._cache_write("devices_static", result)
        logger.info(
            "Devices: %d USB, %d Bluetooth, %d printers, %d audio",
            len(result["usb"]), len(result["bluetooth"]),
            len(result["printers"]), len(result["audio"]))

    def collect_drivers(self) -> None:
        """Collect installed driver info via WMI Win32_PnPSignedDriver."""
        logger.info("Collecting driver info")
        cached = self._cache_read("drivers_static")
        if cached:
            self.data.drivers_info = cached
            return
        results: list[dict[str, str]] = []
        if not self._wmi_conn:
            self.data.drivers_info = results
            return
        try:
            for drv in self._wmi_conn.Win32_PnPSignedDriver():
                results.append({
                    "Device Name": s(getattr(drv, "DeviceName", "N/A")),
                    "Driver Version": s(getattr(drv, "DriverVersion", "N/A")),
                    "Driver Date": s(getattr(drv, "DriverDate", "N/A")),
                    "Provider": s(getattr(drv, "DriverProviderName", "N/A")),
                    "Device Class": s(getattr(drv, "DeviceClass", "N/A")),
                })
            results.sort(key=lambda x: x["Device Name"].lower())
        except Exception as e:
            logger.error("Driver collection failed: %s", e, exc_info=True)
        self.data.drivers_info = results
        if results:
            self._cache_write("drivers_static", results)
        logger.info("Drivers: %d collected", len(results))

    def _collect_usb_devices(self) -> list[dict[str, str]]:
        """Collect connected USB devices via WMI PnPEntity."""
        results: list[dict[str, str]] = []
        if not self._wmi_conn:
            return results

        try:
            wmi_conn = self._wmi_conn
            for dev in wmi_conn.query(
                    "SELECT * FROM Win32_PnPEntity WHERE "
                    "PNPClass = 'USB' OR PNPDeviceID LIKE 'USB%'"):
                device_id = s(getattr(dev, "PNPDeviceID", ""))
                vid = ""
                pid = ""
                m = re.search(r"VID_([0-9A-Fa-f]{4})", device_id)
                if m:
                    vid = m.group(1)
                m = re.search(r"PID_([0-9A-Fa-f]{4})", device_id)
                if m:
                    pid = m.group(1)

                results.append({
                    "Name": s(getattr(dev, "Name", "N/A")),
                    "Description": s(getattr(dev, "Description", "N/A")),
                    "Manufacturer": s(getattr(dev, "Manufacturer", "N/A")),
                    "Status": s(getattr(dev, "Status", "N/A")),
                    "Device ID": device_id,
                    "Vendor ID": vid or "N/A",
                    "Product ID": pid or "N/A",
                })
        except Exception as e:
            logger.debug("USB WMI query failed: %s", e)

        return results

    def _collect_bluetooth_devices(self) -> list[dict[str, str]]:
        """Collect paired/connected Bluetooth devices via WMI PnPEntity."""
        results: list[dict[str, str]] = []
        if not self._wmi_conn:
            return results

        try:
            wmi_conn = self._wmi_conn
            for dev in wmi_conn.query(
                    "SELECT * FROM Win32_PnPEntity WHERE PNPClass = 'Bluetooth'"):
                results.append({
                    "Name": s(getattr(dev, "Name", "N/A")),
                    "Description": s(getattr(dev, "Description", "N/A")),
                    "Manufacturer": s(getattr(dev, "Manufacturer", "N/A")),
                    "Status": s(getattr(dev, "Status", "N/A")),
                    "Device ID": s(getattr(dev, "PNPDeviceID", "N/A")),
                })
        except Exception as e:
            logger.debug("Bluetooth WMI query failed: %s", e)

        return results

    def _collect_printers(self) -> list[dict[str, str]]:
        """Collect installed printers via WMI Win32_Printer."""
        results: list[dict[str, str]] = []
        if not self._wmi_conn:
            return results

        try:
            wmi_conn = self._wmi_conn
            for prn in wmi_conn.Win32_Printer():
                results.append({
                    "Name": s(getattr(prn, "Name", "N/A")),
                    "Driver": s(getattr(prn, "DriverName", "N/A")),
                    "Port": s(getattr(prn, "PortName", "N/A")),
                    "Shared": "Yes" if getattr(prn, "Shared", False) else "No",
                    "Default": ("Yes"
                                if getattr(prn, "Default", False) else "No"),
                    "Status": s(getattr(prn, "Status", "N/A")),
                    "Print Processor": s(getattr(prn, "PrintProcessor", "N/A")),
                })
        except Exception as e:
            logger.debug("Printer WMI query failed: %s", e)

        return results

    def _collect_audio_devices(self) -> list[dict[str, str]]:
        """Collect audio/sound devices via WMI Win32_SoundDevice."""
        results: list[dict[str, str]] = []
        if not self._wmi_conn:
            return results

        try:
            wmi_conn = self._wmi_conn
            for snd in wmi_conn.Win32_SoundDevice():
                results.append({
                    "Name": s(getattr(snd, "Name", "N/A")),
                    "Manufacturer": s(getattr(snd, "Manufacturer", "N/A")),
                    "ProductName": s(getattr(snd, "ProductName", "N/A")),
                    "Status": s(getattr(snd, "Status", "N/A")),
                    "Device ID": s(getattr(snd, "DeviceID", "N/A")),
                })
        except Exception as e:
            logger.debug("Audio WMI query failed: %s", e)

        return results

    # ------------------------------------------------------------------ #
    #  Diagnostics: Event Log, Power Plan, DirectX/OpenGL
    # ------------------------------------------------------------------ #

    def collect_diagnostics(self) -> None:
        """Collect event log, power plan, and DirectX/OpenGL info.

        Power plan + DirectX are cached (rarely change). Event log is
        always collected fresh (changes frequently).
        """
        result: dict[str, Any] = {
            "event_log_system": [],
            "event_log_application": [],
            "bsod_history": [],
            "crash_dump_settings": {},
            "power_plan": {},
            "directx": {},
            "restore_points": [],
            "environment": {},
            "path_entries": [],
        }

        # Event log — always fresh (not cached)
        try:
            system_events, app_events = self._collect_event_log()
            result["event_log_system"] = system_events
            result["event_log_application"] = app_events
        except Exception as e:
            logger.error("Event log collection failed: %s", e, exc_info=True)

        # Power plan + DirectX + restore points + environment — cached
        cached = self._cache_read("diagnostics_static")
        if cached is not None:
            result["power_plan"] = cached.get("power_plan", {})
            result["directx"] = cached.get("directx", {})
            # Collect restore_points + environment if missing from old cache
            if "restore_points" in cached:
                result["restore_points"] = cached.get("restore_points", [])
            else:
                try:
                    result["restore_points"] = self._collect_restore_points()
                except Exception as e:
                    logger.error("Restore points collection failed: %s", e,
                                exc_info=True)
            if "environment" in cached:
                result["environment"] = cached.get("environment", {})
            else:
                try:
                    result["environment"] = self._collect_environment_variables()
                except Exception as e:
                    logger.error("Environment variables collection failed: %s", e,
                                exc_info=True)
            if "path_entries" in cached:
                result["path_entries"] = cached.get("path_entries", [])
            else:
                try:
                    result["path_entries"] = self._collect_path_entries()
                except Exception as e:
                    logger.error("PATH entries collection failed: %s", e,
                                exc_info=True)
            if "bsod_history" in cached:
                result["bsod_history"] = cached.get("bsod_history", [])
            else:
                try:
                    result["bsod_history"] = self._collect_bsod_history()
                except Exception as e:
                    logger.error("BSOD history collection failed: %s", e,
                                exc_info=True)
            if "crash_dump_settings" in cached:
                result["crash_dump_settings"] = cached.get(
                    "crash_dump_settings", {})
            else:
                try:
                    result["crash_dump_settings"] = \
                        self._collect_crash_dump_settings()
                except Exception as e:
                    logger.error("Crash dump settings collection failed: %s", e,
                                exc_info=True)
            logger.info("Diagnostics (power plan + DirectX) loaded from cache")
            # Re-cache if we added missing keys
            cacheable = {
                "power_plan": result["power_plan"],
                "directx": result["directx"],
                "restore_points": result["restore_points"],
                "environment": result["environment"],
                "path_entries": result["path_entries"],
                "bsod_history": result["bsod_history"],
                "crash_dump_settings": result["crash_dump_settings"],
            }
            if ("restore_points" not in cached
                    or "environment" not in cached
                    or "path_entries" not in cached
                    or "bsod_history" not in cached
                    or "crash_dump_settings" not in cached):
                self._cache_write("diagnostics_static", cacheable)
        else:
            try:
                result["power_plan"] = self._collect_power_plan()
            except Exception as e:
                logger.error("Power plan collection failed: %s", e, exc_info=True)

            try:
                result["directx"] = self._collect_directx_info()
            except Exception as e:
                logger.error("DirectX info collection failed: %s", e, exc_info=True)

            try:
                result["restore_points"] = self._collect_restore_points()
            except Exception as e:
                logger.error("Restore points collection failed: %s", e,
                            exc_info=True)

            try:
                result["environment"] = self._collect_environment_variables()
            except Exception as e:
                logger.error("Environment variables collection failed: %s", e,
                            exc_info=True)

            try:
                result["path_entries"] = self._collect_path_entries()
            except Exception as e:
                logger.error("PATH entries collection failed: %s", e,
                            exc_info=True)

            try:
                result["bsod_history"] = self._collect_bsod_history()
            except Exception as e:
                logger.error("BSOD history collection failed: %s", e,
                            exc_info=True)

            try:
                result["crash_dump_settings"] = self._collect_crash_dump_settings()
            except Exception as e:
                logger.error("Crash dump settings collection failed: %s", e,
                            exc_info=True)

            # Cache only the static parts (not event log)
            cacheable = {
                "power_plan": result["power_plan"],
                "directx": result["directx"],
                "restore_points": result["restore_points"],
                "environment": result["environment"],
                "path_entries": result["path_entries"],
                "bsod_history": result["bsod_history"],
                "crash_dump_settings": result["crash_dump_settings"],
            }
            if cacheable["power_plan"] or cacheable["directx"]:
                self._cache_write("diagnostics_static", cacheable)

        self.data.diagnostics_info = result
        self.data.restore_points = result.get("restore_points", [])
        self.data.environment_info = result.get("environment", {})
        logger.info(
            "Diagnostics: %d system events, %d application events, "
            "power plan: %s, DirectX: %s",
            len(result["event_log_system"]),
            len(result["event_log_application"]),
            bool(result["power_plan"]),
            bool(result["directx"]))

    def _collect_event_log(self) -> tuple[list[dict[str, str]],
                                           list[dict[str, str]]]:
        """Collect recent event log errors and warnings.

        Returns two lists: ``(system_events, application_events)``.
        Each is capped at 200 entries (errors + warnings only).
        """
        system_events: list[dict[str, str]] = []
        app_events: list[dict[str, str]] = []
        try:
            import win32evtlog
        except ImportError:
            logger.debug("pywin32 not available for event log")
            return system_events, app_events

        ERROR_TYPE = 1
        WARNING_TYPE = 2
        max_events = 200

        for log_name, target in (("System", system_events),
                                 ("Application", app_events)):
            try:
                handle = win32evtlog.OpenEventLog(None, log_name)
                try:
                    flags = (
                        win32evtlog.EVENTLOG_BACKWARDS_READ
                        | win32evtlog.EVENTLOG_SEQUENTIAL_READ
                    )
                    count = 0
                    while count < max_events:
                        events = win32evtlog.ReadEventLog(handle, flags, 0)
                        if not events:
                            break
                        for evt in events:
                            evt_type = getattr(evt, "EventType", 0)
                            if evt_type not in (ERROR_TYPE, WARNING_TYPE):
                                continue
                            level = "Error" if evt_type == ERROR_TYPE else "Warning"
                            time_gen = getattr(evt, "TimeGenerated", None)
                            time_str = ""
                            if time_gen:
                                try:
                                    time_str = time_gen.strftime(
                                        "%Y-%m-%d %H:%M:%S")
                                except Exception:
                                    time_str = str(time_gen)

                            source = s(getattr(evt, "SourceName", "N/A"))
                            event_id = getattr(evt, "EventID", 0)
                            # EventID is a tuple in some pywin32 versions
                            if isinstance(event_id, tuple):
                                event_id = event_id[0]
                            # Mask to get the low 16 bits
                            event_id_str = str(event_id & 0xFFFF)

                            # Get the message text
                            msg = ""
                            try:
                                inserts = getattr(evt, "StringInserts", None)
                                if inserts:
                                    msg = " ".join(
                                        str(x) for x in inserts[:5])
                            except Exception:
                                pass
                            if len(msg) > 200:
                                msg = msg[:200] + "..."

                            target.append({
                                "Log": log_name,
                                "Level": level,
                                "Time": time_str,
                                "Source": source,
                                "Event ID": event_id_str,
                                "Message": msg or "(no message)",
                            })
                            count += 1
                            if count >= max_events:
                                break
                finally:
                    win32evtlog.CloseEventLog(handle)
            except Exception as e:
                logger.debug("Event log '%s' read failed: %s", log_name, e)

        return system_events, app_events

    def _collect_power_plan(self) -> dict[str, str]:
        """Collect active power plan and settings via ctypes + registry."""
        import ctypes
        import winreg

        result: dict[str, str] = {}

        # Active power scheme GUID via PowerGetActiveScheme
        try:
            import ctypes.wintypes
            powrprof = ctypes.windll.LoadLibrary("powrprof.dll")
            powrprof.PowerGetActiveScheme.argtypes = [
                ctypes.wintypes.LPCVOID,
                ctypes.POINTER(ctypes.wintypes.LPVOID),
            ]
            powrprof.PowerGetActiveScheme.restype = ctypes.wintypes.DWORD
            ctypes.windll.kernel32.LocalFree.argtypes = [
                ctypes.wintypes.HLOCAL]
            ctypes.windll.kernel32.LocalFree.restype = ctypes.wintypes.HLOCAL

            guid_ptr = ctypes.c_void_p()
            if powrprof.PowerGetActiveScheme(
                    None, ctypes.byref(guid_ptr)) == 0:
                try:
                    # Read GUID bytes (16 bytes)
                    guid_bytes = ctypes.string_at(guid_ptr, 16)
                    # Format as GUID string
                    guid_str = str(uuid.UUID(bytes_le=guid_bytes))
                    result["Active Power Scheme GUID"] = guid_str

                    # Look up friendly name via registry
                    try:
                        with winreg.OpenKey(
                            winreg.HKEY_LOCAL_MACHINE,
                            rf"SYSTEM\CurrentControlSet\Control\Power\User"
                            rf"\PowerSchemes\{guid_str}"
                        ) as key:
                            name, _ = winreg.QueryValueEx(
                                key, "FriendlyName")
                            result["Active Power Scheme"] = s(name)
                    except Exception:
                        # Fallback: known GUIDs
                        known = {
                            "381b4222-f694-41f0-9685-ff5bb260df2e": "Balanced",
                            "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c": "High Performance",
                            "a1841308-3541-4fab-bc81-f71556f20b4a": "Power Saver",
                        }
                        result["Active Power Scheme"] = known.get(
                            guid_str.lower(), "Unknown")
                finally:
                    try:
                        ctypes.windll.kernel32.LocalFree(guid_ptr)
                    except Exception:
                        pass
        except Exception as e:
            logger.debug("PowerGetActiveScheme failed: %s", e)

        # Sleep / display timeouts from registry
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Control\Power"
                r"\PowerSettings\Timeout"
            ) as key:
                for name in ("AC", "DC"):
                    try:
                        sub, _ = winreg.QueryValueEx(key, name)
                        result[f"{name} Timeout (s)"] = str(sub)
                    except Exception:
                        pass
        except Exception:
            pass

        # Additional power info via WMI
        wmi_conn = self._wmi_conn
        if wmi_conn:
            try:
                # Battery info if present
                batteries = list(wmi_conn.Win32_Battery())
                if batteries:
                    for bat in batteries:
                        est_charge = getattr(bat, "EstimatedChargeRemaining",
                                              None)
                        if est_charge is not None:
                            result["Battery Charge"] = f"{est_charge}%"
                        bat_status = getattr(bat, "BatteryStatus", None)
                        status_map = {
                            1: "Discharging", 2: "AC Power",
                            3: "Fully Charged", 4: "Low",
                            5: "Critical", 6: "Charging",
                        }
                        if bat_status is not None:
                            result["Battery Status"] = status_map.get(
                                bat_status, f"Code {bat_status}")
                        break
            except Exception as e:
                logger.debug("WMI battery query failed: %s", e)

        return result

    def _collect_directx_info(self) -> dict[str, str]:
        """Collect DirectX version and OpenGL info from registry."""
        import winreg

        result: dict[str, str] = {}

        # DirectX version from registry
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\DirectX"
            ) as key:
                version, _ = winreg.QueryValueEx(key, "Version")
                result["DirectX Version"] = s(version)
                try:
                    installed, _ = winreg.QueryValueEx(key, "InstalledVersion")
                    if isinstance(installed, bytes):
                        result["DirectX Installed Version"] = installed.hex()
                    else:
                        result["DirectX Installed Version"] = s(installed)
                except Exception:
                    pass
        except Exception as e:
            logger.debug("DirectX registry read failed: %s", e)

        # DirectX feature levels via registry (Win10+ has DirectX 12)
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion"
                r"\DirectX\UserGpuPreferences"
            ) as key:
                result["DirectX 12 (UWP)"] = "Available"
        except FileNotFoundError:
            pass
        except Exception:
            pass

        # OpenGL version — check GPU driver registry
        try:
            # Video controller registry keys contain OpenGL info
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\OpenGLDrivers"
            ) as key:
                i = 0
                while i < 10:
                    try:
                        name = winreg.EnumKey(key, i)
                        with winreg.OpenKey(key, name) as sub:
                            try:
                                drv, _ = winreg.QueryValueEx(sub, "Driver")
                                result[f"OpenGL Driver ({name})"] = s(drv)
                            except Exception:
                                pass
                            try:
                                ver, _ = winreg.QueryValueEx(sub, "Version")
                                result[f"OpenGL Version ({name})"] = s(ver)
                            except Exception:
                                pass
                        i += 1
                    except OSError:
                        break
        except FileNotFoundError:
            result["OpenGL"] = "No dedicated OpenGL driver found"
        except Exception as e:
            logger.debug("OpenGL registry read failed: %s", e)

        # GPU-specific: check for Vulkan support
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Khronos\Vulkan\Drivers"
            ) as key:
                i = 0
                drivers = []
                while i < 20:
                    try:
                        name, val, _ = winreg.EnumValue(key, i)
                        if name:
                            drivers.append(name)
                    except OSError:
                        break
                    i += 1
                if drivers:
                    result["Vulkan Drivers"] = ", ".join(drivers)
        except FileNotFoundError:
            pass
        except Exception:
            pass

        # GPU vendor identification (uses already-collected hw_info, no WMI/COM needed)
        try:
            for gpu in self.data.hw_info.get("gpus", []):
                name = gpu.get("Name", "GPU")
                vendor = gpu.get("Vendor", "")
                if "NVIDIA" in name.upper():
                    result["GPU Vendor"] = "NVIDIA"
                    result["GPU API"] = "NVIDIA (NVML/CUDA capable)"
                elif "AMD" in name.upper() or "RADEON" in name.upper():
                    result["GPU Vendor"] = "AMD"
                    result["GPU API"] = "AMD (ADL/Vulkan capable)"
                elif "INTEL" in name.upper():
                    result["GPU Vendor"] = "Intel"
                    result["GPU API"] = "Intel (D3D/Vulkan)"
                else:
                    result["GPU Vendor"] = vendor
                break
        except Exception:
            pass

        # D3D feature level detection via ctypes (d3d11.dll)
        try:
            import ctypes

            # Feature levels (highest first)
            _FL = {
                0xc100: "12.1", 0xc000: "12.0",
                0xb100: "11.1", 0xb000: "11.0",
                0xa100: "10.1", 0xa000: "10.0",
                0x9300: "9.3", 0x9200: "9.2", 0x9100: "9.1",
            }
            levels = (ctypes.c_uint * 9)(
                0xc100, 0xc000, 0xb100, 0xb000,
                0xa100, 0xa000, 0x9300, 0x9200, 0x9100
            )
            out_fl = ctypes.c_uint(0)
            dev_ptr = ctypes.c_void_p(0)
            ctx_ptr = ctypes.c_void_p(0)
            d3d11_ok = False

            try:
                d3d11 = ctypes.windll.d3d11
                hr = d3d11.D3D11CreateDevice(
                    None, 1, None, 0,
                    levels, 9, 7,
                    ctypes.byref(dev_ptr),
                    ctypes.byref(out_fl),
                    ctypes.byref(ctx_ptr)
                )
                if hr == 0 and out_fl.value:
                    d3d11_ok = True
                    result["Max D3D Feature Level"] = _FL.get(
                        out_fl.value, f"0x{out_fl.value:04x}")
                    # List all supported levels
                    supported = []
                    for fl_code, fl_name in [
                        (0xc100, "12.1"), (0xc000, "12.0"),
                        (0xb100, "11.1"), (0xb000, "11.0"),
                        (0xa100, "10.1"), (0xa000, "10.0"),
                        (0x9300, "9.3"), (0x9200, "9.2"),
                        (0x9100, "9.1"),
                    ]:
                        if fl_code <= out_fl.value:
                            supported.append(fl_name)
                    if supported:
                        result["Supported Feature Levels"] = ", ".join(supported)
            except Exception as e:
                logger.debug("D3D11 feature level check failed: %s", e)
            finally:
                # Release COM objects if created (always — even on error,
                # since D3D11CreateDevice may have allocated before failing).
                if dev_ptr.value:
                    try:
                        # IUnknown::Release is at vtable index 2
                        vtable = ctypes.c_void_p.from_address(dev_ptr.value).value
                        release_addr = ctypes.c_void_p.from_address(
                            vtable + 2 * ctypes.sizeof(ctypes.c_void_p)).value
                        release = ctypes.CFUNCTYPE(ctypes.c_ulong)(release_addr)
                        release()
                    except Exception:
                        pass
                if ctx_ptr.value:
                    try:
                        vtable = ctypes.c_void_p.from_address(ctx_ptr.value).value
                        release_addr = ctypes.c_void_p.from_address(
                            vtable + 2 * ctypes.sizeof(ctypes.c_void_p)).value
                        release = ctypes.CFUNCTYPE(ctypes.c_ulong)(release_addr)
                        release()
                    except Exception:
                        pass

            # D3D12 runtime availability (check if d3d12.dll loads)
            try:
                ctypes.windll.d3d12
                if d3d11_ok and out_fl.value >= 0xc000:
                    result["D3D12 Runtime"] = "Available"
                elif d3d11_ok:
                    result["D3D12 Runtime"] = "DLL present (GPU below FL 12.0)"
                else:
                    result["D3D12 Runtime"] = "DLL present (D3D11 check failed)"
            except OSError:
                result["D3D12 Runtime"] = "Not installed"

        except Exception as e:
            logger.debug("D3D feature level detection failed: %s", e)

        # Multi-monitor info via user32
        try:
            import ctypes
            user32 = ctypes.windll.user32
            # SM_CMONITORS = 80
            monitor_count = user32.GetSystemMetrics(80)
            result["Monitor Count"] = str(monitor_count)
            # Get virtual screen size
            # SM_CXVIRTUALSCREEN = 78, SM_CYVIRTUALSCREEN = 79
            vw = user32.GetSystemMetrics(78)
            vh = user32.GetSystemMetrics(79)
            if vw and vh:
                result["Virtual Screen"] = f"{vw} x {vh}"
        except Exception as e:
            logger.debug("Multi-monitor info failed: %s", e)

        return result

    # ------------------------------------------------------------------ #
    #  VPN status detection
    # ------------------------------------------------------------------ #

    def collect_vpn_status(self) -> None:
        """Detect active VPN connections via network adapter inspection (cached)."""
        cached = self._cache_read("vpn_static")
        if cached is not None:
            self.data.vpn_status = cached
            logger.info("VPN status loaded from cache")
            return

        result: dict[str, Any] = {"Active": False, "Connections": []}

        if not self._wmi_conn:
            self.data.vpn_status = result
            return

        try:
            wmi_conn = self._wmi_conn

            # Known VPN adapter keywords in name or description
            vpn_keywords = [
                "vpn", "tap", "tun", "wireguard", "openvpn", "pptp",
                "l2tp", "sstp", "ikev2", "cisco", "anyconnect",
                "forticlient", "nordlayer", "tunnel", "virtual",
            ]

            for adapter in wmi_conn.Win32_NetworkAdapter():
                name = (getattr(adapter, "Name", "") or "").upper()
                desc = (getattr(adapter, "Description", "") or "").upper()
                net_id = getattr(adapter, "NetConnectionID", "") or ""
                status = getattr(adapter, "NetConnectionStatus", 0)

                # NetConnectionStatus: 2 = Connected, 7 = Disconnected
                is_connected = (status == 2)

                matched_keyword = ""
                for kw in vpn_keywords:
                    if kw in name or kw in desc:
                        matched_keyword = kw
                        break

                if matched_keyword:
                    conn = {
                        "Adapter": s(getattr(adapter, "Name", "N/A")),
                        "Description": s(getattr(adapter, "Description",
                                                   "N/A")),
                        "Connection": net_id or "N/A",
                        "Status": "Connected" if is_connected else "Disconnected",
                        "Type": "VPN",
                        "Matched": matched_keyword,
                    }
                    result["Connections"].append(conn)
                    if is_connected:
                        result["Active"] = True

            # Also check via psutil for active VPN-like interfaces
            try:
                stats = psutil.net_if_stats()
                addrs = psutil.net_if_addrs()
                for iface_name in stats:
                    upper = iface_name.upper()
                    for kw in vpn_keywords:
                        if kw in upper:
                            # Check if it has an IP address
                            has_ip = False
                            for addr in addrs.get(iface_name, []):
                                if addr.family in (socket.AF_INET, socket.AF_INET6) \
                                        and addr.address not in ("0.0.0.0", "::"):
                                    has_ip = True
                                    break
                            if has_ip:
                                # Check not already in results
                                existing = [c for c in result["Connections"]
                                            if c["Connection"].upper()
                                            == iface_name.upper()]
                                if not existing:
                                    result["Connections"].append({
                                        "Adapter": iface_name,
                                        "Description": "VPN-like interface",
                                        "Connection": iface_name,
                                        "Status": "Connected",
                                        "Type": "VPN",
                                        "Matched": kw,
                                    })
                                    result["Active"] = True
                            break
            except Exception as e:
                logger.debug("psutil VPN check failed: %s", e)

        except Exception as e:
            logger.error("VPN status collection failed: %s", e, exc_info=True)

        self.data.vpn_status = result
        self._cache_write("vpn_static", result)
        logger.info("VPN status: active=%s, %d connection(s) found",
                    result["Active"], len(result["Connections"]))

    # ------------------------------------------------------------------ #
    #  UEFI / Secure Boot info (added to BIOS section)
    # ------------------------------------------------------------------ #

    def _collect_restore_points(self) -> list[dict[str, str]]:
        """Collect system restore points via WMI SystemRestore (root/default)."""
        results: list[dict[str, str]] = []
        with self._wmi_namespace("root/default") as sr:
            if sr is None:
                return results
            try:
                for rp in sr.SystemRestore():
                    creation = getattr(rp, "CreationTime", "")
                    desc = s(getattr(rp, "Description", ""))
                    seq = s(getattr(rp, "SequenceNumber", ""))
                    results.append({
                        "Creation Time": creation,
                        "Description": desc or "(no description)",
                        "Sequence #": seq,
                    })
                results.reverse()  # newest first
            except Exception as e:
                logger.debug("Restore points query failed: %s", e)
        return results

    def _collect_environment_variables(self) -> dict[str, str]:
        """Collect system + user environment variables from registry."""
        import winreg
        result: dict[str, str] = {}
        # System environment variables
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment") as sys_key:
                i = 0
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(sys_key, i)
                        result[f"[System] {name}"] = str(value)
                        i += 1
                    except OSError:
                        break
        except Exception as e:
            logger.debug("System env vars read failed: %s", e)
        # User environment variables
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, r"Environment") as usr_key:
                i = 0
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(usr_key, i)
                        result[f"[User] {name}"] = str(value)
                        i += 1
                    except OSError:
                        break
        except Exception as e:
            logger.debug("User env vars read failed: %s", e)
        return dict(sorted(result.items()))

    def _collect_path_entries(self) -> list[dict[str, str]]:
        """Collect PATH entries split into individual directories.

        Returns a list of dicts with keys: Source (System/User),
        Index, Path.
        """
        import winreg
        results: list[dict[str, str]] = []
        for source, hive, subkey in (
            ("System", winreg.HKEY_LOCAL_MACHINE,
             r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
            ("User", winreg.HKEY_CURRENT_USER, r"Environment"),
        ):
            try:
                with winreg.OpenKey(hive, subkey) as key:
                    path_val, _ = winreg.QueryValueEx(key, "Path")
                for idx, entry in enumerate(str(path_val).split(";")):
                    entry = entry.strip()
                    if entry:
                        results.append({
                            "Source": source,
                            "Index": str(idx),
                            "Path": entry,
                        })
            except FileNotFoundError:
                pass
            except Exception as e:
                logger.debug("PATH read failed (%s): %s", source, e)
        return results

    # ------------------------------------------------------------------ #
    #  BSOD / crash history + crash dump settings
    # ------------------------------------------------------------------ #

    def _collect_bsod_history(self) -> list[dict[str, str]]:
        """Collect BSOD/kernel crash history from WMI BugCheck events
        (Event ID 1001 in System log) and minidump files.
        """
        results: list[dict[str, str]] = []

        # 1. WMI BugCheck events (Event ID 1001, Source "BugCheck" or
        #    "Microsoft-Windows-WER-SystemErrorReporting")
        try:
            import win32evtlog
            handle = win32evtlog.OpenEventLog(None, "System")
            try:
                flags = (
                    win32evtlog.EVENTLOG_BACKWARDS_READ
                    | win32evtlog.EVENTLOG_SEQUENTIAL_READ
                )
                count = 0
                max_crashes = 50
                while count < max_crashes:
                    events = win32evtlog.ReadEventLog(handle, flags, 0)
                    if not events:
                        break
                    for evt in events:
                        source = s(getattr(evt, "SourceName", ""))
                        event_id = getattr(evt, "EventID", 0)
                        if isinstance(event_id, tuple):
                            event_id = event_id[0]
                        event_id_low = event_id & 0xFFFF
                        if event_id_low != 1001:
                            continue
                        if source not in ("BugCheck",
                                         "Microsoft-Windows-WER-SystemErrorReporting"):
                            continue
                        time_gen = getattr(evt, "TimeGenerated", None)
                        time_str = ""
                        if time_gen:
                            try:
                                time_str = time_gen.strftime(
                                    "%Y-%m-%d %H:%M:%S")
                            except Exception:
                                time_str = str(time_gen)
                        # Extract bugcheck code + parameters from message
                        msg = ""
                        try:
                            inserts = getattr(evt, "StringInserts", None)
                            if inserts:
                                msg = " ".join(str(x) for x in inserts[:5])
                        except Exception:
                            pass
                        # First insert is usually the bugcheck code (hex),
                        # followed by parameters
                        bugcheck_code = ""
                        bugcheck_params = ""
                        if msg:
                            parts = msg.split()
                            if parts:
                                bugcheck_code = parts[0]
                                bugcheck_params = " ".join(parts[1:5])
                        results.append({
                            "Time": time_str,
                            "BugCheck Code": bugcheck_code or "Unknown",
                            "Parameters": bugcheck_params or "",
                            "Message": msg[:300] if msg else "(no details)",
                        })
                        count += 1
                        if count >= max_crashes:
                            break
            finally:
                win32evtlog.CloseEventLog(handle)
        except Exception as e:
            logger.debug("BSOD BugCheck event query failed: %s", e)

        # 2. Minidump files in C:\Windows\Minidump\
        minidump_dir = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                                     "Minidump")
        try:
            if os.path.isdir(minidump_dir):
                for fname in sorted(os.listdir(minidump_dir), reverse=True):
                    if fname.lower().endswith(".dmp"):
                        fpath = os.path.join(minidump_dir, fname)
                        try:
                            stat = os.stat(fpath)
                            mod_time = datetime.datetime.fromtimestamp(
                                stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                            size_kb = stat.st_size // 1024
                            results.append({
                                "Time": mod_time,
                                "BugCheck Code": "(minidump file)",
                                "Parameters": f"{fname} ({size_kb} KB)",
                                "Message": f"Minidump: {fpath}",
                            })
                        except Exception:
                            pass
        except Exception as e:
            logger.debug("Minidump scan failed: %s", e)

        # 3. Check for full MEMORY.DMP
        memdump = os.path.join(
            os.environ.get("SystemRoot", r"C:\Windows"), "MEMORY.DMP")
        try:
            if os.path.isfile(memdump):
                stat = os.stat(memdump)
                mod_time = datetime.datetime.fromtimestamp(
                    stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                size_mb = stat.st_size // (1024 * 1024)
                results.append({
                    "Time": mod_time,
                    "BugCheck Code": "(full dump)",
                    "Parameters": f"MEMORY.DMP ({size_mb} MB)",
                    "Message": f"Full dump: {memdump}",
                })
        except Exception:
            pass

        return results

    def _collect_crash_dump_settings(self) -> dict[str, str]:
        """Collect crash dump settings from registry CrashControl key."""
        import winreg
        result: dict[str, str] = {}
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Control\CrashControl") as key:
                # CrashDumpEnabled: 0=none, 1=complete, 2=kernel, 3=small (minidump),
                #                   7=automatic
                dump_types = {
                    0: "None",
                    1: "Complete memory dump",
                    2: "Kernel memory dump",
                    3: "Small memory dump (minidump, 256KB)",
                    7: "Automatic memory dump",
                }
                try:
                    val, _ = winreg.QueryValueEx(key, "CrashDumpEnabled")
                    result["Dump Type"] = dump_types.get(val, f"Unknown ({val})")
                except FileNotFoundError:
                    pass
                try:
                    val, _ = winreg.QueryValueEx(key, "AutoReboot")
                    result["Auto Reboot"] = "Yes" if val else "No"
                except FileNotFoundError:
                    pass
                try:
                    val, _ = winreg.QueryValueEx(key, "MinidumpDir")
                    result["Minidump Directory"] = str(val)
                except FileNotFoundError:
                    pass
                try:
                    val, _ = winreg.QueryValueEx(key, "DumpFile")
                    result["Dump File"] = str(val)
                except FileNotFoundError:
                    pass
                try:
                    val, _ = winreg.QueryValueEx(key, "AlwaysKeepMemoryDump")
                    result["Always Keep Dump"] = "Yes" if val else "No"
                except FileNotFoundError:
                    pass
        except Exception as e:
            logger.debug("CrashControl registry read failed: %s", e)
        return result

    # ------------------------------------------------------------------ #
    #  UEFI / Secure Boot info (added to BIOS section)
    # ------------------------------------------------------------------ #
    def _collect_uefi_info(self) -> dict[str, str]:
        import ctypes
        import winreg

        result: dict[str, str] = {}

        # Firmware type (UEFI vs Legacy BIOS) — use GetFirmwareType API
        try:
            kernel32 = ctypes.windll.kernel32
            fw_type = ctypes.c_uint(0)
            if kernel32.GetFirmwareType(ctypes.byref(fw_type)):
                if fw_type.value == 2:
                    result["Firmware Type"] = "UEFI"
                elif fw_type.value == 1:
                    result["Firmware Type"] = "Legacy BIOS"
                else:
                    result["Firmware Type"] = f"Unknown ({fw_type.value})"
        except Exception as e:
            logger.debug("GetFirmwareType failed: %s", e)

        # Fallback to registry if API fails
        if "Firmware Type" not in result:
            try:
                with winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SYSTEM\CurrentControlSet\Control"
                ) as key:
                    fw_type, _ = winreg.QueryValueEx(key, "PEFirmwareType")
                if fw_type == 2:
                    result["Firmware Type"] = "UEFI"
                elif fw_type == 1:
                    result["Firmware Type"] = "Legacy BIOS"
                else:
                    result["Firmware Type"] = f"Unknown ({fw_type})"
            except FileNotFoundError:
                pass  # Don't set if we can't determine
            except Exception as e:
                logger.debug("PEFirmwareType read failed: %s", e)

        # Secure Boot status
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Control\SecureBoot"
            ) as key:
                # If the key exists, Secure Boot is likely supported
                result["Secure Boot"] = "Supported"
                try:
                    state, _ = winreg.QueryValueEx(key, "State")
                    if state == 1:
                        result["Secure Boot"] = "Enabled"
                    elif state == 0:
                        result["Secure Boot"] = "Disabled"
                    else:
                        result["Secure Boot"] = f"State {state}"
                except FileNotFoundError:
                    # State value may not exist, but key does
                    pass
                except Exception:
                    pass
        except FileNotFoundError:
            result["Secure Boot"] = "Not supported (Legacy BIOS)"
        except Exception as e:
            logger.debug("SecureBoot registry read failed: %s", e)

        # Memory integrity (Core Isolation) status
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Control\DeviceGuard"
                r"\Scenarios\HypervisorEnforcedCodeIntegrity"
            ) as key:
                enabled, _ = winreg.QueryValueEx(key, "Enabled")
                result["Core Isolation (HVCI)"] = (
                    "Enabled" if enabled else "Disabled")
        except FileNotFoundError:
            result["Core Isolation (HVCI)"] = "Disabled"
        except Exception:
            pass

        # TPM status
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Services\TPM"
            ) as key:
                start, _ = winreg.QueryValueEx(key, "Start")
                result["TPM"] = "Present" if start <= 3 else "Disabled"
        except FileNotFoundError:
            result["TPM"] = "Not present"
        except Exception:
            pass

        return result
