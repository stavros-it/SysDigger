# SysDigger

[![CI](https://github.com/stavros-it/SysDigger/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/stavros-it/SysDigger/actions/workflows/ci.yml)
[![Build and Sign](https://github.com/stavros-it/SysDigger/actions/workflows/build-and-sign.yml/badge.svg)](https://github.com/stavros-it/SysDigger/actions/workflows/build-and-sign.yml)
[![Release](https://img.shields.io/github/v/release/stavros-it/SysDigger?include_prereleases)](https://github.com/stavros-it/SysDigger/releases)
[![Downloads](https://img.shields.io/github/downloads/stavros-it/SysDigger/total)](https://github.com/stavros-it/SysDigger/releases)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-0078D6)](https://github.com/stavros-it/SysDigger)
[![License](https://img.shields.io/badge/license-Proprietary-red)](LICENSE)
[![Last commit](https://img.shields.io/github/last-commit/stavros-it/SysDigger)](https://github.com/stavros-it/SysDigger/commits/main)

Windows system information and diagnostics viewer with a Fluent-style GUI. SysDigger
surfaces everything from CPU/GPU sensors and live network connections to BSOD history
and 29 integrated maintenance tools — all in a single dark-themed PySide6 window with
live search, copy-to-clipboard, and JSON/Text/HTML export.

<p align="center">
  <img src="app_preview.png" alt="SysDigger" width="500">
</p>

## Features

- **Hardware** — CPU, GPU, memory, motherboard, BIOS, disks, battery with live sensor refresh (temperatures, fan speeds, voltages) and sparkline graphs
- **Sensors** — per-component sensor breakdown (CPU, GPU, motherboard, storage) with temperature sparklines
- **Operating System** — edition, build, uptime, activation status, UEFI/Secure Boot/TPM
- **Network** — adapters, active TCP/UDP connections (live), Wi-Fi signal, DNS cache, external IP, speed test, bufferbloat grade
- **Software** — installed programs, services, startup items with boot impact analysis, Windows updates
- **Processes** — sortable list view + parent-child tree view, top 200 by CPU usage, disk I/O per process
- **Devices** — USB, Bluetooth, printers, audio devices
- **Health** — Windows Defender, activation, battery wear, restore points
- **Diagnostics** — event logs, BSOD history, crash dumps, DirectX/D3D feature levels, environment variables, PATH entries
- **Tools** — 29 integrated maintenance utilities (disk cleanup, SFC/DISM, disk analyzer with scan-then-pick cleanup, Appx manager, dev cache cleaner, hibernate manager, hosts editor, memory diagnostic, Windows Update trigger, UEFI BIOS reboot, Autopilot hash export, MTP/Android USB repair, SATA/AHCI controller reset, disk status/online, disk rescue for failing disks, and more)

### Disk Rescue — recover files from a failing disk

A dedicated recovery tool for hard drives that are starting to fail, where a normal
copy stalls for hours retrying a handful of unreadable sectors:

- **Read-only scan** — maps the physical disk with watchdog-protected raw probes
  (each probe is cancelled after a timeout instead of hanging forever), refining
  around damaged regions with adjustable step numbers (probe size, refine floor,
  timeout). Builds a resumable GOOD/BAD map with checkpoints — stopping mid-scan
  is safe.
- **Bad-aware copy** — copies every file off the disk, skipping known-damaged
  regions (zero-filled) and reading everything else through the same watchdog, so
  one bad sector can no longer freeze the whole recovery. Files are ordered by
  physical location to minimise head movement on mechanical drives.
- **Reports** — ASCII disk map, per-file copy report, and a lost-files list;
  damage discovered during copying is written back to the map.
- **Safety guards** — refuses to write the map or copy to the same physical disk
  it is rescuing from; the scan never writes to the source disk at all.

## Requirements

- Windows 10/11 (64-bit)
- Administrator privileges (required for sensor access — UAC prompt on launch)
- .NET Framework 4.x (pre-installed on Windows 10/11)

## Launch modes

On startup, SysDigger shows a launch mode picker:

- **Normal Mode** — full app. Loads LibreHardwareMonitorLib + PawnIO kernel driver for live CPU/GPU/motherboard sensors (temperatures, fan speeds, voltages, clocks). All 14 pages fully functional. Startup takes ~3-6 seconds longer for driver install.
- **Fast Mode** — skips LHM / pythonnet / .NET / PawnIO entirely. All pages work except Hardware/Sensors (show WMI fallback or "N/A"). OS, Network, Processes, Software, Devices, Diagnostics, Tools — all fully functional. Saves ~3-6 seconds on startup.

The menu appears on every launch. Pick Fast Mode when you just need to run maintenance tools or check system info without waiting for the sensor stack to load.

## Download

Download the latest release from the [Releases page](../../releases).

Extract the zip and run `SysDigger.exe`. Windows will show a UAC prompt — click Yes to allow sensor access.

## Run from source

```pwsh
# Install dependencies
python -m pip install -r requirements.txt

# Launch
pythonw sysdigger.pyw
```

Requires Python 3.12+.

## Build

To build a standalone exe:

```pwsh
.\build.ps1
```

See [BUILD_GUIDE.md](BUILD_GUIDE.md) for detailed build and code signing instructions.

## How it works

- **GUI**: PySide6 (Qt for Python) with a custom Fluent-style dark/light theme
- **Sensors**: LibreHardwareMonitorLib via pythonnet for CPU/GPU/motherboard sensors. A portable `LibreHardwareMonitor.exe` is launched hidden on startup to load the PawnIO kernel driver for motherboard SuperIO sensors (fan RPM, voltages, VRM temps). The driver is cleaned up on exit — nothing is permanently installed.
- **Data collection**: WMI, winreg, psutil, ctypes — no PowerShell in the data layer (only in the Tools tab)
- **Portability**: All writes go to the app directory (config, logs, cache). When built as exe and installed to a read-only location, falls back to `%LOCALAPPDATA%\SysDigger\`.

## Project structure

| File | Role |
|---|---|
| `sysdigger.pyw` | Entry point — UAC elevation, crash handler |
| `app.py` | QApplication setup, theme, launch menu, LHM bridge launch |
| `launch_menu.py` | Launch mode picker — Normal (full sensors) vs Fast (skip .NET/PawnIO, ~3-6s faster) |
| `gui.py` | Main GUI — 13 pages, cards, tables, sparklines, tools, settings |
| `collectors.py` | All data collection (OS, HW, net, SW, health, diagnostics, processes) |
| `sensors.py` | LibreHardwareMonitorLib .NET assembly loading (skipped in Fast Mode) |
| `lhm_process.py` | Portable PawnIO installer (kernel driver for motherboard sensors) |
| `tools.py` | 29 maintenance tools (4 categories, 67 PowerShell modes) |
| `tools source/DiskRescueLib.ps1` | Disk Rescue engine — original failing-disk mapper + bad-aware copier (see Acknowledgements) |
| `config.py` | Config dataclass + JSON persistence |
| `paths.py` | Portable path resolution for frozen exe |
| `helpers.py` | Formatting utilities (bytes, speed, uptime) |
| `updater.py` | GitHub release updater for LHM DLLs |
| `app_logger.py` | Rotating file logger |

## Documentation

- [BUILD_GUIDE.md](BUILD_GUIDE.md) — How to build and sign the exe
- [GITHUB_SIGNING_GUIDE.md](GITHUB_SIGNING_GUIDE.md) — How to set up GitHub + free SignPath signing
- [roadmap.md](roadmap.md) — Version history and planned features
- [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) — Architecture overview
- [THIRD-PARTY-NOTICES](THIRD-PARTY-NOTICES) — Third-party component licenses and attributions

## Code signing policy

Free code signing provided by [SignPath.io](https://about.signpath.io), certificate by [SignPath Foundation](https://signpath.org)

- **Committers and reviewers**: [Contributors](../../graphs/contributors)
- **Approvers**: [Owner](https://github.com/StavrosAntoniou)

### Privacy policy

This program will not transfer any information to other networked systems unless specifically requested by the user or the person installing or operating it.

## Third-party components

SysDigger bundles or uses the following third-party components:

- **[LibreHardwareMonitorLib](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor)** (MPL-2.0) — hardware sensor readings (CPU/GPU/motherboard temps, fan speeds, voltages)
- **[PawnIO](https://github.com/namazso/PawnIO)** kernel driver (GPL-2.0+ with DeviceIoControl exception) — required for motherboard SuperIO and AMD CPU MSR sensor access. The driver is NOT bundled with SysDigger; the official `PawnIO_setup.exe` installer is downloaded from the [PawnIO GitHub releases](https://github.com/namazso/PawnIO.Setup/releases) on first launch and uninstalled on exit. SysDigger communicates with the driver exclusively via DeviceIoControl IOCTLs (through LibreHardwareMonitorLib), so the GPL exception applies — SysDigger's proprietary code does not become GPL.
- **[Aga.Controls](https://github.com/libertyvnc/Aga.Controls)** (BSD) — tree-view UI control (bundled with LibreHardwareMonitorLib)
- Python packages: [PySide6](https://www.qt.io) (LGPL-3.0+), [psutil](https://github.com/giampaolo/psutil) (BSD-3-Clause), [requests](https://github.com/psf/requests) (Apache-2.0), [pythonnet](https://github.com/pythonnet/pythonnet) (MIT), [wmi](https://github.com/tjguk/wmi) (MIT), [pywin32](https://github.com/mhammond/pywin32) (MIT-0)

Full license texts and attribution notices: see [THIRD-PARTY-NOTICES](THIRD-PARTY-NOTICES).

## Acknowledgements

- The **Disk Rescue** engine (`tools source/DiskRescueLib.ps1`) was inspired by the
  [AdaptiveDisk](https://github.com/orloxgr/AdaptiveDisk) project's GOOD-first
  recovery approach — map readable regions first, skip damaged areas instead of
  fighting them, and learn from failures during real copying. The engine itself is
  **an original proprietary implementation** (© Stavros Antoniou): all C# and
  PowerShell code was written from scratch for SysDigger and contains no code from
  AdaptiveDisk, which is GPL-3.0 licensed. Only the concept was taken as inspiration.

## License

Proprietary — Copyright (c) 2026 Stavros Antoniou. All rights reserved. See [LICENSE](LICENSE) for details.
