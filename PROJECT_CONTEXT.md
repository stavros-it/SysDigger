# Project Context — SysDigger

> **Purpose of this file:** Give any AI model (or developer) a complete,
> self-contained understanding of what this project is, how it's structured,
> what each file does, and the key design decisions — without needing to read
> every line of code first.

---

## 1. What This App Does

**SysDigger** is a Windows desktop application that gathers and displays detailed
system information in a modern, dark-themed GUI. It shows:

- **Operating System** — name, edition, version, build, architecture, hostname, user, domain/workgroup, install date, boot time, uptime
- **Hardware** — CPU (name, cores, threads, clock, usage), RAM (total/used/free + per-slot manufacturer/part/speed/serial), motherboard, BIOS, GPU(s) (name, VRAM, driver, resolution, memory type, max refresh, color depth, DAC type, vendor, architecture), physical disks (model, size, type, free space), battery (health, wear %, cycle count); **live sparkline graphs** for CPU/RAM usage + CPU/GPU temp (60-sample rolling window, updated every 2s); **disk benchmark** (sequential read/write speed test)
- **Sensors** — real-time temperatures, fan speeds, power draw, clocks, voltages, and load percentages, grouped by hardware component (CPU, GPU, Motherboard, SSD, HDD, Memory, etc.)
- **Network** — adapters (name, MAC, IPs, gateway, DNS, bytes, link speed), **active TCP/UDP connections** (live, auto-refresh every 5s, protocol/local/remote/state/PID/process), **Wi-Fi signal info** (SSID, channel, band, signal %, standard, auth, cipher, rates), **DNS cache viewer** (record name/type/TTL/address), VPN status, external IP + geo lookup
- **Processes** — list view (sortable table, top 200 by CPU%) + **tree view** (parent-child hierarchy via psutil `ppid()`); columns: PID/Name/CPU%/Memory/Disk (KB/s)/Network (conn count); smart colorization: red (critical) for CPU>50% / Mem>500MB / Disk>10MB/s / Net>10 conn, orange (high) for CPU>10% / Mem>100MB / Disk>1MB/s / Net>3 conn
- **Software** — installed programs, Windows services, startup programs, **startup impact analysis** (boot duration from Event log, boot history table), Windows updates
- **Devices** — USB devices (VID/PID), Bluetooth, printers, audio devices, signed drivers
- **Health** — disk SMART status, Windows Defender, firewall, Windows activation status, battery wear
- **Diagnostics** — event logs (System + Application, 200 each, color-coded), BSOD history, crash dump settings, system restore points, environment variables, PATH entries, DirectX/D3D feature levels (via ctypes `D3D11CreateDevice`), power plan
- **Speed Test** — download/upload via Cloudflare (99MB/50MB), bufferbloat grade (A-F)
- **Windows Tools** — 28 maintenance utilities across 4 categories (System Repair, Maintenance, Hardware & Diagnostics, System Info & Status) powered by PowerShell subprocess execution with live-streamed output: SFC, DISM (Clean/Repair), WinRE Manager, Cleanup, Disk Analyzer (large files / top folders / recursive folder size map / duplicate file finder + scan-then-pick cleanup of biggest AppData folders or user profile files), Appx Manager (uninstall Appx packages by size), Dev Cache Cleaner (npm/pip cache + uv / LM Studio / Vortex / RSI Launcher updater folders), Hibernate Manager (enable/disable), Reset Spooler, Install/Uninstall repair, Flush Network (6 modes), Trim SSD, Check HDD, Disk Status (list status / bring disk online), Device Query (4 modes — HID services, remove HID errors, reset Bluetooth adapter, reset MTP/Android USB), Services Check, Memory Diagnostic (GUI + schedule on reboot), Time Sync, Activation, Wi-Fi, Firewall, Power & System, Autopilot Hash, Hosts File Editor, Windows Update (scan + install), UEFI BIOS Reboot (shutdown /r /fw /t 0)

The app has a **live search** feature that filters across all fields instantly,
**copy to clipboard** from any table (Ctrl+C or right-click), and
**JSON/Text/HTML export** of all system info.

---

## 2. Tech Stack

| Layer | Technology | Notes |
|---|---|---|
| GUI framework | **PySide6 (Qt6)** | Fluent dark design, sidebar navigation, scrollable cards |
| System info (general) | **psutil** | CPU, RAM, disk, network, battery, uptime |
| System info (Windows-specific) | **wmi** (Python) + **winreg** | Motherboard, BIOS, GPU, RAM slots, disk drives, OS details. Uses COM/WMI directly — **zero PowerShell subprocesses** |
| Hardware sensors | **LibreHardwareMonitorLib** via **pythonnet** | Temperatures, fans, power, clocks, voltages, loads. DLLs in `lib/` folder |
| External IP / geo | **requests** → ipify.org + ipinfo.io | HTTP API calls |
| Maintenance tools | **PowerShell** via `subprocess` | Tools tab runs scripts ported from `tools source/` as hidden-window `powershell.exe -File` processes with live stdout streaming. Uses `CREATE_NO_WINDOW` so no console flashes |
| Launcher | **pythonw** (`.pyw` file) | No console window, self-elevates to admin via UAC |

### Dependencies (installed via `install_deps.bat`)
- `psutil` — cross-platform system metrics
- `requests` — HTTP client for IP/geo lookups
- `wmi` + `pywin32` — Windows Management Instrumentation access
- `pythonnet` — .NET CLR bridge for loading LibreHardwareMonitorLib
- `PySide6` — Qt6 GUI framework

### Bundled DLLs (`lib/` folder)
Downloaded from the [LibreHardwareMonitor GitHub releases](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases).
The release ZIP is self-contained with all transitive .NET dependencies:

| DLL | Purpose |
|---|---|
| `LibreHardwareMonitorLib.dll` | Core hardware monitoring library |
| `HidSharp.dll` | HID device access (USB sensors) |
| `System.Memory.dll` | .NET Span/Memory types |
| `System.Runtime.CompilerServices.Unsafe.dll` | .NET unsafe memory ops |
| `RAMSPDToolkit-NDD.dll` | RAM SPD data parsing |
| `DiskInfoToolkit.dll` | Disk SMART data |
| `BlackSharp.Core.dll` | Internal helper |
| `System.Buffers.dll` | .NET buffer pooling |
| `System.Numerics.Vectors.dll` | SIMD vector types |
| `System.Threading.Tasks.Extensions.dll` | Async extensions |
| `Microsoft.Bcl.AsyncInterfaces.dll` | Async interfaces |
| `Microsoft.Bcl.HashCode.dll` | Hash code utilities |

Version tracked in `lib/version.txt`.

---

## 3. File Structure

```
SysDigger/
├── sysdigger.pyw          # Entry point — double-click to run. Self-elevates to admin, no console
├── app.py                # Main entry — creates QApplication, Collector, InfoWindow
├── app_logger.py         # Centralized logging — rotating file handler writing to app.log
├── config.py             # Application config (config.json) — 15 settings: refresh intervals, process top N, theme, font, sensor/hardware types, sparkline samples, speed test params, cache TTL, window geometry
├── collectors.py         # System data collection: OS, hardware, network, IP, sensors, processes, software, updates, health, speed test, devices, diagnostics, GPU details, VPN, active connections, Wi-Fi, DNS cache, disk benchmark, startup impact (~4130 lines)
├── gui.py                # PySide6 Fluent GUI — InfoWindow, cards, search, export, settings dialog, about dialog, 13 pages (incl. Tools), theme/compact/progress bar, sparkline graphs, process tree, table copy, tab persistence (~5430 lines)
├── sensors.py            # LibreHardwareMonitorLib integration via pythonnet
├── lhm_process.py        # Portable LHM.exe process manager — downloads, launches hidden, loads PawnIO kernel driver for motherboard SuperIO sensors, cleans up on close
├── paths.py              # Portable path resolution — resource_dir() / data_dir() for frozen-exe support
├── updater.py            # GitHub release updater for LHM DLLs
├── helpers.py            # Formatting & utility helpers (fmt_bytes, fmt_speed, reg_value, etc.)
├── tools.py              # Windows maintenance tools catalogue: 4 categories / 28 tools / 61 modes (PowerShell scripts ported verbatim from `tools source/`, plus v4.11 scan-then-pick cleanup scripts)
├── install_deps.bat      # Installs all pip packages, verifies imports, checks for DLLs
├── app.log               # Application log (rotating, 2MB max, 3 backups)
├── config.json           # User settings (15 settings: refresh intervals, process top N, theme, font, compact/progress, sensor/hardware types, sparkline samples, speed test params, cache TTL, window geometry)
├── settings.json         # (Deprecated — migrated to config.json in v1.9)
├── cache/                # Static data cache (1-hour TTL): hw_static, os_static, net_static, software_static, services_static, drivers_static, devices_static, health_static, updates_static, diagnostics_static, vpn_static
├── lib/                  # LibreHardwareMonitorLib DLLs (12 files + version.txt)
│   ├── LibreHardwareMonitorLib.dll
│   ├── HidSharp.dll
│   ├── System.Memory.dll
│   ├── ... (9 more dependency DLLs)
│   └── version.txt       # Current installed version (e.g. "0.9.6")
├── lib/lhm_standalone/    # Standalone LibreHardwareMonitor.exe (cached, not installed) — launched hidden on startup to load PawnIO kernel driver for motherboard sensors
│   ├── LibreHardwareMonitor.exe
│   ├── LibreHardwareMonitor.exe.config  # Patched: wmiProvider=True
│   ├── LibreHardwareMonitorLib.dll
│   └── ... (28 more dependency DLLs + version.txt)
├── tools source/         # Standalone SA WinTools Professional PowerShell app (v20.10) — source of all Tools tab scripts
│   ├── SA_WinTools.ps1               # PowerShell GUI entry point (not run by this app — superseded by the Tools tab)
│   ├── SA_WinTools_Buttons.ps1       # All 20 button definitions + factory helpers (scripts ported into tools.py)
│   ├── SA_WinTools_Lib.ps1           # Shared backend library (dot-sourced by Install/Uninstall tool scripts at runtime)
│   ├── SA_Launcher.bat               # Standalone launcher (not used by SysDigger)
│   ├── aistart.bat                   # Standalone launcher (not used by SysDigger)
│   └── MicrosoftProgram_Install_and_Uninstall.meta.diagcab  # Microsoft troubleshooter (bundled for Install/Uninstall Fix tool)
├── roadmap.md            # Feature roadmap and version history
└── PROJECT_CONTEXT.md    # This file
```

---

## 4. Architecture (app.py)

The file is divided into clear sections, top to bottom:

### 4.1. Imports & DLL Loading (lines 1–70)
- Imports all Python modules
- Attempts to load `LibreHardwareMonitorLib.dll` via `pythonnet` (`clr` module)
- Registers a .NET `AssemblyResolve` handler so all DLLs in `lib/` are found automatically (handles transitive dependencies)
- Swaps in any pending `.new` DLL files (from the update feature) before loading
- Sets global flags: `_WMI_AVAILABLE`, `_LHM_AVAILABLE`

### 4.2. Helper Functions (lines 75–165)
- `_fmt_bytes()` — human-readable byte sizes (B/KB/MB/GB/TB)
- `_fmt_speed()` — link speed formatting (bps/Kbps/Mbps/Gbps)
- `_fmt_uptime()` — uptime as "Xd Xh Xm Xs"
- `_s()` — stringify WMI values, treating None/empty as "N/A"
- `_fmt_wmi_time()` — convert WMI datetime formats to readable strings
- `_reg_value()` — read a string from the Windows registry via `winreg`

### 4.3. Data Layer — `SystemData` + `Collector` (lines 186–760)

**`SystemData`** — a dataclass holding all collected info:
```python
os_info: dict[str, str]           # OS details
hw_info: dict[str, Any]           # CPU, RAM, motherboard, BIOS (incl. UEFI/Secure Boot), GPU, disks, battery, sensors
net_info: list[dict[str, Any]]    # Network adapters
ext_ip_info: dict[str, str]       # External IP + geo
ext_ip_error: str                 # Error message if IP lookup fails
ext_ip_time: str                  # Timestamp of last IP check
processes: list[dict]             # Running processes (PID, PPID, Name, CPU%, Memory, User)
startup_programs: list[dict]      # Startup programs (Name, Command, Source)
installed_programs: list[dict]     # Installed programs (Name, Version, Publisher, Date)
update_history: list[dict]         # Windows updates (KB, Description, Date, InstalledBy)
health_info: dict                  # SMART, Defender, Firewall, Activation status
speed_test_result: dict            # Download/upload speeds (Mbps), timestamp
bufferbloat_result: dict           # Bufferbloat grade (A-F)
devices_info: dict[str, Any]       # USB, Bluetooth, Printers, Audio devices
diagnostics_info: dict[str, Any]   # Event log (System+App), BSOD history, crash dumps, restore points, env vars, PATH, DirectX/D3D, power plan
gpu_details: list[dict[str, Any]]  # GPU vendor SDK metrics (NVML for NVIDIA)
vpn_status: dict[str, Any]         # VPN connection status + adapter list
services_info: list[dict]          # Windows services (Name, Display, State, Start Type, Log On As)
drivers_info: list[dict]           # Signed drivers (Name, Version, Date, Provider, Class)
restore_points: list[dict]         # System restore points (Time, Description, Sequence #)
environment_info: dict[str, str]   # Environment variables (System + User)
active_connections: list[dict]     # Live TCP/UDP connections (Protocol, Local, Remote, State, PID, Process)
wifi_info: dict[str, str]          # Wi-Fi adapter info (SSID, BSSID, Channel, Band, Signal, Standard, etc.)
dns_cache: list[dict]             # DNS resolver cache (Record Name, Type, TTL, Section, Address)
disk_benchmark: dict[str, Any]     # Last disk benchmark result (Drive, Size, Write/Read MB/s, Status)
startup_impact: dict[str, Any]    # Boot duration from Event log + startup programs correlation
```

**`Collector`** — gathers data via these methods:
| Method | Source | What it collects |
|---|---|---|
| `collect_os()` | WMI (`Win32_OperatingSystem`, `Win32_ComputerSystem`) + registry | OS name, version, build, architecture, domain, install/boot dates |
| `collect_hardware()` | WMI (`Win32_Processor`, `Win32_PhysicalMemory`, `Win32_BaseBoard`, `Win32_BIOS`, `Win32_VideoController`, `Win32_DiskDrive`) + psutil | CPU, RAM slots, motherboard, BIOS, GPU(s) with extended fields, disks, battery |
| `_collect_sensors()` | LibreHardwareMonitorLib via pythonnet | Temps, fans, power, clocks, voltages, loads — grouped by hardware component |
| `collect_network()` | psutil + WMI (`Win32_NetworkAdapterConfiguration`) | Adapter names, MAC, IPs, gateway, DNS, bytes, link speed |
| `collect_ext_ip()` | requests → ipify.org + ipinfo.io | Public IP + ISP/country/region/city/timezone (fire-and-forget, non-blocking) |
| `refresh_dynamic()` | psutil | Live CPU%, per-core%, RAM usage, disk free, uptime, network bytes |
| `collect_processes()` | psutil (two-pass `cpu_percent`) | Top 200 processes by CPU%, with PID/PPID/Name/CPU%/Memory/User |
| `collect_software()` | Registry (`Run` keys, `Uninstall` keys) + Startup folders | Startup programs + installed programs with versions/publishers |
| `collect_services()` | WMI (`Win32_Service`) | All Windows services (Name, Display, State, Start Type, Log On As) |
| `collect_updates()` | WMI (`Win32_QuickFixEngineering`) | Windows Update hotfixes (KB number, date, installed by) |
| `collect_health()` | WMI (`Win32_DiskDrive` status, `root/Microsoft/Windows/Defender`) + COM (`HNetCfg.FwPolicy2`) + `SoftwareLicensingProduct` | Disk SMART, Defender, Firewall, Windows Activation |
| `run_speed_test()` | requests → Cloudflare (99MB download / 50MB upload) | Download/upload speed (Mbps) |
| `run_bufferbloat_test()` | ping + Cloudflare load | Bufferbloat grade (A-F) |
| `collect_gpu_details()` | ctypes NVML (`nvml.dll`) for NVIDIA; WMI fallback for AMD/Intel | GPU temp, utilization, VRAM used/free, power, fan, clocks, driver version |
| `collect_devices()` | WMI (`Win32_PnPEntity`, `Win32_Printer`, `Win32_SoundDevice`) | USB devices (VID/PID), Bluetooth, printers, audio devices (cached) |
| `collect_drivers()` | WMI (`Win32_PnPSignedDriver`) | Signed drivers (Name, Version, Date, Provider, Class) |
| `collect_diagnostics()` | `win32evtlog` + ctypes `PowerGetActiveScheme` + `D3D11CreateDevice` + registry | Event log (System+App 200 each), BSOD history, crash dumps, restore points, env vars, PATH, DirectX/D3D feature levels, power plan |
| `collect_vpn_status()` | WMI `Win32_NetworkAdapter` keyword matching + psutil | VPN adapter detection (TAP, TUN, WireGuard, etc.), active status |
| `collect_active_connections()` | psutil `net_connections(kind="inet")` | Live TCP/UDP connections (Protocol, Local, Remote, State, PID, Process) |
| `collect_wifi_info()` | `netsh wlan show interfaces` | SSID, BSSID, Channel, Band, Signal %, Standard, Auth, Cipher, Rates |
| `collect_dns_cache()` | `ipconfig /displaydns` | DNS resolver cache (Record Name, Type, TTL, Section, Address) |
| `run_disk_benchmark()` | File I/O with `time.perf_counter()` | Sequential read/write speed (MB/s) for selected drive |
| `collect_startup_impact()` | `win32evtlog` (Event ID 12/13) | Boot duration history + startup programs correlation |
| `_collect_uefi_info()` | ctypes `GetFirmwareType` + registry | Firmware type (UEFI/Legacy), Secure Boot, Core Isolation (HVCI), TPM |

### 4.4. Sensor Collection Details

`_collect_sensors()` creates a `Computer` object from LibreHardwareMonitorLib,
enables all hardware groups, opens it, then iterates through hardware and
sub-hardware reading all sensors. Each sensor entry stores:
```python
{
    "Name": "GPU Core",        # sensor name
    "Value": 45.0,             # numeric value
    "Source": "AMD Radeon RX 7600",  # hardware name
    "Type": "Temperature",     # sensor type
    "Category": "GPU",         # display category (CPU/GPU/SSD/etc.)
}
```

`_hw_type_to_category()` maps LibreHardwareMonitor's `HardwareType` enum to
display categories: CPU, GPU, Motherboard, SSD, Hard Disk, Memory, Network,
Battery, PSU, Controller.

If LibreHardwareMonitorLib is unavailable, falls back to WMI
(`MSAcpi_ThermalZoneTemperature`, `Win32_TemperatureProbe`, `Win32_Fan`)
which usually returns nothing on modern hardware.

### 4.5. Library Updater — `LibraryUpdater` (lines 930–1140)

Downloads the latest LibreHardwareMonitorLib from **GitHub releases** (not
NuGet — the release ZIP is self-contained with all dependencies).

**Update flow:**
1. Check current version from `lib/version.txt`
2. Query GitHub API for latest release tag
3. If versions match → "Already up to date"
4. Download `LibreHardwareMonitor.zip` with live progress %
5. Extract the 12 needed DLLs from the ZIP
6. Write them as `.new` files (DLLs are locked while running)
7. On next app restart, `.new` files are swapped in before loading

Uses Qt signals (`_UpdateSignals`) for cross-thread communication:
`status(message, kind)` and `finished(success, message)`.

### 4.6. GUI — `InfoWindow`

**Layout:**
- Left **sidebar** (210px): app title, 13 nav buttons (OS, Hardware, Sensors, Network, External IP, Processes, Software, Updates, Health, Speed Test, Devices, Diagnostics, Tools), hostname, Update Libraries button + status label
- Right **content area**: page title + search box on top, stacked pages below

**13 pages** (indices 0–12) + 1 search results page (index 13):

| Idx | Nav Label | Page Title | Content |
|---|---|---|---|
| 0 | OS | Operating System | Single card with all OS info |
| 1 | Hardware | Hardware | Sub-tabs: CPU (card + sparkline graphs: CPU Usage % + CPU Temp °C), Memory (card + sparkline graphs: RAM Usage % + GPU Temp °C), Motherboard, BIOS (incl. UEFI/Secure Boot/TPM), GPUs, Disks (cards + disk benchmark button with drive/size pickers), Battery |
| 2 | Sensors | Sensors | Cards grouped by component: CPU, GPU, Motherboard, SSD, Memory, etc. Each card has sub-sections [Temperature], [Fan], [Power], [Clock], [Voltage], [Load] |
| 3 | Network | Network | Sub-tabs: Adapters (cards + VPN status), Active Connections (live TCP/UDP table, auto-refresh 5s), Wi-Fi (signal/SSID/channel/band), DNS Cache (hostname→IP table) |
| 4 | External IP | External IP | Single card with IP + geo info (fire-and-forget — renders placeholder, updates when network call completes) |
| 5 | Processes | Processes | Sub-tabs: List View (QTableWidget, top 200 by CPU%) + Tree View (QTreeWidget parent-child via psutil ppid()); columns: PID/Name/CPU%/Memory/Disk KB/s/Network conn count; smart colorization (red=critical, orange=high); auto-refreshes every 5s |
| 6 | Software | Software | Sub-tabs: Startup Programs, Installed Programs (sortable tables), Windows Services (state color-coded), Startup Impact (boot duration from Event log + boot history table + top startup programs) |
| 7 | Updates | Windows Updates | QTableWidget (KB, Description, Installed On, Installed By) |
| 8 | Health | System Health | Cards: Disk SMART, Windows Defender, Firewall, Windows Activation |
| 9 | Speed Test | Network Speed Test | Download/upload via Cloudflare (99MB/50MB), bufferbloat grade (A-F) |
| 10 | Devices | Connected Devices | Sub-tabs: USB, Bluetooth, Printers, Audio, Drivers |
| 11 | Diagnostics | System Diagnostics | Sub-tabs: System Events, Application Events (200 each, color-coded), BSOD/Crash History, Crash Dump Settings, Restore Points, Environment Variables, PATH Entries, Graphics API (DirectX/D3D feature levels via ctypes) |
| 12 | Tools | Windows Tools | Category sidebar + search filter + flow-layout tool card grid (fixed-width cards showing name/desc/mode badge) + collapsible log panel with live-streamed PowerShell output, bottom controls (Open Log / Clear / Stop / Reboot) |
| 13 | (search) | Search Results | Dynamic — filtered cards from all pages |

**Key UI patterns:**
- `_make_card(parent_layout, title, rows, page_idx, value_labels=None, bar_labels=None)` — creates a rounded card with a blue header and key/value rows. Also indexes rows into `_search_items` (only when `page_idx >= 0`). `value_labels`/`bar_labels` capture QLabels for live 2s sensor refresh (CPU/RAM usage + progress bars)
- `_search_items` — flat list of `{page, section, key, value}` dicts
- **Search**: tokenizes query into words (2+ chars), skips overly-common tokens (>25% of items matched) when other tokens exist, caps at 200 results, OR-matching across section/key/value
- **Esc key** clears search
- Dark title bar via DWM API (`DwmSetWindowAttribute`)
- `_SelBlackItem(QTableWidgetItem)` — custom table item that shows black foreground when selected (for color-coded cells like State/Status/Level that use `setForeground()`)
- `_setup_table_copy(table)` — wires Ctrl+C + right-click context menu (Copy row / Copy N rows / Copy all rows) on any QTableWidget; output is tab-separated with header row
- `_Sparkline(QWidget)` — mini sparkline graph with QPainter (filled polygon + polyline + min/max/current label); 60-sample rolling window; used for CPU/RAM usage + CPU/GPU temp graphs
- **Tab persistence**: any page with a QTabWidget that gets rebuilt on auto-refresh preserves selected sub-tab index + scroll position across rebuilds (applied to Network + Processes pages)
- **Lazy page rendering**: `_pages_ready` set tracks which pages have data; only the current page renders immediately, others render on-demand via `_render_page()` when the user navigates — saves ~500ms+ UI setup during startup
- All text is selectable for copying

### 4.7. Tools Page (Windows Tools)

The Tools page (index 12) surfaces every feature from the standalone
**SA WinTools Professional** PowerShell suite that lives in `tools source/`.
Rather than re-implementing ~2000 lines of tested logic in Python, the app
reuses the verbatim PowerShell scripts and runs them as hidden-window
subprocesses with stdout streamed live into a Qt log panel.

**Tool catalogue (`tools.py`):**
- 4 categories, 28 tools, 61 modes total
- Each mode carries: `label`, `script` (PowerShell body), and optional
  flags: `confirm` (destructive — show Yes/No dialog first), `reboot`
  (show "reboot required" notice after), `input` (collect user input
  before running)
- `input` types: `"text"` (free-form, e.g. product key / Wi-Fi profile),
  `"drive"` (pick a mounted drive letter), `"hdd_check"` (drive + chkdsk
  mode: read-only / `/f` / `/r` / `/scan`), `"path_select"` (two-phase
  scan-then-pick: a `scan_script` emits `__SCAN_BEGIN__`/`__SCAN_END__`
  with `size\tpath` rows; GUI shows a multi-select checkbox dialog with
  critical-path blocklist; selected paths are substituted into `__PATHS__`
  in the cleanup `script`. For Appx, scan emits `size\tid\tlabel` and
  `id_col=True` is set — `__PATHS__` then carries package FullNames)
- Substitution tokens (`__LIB__`, `__BACKUP__`, `__DRIVE__`, `__MODE__`,
  `__INPUT__`, `__PATHS__`) are replaced by `resolve_placeholders()`
  (lib/backup) and by the GUI (drive/mode/input/paths, after the user
  provides values) just before execution

**Execution flow:**
1. `_on_tool_clicked(category, tool_name, tool)` — single-mode tools run
   directly; multi-mode tools show a popup menu of modes at the button
2. `_run_tool_mode(category, tool_name, mode)` — collects input (if any),
   shows confirmation (if `confirm`), substitutes tokens, then calls
   `_run_powershell_tool(label, script, reboot)`
3. `_run_powershell_tool()` sets running state, clears the log, disables
   all tool buttons, and launches a background `_tool_worker` thread
4. `_tool_worker()` writes the script to a temp `.ps1` file (UTF-8 with
   BOM so PowerShell 5.1 reads box-drawing characters correctly), runs
   `powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File`
   with `CREATE_NO_WINDOW` (no console flash), and reads stdout
   line-by-line emitting `ToolSignals.output(line)` for each line while
   also writing to `%TEMP%\SA_WinTools_Active.log`
5. `_on_tool_output(line)` appends to the `QPlainTextEdit` log and scrolls
   to the bottom; `_on_tool_finished(rc)` re-enables buttons, shows
   `COMPLETED` / `TERMINATED`, and (if `reboot=True`) appends a
   "REBOOT REQUIRED" notice

**Bottom controls:**
- **Open Current Log** — opens `%TEMP%\SA_WinTools_Active.log` in Notepad
- **Clear** — stops any running tool, clears the log
- **Stop** — kills the running PowerShell process tree via
  `taskkill /F /T /PID <pid>`
- **Reboot** — `shutdown /r /f /t 0` after Yes/No confirmation

**Safety / lifecycle:**
- The Tools page is built once at startup (`_populate_tools()`) — it has
  no collection dependency. `_show_loading_placeholders()` and
  `_on_settings_clicked()` skip the Tools page so the live log is never
  wiped during refresh or settings changes
- `_tools_built` guard makes `_populate_tools()` idempotent
- `closeEvent()` terminates any running tool subprocess before the app
  exits

### 4.8. Styling (QSS)

Themes are built dynamically via `build_qss(theme)` which returns a QSS
stylesheet string and sets module-level color constants (`_BG`, `_ACCENT`,
etc.) used by sensor highlighting and other code.

**Dark theme** (default):
- Background: `#1c1c1c`, Sidebar: `#252525`, Cards: `#2d2d2d`
- Accent (blue): `#60cdff`
- Text: primary `#ffffff`, secondary `#9a9a9a`, dim `#6a6a6a`
- Error: `#e07b7b`

**Light theme:**
- Background: `#f5f5f5`, Sidebar: `#e8e8e8`, Cards: `#ffffff`
- Accent (blue): `#0078d4`
- Text: primary `#1a1a1a`, secondary `#666666`, dim `#999999`
- Error: `#c0392b`

**Theme modes:**
- `"dark"` — always dark
- `"light"` — always light
- `"system"` — auto-follows Windows via registry `AppsUseLightTheme` (0=dark, 1=light)

Quick toggle button in topbar switches between dark/light. DWM titlebar
follows the active theme via `set_dark_titlebar(force_dark=...)`.

**Compact view:** When enabled, rows use 12px text, tighter spacing, no
word wrap, and narrower key columns (170px vs 230px). Toggle button in
topbar.

**Progress bars:** When enabled, any value containing a percentage
(e.g. `45.2%` or `45.2% (8.5 GB / 16.0 GB)`) gets a mini inline bar
(8px tall, 120px wide) next to it, color-coded green/yellow/red.

**Font:** User can pick any system font via QFontDatabase dropdown in
Settings. Applied app-wide via `QApplication.setFont()`.

Font sizes: page title 24px, nav buttons 15px, card titles 14px, row text
14px (expanded) or 12px (compact).

---

## 5. Launcher (sysdigger.pyw)

- Runs via `pythonw.exe` — no console window
- **Self-elevates to admin** via `ShellExecuteW` with "runas" verb (UAC prompt)
  - Needed for LibreHardwareMonitorLib sensor access (CPU temps, fan RPM, motherboard SuperIO)
- Initializes the centralized logger (`app_logger.log_startup()`)
- Redirects `stderr` to the logger (no console under pythonw)
- On crash: logs full traceback + shows a Windows message box

---

## 5.1. Logging (app_logger.py)

All modules use `get_logger(__name__)` to obtain a named child logger that
writes to **`app.log`** next to the script directory.

**Features:**
- Rotating file handler (2 MB max, 3 backups)
- Format: `YYYY-MM-DD HH:MM:SS [LEVEL] module: message`
- Levels: DEBUG (default), INFO, WARNING, ERROR
- `log_startup()` — logs a startup banner with Python version
- `log_exception(logger, context, exc)` — convenience for logging exceptions with context

**What's logged:**
- Startup banner (Python version, log path)
- Collection milestones (`collect_os`, `collect_hardware`, `collect_network`, `collect_ext_ip`)
- Sensor refresh failures
- Dynamic refresh (CPU usage) failures
- Export/autopilot export failures
- Library update start/success/failure
- LHM DLL loading (success/failure, DLL swaps)
- Window settings load/save failures
- External IP lookup failures
- Collection thread errors (with full traceback via `exc_info=True`)
- All uncaught exceptions (via launcher's stderr redirect)
- WMI module availability warnings
- Tools page: tool worker failures (with full traceback), tool log open failures

**GUI access:** "Log" button in the topbar opens `app.log` in the default text editor.

---

## 5.2. Configuration (config.py)

All user-editable settings live in **`config.json`** next to the script.
The `Config` dataclass (singleton via `get_config()`) provides typed
access with defaults.

**Settings:**
| Key | Type | Default | Description |
|---|---|---|---|
| `sensor_refresh_interval_ms` | int | 2000 | Live sensor refresh period (500–60000 ms) |
| `process_refresh_interval_ms` | int | 5000 | Process & network page refresh period (1000–60000 ms) |
| `process_top_n` | int | 200 | Max processes to show in Processes page (10–500) |
| `theme` | str | "dark" | UI theme: "dark", "light", or "system" (auto-follow Windows via registry `AppsUseLightTheme`) |
| `font_family` | str | "" | Font family override (empty = system default; pick from QFontDatabase in Settings) |
| `compact_view` | bool | False | Compact row layout (12px text, tighter spacing, no word wrap) vs expanded (14px, word-wrapped) |
| `show_progress_bars` | bool | True | Show inline mini progress bars next to percentage values (CPU/RAM/disk/battery/load) |
| `enabled_sensor_types` | list[str] | all 12 | Which LHM sensor types to collect/display |
| `enabled_hardware_types` | dict[str,bool] | all True except Network | Which LHM hardware groups to enable (CPU, GPU, Motherboard, etc.) |
| `window_geometry` | str | "" | base64-encoded `saveGeometry()` (replaces old settings.json) |
| `cache_ttl_seconds` | int | 3600 | Static hardware cache time-to-live (60–86400 s) |
| `sparkline_max_samples` | int | 60 | Rolling window size for sparkline graphs (10–300) |
| `speed_test_download_mb` | int | 99 | Cloudflare speed test download size (1–500 MB, keep <100 to avoid 403) |
| `speed_test_upload_mb` | int | 50 | Cloudflare speed test upload size (1–500 MB) |
| `speed_test_timeout_s` | int | 120 | Speed test request timeout (10–600 s) |

**API:**
- `get_config()` — returns the singleton `Config` (lazy-loaded)
- `reload_config()` — force-reload from disk (after Settings dialog saves)
- `Config.save()` — write to `config.json`
- `Config.is_hardware_type_enabled(hw_type)` — check if a hardware group is enabled
- `Config.is_sensor_type_enabled(stype)` — check if a sensor type is enabled
- `Config.get_lhm_computer_settings()` — returns dict of `IsXxxEnabled` → bool for LHM

**GUI access:** "Settings" button in the topbar opens a sidebar-style
modal dialog with 5 sections (General, Refresh, Processes, Sensors,
Speed Test). The left sidebar has clickable nav items; the right shows
the selected section's options in a scrollable area. Changes are saved
immediately, both sensor and process timers restart with new intervals,
the QSS is rebuilt for the new theme, and all pages are re-rendered.

---

## 5.3. Error Boundaries

Both collectors and the GUI use per-section error boundaries so a failure
in one component doesn't break the others.

**Collectors (`collectors.py`):**
- `collect_hardware()` splits static collection into `_collect_hardware_static()`
  where each section (CPU, RAM, Motherboard, BIOS, GPU, Disks) is wrapped
  in its own try/except. A failure logs the error and leaves that section
  with safe defaults (e.g. `{"Name": "N/A", ...}`) while the other
  sections still populate normally.
- `collect_os()` — each WMI query (Win32_OperatingSystem, Win32_ComputerSystem)
  has its own try/except that logs failures.
- `collect_network()` — top-level try/except wraps the psutil + WMI
  collection so a psutil failure doesn't crash the thread.
- `_collect_sensors()` — wrapped at the `collect_hardware()` level so a
  sensor error leaves an empty-but-valid sensors dict.
- `refresh_dynamic()` — each psutil call (CPU, RAM, disk, uptime, network)
  has its own try/except (already existed, now logs failures).

**GUI (`gui.py`):**
- `_on_page_ready(page_idx)` — wraps each page render in try/except. On
  failure, calls `_render_page_error()` which shows an error card with
  the exception message and a hint to check `app.log`. Other pages
  remain unaffected.
- `_collect_worker()` / `_run()` — collection thread errors are caught
  per-thread and logged (already existed).
- `_sensor_refresh_worker()` — sensor refresh errors logged (already existed).

---

## 6. Key Design Decisions

1. **No PowerShell for data collection** — all WMI queries in `collectors.py` use the `wmi` Python library (COM-based) and `winreg` for registry. Zero subprocess spawning, no console window flashes. This also makes data collection ~2x faster. (Note: the Tools tab is a separate concern — see decision 9.)

2. **GitHub releases over NuGet** — the updater downloads from GitHub because the release ZIP bundles all .NET dependencies. The NuGet package has transitive dependencies that don't resolve when loading DLLs directly via pythonnet.

3. **`.new` file swap pattern** — DLLs can't be replaced while the app is running (file locks). Updates write `.new` files, and the swap happens on next startup before loading.

4. **AssemblyResolve handler** — registers a .NET event handler so the CLR automatically finds any DLL in `lib/` when resolving transitive dependencies.

5. **Admin elevation** — required for hardware sensor access (AMD SMU, motherboard SuperIO). The launcher handles this transparently via UAC.

6. **Search safety** — caps at 200 rendered results, skips stop-word tokens, prevents UI widget overload crashes.

7. **Centralized config** — all user preferences (15 settings: refresh intervals, process top N, theme, font, compact/progress, sensor/hardware types, sparkline samples, speed test params, cache TTL, window geometry) live in a single `config.json` loaded via a singleton `Config` dataclass. The old `settings.json` (window geometry only) is deprecated and superseded.

8. **Per-section error boundaries** — collectors wrap each hardware section (CPU, RAM, motherboard, BIOS, GPU, disks) in its own try/except so one failure doesn't break the others. The GUI wraps each page render so a failing page shows an error card while the rest of the UI stays functional.

9. **PowerShell for maintenance tools** (Tools tab only) — the maintenance tools inherently wrap command-line utilities that have no Python equivalent (`sfc`, `dism`, `chkdsk`, `Optimize-Volume`, `Get-PnpDevice`, `Get-WinEvent`, `Clear-RecycleBin`, `reagentc`, `slmgr.vbs`, `w32tm`, `powercfg`, `netsh`...). The Tools tab reuses the verbatim, tested PowerShell scripts from `tools source/` and runs them as hidden-window subprocesses with live stdout streaming. This is scoped strictly to the Tools page; the rest of the app remains PowerShell-free (see decision 1). The system-wide "no PowerShell" rule applies only to the **system data collection** path (`collectors.py`). Note: `netsh wlan` and `ipconfig /displaydns` are used in collectors.py for Wi-Fi info and DNS cache — these are Windows builtins with no Python/WMI equivalent, not PowerShell cmdlets.

10. **4-way parallel collection + lazy rendering** — data collection runs in 4 parallel threads (os_hw, net_sw, health_dev, proc) instead of 3+sequential. Process collection (3.6s) was the post-thread bottleneck; it now runs parallel since it only needs psutil. External IP is fire-and-forget (page renders with placeholder, updates when network call completes). Page rendering is lazy — only the current page renders immediately, others render on-demand when the user navigates. Cold start ~15s→~4s (3.8x), warm start ~4.6s→~3.4s (1.4x).

11. **Tab persistence on auto-refresh** — any page with a QTabWidget that gets rebuilt on auto-refresh (Network every 5s, Processes every 5s) preserves the selected sub-tab index and scroll position across rebuilds via `_clear_layout()` → save `currentIndex()` + `verticalScrollBar().value()` → rebuild → restore via `QTimer.singleShot(0, ...)`.

---

## 7. How to Run

### First-time setup
```bat
install_deps.bat
```

### Launch the app
Double-click `sysdigger.pyw` (or run `pythonw sysdigger.pyw`).

A UAC prompt will appear (admin needed for sensor data).

### Update sensor libraries
Click "Update Libraries" in the sidebar. After update completes, restart the app.

---

## 8. Environment

- **OS**: Windows 10/11 (x64)
- **Python**: 3.12+
- **Target hardware tested**: AMD Ryzen 7 5700X, AMD Radeon RX 7600, MSI B550 GAMING PLUS, 32GB RAM, 6 disks
