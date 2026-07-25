# SysPeek

Windows system information and diagnostics viewer with a Fluent-style GUI.

![SysPeek](app_preview.png)

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
- **Tools** — 26 integrated maintenance utilities (disk cleanup, SFC/DISM, disk analyzer with scan-then-pick cleanup, Appx manager, dev cache cleaner, hibernate manager, hosts editor, memory diagnostic, Windows Update trigger, Autopilot hash export, and more)

## Requirements

- Windows 10/11 (64-bit)
- Administrator privileges (required for sensor access — UAC prompt on launch)
- .NET Framework 4.x (pre-installed on Windows 10/11)

## Download

Download the latest release from the [Releases page](../../releases).

Extract the zip and run `SysPeek.exe`. Windows will show a UAC prompt — click Yes to allow sensor access.

## Run from source

```pwsh
# Install dependencies
python -m pip install -r requirements.txt

# Launch
pythonw syspeek.pyw
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
- **Portability**: All writes go to the app directory (config, logs, cache). When built as exe and installed to a read-only location, falls back to `%LOCALAPPDATA%\SysPeek\`.

## Project structure

| File | Role |
|---|---|
| `syspeek.pyw` | Entry point — UAC elevation, crash handler |
| `app.py` | QApplication setup, theme, LHM bridge launch |
| `gui.py` | Main GUI — 13 pages, cards, tables, sparklines, tools, settings |
| `collectors.py` | All data collection (OS, HW, net, SW, health, diagnostics, processes) |
| `sensors.py` | LibreHardwareMonitorLib .NET assembly loading |
| `lhm_process.py` | Portable LHM.exe process manager (kernel driver for motherboard sensors) |
| `tools.py` | 26 maintenance tools (4 categories, 57 PowerShell modes) |
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

## Code signing policy

Free code signing provided by [SignPath.io](https://about.signpath.io), certificate by [SignPath Foundation](https://signpath.org)

- **Committers and reviewers**: [Contributors](../../graphs/contributors)
- **Approvers**: [Owner](https://github.com/StavrosAntoniou)

### Privacy policy

This program will not transfer any information to other networked systems unless specifically requested by the user or the person installing or operating it.

## License

MIT License — see [LICENSE](LICENSE)
