# AGENTS.md — SysDigger Agent Memory

> Operational memory for AI agents working on this codebase.
> Read this before making changes. Update after non-trivial work.
> For feature history see `roadmap.md`. For architecture see `PROJECT_CONTEXT.md`.

---

## Quick Reference

- **App name:** SysDigger (renamed from "SysPeek" in v4.16, originally "Windows Info" in v4.5)
- **Version:** 4.19
- **Entry point:** `sysdigger.pyw` (renamed from `launcher.pyw`)
- **AppUserModelID:** `"Stavros.SysDigger"`
- **Window title:** `"SysDigger  ·  Copyright (C) Stavros Antoniou"`
- **Copyright:** Copyright (C) Stavros Antoniou

## Verification Commands

```pwsh
# Compile-check (run after every code change)
python -m py_compile app.py gui.py collectors.py sysdigger.pyw tools.py sensors.py helpers.py config.py lhm_process.py paths.py launch_menu.py

# Test a collector method
python -c "from collectors import Collector; c = Collector(); c._init_wmi(); c.collect_hardware(); print(c.data.hw_info['gpus'])"

# Check cache contents
python -c "import json; d = json.load(open('cache/diagnostics_static.json')); print(list(d['value'].keys()))"

# Clear all caches (forces fresh collection)
Remove-Item cache\*.json
```

## Critical Patterns (easy to forget)

### 1. Table sorting — enable AFTER population
`setSortingEnabled(True)` must be called **after** all `setItem()` calls, never before. If enabled before, Qt re-sorts rows during insertion and column data gets misaligned (only the first-populated column shows data). This bug affected Software, Services, and Updates tables.

### 2. `_SelBlackItem` for color-coded table cells
When a `QTableWidgetItem` gets `setForeground(QColor(...))`, that QBrush overrides the QSS `::item:selected { color: #000000 }` rule — so colored cells keep their color when the row is selected instead of going black. Use `_SelBlackItem` (subclass in gui.py) instead of `QTableWidgetItem` for any cell that gets `setForeground()`. It overrides `data(ForegroundRole)` to return black when `isSelected()`.

### 3. `_setup_table_copy()` for clipboard support
Call `self._setup_table_copy(table_widget)` right before `addWidget(table)`. Wires Ctrl+C shortcut + right-click context menu (Copy row / Copy N rows / Copy all rows). Output is tab-separated with header row.

### 4. Tab + scroll persistence on auto-refresh pages (ALWAYS APPLY)
**CRITICAL**: Any page with a `QTabWidget` OR any `QTableWidget`/`QTreeWidget` that gets rebuilt on auto-refresh (every 2s or 5s) MUST preserve the selected sub-tab index AND scroll position across rebuilds. Without this, the page jumps back to the first tab and resets scroll to top on each refresh. This applies to Network (5s), Processes (5s), and ANY future page with auto-refresh + tables/trees.

Apply this pattern in the populate method BEFORE `_clear_layout()`:

```python
prev_tab = -1
prev_scroll = 0
for i in range(layout.count()):
    w = layout.itemAt(i).widget()
    if isinstance(w, QTabWidget):
        prev_tab = w.currentIndex()
        # Find QTableWidget/QTreeWidget in the current tab for scroll preservation
        tab_content = w.widget(prev_tab)
        if isinstance(tab_content, QScrollArea):
            inner = tab_content.widget()
            if inner and inner.layout():
                for j in range(inner.layout().count()):
                    child = inner.layout().itemAt(j).widget()
                    if isinstance(child, (QTableWidget, QTreeWidget)):
                        prev_scroll = child.verticalScrollBar().value()
                        break
        elif tab_content and tab_content.layout():
            # Direct layout (no QScrollArea wrapper, e.g. Processes page)
            for j in range(tab_content.layout().count()):
                child = tab_content.layout().itemAt(j).widget()
                if isinstance(child, (QTableWidget, QTreeWidget)):
                    prev_scroll = child.verticalScrollBar().value()
                    break
        break
self._clear_layout(layout)
# ... rebuild tabs ...
if prev_tab >= 0:
    tabs.setCurrentIndex(min(prev_tab, tabs.count() - 1))
layout.addWidget(tabs)
if prev_scroll > 0:
    from PySide6.QtCore import QTimer
    def _restore_scroll():
        idx = tabs.currentIndex()
        if idx < 0: return
        tab_content = tabs.widget(idx)
        if not (tab_content and tab_content.layout()): return
        for j in range(tab_content.layout().count()):
            child = tab_content.layout().itemAt(j).widget()
            if isinstance(child, (QTableWidget, QTreeWidget)):
                child.verticalScrollBar().setValue(prev_scroll)
                break
    QTimer.singleShot(0, _restore_scroll)
```

For pages WITHOUT sub-tabs (single QTableWidget/QTreeWidget on the page that gets rebuilt on auto-refresh), save `table.verticalScrollBar().value()` before `_clear_layout()` and restore after `addWidget(table)` via `QTimer.singleShot(0, ...)`.

Currently applied to: Network page (`_populate_network` — QScrollArea wrapper), Processes page (`_populate_processes` — direct layout, both QTableWidget + QTreeWidget). **Apply to any new page with auto-refresh + tables/trees.**

### 5. Per-thread progress bar
Progress is tracked per collection thread via `self._thread_progress` dict with keys: `"os_hw"` (3 steps), `"net_sw"` (4), `"health_dev"` (4), `"post"` (2) = 13 total. `CollectSignals.step` is `Signal(str, str, int, int)` = (label, thread_key, completed, total). Bar turns green at 100%.

### 6. QSS table selection ordering
In `build_qss()`, the order matters:
```css
QTableWidget::item { ... }
QTableWidget::item:alternate { ... }       /* BEFORE selected */
QTableWidget::item:selected,
QTableWidget::item:alternate:selected { ... } /* wins */
```
If `:alternate` comes after `:selected`, alternating rows lose the blue selected background.

### 7. `_make_card()` params
`_make_card(layout, title, rows, page_idx, value_labels=None, bar_labels=None)`:
- `value_labels`: dict of key → QLabel, captured for live refresh (CPU/RAM)
- `bar_labels`: dict of key → QLabel, captured for ASCII progress bar live refresh
- `page_idx = -1` disables search indexing (for non-data cards)

### 8. Live hardware refresh
`refresh_sensors()` runs every 2s (configurable). Updates:
- CPU: Usage, Per-core, Current Freq via LHM sensors (psutil `cpu_freq()` fallback for AMD)
- RAM: Used, Available, Usage% via psutil `virtual_memory()`
- Sparklines: CPU Usage, CPU Temp, RAM Usage, GPU Temp (Hardware page), GPU Util, GPU Temp (GPU tab), Disk Read/Write, Network Up/Down, Battery %, and per-sensor Temperature graphs (Sensors page)
Pushes values into captured `value_labels`/`bar_labels` without page rebuild via `_update_hardware_labels()`.

**Sparkline data persistence across page rebuilds:** Sparkline samples that live on auto-rebuilt pages (Network page rebuilds every 5s) MUST be persisted in instance-level lists (`self._net_spark_up`, `self._disk_spark_read`, `self._battery_spark`, `self._sensor_spark_data`) and re-injected into new widgets via `_Sparkline.set_samples()` on rebuild. The `_Sparkline.set_samples(list)` method replaces the internal sample buffer (capped at `max_samples`). Pages that don't auto-rebuild (Hardware, Sensors) store widgets directly in `self._sparklines` dict — but sensor temperature sparkline DATA is still persisted in `self._sensor_spark_data` so history survives manual page rebuilds (settings change, refresh).

### 9. D3D feature level detection
Uses `ctypes.windll.d3d11.D3D11CreateDevice()` with `ctypes.byref(dev_ptr)` (must pass real COM pointer, not None). Returns max feature level + supported levels list. D3D12 runtime check: just test if `ctypes.windll.d3d12` loads.

### 10. Cache structure
Cache files in `cache/` are JSON: `{"_ts": timestamp, "value": actual_data}`. `_cache_read()` returns the `value` key directly (not the wrapper). TTL from `config.cache_ttl_seconds` (default 3600s = 1h).

Cache files: `hw_static`, `os_static`, `net_static`, `software_static`, `services_static`, `drivers_static`, `devices_static`, `health_static`, `updates_static`, `diagnostics_static`, `vpn_static`.

### 11. Stale cache auto-heal
`collect_diagnostics()` checks for missing keys in old cache and collects them fresh. If you add a new diagnostics sub-feature, add the key to the "missing keys" check list.

### 12. Startup white flash — three-phase show
The app must NOT call `_start_collection()` in `InfoWindow.__init__()`. Qt processes paint events at low priority; if collection signals are already queued when `app.exec()` starts, they starve the first paint, leaving the window white for seconds. Instead, `app.main()` uses a three-phase show:
1. Set dark `QPalette` on `QApplication` BEFORE creating any widgets (so `WM_ERASEBKGND` uses dark)
2. `window.setWindowOpacity(0.0)` → `window.show()` → `app.processEvents()` (paints dark palette, ~6ms)
3. `app.setStyleSheet(build_qss(theme))` → `app.processEvents()` (QSS parse + repaint, ~350ms, invisible)
4. `window.setWindowOpacity(1.0)` → `window._start_collection()` (reveal dark styled window, then collect)

`InfoWindow.nativeEvent()` intercepts `WM_ERASEBKGND` (0x0014) and returns `(True, 1)` to suppress Windows' white erase. `InfoWindow.__init__()` sets `setAutoFillBackground(True)` on itself, the central widget, and each scroll page container + viewport.

## File Sizes (approximate, as of v4.9)

| File | Lines | Role |
|---|---|---|
| `gui.py` | ~5830 | Main GUI: all pages, cards, tables, dialogs, exports, `_FlowLayout`, `_ToolCard`, `_Sparkline`, `SettingsDialog` (sidebar-style), `path_select` multi-select input |
| `collectors.py` | ~3816 | All data collection (OS, HW, net, SW, health, diagnostics, speed test, processes with Disk/Network) |
| `tools.py` | ~2280 | Tool catalogue: 4 categories, 29 tools, 67 PowerShell modes (includes Autopilot hash with validation, disk analyzer with 8 modes incl. scan-then-pick cleanup, memory diagnostic, hosts editor, WU trigger, appx manager, dev cache cleaner, hibernate manager, UEFI BIOS reboot, MTP/Android USB reset, SATA/AHCI controller reset, disk status/online, disk rescue) |
| `tools source/DiskRescueLib.ps1` | ~1720 | Disk Rescue engine (v4.19, original proprietary code): C# Add-Type raw-probe session (overlapped reads + watchdog timeout + CancelIoEx + handle reopen), C# TimedFileReader (per-chunk watchdog file reads), C# NtfsTools (FSCTL_GET_RETRIEVAL_POINTERS extents + cluster size), JSON map persistence (atomic save, checkpoints, resume), hierarchical GOOD-first scanner with recovery gate, ASCII map report, bad-aware copier (extent-vs-BAD intersection, zero-fill known-bad chunks, runtime BAD discovery with raw confirmation, physical-order copy, resume by size+timestamp, same-disk guards, PARTIAL sidecars, copy-report), lost-files listing. Referenced from tools.py via `__DISKRESCUE__` token; bundled by sysdigger.spec (whole `tools source/` folder). Keep the file ASCII-only (PS 5.1 reads no-BOM .ps1 as ANSI). |
| `config.py` | ~232 | Config dataclass (23 settings incl. 8 colorization thresholds) + JSON persistence |
| `sensors.py` | ~115 | LibreHardwareMonitorLib wrapper |
| `app.py` | ~109 | Entry point: QApplication, icon, AppUserModelID, theme, three-phase show, launch menu (Normal/Fast mode picker) |
| `launch_menu.py` | ~190 | Launch mode picker QDialog — shown before collectors/gui imports. Normal Mode = full LHM/PawnIO/.NET sensor stack. Fast Mode = skip pythonnet + .NET + PawnIO (saves ~3-6s, Hardware/Sensors pages degrade to WMI fallback). MUST NOT import collectors/sensors (those trigger pythonnet at import time). |
| `sysdigger.pyw` | ~85 | Launcher: UAC elevation, logging, crash handler |
| `helpers.py` | ~120 | fmt_bytes, fmt_speed, fmt_uptime, reg_value, etc. |
| `updater.py` | ~148 | GitHub release updater for LHM DLLs |
| `lhm_process.py` | ~280 | PawnIO driver installer (portable): downloads + runs `PawnIO_setup.exe -install` on launch, runs `uninstall.exe -uninstall -silent` on close. No permanent installation left behind |
| `paths.py` | ~90 | Portable path resolution: `resource_dir()` (read-only bundled assets), `data_dir()` (writable per-user data with `%LOCALAPPDATA%` fallback), `cache_dir()`, `lib_dir()`, `pawnio_dir()` |
| `app_logger.py` | ~95 | Rotating file logger (with read-only location fallback to `%LOCALAPPDATA%\SysDigger\app.log`) |
| `runtime_hook.py` | ~15 | PyInstaller runtime hook: `os.chdir(exe_dir)` + `QT_PLUGIN_PATH` |
| `GITHUB_SIGNING_GUIDE.md` | ~580 | Step-by-step GitHub + SignPath free signing guide for non-developers |

## Page Index Map (gui.py PAGES tuple)

| Idx | Nav Label | Populate Method |
|---|---|---|
| 0 | OS | `_populate_os()` |
| 1 | Hardware | `_populate_hardware()` |
| 2 | Sensors | `_populate_sensors()` |
| 3 | Network | `_populate_network()` |
| 4 | External IP | `_populate_ip()` |
| 5 | Processes | `_populate_processes()` |
| 6 | Software | `_populate_software()` |
| 7 | Updates | `_populate_updates()` |
| 8 | Health | `_populate_health()` |
| 9 | Speed Test | `_populate_speed_test()` |
| 10 | Devices | `_populate_devices()` |
| 11 | Diagnostics | `_populate_diagnostics()` |
| 12 | Tools | `_populate_tools()` (static, built once) |
| 13 | (search) | Dynamic search results |

## Collection Thread Map

| Thread | Steps | Collects |
|---|---|---|
| `os_hw` (thread_a) | 3 | OS, hardware, GPU details → pages 0, 1, 2 |
| `net_sw` (thread_b) | 6 | Network, Wi-Fi, DNS cache, ext IP (fire-and-forget), software, services, startup impact, updates → pages 3, 4, 6, 7 |
| `health_dev` (thread_c) | 4 | Health, VPN, devices, drivers, diagnostics → pages 8, 10, 11 |
| `proc` (thread_d) | 1 | Processes (runs in parallel, doesn't depend on anything) → page 5 |
| `post` (main) | 2 | Dynamic refresh, active connections → pages 0, 1, 3 |

## SystemData Fields (collectors.py)

```python
os_info, hw_info, net_info, ext_ip_info, ext_ip_error, ext_ip_time,
processes, startup_programs, installed_programs, update_history,
health_info, speed_test_result, bufferbloat_result, devices_info,
diagnostics_info, gpu_details, vpn_status,
services_info, drivers_info, restore_points, environment_info,
active_connections, wifi_info, dns_cache,
disk_benchmark, startup_impact
```

## Diagnostics Keys

`diagnostics_info` dict keys: `event_log_system`, `event_log_application`,
`bsod_history`, `crash_dump_settings`, `power_plan`, `directx`,
`restore_points`, `environment`, `path_entries`

## Maintenance Reminders

### When version bumps
- Update `Version X.Y` label in `_on_about_clicked()` in `gui.py`
- Update `Version:` row in the Version History table in `roadmap.md`
- Update `**Version:**` in the Quick Reference section above

### When adding a feature
- Add a bullet to the About dialog description in `_on_about_clicked()` (`gui.py`) summarizing what the new feature does (user-facing, plain English — not implementation details)
- Add a Done item + Version History entry in `roadmap.md`
- If new data fields, add to `SystemData Fields` list above
- If new cache file, add to the `Cache structure` list above
- If new page, update `Page Index Map` above
- If new collection thread/rebalancing, update `Collection Thread Map` above

### When removing/changing a feature
- Remove the corresponding bullet from the About dialog description in `_on_about_clicked()` (`gui.py`) so it never advertises something the app no longer does
- Update `roadmap.md` if needed

## Common Pitfalls

1. **Don't rename the app back to "Windows Info"** — "Windows" is a Microsoft trademark.
2. **Don't use `Get-Content`/`Set-Content`/`Select-String` for file ops** — use the Read/Edit/Grep/Glob tools.
3. **Don't add comments** unless explicitly requested.
4. **Always compile-check** after edits: `python -m py_compile gui.py collectors.py`
5. **Clear cache** when adding new collector fields so fresh data is collected.
6. **PowerShell is OK in `tools.py`** (maintenance tools) but NOT in `collectors.py` (data collection uses `wmi` + `winreg` + `ctypes`).
7. **LHM reports 0 MHz clock on AMD** — always have psutil `cpu_freq()` fallback.
8. **Cloudflare blocks exactly 100MB downloads** — use 99MB.
9. **Cloudflare requires browser User-Agent** header or returns 403.
10. **Always use subagents** for large/complex tasks — auditing large files (>500 lines), searching across the codebase, or running multiple independent investigations. Launch subagents in parallel whenever possible to maximize performance. Delegate research-heavy or multi-step work instead of doing it inline.

## Speed Test Details

- Download: configurable (default 99MB) from Cloudflare (100MB gets HTTP 403)
- Upload: configurable (default 50MB) to Cloudflare
- Timeouts: configurable (default 120s) for both
- User-Agent: browser-style header on all Cloudflare requests
- Bufferbloat: baseline ping → ping under download load → ping under upload load, graded A-F
- All params configurable in Settings → Speed Test section

## Desktop Shortcut

`install_desktop_shortcut.bat` creates `SysDigger.lnk` on Desktop pointing to `sysdigger.pyw` with `app.ico`. Re-run after any path/name change.

## Icon Generation

- `make_icon.py` → `app.ico` (16-256px, dark monitor with blue accent)
- `make_nav_icons.py` → 13 sidebar nav icons (24x24 PNGs)
- `make_category_icons.py` → 4 Tools-page category icons (64x64 PNGs)

## Code Audit Tracker

- **`bugsescalation.md`** — merged from BUGS.md + IMPROVEMENTS.md. 53 original items (all fixed) organized into 9 themed escalations + 28 items from v4.17 re-audit (all fixed). Read this before starting audit fixes.
- **`roadmap.md` → Planned — Short Term → Audit Escalation** — 10 checklist items summarizing the open bugsescalation work (all completed).
- **v4.17 re-audit** — 28 new items found and fixed (2 High, 14 Medium, 9 Low + 3 dead code). See `bugsescalation.md → v4.17 Audit` section and `AGENTS.md → Audit fixes already applied (v4.17)` below.

### Audit fixes already applied (v4.8)
- **B-01** Restored `_collect_uefi_info()` method definition (was missing `def` line — UEFI/Secure Boot/TPM/Core Isolation never collected)
- **B-02** Clear `_sensor_value_labels` + `_sensor_minmax` in `_populate_sensors` (crash on settings change)
- **B-04** Clear `_sensor_minmax` on manual refresh (stale min/max)
- **B-05** Version string 4.7→4.8 in About dialog
- **B-12/I-19** LHM initialization lock (`threading.Lock()` in `_get_lhm_computer`)
- **B-15/I-09** Prune stale PIDs from `_process_io_prev`
- **B-16** Removed duplicate IAD entry in `_CLOUDFLARE_COLOS`
- **B-17** Removed dead power plan sub-settings block
- **B-19/I-18** HTTP status check on ext_ip collection
- **B-22/I-04** Lazy page re-render after settings (clear `_pages_ready`, only render current page)
- **B-23/I-13** Reuse single QTimer for refresh dot pulse
- **B-24** Removed dead `QSS =` line
- **B-25** Removed dead `QTableWidgetItem` creation
- **B-27/I-08** Stored tool card name/desc as instance attributes (eliminated `findChild` per keystroke)
- **I-15** Moved Sparkline `paintEvent` imports to module level (`QPolygon`, `QBrush`, `QPen` now in top-level import)

### Audit fixes already applied (v4.9)
- **B-21/I-01** Extracted `_com_context()` context manager — `CoUninitialize` now called in `finally` (13 leak sites fixed)
- **B-11** Removed cross-thread `self._wmi` fallback — `_wmi_conn` returns thread-local only
- **I-02** Extracted `_wmi_namespace()` helper — ad-hoc WMI connections properly paired with COM init/uninit (6 sites)
- **B-18/I-03** All `winreg.OpenKey()` now use `with` statement (15 sites)
- **B-13/I-20** Event log handles (`OpenEventLog`/`CloseEventLog`) wrapped in `try/finally` (3 sites)
- **I-21** `PowerGetActiveScheme`/`LocalFree` argtypes set + `LocalFree` in `finally`
- **B-03/I-14** `_NumericItem(_SelBlackItem)` subclass for numeric sorting — Processes, Boot History, DNS Cache, PATH Entries
- **B-30/I-10** Event log tables capped at 500 rows + "showing N of M" label
- **I-11** Active connections table capped at 200 rows
- **I-12** Device search index reduced to Name+Status only (~200/tab, was ~600)
- **B-07** Theme toggle now re-renders current page (clears `_pages_ready`)
- **B-08/I-17** 8 threshold spinboxes wired to config (CPU/Mem/Disk/Net × warn/crit)
- **B-09** `_collect_installed_programs` N+1 registry opens fixed (4→1 per subkey)
- **B-10/I-07** Lazy KB title fetching via `get_kb_title()` with 7-day TTL cache
- **I-06** Merged process priming loops (3→2 iterations)
- **B-06** Disk partition mapping — multiple partitions per disk, none dropped
- **B-20** D3D12 check independent of D3D11 success (`d3d11_ok` flag)
- **B-26** Wi-Fi netsh parsing position-based (locale-independent)
- **B-28** Defensive `.get()` on all collector data access (32+ locations)
- **B-14** Disk benchmark worker guarded with `try/except RuntimeError` for deleted widgets
- **B-29** Nav click clears search box (exits search mode)
- **I-05** `_iter_export_sections()` shared generator for text/HTML exports (~355 lines removed)
- **I-16** Removed redundant in-function imports + hoisted movable ones to module level
- **I-22** Keyboard activation for `_ToolCard` (Enter/Space + `StrongFocus`)
- **I-23** Tool card mode badge tooltip with all mode labels

### Audit fixes already applied (v4.11)
- **C-1 gui** `closeEvent` used `self._collector` instead of `self.collector` → LHM.exe never stopped, `super().closeEvent()` never called
- **C-2 gui** Stale clipboard on live-refreshed pages — `_show_row_copy_menu` now uses `label.text()` instead of captured `value` string
- **C-1 collectors** LHM Computer iteration thread-unsafe — added `_sensor_read_lock` around `computer.Hardware` iteration (called from both `collect_hardware` thread + 2s `refresh_sensors` timer)
- **H-1 collectors** Speed test + bufferbloat streaming HTTP responses never closed — now use `with requests.get(..., stream=True) as response:`
- **H-2 collectors** VPN detection via psutil crashed on `addr.family.name` (AF_LINK has no `.name`) — now uses `addr.family in (socket.AF_INET, socket.AF_INET6)`
- **H-3 collectors** LHM `Computer.Close()` never called on invalidation — `set_lhm_process()` now calls `old.Close()` before setting `_lhm_computer = None`
- **H-4 lhm_process** `wait_for_driver()`/`is_driver_ready()`/`is_running` read `self._process` without lock — now capture local `proc = self._process` reference
- **H-5 collectors** USB/Bluetooth/printer/audio collectors checked `_WMI_AVAILABLE` instead of `self._wmi_conn` — crashed if thread hadn't called `_init_wmi()`
- **H-3 app** LHM.exe orphaned on rapid close during startup — `set_lhm_process(proc)` now called immediately after construction (before download/start)
- **H-6 SysDigger** UAC elevation broke when frozen — `elevate()` now detects `sys.frozen` and uses `sys.executable` directly; elevation failure shows MessageBox
- **C-1 app_logger** Crashed on read-only location — `_resolve_log_dir()` falls back to `%LOCALAPPDATA%\SysDigger\app.log`; `RotatingFileHandler` wrapped in try/except
- **C-1 portability** New `paths.py` module with `resource_dir()` / `data_dir()` for frozen-exe path resolution
- **H-1 config** `load()` crashed on wrong-typed JSON values — construction now wrapped in `try/except (TypeError, ValueError)`
- **config** UTF-8 encoding on `open()` calls (was locale-default cp1252)
- **H-5 tools** Autopilot hash hardcoded `C:\AutopilotHWID.csv` → now writes to Desktop
- **H-4 tools** powercfg energy/battery reports saved to wrong location (System32) → now uses `$env:TEMP` with `/output` flag
- **M-1 gui** Pages not re-rendered after settings/theme change — now re-adds pages 0-11 to `_pages_ready` after clearing
- **M-3 gui** `closeEvent` shutdown race — added `_closing` flag, checked in `_update_sensor_values`
- **L-1 gui** Sidebar title "System Info" → "SysDigger"
- **Packaging** New files: `paths.py`, `requirements.txt`, `sysdigger.spec`, `runtime_hook.py`, `version.txt`, `build.ps1`

### Audit fixes already applied (v4.12)
- **C-1 lhm_process** `version.txt` never written after downloading LHM.exe → `is_downloaded()` always returned False → `start()` refused to launch LHM.exe → PawnIO driver never loaded → AMD CPU temp/power/clock sensors returned 0, motherboard SuperIO sensors missing. Now writes `version.txt` with `LHM_VERSION` after extraction.
- **C-1 collectors** `set_lhm_process()` called `old.Close()` outside `_sensor_read_lock` → race with 2s `refresh_sensors` timer iterating the same Computer → crash or empty sensor results for one refresh cycle. Now holds `_sensor_read_lock` during `old.Close()`.
- **M-1 collectors** WMI fallback sensor entries missing `"Type"` and `"Category"` keys → would crash GUI rendering if LHM unavailable and WMI fallback used. Added both keys to all WMI fallback entries.
- **AMD Ryzen sensors** LHM 0.9.6 returns 0 MHz / 0 W for AMD Zen CPU Clock + Power (SMU limitation). Added `_apply_amd_cpu_fallbacks()` in `collectors.py:_collect_sensors()` that detects zero-value CPU Clock entries and replaces them with real per-core frequencies from `psutil.cpu_freq(percpu=True)`. Zero-value CPU Power entries are removed. No new dependencies, no kernel driver, fully portable.

### Audit fixes already applied (v4.13) — Full codebase audit
- **C-1 security gui** PowerShell injection via `__INPUT__` substitution — user input (product key, Wi-Fi profile name) was substituted directly into PowerShell single-quoted strings without escaping. A single quote `'` in the input would break out and execute arbitrary code (app runs as admin). Now escapes `'` → `''` (PowerShell single-quote escaping) in `_collect_text_input`.
- **C-1 perf gui** `_search_items` unbounded growth — auto-refresh pages (Network @ 5s, Processes @ 5s) appended ~30-50 items per rebuild without ever discarding old entries, growing ~36k items/hour and slowing search to 100-300ms per keystroke. Added `_search_items_by_page` dict tracking per-page indices; `_discard_search_items_for_page()` called at top of `_render_page` and `_on_process_refreshed`.
- **C-2 perf gui** Processes double-build every 5s — both QTableWidget (1200 items) and QTreeWidget (200 items + recursion) were built unconditionally on every refresh, even though only one tab is visible. Now only populates the visible tab's rows; `currentChanged` triggers a rebuild when the user switches tabs (with `_process_tab_rebuilding` re-entry guard + `blockSignals` during `setCurrentIndex`).
- **C-1 correctness gui** `_make_card` ordering bug in `_populate_health` — `insertWidget(count-1, card)` assumes a stretch is the last item; when stretch was added AFTER cards (Health page), each new card was inserted before the previous one, reversing card order (Defender→Firewall→Activation→Disk SMART instead of Disk SMART→Defender→Firewall→Activation). Now adds stretch BEFORE any `_make_card` calls.
- **C-1 crash collectors** H-5 anti-pattern survived in `_collect_power_plan` and `collect_vpn_status` — checked `_WMI_AVAILABLE` (module-level flag) instead of `self._wmi_conn` (thread-local). If `_init_wmi()` ran but `WMI()` failed, these methods would crash with `AttributeError: 'NoneType' object has no attribute 'Win32_Battery'`/`Win32_NetworkAdapter`. Now checks `self._wmi_conn` directly.
- **C-1 correctness collectors** `_process_io_prev` stale pruning — computed `current_pids` from the top-N slice AFTER sorting, pruning every non-top-N PID. On the next refresh, non-top-N processes had `prev = None` and always reported 0 KB/s disk I/O. Now computes `current_pids` from the FULL process list BEFORE slicing.
- **C-1 correctness collectors** Disk benchmark drive-relative path — `os.path.join("C:", "file")` produces `"C:file"` (relative to current dir on drive C), NOT `"C:\file"`. Benchmark wrote to the wrong location. Now uses `drive + os.sep`.
- **M-1 gui** `closeEvent` taskkill had no timeout — could hang the window open indefinitely if `taskkill` itself hung. Now uses `timeout=5` + `except subprocess.TimeoutExpired`.
- **M-2 gui** `_on_tool_clear` race condition — reset `_tool_stopped`/`_tool_stopping` while async kill was in progress, causing `_on_tool_finished` to show "COMPLETED SUCCESSFULLY" instead of "TERMINATED BY USER". Now only resets stop flags if no tool is running.
- **M-3 perf collectors** Duplicate `psutil.process_iter` and `psutil.net_connections` syscalls — `collect_processes` and `collect_active_connections` each iterated all processes and called `net_connections` separately (~50-200ms each, duplicated every 5s). Added `_pid_name_cache` and `_net_conns_cache` shared between both methods.
- **M-4 portability** `paths.py` module existed but was never imported — 17 sites across 8 files used `os.path.dirname(os.path.abspath(__file__))` for writable paths (config, cache, logs, LHM download), which breaks in frozen `--onedir` exe (`__file__` resolves to `_internal/`). Now all files import `paths.resource_dir()` / `paths.data_dir()` / `paths.cache_dir()` / `paths.lib_dir()` / `paths.lhm_standalone_dir()` / `paths.icon_path()` / `paths.icons_dir()`.
- **M-5 collectors** AMD fallback regression — `self.data.hw_info = hw` was set AFTER `_collect_sensors()` (line 432), so `_apply_amd_cpu_fallbacks` read stale `self.data.hw_info` and the AMD vendor check failed, skipping the psutil clock fallback. Now sets `self.data.hw_info = hw` BEFORE calling `_collect_sensors()`.
- **m-1 app** `winreg.OpenKey()` without `with` statement — handle leaked if `QueryValueEx` raised. Now uses `with winreg.OpenKey(...) as key:`.
- **m-2 lhm_process/updater** Streaming HTTP responses not closed — `requests.get(..., stream=True)` without `with`/`close()`, connection lingered until GC. Now uses `with`/`try-finally close()`.
- **m-3 app_logger** Stale log message "Windows System Information Viewer starting" → "SysPeek starting" (app renamed in v4.5, later "SysDigger starting" in v4.16).
- **m-4 updater** `version.txt` written even when all DLL writes failed → `is_up_to_date()` would report "already up to date" despite stale DLLs. Now only writes `version.txt` if `written > 0`.
- **m-5 lhm_process/updater** `version.txt` opened without `encoding="utf-8"` (was locale-default cp1252). Now uses `encoding="utf-8"` consistently.

### Audit fixes already applied (v4.14) — PawnIO driver migration
- **C-1 lhm_process** LHM 0.9.6 (Feb 2026) updated to PawnIO 2.2 which is now distributed as a separate installer (https://github.com/namazso/PawnIO.Setup). LHM.exe can no longer install the driver on its own — it expects PawnIO to be pre-installed. Rewrote `lhm_process.py` to download and run `PawnIO_setup.exe` v2.2.0 instead of launching LHM.exe. The installer uses the `-install` flag (same as LHM uses internally) for silent installation (~2.5s, idempotent).
- **C-1 lhm_process** Portable mode: on `closeEvent`, runs `uninstall.exe -uninstall -silent` to remove `C:\Program Files\PawnIO` + `sc stop PawnIO` (best-effort). The driver stays in kernel memory until reboot (Windows limitation — becomes NOT_STOPPABLE after uninstall marks it for deletion), but re-install works cleanly on next launch.
- **C-1 collectors** `set_lhm_process()` docstring updated — the driver is now installed by the standalone PawnIO installer, not by LHM.exe.
- **paths** Added `pawnio_dir()` for the installer cache (`lib/pawnio/`). `lhm_standalone_dir()` kept for backward compatibility but no longer used.

### Audit fixes already applied (v4.17) — Post-v4.14 follow-up audit
- **A-01 gui** Bufferbloat streaming HTTP response (`_req.get(..., stream=True)`) in `_run_bufferbloat_with_progress` never closed — now uses `with` (same pattern as H-1 fix for speed test)
- **A-02 collectors** `_fetch_kb_title` HTTP response never closed — now uses `with requests.get(...) as r:`
- **A-03 collectors** `run_speed_test` Cloudflare meta lookup response never closed — now uses `with`
- **A-04 collectors** `run_speed_test` upload `requests.post()` Response discarded without `with`/`close()` — now uses `with`
- **A-05 collectors** `run_bufferbloat_test` upload `requests.post()` Response discarded — now uses `with`
- **A-06 tools** `_TRIM_SSD` false-negative on non-numeric `Get-PhysicalDisk.DeviceId` (NVMe storage spaces paths like `\\?\PCI#VEN_...`) — now checks if DeviceId is already an int, falls back to DeviceNumber/Number, then tries `[int]` cast in try/catch
- **A-07 tools** `_CHECK_HDD` (chkdsk /f, /r) lacked `confirm=True` — now added (destructive operations need confirmation dialog)
- **A-08 gui** `_make_card` ordering bug — `insertWidget(count-1, card)` scrambled card order on pages without trailing stretch (Speed Test page had cards between button and status label; Network Adapters tab had adapter cards in reversed order). Rewrote to scan backwards for last stretch item and insert before it, or append if no stretch found. Fixes both pages without affecting pages that already had stretch-at-top pattern.
- **A-09 gui** Process tree dropped orphaned processes when any PPID was None — `root_items = children_map.get(None, [])` only fell back to orphan scan when the first branch was empty. Now always uses comprehensive orphan scan: `p for p in procs if p.get("PPID") is None or p.get("PPID") not in proc_by_pid`.
- **A-10 collectors** PDH query state (`_pdh_query`, `_pdh_perf_counters`, `_pdh_base_freq`) accessed without lock from two threads (`collect_hardware` thread + 2s `refresh_sensors` timer) — added `_pdh_lock = threading.Lock()` and wrapped entire `_read_amd_per_core_freqs` body in `with self._pdh_lock:`
- **A-11 tools** `_AUTOPILOT_HASH` UTF-8/Default encoding mismatch (wrote CSV with UTF-8, read back with `[System.Text.Encoding]::Default` which is Windows-1252 on most systems) + fragile CSV parsing (`($csvContent -split "`r`n")[1].Split(',')[2]` assumed line 2 exists + 3+ fields) — now reads with UTF-8 + bounds-checks line count and field count
- **A-12 tools** `_WU_INSTALL` (Windows Update install via `usoclient StartInstall`) lacked `confirm=True` — now added (downloads + installs pending updates)
- **A-13 tools** `_HIBERNATE_OFF`/`_HIBERNATE_ON` used locale-dependent regex on `powercfg /a` output (English strings like `'Hibernation has been disabled by the'`). On non-English Windows the early-exit checks were skipped. Now uses `Test-Path "$env:SystemRoot\hiberfil.sys"` which is locale-independent.
- **A-14 collectors** `D3D11CreateDevice` COM objects (`dev_ptr`/`ctx_ptr`) could leak on `ArgumentError` (argtypes not set, and inner `except (OSError, AttributeError)` didn't catch `ArgumentError`). Moved COM release code to `finally` block + broadened `except` to `Exception`.
- **A-15 collectors** `updates.sort(key=lambda x: x.get("Installed On", ""))` sorted locale-formatted date strings lexically, not chronologically (e.g. `"1/15/2024"` sorted after `"10/10/2023"`). Added `_parse_date` helper that tries multiple `datetime.strptime` formats with fallback to `datetime.min`.
- **A-16 gui** `_on_sensor_refresh_tick` missing `_closing` guard — queued `timeout` signal after `closeEvent` stopped the sensor timer could create a new `_refresh_dot_timer`, which would fire `_dim_refresh_dot` accessing the deleted `_refresh_dot` widget → `RuntimeError`. Added `if self._closing: return` at top.
- **A-17 gui** `_on_tool_reboot` `subprocess.Popen(["shutdown", "/r", "/f", "/t", "0"])` not wrapped in try/except — now wrapped, shows error dialog on failure.
- **A-18 gui** Missing `setSortingEnabled(True)` on 6 tables: Active Connections (`conn_table`), Event Log System + Application, BSOD History (`bsod_table`), Restore Points (`rp_table`), Environment Variables (`env_table`), and all 5 device tables via `_make_device_table` — now added after population loop on all.
- **A-19 gui** `_sensor_spark_data` not cleared in `_populate_sensors` (only cleared in `_on_refresh_clicked`) — stale sensor keys accumulated when hardware changed. Added `self._sensor_spark_data.clear()` alongside `_sensor_value_labels`/`_sensor_minmax`/`_sensor_sparklines`.
- **A-20 collectors** PDH query handle never closed on app exit — added `Collector.close()` method that calls `win32pdh.CloseQuery(self._pdh_query)` under `_pdh_lock`, called from gui.py `closeEvent`.
- **A-21 collectors** `collect_ext_ip` HTTP responses (ipify + ipinfo) not closed with `with` — now uses `with requests.get(...) as resp:`
- **A-22 tools** `_RESET_SPOOLER` lacked `confirm=True` (clears print queue, loses pending jobs) — now added.
- **A-23 tools** `_REMOVE_HID_ERRORS` lacked `confirm=True` — now added for consistency with `_BT_RESET`.
- **A-24 tools** `_WIFI_PASSWORD` passed profile name to netsh as `name="$profileName"` without escaping `"`. Now escapes `"` → `` `" `` (PowerShell backtick-quote) via `-replace '"', '`"'`.
- **A-25 tools** `_INSTALL_SCAN`/`_INSTALL_FIX` substituted `__LIB__`/`__BACKUP__` into double-quoted PowerShell strings (`". "__LIB__""`). Changed to single-quoted (`". '__LIB__'"`) since these paths are app-controlled and don't contain single quotes.
- **A-26 collectors** Dead `del conn` in `_wmi_namespace` `finally` block was a no-op (only cleared local alias, not caller's `as` variable). Replaced with `conn = None` + explanatory comment.
- **A-27 collectors** Dead `static_fields = {}` assignment at line 295 was reassigned at line 331 without being read. Removed.
- **A-28 collectors** Redundant `except (FileNotFoundError, Exception)` at line 2358 — `FileNotFoundError` is a subclass of `Exception`, so listing both is the same as `except Exception:`. Simplified.

## PyInstaller Packaging (v4.11)

Build: `.\build.ps1` (installs deps, compile-checks, builds, signs)

- **Spec**: `sysdigger.spec` — `--onedir` mode (faster startup, lower AV false-positive)
- **UAC**: `uac_admin=True` in EXE — manifest requests elevation, skips `sysdigger.pyw` self-elevation
- **Frozen detection**: `sysdigger.pyw` checks `getattr(sys, "frozen", False)` — skips elevation relaunch when frozen
- **Path resolution**: `paths.py` distinguishes `resource_dir()` (read-only `sys._MEIPASS`) from `data_dir()` (writable exe dir or `%LOCALAPPDATA%\SysDigger` fallback)
- **Runtime hook**: `runtime_hook.py` sets `os.chdir(exe_dir)` + `QT_PLUGIN_PATH`
- **Signing**: Set `$env:SIGN_CERT_THUMBPRINT` and run `build.ps1` — signs all exe/dll with `signtool.exe` + RFC 3161 timestamp
- **Cert recommendation**: Azure Trusted Signing (~$10/mo), EV cert (immediate SmartScreen reputation), or **SignPath Foundation** (free for open-source — see `GITHUB_SIGNING_GUIDE.md`)

## GitHub Repository (v4.11)

GitHub username: `stavros-it` (user ID: 151866740)
Git identity: `Stavros Antoniou <151866740+stavros-it@users.noreply.github.com>` (noreply email)

**State**: Initial commit created locally (`a53314f`, 74 files, 21,093 lines). Repo NOT yet created on GitHub — awaiting user to create `stavros-it/SysDigger` on github.com and push.

**Files added for GitHub:**
- `README.md` — front-page project description (features, requirements, download link, project structure, docs links, code signing policy, privacy policy)
- `LICENSE` — Proprietary License (Copyright (c) 2026 Stavros Antoniou, All Rights Reserved)
- `.gitignore` — excludes runtime artifacts (`cache/`, `app.log`, `config.json`, `lib/lhm_standalone/`, `build/`, `dist/`, `__pycache__/`, `tools source/SA_WinTools_RegBackup/`)
- `.github/workflows/build-and-sign.yml` — GitHub Actions workflow (build → zip → submit to SignPath if secrets set → upload to release; falls back to unsigned zip if SignPath not configured)
- `GITHUB_SIGNING_GUIDE.md` — step-by-step guide for GitHub setup + code signing (written for non-developer). NOTE: SignPath free signing requires an OSI-approved open-source license (e.g. MIT); since the app is now proprietary, use Azure Trusted Signing (~$10/mo) or an OV/EV cert instead — see BUILD_GUIDE.md

**Files removed (stale):**
- `BUGS.md`, `IMPROVEMENTS.md` — merged into `bugsescalation.md` (stale duplicates)
- `tools source/project_context.md`, `tools source/roadmap.md` — old SA WinTools docs (not referenced by code, were bloating the exe)
- `Windows Info.7z` — old archive
- `tools source/SA_WinTools_RegBackup/` — runtime artifact (created at runtime by Install/Uninstall Fix tool)

**Committed to repo (must stay):**
- `lib/` (12 DLLs, ~3 MB) — required for the build; `lhm_standalone/` excluded via `.gitignore` (downloaded at runtime)
- `tools source/` (6 files) — `SA_WinTools_Lib.ps1` is referenced at runtime by `tools.py:43`; the `.diagcab` is bundled for the Install/Uninstall Fix tool
- `icons/`, `app.ico`, `app_preview.png` — bundled into exe and shown in README

**SignPath free signing workflow (NOT available — app is proprietary):**
> SignPath free signing requires an OSI-approved open-source license. Since the app is now proprietary, this workflow is no longer applicable. Use Azure Trusted Signing (~$10/mo) or an OV/EV certificate instead.

See `GITHUB_SIGNING_GUIDE.md` for full step-by-step instructions.

## Critical Patterns (learned from audit)

### 13. `_sensor_value_labels` must be cleared before rebuild
`_populate_sensors()` MUST clear `self._sensor_value_labels` and `self._sensor_minmax` at the top, BEFORE `_clear_layout()`. Otherwise stale QLabel references survive and the next 2s sensor refresh crashes with `RuntimeError: wrapped C/C++ object has been deleted`. Same applies to `_on_refresh_clicked` — clear both dicts.

### 14. Lazy page re-render after settings change
`_on_settings_clicked()` must NOT rebuild all 13 pages synchronously. Instead: clear `_pages_ready` (marks all as dirty), render only the current page, let others rebuild on-demand when navigated to. This prevents multi-second UI freeze.

### 15. `_collect_uefi_info()` is a separate method
The UEFI/Secure Boot/TPM/Core Isolation collection code lives in `_collect_uefi_info()` method in `collectors.py`. It was previously dead code (missing `def` line, unreachable after `return` in `_collect_crash_dump_settings`). If it stops working, check that the `def` line exists.

### 16. LHM Computer requires thread-safe initialization
`_get_lhm_computer()` uses `self._lhm_lock` (a `threading.Lock()`) to prevent double initialization. If adding new sensor collection paths, ensure they go through `_get_lhm_computer()` and don't create their own `Computer()` objects.

### 17. Tool log must use NoWrap + as-needed scrollbars
`_tool_log` (QPlainTextEdit) must have `setLineWrapMode(NoWrap)` and both scrollbars set to `ScrollBarAsNeeded`. Without this, long lines wrap and appear truncated. Horizontal scrollbar QSS must be styled (was vertical-only before).

### 18. PowerShell scripts — `Out-String -Width 4096` for TABLES only, streaming for native commands
Two distinct output patterns in `tools.py`:

- **Table output** (from `Format-Table`, `Format-List`, `Get-*` cmdlets that emit objects): MUST use `| Format-Table -AutoSize | Out-String -Width 4096 | Write-Output`. The `Out-String -Width 4096` is required because PowerShell's default 80-char width truncates wide tables. Buffering is acceptable here since table output is short (a few rows).

- **Native command output** (from `sfc`, `dism`, `chkdsk`, `Optimize-Volume`, `powercfg`, `netsh`, `npm`, `pip`, `klist`, `net use`, etc.): MUST use `2>&1 | ForEach-Object { Write-Output $_ }` for live streaming. NEVER wrap these with `Out-String -Width 4096` — that buffers ALL output until the command exits, defeating live streaming for operations that take 60s–30min (SFC, DISM RestoreHealth, chkdsk /r, powercfg /energy). The user would see NOTHING in the log window for the entire duration.

The preamble must include `$FormatEnumerationLimit=-1` to prevent array/list truncation.

### 19. COM init/uninit via `_com_context()` and `_wmi_namespace()` (v4.9)
Short-lived COM usage (ad-hoc WMI namespaces, firewall COM dispatch) MUST use `with _com_context():` which pairs `CoInitialize`/`CoUninitialize` in a `finally`. Ad-hoc WMI namespace queries MUST use `with self._wmi_namespace("root/...") as conn:` which wraps `_com_context()` + creates + cleans up the WMI connection. The thread-local WMI connection (`_init_wmi()`) intentionally does NOT call `CoUninitialize` — the COM apartment lives for the thread's lifetime (one `CoInitialize` per collection thread, cleaned up by Windows on thread exit). Never fall back to another thread's WMI connection (B-11 fix: `self._wmi` removed, `_wmi_conn` returns thread-local only).

### 20. `_NumericItem` for numeric table sorting (v4.9)
Numeric table columns (PID, CPU%, Memory, Disk, Network, Duration, TTL, Index) MUST use `_NumericItem(_SelBlackItem)` instead of `_SelBlackItem` or `QTableWidgetItem`. It stores the numeric value in `Qt.UserRole` and overrides `__lt__` for correct numeric sorting. Inherits from `_SelBlackItem` so `setForeground()` color-coding still works and goes black on selection.

### 21. Defensive `.get()` on collector data (v4.9)
NEVER use `dict["key"]` direct access on collector data dicts (GPU, disk, RAM slot, adapter, process, startup, program, update, service, driver, SMART, firewall entries). ALWAYS use `dict.get("key", "N/A")` (or `[]` for list fields like IPv4/IPv6, `0`/`0.0` for numeric fields). A missing key from a partially-failed collector should show "N/A", not crash the entire page.

### 22. `path_select` two-phase scan-then-pick flow (v4.11)
Tools that scan a location and let the user pick which items to delete use a `path_select` input type. The flow is:
1. `_run_tool_mode` detects `input.type == "path_select"` and calls `_begin_path_select_flow` instead of the normal input/confirm/run path.
2. The mode's `scan_script` runs through the standard `_run_powershell_tool` pipeline — output streams into the log panel so the user sees what was found. The scan script MUST emit a `__SCAN_BEGIN__` / `__SCAN_END__` block with one `size\tpath` row per line (or `size\tid\tlabel` when `id_col=True`, e.g. Appx where the FullName differs from the display name).
3. `_on_tool_finished` checks `self._path_select_pending`. If set, it emits a SCAN COMPLETE banner, parses the captured log (`_tool_log.toPlainText()`), shows a multi-select checkbox dialog (`_path_select_dlg`), and (if confirmed) substitutes `__PATHS__` into the mode's `script` and launches a second `_run_powershell_tool` call for the actual cleanup (with `(cleaning N item(s)...)` suffix in the label).
4. Critical-path blocklist (`_is_critical_path`) is applied to filesystem paths: `C:\Windows`, `C:\Program Files*`, `C:\ProgramData`, `C:\$Windows.~*`, `C:\Recovery`, user profile root, and any path containing `\Microsoft\` are filtered out and never shown in the dialog. Set `blocklist: False` on the spec (e.g. for Appx, which uses `Remove-AppxPackage` instead of file deletion) to disable.

`_path_select_pending` MUST be cleared in `_on_tool_stop`, `_on_tool_clear`, and on every cancel path inside `_on_tool_finished`. If left set, the next non-path_select tool's finished signal would misfire the dialog.

### 23. Tool Stop — graceful then force, with critical-op prompt (v4.11)
`_on_tool_stop` does NOT immediately `taskkill /F`. The flow is:
1. **Double-click guard**: if `self._tool_stopping` is already True, return.
2. **Critical-op prompt**: call `_is_critical_stop_operation(mode)` — returns True if the mode has `confirm=True` OR its script contains any `_CRITICAL_SCRIPT_PATTERNS` substring (`sfc /scannow`, `dism.exe /Online /Cleanup-Image`, `chkdsk`, `Optimize-Volume`, `Remove-AppxPackage`, `reagentc`, `slmgr.vbs" /ato`, `powercfg /hibernate`, `Clear-RecycleBin`, `Stop-Service`, `Start-Service`, `Set-ItemProperty`, `Remove-Item`, `Disable-PnpDevice`, `Enable-PnpDevice`, `Rename-Item`, `New-Item`, `net use * /delete`, `w32tm /unregister`/`/register`). The path_select **scan phase** is excluded (read-only) via the `self._path_select_pending is not None` check — only the cleanup phase prompts. If critical and the user clicks "No", the tool keeps running.
3. **Background kill thread** (`_stop_tool_proc_async`): Phase 1 sends `taskkill /T /PID` (no `/F`) — posts `WM_CLOSE` to windows in the tree so GUI children (Notepad, mdtsched, slmgr dialogs) can close cleanly. Polls `proc.poll()` for 3 seconds. Phase 2 falls back to `taskkill /F /T /PID` (force kill the whole tree) if the grace period expires.
4. The worker thread's `for line in proc.stdout` loop exits naturally when the process dies (pipe EOF), then emits `finished` → `_on_tool_finished` shows TERMINATED.

Mode tracking (`_tool_running_mode`, `_tool_running_name`) is set in `_run_tool_mode` / `_begin_path_select_flow` and cleared in `_on_tool_finished`, `_on_tool_stop`, `_on_tool_clear`. `closeEvent` still uses immediate `taskkill /F /T` (no grace period — app is exiting).

### 24. PawnIO kernel driver for motherboard + CPU sensors (v4.14)
The DLL-based sensor collection (`sensors.py` + `collectors.py:_collect_sensors`) reads CPU/GPU sensors via PCI config space and ADL, but CANNOT read motherboard SuperIO sensors (fan RPM, voltages, VRM temps) or AMD CPU MSR registers (clock, power, temperature) without the PawnIO kernel driver.

**Background:** Starting with LHM 0.9.6 (Feb 2026), PawnIO is distributed as a separate installer (https://github.com/namazso/PawnIO.Setup) and is no longer bundled inside the LHM.exe release ZIP. LHM.exe and the DLL-based `Computer.Open()` both expect PawnIO to already be installed. Previous versions of SysDigger launched LHM.exe hidden to load the driver, but this no longer works with LHM 0.9.6.

**Portable flow (install on launch, uninstall on close):**
1. `app.py:main()` launches a background thread that calls `LhmProcess.ensure_downloaded()` (downloads `PawnIO_setup.exe` v2.2.0 from GitHub to `lib/pawnio/`, cached), then `start()` (runs `PawnIO_setup.exe -install` — silent, ~2.5s, idempotent: works whether the service is absent, stopped, or already running), then `wait_for_driver(timeout=20s)` (polls `sc query PawnIO` until RUNNING), then `collector.set_lhm_process(proc)`.
2. `set_lhm_process()` invalidates `self._lhm_computer = None` (under `_lhm_lock`) so the next `_collect_sensors()` call recreates the `Computer` object — now with the PawnIO driver available, so `computer.Hardware` includes the SuperIO subhardware (e.g. Nuvoton NCT6687D) with all motherboard sensors AND the AMD CPU sensors (Tctl/Tdie temperature, per-core clocks, per-core SMU power, VID/SVI2 voltages).
3. On `closeEvent`, `lhm_proc.stop()` runs `uninstall.exe -uninstall -silent` (removes `C:\Program Files\PawnIO`) + `sc stop PawnIO` (best-effort — may fail if the driver is NOT_STOPPABLE after uninstall marks it for deletion). Only legacy WinRing0 services are `sc delete`d.

**Residue after close:** The driver stays in kernel memory until reboot (Windows kernel driver limitation — the driver becomes NOT_STOPPABLE after the uninstaller marks it for deletion). This is harmless (just provides I/O port access). `C:\Program Files\PawnIO` is gone immediately. The service entry is removed on reboot. On next app launch, `start()` re-runs `PawnIO_setup.exe -install` which handles the stopped/marked-for-deletion service cleanly.

**Installer silent mode:** The PawnIO installer supports the `-install` flag (used by LHM itself). `/S`, `/silent`, `/quiet` all return exit 87. The uninstaller (`uninstall.exe` placed at `C:\Program Files\PawnIO\uninstall.exe`) supports `-uninstall -silent`.

**Result:** On MSI B550 GAMING PLUS with AMD Ryzen 7 5700X:
- 7 motherboard temperatures (CPU, System, VRM MOS, PCH, CPU Socket, PCIe x1, M2 #1)
- 7 fan RPMs (CPU Fan, Pump Fan, System Fan #1-6) + 7 fan controls (PWM duty)
- 14 motherboard voltages (+12V, +5V, Vcore, DIMM, CPU I/O, etc.)
- CPU temps: Tctl/Tdie, CCD1 (Tdie)
- CPU clocks: per-core (4650 MHz live boost), Cores (Average), Bus Speed
- CPU power: per-core SMU
- CPU voltages: per-core VID, Core (SVI2 TFN), SoC (SVI2 TFN)

### 25. Tool execution log — GUI-side status banners (v4.11)
The Tools page execution log (`_tool_log`) shows GUI-side status banners in addition to the streamed PowerShell output. These banners are emitted by the main thread (NOT the worker thread) via `_emit_log_line()`, which appends to both the GUI log AND the on-disk log file (`%TEMP%\SA_WinTools_Active.log`) so "Open Log" shows the same content as the GUI.

**Banner format:**
- Start: `[HH:MM:SS] ===== STARTED: <tool_name> - <mode_label> =====` — emitted in `_run_powershell_tool` after clearing the log, BEFORE the worker starts.
- End (success): `[HH:MM:SS] ===== COMPLETED SUCCESSFULLY (X.Xs, exit 0) =====` — emitted in `_on_tool_finished` when rc == 0.
- End (errors): `[HH:MM:SS] ===== COMPLETED WITH ERRORS (X.Xs, exit N) =====` — emitted when rc != 0.
- End (terminated): `[HH:MM:SS] ===== TERMINATED BY USER (X.Xs) =====` — emitted when `_tool_stopped` is True.
- Scan complete (path_select phase 1): `[HH:MM:SS] ===== SCAN COMPLETE (X.Xs, exit N) - pick items to proceed =====` — emitted before the multi-select dialog.
- Cancel paths: `[!] Cancelled by user - no items selected.` / `[!] Cancelled by user - no cleanup performed.`

**Invariants:**
1. `_tool_worker` MUST open the on-disk log in append mode (`"a"`) — `_run_powershell_tool` already truncated it and wrote the STARTED banner. If the worker opens in `"w"` mode, it wipes the banner from disk (the GUI log keeps it, but "Open Log" would lose it).
2. `_tool_start_time` MUST be set in `_run_powershell_tool` (main thread) BEFORE the worker starts, so `_on_tool_finished` can compute duration. Reset to `0.0` in `_on_tool_clear`.
3. The worker MUST NOT filter out blank lines, `SA WinTools -` headers, or `=====` separator lines from the streamed output — these provide visual structure (section breaks, tool name banners, dividers). Earlier versions stripped them for "compactness" but that made the log a wall of text.
4. Long-running scan scripts (`_SCAN_APPDATA_LOCAL`, `_SCAN_APPDATA_ROAMING`, `_SCAN_PROFILE_FILES`, `_SCAN_APPX`, `_DISK_FOLDER_MAP` Phase 2, `_DISK_DUPLICATES` Phase 3) MUST emit per-item or per-N-items progress messages so the user sees activity during multi-second scans.

### 26. Launch menu + Fast Mode (v4.18)
On startup, `app.py:main()` shows a launch mode picker dialog (`launch_menu.py:show_launch_menu()`) BEFORE importing `collectors` or `gui`. This is critical because `collectors.py:73` eagerly imports `sensors.py`, which loads pythonnet + 12 .NET DLLs + .NET CLR runtime at import time (~200-500ms) — and `app.py` needs to set `SYSDIGGER_FAST_MODE=1` BEFORE that import happens so `sensors.py` can skip the pythonnet block.

**Normal Mode:** Full app. `app.py` launches a background thread (`_start_lhm_bridge`) that downloads + runs `PawnIO_setup.exe -install` (~2.5s), waits for the driver (~0.5-3s), then calls `collector.set_lhm_process(proc)` to invalidate the cached LHM Computer so the next `_collect_sensors()` recreates it with the driver available. All 14 pages fully functional.

**Fast Mode:** Skips the `_start_lhm_bridge` thread entirely. `SYSDIGGER_FAST_MODE=1` env var is set before `from collectors import Collector` runs, so `sensors.py` skips the pythonnet loading block (`_LHM_AVAILABLE = False`, `_LhmHardware = None`). The 12 .NET DLLs are never loaded, PawnIO is never downloaded/installed. All LHM-touching collector methods already have graceful fallbacks (`_collect_sensors` → `_collect_sensors_wmi_fallback`, `_get_lhm_computer` returns None early). Hardware/Sensors pages show WMI fallback (ACPI thermal zone, Win32_Fan) or "Not available" card. All other pages (OS, Network, Processes, Software, Devices, Diagnostics, Tools) work fully. Saves ~3-6 seconds on startup.

**Invariants:**
1. `launch_menu.py` MUST NOT import `collectors` or `sensors` — those trigger pythonnet. Only PySide6 + stdlib imports allowed.
2. `app.py` MUST defer `from collectors import Collector` and `from gui import ...` to AFTER `show_launch_menu()` returns and the env var is set.
3. `sensors.py` checks `os.environ.get("SYSDIGGER_FAST_MODE")` at module level. If set, the entire pythonnet `try` block is skipped.
4. `closeEvent` in `gui.py` already guards with `if lhm_proc is not None` — in fast mode `collector._lhm_process` stays `None`, so the PawnIO uninstall block is correctly skipped.
5. `Collector.close()` (PDH query cleanup) is safe to call in fast mode — `_pdh_query` is only created when `_read_amd_per_core_freqs()` is called, which only runs in the LHM sensor path (not reached in fast mode). The `if self._pdh_query is not None` guard handles this.

### 27. Disk Rescue tool (v4.19)
Failing-disk recovery in the Hardware & Diagnostics category. Engine in `tools source/DiskRescueLib.ps1` (original proprietary code — do NOT port anything from the GPL-3.0 AdaptiveDisk project; the concept was analyzed but all code written from scratch). 5 modes in tools.py use tiny stub scripts that dot-source the lib via `. '__DISKRESCUE__'` and call `Show-DiskRescueDisks` / `Invoke-DiskRescueScan` / `Show-DiskRescueReport` / `Invoke-DiskRescueCopy` / `Show-DiskRescueLost`. The `rescue_copy` input type (gui.py `_collect_rescue_copy_input`) returns `__DRIVE__` (bare source letter), `__DEST__` and `__MAP__` (both `'`-escaped single-quoted PS strings). The `rescue_scan` input type (`_collect_rescue_scan_input`) returns `__INPUT__` (disk number), `__MAP__` (optional path, blank = `Documents\DiskRescue\diskN-map.json`) plus the scan step numbers `__PROBEMIB__` (probe sample 1-64 MiB), `__MINSTEP__` (refine floor 1-1024 MiB) and `__TIMEOUTMS__` (probe timeout 500-60000 ms). Text-input modes can carry `"browse_filter": "<QFileDialog filter>"` to get a file-explorer Browse button next to the text field (used by Show Map Report for map .json and Show Lost Files for report .txt). Copy runs can take hours on real failing disks — Stop (taskkill tree) is safe: map checkpoints every 50 probes, per-file temp-write + timestamp preservation enables resume.

**Raw probe invariants (bugs hit during v4.19):** every raw read offset AND length must be a multiple of the disk's bytes-per-sector — `FILE_FLAG_NO_BUFFERING` rejects misaligned requests with Win32 error 87 ("The parameter is incorrect"), which must never be classified as BAD. The scan re-aligns the step at the start of every depth level (halving an aligned step can yield a non-multiple of 512), and clamps probe reads+ranges to the disk end. A single timeout is retried once after the recovery gate (`Invoke-DiskRescueProbeVerified`) — one flaky timeout on a healthy drive must not mark a region BAD.

**PowerShell collection-return pitfall (hit during v4.19, applies to any .ps1):** functions must NEVER return a collection (`return $list` unrolls it — empty List arrives as `$null`, single-item List arrives as the item). Also `@($someList)` misbehaves on pwsh 7.6 builds ("Argument types do not match" when assigned to a NoteProperty), and `Mandatory` parameters reject empty collections ("Cannot bind argument... empty collection"). DiskRescueLib patterns to copy: range helpers (`Add-DiskRescueRange`, `Populate-DiskRescueRangeList`) MUTATE a caller-created `List[object]` in place and return nothing; always count with `.Count` on the typed list, never `@($x).Count`.
