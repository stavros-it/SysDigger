# AGENTS.md — SysPeek Agent Memory

> Operational memory for AI agents working on this codebase.
> Read this before making changes. Update after non-trivial work.
> For feature history see `roadmap.md`. For architecture see `PROJECT_CONTEXT.md`.

---

## Quick Reference

- **App name:** SysPeek (renamed from "Windows Info" in v4.5)
- **Version:** 4.11
- **Entry point:** `syspeek.pyw` (renamed from `launcher.pyw`)
- **AppUserModelID:** `"Stavros.SysPeek"`
- **Window title:** `"SysPeek  ·  Copyright (C) Stavros Antoniou"`
- **Copyright:** Copyright (C) Stavros Antoniou

## Verification Commands

```pwsh
# Compile-check (run after every code change)
python -m py_compile app.py gui.py collectors.py syspeek.pyw tools.py sensors.py helpers.py config.py lhm_process.py paths.py

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
| `tools.py` | ~1710 | Tool catalogue: 4 categories, 26 tools, 57 PowerShell modes (includes Autopilot hash with validation, disk analyzer with 8 modes incl. scan-then-pick cleanup, memory diagnostic, hosts editor, WU trigger, appx manager, dev cache cleaner, hibernate manager) |
| `config.py` | ~232 | Config dataclass (23 settings incl. 8 colorization thresholds) + JSON persistence |
| `sensors.py` | ~115 | LibreHardwareMonitorLib wrapper |
| `app.py` | ~109 | Entry point: QApplication, icon, AppUserModelID, theme, three-phase show |
| `syspeek.pyw` | ~85 | Launcher: UAC elevation, logging, crash handler |
| `helpers.py` | ~120 | fmt_bytes, fmt_speed, fmt_uptime, reg_value, etc. |
| `updater.py` | ~148 | GitHub release updater for LHM DLLs |
| `lhm_process.py` | ~310 | Portable LHM.exe process manager: downloads, launches hidden, loads PawnIO kernel driver for motherboard SuperIO sensors, cleans up on close |
| `paths.py` | ~75 | Portable path resolution: `resource_dir()` (read-only bundled assets), `data_dir()` (writable per-user data with `%LOCALAPPDATA%` fallback), `cache_dir()`, `lib_dir()`, `lhm_standalone_dir()` |
| `app_logger.py` | ~95 | Rotating file logger (with read-only location fallback to `%LOCALAPPDATA%\SysPeek\app.log`) |
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

`install_desktop_shortcut.bat` creates `SysPeek.lnk` on Desktop pointing to `syspeek.pyw` with `app.ico`. Re-run after any path/name change.

## Icon Generation

- `make_icon.py` → `app.ico` (16-256px, dark monitor with blue accent)
- `make_nav_icons.py` → 13 sidebar nav icons (24x24 PNGs)
- `make_category_icons.py` → 4 Tools-page category icons (64x64 PNGs)

## Code Audit Tracker

- **`bugsescalation.md`** — merged from BUGS.md + IMPROVEMENTS.md. 53 total items (19 fixed, 34 open) organized into 9 themed escalations with recommended fix sequences. Read this before starting audit fixes.
- **`roadmap.md` → Planned — Short Term → Audit Escalation** — 10 checklist items summarizing the open bugsescalation work. Start with Escalation 1 (Thread Safety) → 9 (Accessibility).

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
- **H-6 syspeek** UAC elevation broke when frozen — `elevate()` now detects `sys.frozen` and uses `sys.executable` directly; elevation failure shows MessageBox
- **C-1 app_logger** Crashed on read-only location — `_resolve_log_dir()` falls back to `%LOCALAPPDATA%\SysPeek\app.log`; `RotatingFileHandler` wrapped in try/except
- **C-1 portability** New `paths.py` module with `resource_dir()` / `data_dir()` for frozen-exe path resolution
- **H-1 config** `load()` crashed on wrong-typed JSON values — construction now wrapped in `try/except (TypeError, ValueError)`
- **config** UTF-8 encoding on `open()` calls (was locale-default cp1252)
- **H-5 tools** Autopilot hash hardcoded `C:\AutopilotHWID.csv` → now writes to Desktop
- **H-4 tools** powercfg energy/battery reports saved to wrong location (System32) → now uses `$env:TEMP` with `/output` flag
- **M-1 gui** Pages not re-rendered after settings/theme change — now re-adds pages 0-11 to `_pages_ready` after clearing
- **M-3 gui** `closeEvent` shutdown race — added `_closing` flag, checked in `_update_sensor_values`
- **L-1 gui** Sidebar title "System Info" → "SysPeek"
- **Packaging** New files: `paths.py`, `requirements.txt`, `syspeek.spec`, `runtime_hook.py`, `version.txt`, `build.ps1`

## PyInstaller Packaging (v4.11)

Build: `.\build.ps1` (installs deps, compile-checks, builds, signs)

- **Spec**: `syspeek.spec` — `--onedir` mode (faster startup, lower AV false-positive)
- **UAC**: `uac_admin=True` in EXE — manifest requests elevation, skips `syspeek.pyw` self-elevation
- **Frozen detection**: `syspeek.pyw` checks `getattr(sys, "frozen", False)` — skips elevation relaunch when frozen
- **Path resolution**: `paths.py` distinguishes `resource_dir()` (read-only `sys._MEIPASS`) from `data_dir()` (writable exe dir or `%LOCALAPPDATA%\SysPeek` fallback)
- **Runtime hook**: `runtime_hook.py` sets `os.chdir(exe_dir)` + `QT_PLUGIN_PATH`
- **Signing**: Set `$env:SIGN_CERT_THUMBPRINT` and run `build.ps1` — signs all exe/dll with `signtool.exe` + RFC 3161 timestamp
- **Cert recommendation**: Azure Trusted Signing (~$10/mo), EV cert (immediate SmartScreen reputation), or **SignPath Foundation** (free for open-source — see `GITHUB_SIGNING_GUIDE.md`)

## GitHub Repository (v4.11)

GitHub username: `stavros-it` (user ID: 151866740)
Git identity: `Stavros Antoniou <151866740+stavros-it@users.noreply.github.com>` (noreply email)

**State**: Initial commit created locally (`a53314f`, 74 files, 21,093 lines). Repo NOT yet created on GitHub — awaiting user to create `stavros-it/SysPeek` on github.com and push.

**Files added for GitHub:**
- `README.md` — front-page project description (features, requirements, download link, project structure, docs links, code signing policy, privacy policy)
- `LICENSE` — MIT License
- `.gitignore` — excludes runtime artifacts (`cache/`, `app.log`, `config.json`, `lib/lhm_standalone/`, `build/`, `dist/`, `__pycache__/`, `tools source/SA_WinTools_RegBackup/`)
- `.github/workflows/build-and-sign.yml` — GitHub Actions workflow (build → zip → submit to SignPath if secrets set → upload to release; falls back to unsigned zip if SignPath not configured)
- `GITHUB_SIGNING_GUIDE.md` — step-by-step guide for GitHub setup + SignPath free signing (written for non-developer)

**Files removed (stale):**
- `BUGS.md`, `IMPROVEMENTS.md` — merged into `bugsescalation.md` (stale duplicates)
- `tools source/project_context.md`, `tools source/roadmap.md` — old SA WinTools docs (not referenced by code, were bloating the exe)
- `Windows Info.7z` — old archive
- `tools source/SA_WinTools_RegBackup/` — runtime artifact (created at runtime by Install/Uninstall Fix tool)

**Committed to repo (must stay):**
- `lib/` (12 DLLs, ~3 MB) — required for the build; `lhm_standalone/` excluded via `.gitignore` (downloaded at runtime)
- `tools source/` (6 files) — `SA_WinTools_Lib.ps1` is referenced at runtime by `tools.py:43`; the `.diagcab` is bundled for the Install/Uninstall Fix tool
- `icons/`, `app.ico`, `app_preview.png` — bundled into exe and shown in README

**SignPath free signing workflow:**
1. Apply at https://signpath.org/apply (requires public GitHub repo + MIT license)
2. Set GitHub secrets: `SIGNPATH_API_TOKEN`, `SIGNPATH_ORG_ID`
3. Publish a release (tag `v4.11` → push → draft release on GitHub)
4. GitHub Actions builds → submits to SignPath → you approve at app.signpath.io → signed zip uploaded to release
5. SmartScreen reputation builds over ~100 downloads (OV cert, not EV)

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

### 18. PowerShell scripts must use `Out-String -Width 4096`
All PowerShell scripts in `tools.py` must use `Out-String -Width 4096` (not the default 80 or 500) to prevent wide table output truncation. The preamble must include `$FormatEnumerationLimit=-1` to prevent array/list truncation.

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
3. `_on_tool_finished` checks `self._path_select_pending`. If set, it parses the captured log (`_tool_log.toPlainText()`), shows a multi-select checkbox dialog (`_path_select_dlg`), and (if confirmed) substitutes `__PATHS__` into the mode's `script` and launches a second `_run_powershell_tool` call for the actual cleanup.
4. Critical-path blocklist (`_is_critical_path`) is applied to filesystem paths: `C:\Windows`, `C:\Program Files*`, `C:\ProgramData`, `C:\$Windows.~*`, `C:\Recovery`, user profile root, and any path containing `\Microsoft\` are filtered out and never shown in the dialog. Set `blocklist: False` on the spec (e.g. for Appx, which uses `Remove-AppxPackage` instead of file deletion) to disable.

`_path_select_pending` MUST be cleared in `_on_tool_stop`, `_on_tool_clear`, and on every cancel path inside `_on_tool_finished`. If left set, the next non-path_select tool's finished signal would misfire the dialog.

### 23. Tool Stop — graceful then force, with critical-op prompt (v4.11)
`_on_tool_stop` does NOT immediately `taskkill /F`. The flow is:
1. **Double-click guard**: if `self._tool_stopping` is already True, return.
2. **Critical-op prompt**: call `_is_critical_stop_operation(mode)` — returns True if the mode has `confirm=True` OR its script contains any `_CRITICAL_SCRIPT_PATTERNS` substring (`sfc /scannow`, `dism.exe /Online /Cleanup-Image`, `chkdsk`, `Optimize-Volume`, `Remove-AppxPackage`, `reagentc`, `slmgr.vbs" /ato`, `powercfg /hibernate`, `Clear-RecycleBin`, `Stop-Service`, `Start-Service`, `Set-ItemProperty`, `Remove-Item`, `Disable-PnpDevice`, `Enable-PnpDevice`, `Rename-Item`, `New-Item`, `net use * /delete`, `w32tm /unregister`/`/register`). The path_select **scan phase** is excluded (read-only) via the `self._path_select_pending is not None` check — only the cleanup phase prompts. If critical and the user clicks "No", the tool keeps running.
3. **Background kill thread** (`_stop_tool_proc_async`): Phase 1 sends `taskkill /T /PID` (no `/F`) — posts `WM_CLOSE` to windows in the tree so GUI children (Notepad, mdtsched, slmgr dialogs) can close cleanly. Polls `proc.poll()` for 3 seconds. Phase 2 falls back to `taskkill /F /T /PID` (force kill the whole tree) if the grace period expires.
4. The worker thread's `for line in proc.stdout` loop exits naturally when the process dies (pipe EOF), then emits `finished` → `_on_tool_finished` shows TERMINATED.

Mode tracking (`_tool_running_mode`, `_tool_running_name`) is set in `_run_tool_mode` / `_begin_path_select_flow` and cleared in `_on_tool_finished`, `_on_tool_stop`, `_on_tool_clear`. `closeEvent` still uses immediate `taskkill /F /T` (no grace period — app is exiting).

### 24. LHM.exe portable bridge for motherboard sensors (v4.11)
The DLL-based sensor collection (`sensors.py` + `collectors.py:_collect_sensors`) reads CPU/GPU sensors via PCI config space and ADL, but CANNOT read motherboard SuperIO sensors (fan RPM, voltages, VRM temps) without a kernel driver. The standalone `LibreHardwareMonitor.exe` loads the PawnIO kernel driver, which gives the DLL access to SuperIO chips.

**Flow:**
1. `app.py:main()` launches a background thread that calls `LhmProcess.ensure_downloaded()` (downloads LHM.exe v0.9.6 to `lib/lhm_standalone/`, cached), then `start()` (launches hidden with `SW_HIDE`), then `wait_for_driver(timeout=20s)` (polls `sc query PawnIO` until RUNNING), then `collector.set_lhm_process(proc)`.
2. `set_lhm_process()` invalidates `self._lhm_computer = None` (under `_lhm_lock`) so the next `_collect_sensors()` call recreates the `Computer` object — now with the PawnIO driver available, so `computer.Hardware` includes the SuperIO subhardware (e.g. Nuvoton NCT6687D) with all motherboard sensors.
3. On `closeEvent`, `lhm_proc.stop()` kills LHM.exe (`taskkill /F /T /PID`) and calls `_cleanup_driver_services()` which sends `sc stop` + `sc delete` for `PawnIO`, `WinRing0_1_2_0`, `WinRing0`.

**Kernel driver cleanup limitation:** `sc stop` may fail for kernel drivers that don't support unloading (the PawnIO driver remains in kernel memory until reboot). `sc delete` still succeeds and marks the service as `Disabled` — so it won't start on next boot and will be fully removed by Windows on reboot. This is a Windows limitation, not a bug. The driver being loaded is harmless (just provides I/O port access). On next SysPeek launch, if the driver is still loaded, sensors work immediately; if not, LHM.exe creates a new service.

**Config patching:** `_patch_config()` injects `<userSettings><wmiProvider>True</wmiProvider>` into `LibreHardwareMonitor.exe.config` after extraction. Although we don't use WMI (the DLL approach works once the driver is loaded), enabling WMI ensures LHM.exe fully initializes its sensor infrastructure.

**WMI bridge not used:** LHM's WMI namespace `root/LibreHardwareMonitor` requires the WMI provider to be enabled AND the LHM.exe process to register it with WMI. Even with `wmiProvider=True` in the config, the namespace wasn't available in testing. The DLL approach works directly once the PawnIO driver is loaded, so WMI is unnecessary.

**LHM.exe is NOT installed:** it's cached as files in `lib/lhm_standalone/` (not registered with Windows). The PawnIO driver service IS created (kernel drivers can't be loaded without a service), but it's marked for deletion on close. Nothing persists across reboots.
