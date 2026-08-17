"""Application configuration.

Loads and saves user preferences to ``config.json`` next to the script.
All modules access the singleton via :func:`get_config` (lazy-loaded on
first call).

Settings stored:
    - sensor_refresh_interval_ms  — live sensor refresh period (default 2000)
    - process_refresh_interval_ms — process/network refresh period (default 5000)
    - process_top_n               — max processes to show (default 200)
    - theme                       — "dark" / "light" / "system"
    - font_family                 — custom font family ("" = default)
    - compact_view                — denser row layout
    - show_progress_bars          — show ASCII bars for usage values
    - enabled_sensor_types        — which LHM sensor types to collect/display
    - enabled_hardware_types      — which LHM hardware groups to enable
    - window_geometry             — base64-encoded QByteArray from saveGeometry()
    - cache_ttl_seconds           — static hardware cache time-to-live
    - sparkline_max_samples       — rolling window size for sparkline graphs
    - speed_test_download_mb      — Cloudflare speed test download size
    - speed_test_upload_mb        — Cloudflare speed test upload size
    - speed_test_timeout_s        — Cloudflare speed test timeout
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from typing import Any

from app_logger import get_logger
from paths import data_dir

logger = get_logger(__name__)

_ALL_SENSOR_TYPES = [
    "Temperature", "Fan", "Power", "Clock", "Voltage", "Load",
    "Level", "Data", "Factor", "Throughput", "SmallData", "Control",
]

_ALL_HARDWARE_TYPES = [
    "CPU", "GPU", "Motherboard", "Controller", "Storage",
    "Battery", "Memory", "Network", "PSU",
]

# Map hardware type keys to LHM Computer.IsXxxEnabled property names
_HW_TYPE_TO_LHM_PROP = {
    "CPU": "IsCpuEnabled",
    "GPU": "IsGpuEnabled",
    "Motherboard": "IsMotherboardEnabled",
    "Controller": "IsControllerEnabled",
    "Storage": "IsStorageEnabled",
    "Battery": "IsBatteryEnabled",
    "Memory": "IsMemoryEnabled",
    "Network": "IsNetworkEnabled",
    "PSU": "IsPsuEnabled",
}


def _default_sensor_types() -> list[str]:
    return list(_ALL_SENSOR_TYPES)


def _default_hardware_types() -> dict[str, bool]:
    # Network is disabled by default (no useful sensors on most systems)
    return {ht: (ht != "Network") for ht in _ALL_HARDWARE_TYPES}


@dataclass
class Config:
    sensor_refresh_interval_ms: int = 2000
    process_refresh_interval_ms: int = 5000
    process_top_n: int = 200
    theme: str = "dark"
    font_family: str = ""
    compact_view: bool = False
    show_progress_bars: bool = True
    enabled_sensor_types: list[str] = field(default_factory=_default_sensor_types)
    enabled_hardware_types: dict[str, bool] = field(default_factory=_default_hardware_types)
    window_geometry: str = ""
    cache_ttl_seconds: int = 3600
    sparkline_max_samples: int = 60
    speed_test_download_mb: int = 99
    speed_test_upload_mb: int = 50
    speed_test_timeout_s: int = 120
    cpu_warn_threshold: float = 10.0
    cpu_crit_threshold: float = 50.0
    mem_warn_threshold: float = 100.0
    mem_crit_threshold: float = 500.0
    disk_warn_threshold: float = 1024.0
    disk_crit_threshold: float = 10240.0
    net_warn_threshold: int = 3
    net_crit_threshold: int = 10

    # ------------------------------------------------------------------ #
    #  Persistence
    # ------------------------------------------------------------------ #
    @classmethod
    def _path(cls) -> str:
        return os.path.join(data_dir(), "config.json")

    @classmethod
    def load(cls) -> "Config":
        """Load config from disk, falling back to defaults on any error."""
        path = cls._path()
        try:
            with open(path, "r", encoding="utf-8") as f:
                data: dict[str, Any] = json.load(f)
        except FileNotFoundError:
            logger.info("config.json not found — using defaults")
            return cls()
        except Exception as e:
            logger.warning("Failed to load config.json: %s — using defaults", e)
            return cls()

        defaults = cls()
        try:
            cfg = cls(
                sensor_refresh_interval_ms=int(
                    data.get("sensor_refresh_interval_ms",
                              defaults.sensor_refresh_interval_ms)
                ),
                process_refresh_interval_ms=int(
                    data.get("process_refresh_interval_ms",
                              defaults.process_refresh_interval_ms)
                ),
                process_top_n=int(
                    data.get("process_top_n", defaults.process_top_n)
                ),
                theme=str(data.get("theme", defaults.theme)),
                font_family=str(data.get("font_family", defaults.font_family)),
                compact_view=bool(data.get("compact_view", defaults.compact_view)),
                show_progress_bars=bool(
                    data.get("show_progress_bars", defaults.show_progress_bars)),
                enabled_sensor_types=list(
                    data.get("enabled_sensor_types", defaults.enabled_sensor_types)
                ),
                enabled_hardware_types=dict(
                    data.get("enabled_hardware_types", defaults.enabled_hardware_types)
                ),
                window_geometry=str(data.get("window_geometry", "")),
                cache_ttl_seconds=int(
                    data.get("cache_ttl_seconds", defaults.cache_ttl_seconds)
                ),
                sparkline_max_samples=int(
                    data.get("sparkline_max_samples",
                              defaults.sparkline_max_samples)
                ),
                speed_test_download_mb=int(
                    data.get("speed_test_download_mb",
                              defaults.speed_test_download_mb)
                ),
                speed_test_upload_mb=int(
                    data.get("speed_test_upload_mb",
                              defaults.speed_test_upload_mb)
                ),
                speed_test_timeout_s=int(
                    data.get("speed_test_timeout_s",
                              defaults.speed_test_timeout_s)
                ),
                cpu_warn_threshold=float(
                    data.get("cpu_warn_threshold", defaults.cpu_warn_threshold)
                ),
                cpu_crit_threshold=float(
                    data.get("cpu_crit_threshold", defaults.cpu_crit_threshold)
                ),
                mem_warn_threshold=float(
                    data.get("mem_warn_threshold", defaults.mem_warn_threshold)
                ),
                mem_crit_threshold=float(
                    data.get("mem_crit_threshold", defaults.mem_crit_threshold)
                ),
                disk_warn_threshold=float(
                    data.get("disk_warn_threshold", defaults.disk_warn_threshold)
                ),
                disk_crit_threshold=float(
                    data.get("disk_crit_threshold", defaults.disk_crit_threshold)
                ),
                net_warn_threshold=int(
                    data.get("net_warn_threshold", defaults.net_warn_threshold)
                ),
                net_crit_threshold=int(
                    data.get("net_crit_threshold", defaults.net_crit_threshold)
                ),
            )
        except (TypeError, ValueError) as e:
            logger.warning("Invalid config value: %s — using defaults", e)
            return cls()
        # Clamp refresh intervals to a sane range
        cfg.sensor_refresh_interval_ms = max(500, min(60_000, cfg.sensor_refresh_interval_ms))
        cfg.process_refresh_interval_ms = max(1000, min(60_000, cfg.process_refresh_interval_ms))
        # Clamp process top N
        cfg.process_top_n = max(10, min(500, cfg.process_top_n))
        # Clamp sparkline samples
        cfg.sparkline_max_samples = max(10, min(300, cfg.sparkline_max_samples))
        # Clamp speed test params
        cfg.speed_test_download_mb = max(1, min(500, cfg.speed_test_download_mb))
        cfg.speed_test_upload_mb = max(1, min(500, cfg.speed_test_upload_mb))
        cfg.speed_test_timeout_s = max(10, min(600, cfg.speed_test_timeout_s))
        # Validate theme
        if cfg.theme not in ("dark", "light", "system"):
            cfg.theme = "dark"
        logger.info("Config loaded from %s (sensor_refresh=%dms, proc_refresh=%dms, "
                     "proc_top=%d, theme=%s, compact=%s, progress=%s, "
                     "sparkline=%d, speed_test=%d/%dMB/%ds)",
                    path, cfg.sensor_refresh_interval_ms,
                    cfg.process_refresh_interval_ms, cfg.process_top_n,
                    cfg.theme, cfg.compact_view, cfg.show_progress_bars,
                    cfg.sparkline_max_samples,
                    cfg.speed_test_download_mb, cfg.speed_test_upload_mb,
                    cfg.speed_test_timeout_s)
        return cfg

    def save(self) -> None:
        """Save config to disk."""
        path = self._path()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(asdict(self), f, indent=2, ensure_ascii=False)
            logger.info("Config saved to %s", path)
        except Exception as e:
            logger.error("Failed to save config.json: %s", e, exc_info=True)

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #
    def is_hardware_type_enabled(self, hw_type: str) -> bool:
        """Check if a hardware type is enabled in config."""
        return self.enabled_hardware_types.get(hw_type, True)

    def is_sensor_type_enabled(self, stype: str) -> bool:
        """Check if a sensor type is enabled in config."""
        return stype in self.enabled_sensor_types

    def get_lhm_computer_settings(self) -> dict[str, bool]:
        """Return a dict of LHM Computer.IsXxxEnabled -> bool for the config."""
        result: dict[str, bool] = {}
        for hw_key, lhm_prop in _HW_TYPE_TO_LHM_PROP.items():
            result[lhm_prop] = self.is_hardware_type_enabled(hw_key)
        return result


# ------------------------------------------------------------------ #
#  Singleton access
# ------------------------------------------------------------------ #
_config: Config | None = None


def get_config() -> Config:
    """Return the singleton Config instance (loaded lazily on first call)."""
    global _config
    if _config is None:
        _config = Config.load()
    return _config


def reload_config() -> Config:
    """Force-reload config from disk (used after Settings dialog saves)."""
    global _config
    _config = Config.load()
    return _config
