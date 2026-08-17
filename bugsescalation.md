# bugsescalation.md — SysDigger Audit Escalation Tracker

> Merged from BUGS.md (30 findings) + IMPROVEMENTS.md (23 recommendations).
> Full-app code audit conducted on v4.8. Items verified against source.
>
> Status: **[FIXED]** = applied during audit | **[OPEN]** = remaining work
>
> Severities: **Critical** (crash/data-loss) > **High** (wrong-data/perf) > **Medium** > **Low**

---

## Escalation 1: Thread Safety & COM Lifecycle

> All COM/WMI threading issues are interrelated — fixing the context manager
> (I-01) provides the foundation for B-21, which in turn makes B-11 easier
> to address. The LHM race (B-12) was already fixed with a lock.

| ID | Status | Sev | Description | File(s) |
|----|--------|-----|-------------|---------|
| B-12 | **[FIXED]** | High | `_get_lhm_computer` race condition — double initialization | collectors.py:709 |
| I-19 | **[FIXED]** | — | Added `threading.Lock()` around LHM check-and-create | collectors.py:709 |
| B-21 | **[FIXED]** | Medium | COM `CoUninitialize` never called (13 occurrences) — extracted `_com_context()` context manager, replaced all sites | collectors.py |
| I-01 | **[FIXED]** | — | Extracted COM init to `@contextmanager` `_com_context()` + `_wmi_namespace()` helper | collectors.py |
| B-11 | **[FIXED]** | High | WMI cross-thread COM violation via `self._wmi` fallback — removed fallback, each thread must call `_init_wmi()` | collectors.py |
| I-02 | **[FIXED]** | — | Extracted WMI connection helper `_wmi_namespace()` — tracks/cleans up per-namespace connections | collectors.py |

**Sequence:** I-01 (context manager) → B-21 (CoUninitialize in finally) → B-11 (remove cross-thread fallback) → I-02 (WMI helper)

---

## Escalation 2: Resource Handle Safety

> All resource leaks share the same pattern: handles opened without `with`
> or `finally`. Fixing them together ensures consistent resource management.

| ID | Status | Sev | Description | File(s) |
|----|--------|-----|-------------|---------|
| B-18 | **[FIXED]** | Medium | Registry keys converted to `with winreg.OpenKey(...)` consistently (15 sites) | collectors.py |
| I-03 | **[FIXED]** | — | Used `with winreg.OpenKey(...)` consistently (15+ occurrences) | collectors.py |
| B-13 | **[FIXED]** | High | Event log handles wrapped in `try/finally` (3 sites) | collectors.py |
| I-20 | **[FIXED]** | — | Wrapped `OpenEventLog`/`CloseEventLog` in `try/finally` | collectors.py |
| I-21 | **[FIXED]** | Medium | `PowerGetActiveScheme` `LocalFree` argtypes set + moved to `finally` | collectors.py |

**Sequence:** I-03 (registry `with`) → I-20 (event log `finally`) → I-21 (LocalFree argtypes)

---

## Escalation 3: Table UX — Sorting & Row Limits

> Numeric sorting (B-03) and row capping (B-30, I-11) are all table UX issues.
> The `_NumericItem` subclass from I-14/B-03 is a prerequisite for consistent
> sorting across all tables. Row capping prevents the same freeze pattern.

| ID | Status | Sev | Description | File(s) |
|----|--------|-----|-------------|---------|
| B-03 | **[FIXED]** | High | Numeric columns now sort numerically via `_NumericItem` subclass | gui.py |
| I-14 | **[FIXED]** | — | `_NumericItem(_SelBlackItem)` subclass with `__lt__` + `UserRole` numeric value | gui.py |
| B-30 | **[FIXED]** | Medium | Event log tables capped at 500 rows with "showing N of M" label | gui.py |
| I-10 | **[FIXED]** | — | Capped event log tables at 500 rows with "showing N of M" label | gui.py |
| I-11 | **[FIXED]** | Medium | Capped active connections table at 200 rows during 5s auto-refresh | gui.py |
| I-12 | **[FIXED]** | Medium | Reduced search index bloat for device tables (Name+Status only, ~200/tab) | gui.py |

**Sequence:** I-14/B-03 (numeric sorting) → I-10/B-30 (event log cap) → I-11 (connections cap) → I-12 (search index)

---

## Escalation 4: Settings & Theme Consistency

> Theme toggle (B-07) and threshold settings (B-08) are both Settings dialog
> issues. The lazy re-render (B-22) was already applied as the foundation.

| ID | Status | Sev | Description | File(s) |
|----|--------|-----|-------------|---------|
| B-22 | **[FIXED]** | High | `_on_settings_clicked` re-renders all 13 pages synchronously — now lazy | gui.py:5145 |
| B-07 | **[FIXED]** | High | Theme toggle now re-renders current page (clears `_pages_ready`) | gui.py |
| B-08 | **[FIXED]** | High | Settings → Processes thresholds wired to config (8 spinboxes: CPU/Mem/Disk/Net × warn/crit) | gui.py, config.py |
| I-17 | **[FIXED]** | — | Wired threshold spinboxes to config fields (cpu/mem/disk/net warn+crit) | config.py, gui.py |

**Sequence:** B-07 (theme re-render) → I-17/B-08 (wire thresholds to config)

---

## Escalation 5: Collector Performance

> N+1 patterns in installed programs (B-09) and updates (B-10) are the same
> anti-pattern in different collectors. Process priming (I-06) is a separate
> optimization that reduces iterations.

| ID | Status | Sev | Description | File(s) |
|----|--------|-----|-------------|---------|
| B-09 | **[FIXED]** | High | `_collect_installed_programs` — N+1 registry key opens fixed (4→1 open per subkey) | collectors.py |
| B-10 | **[FIXED]** | High | `collect_updates` — lazy KB title fetching with per-KB TTL cache | collectors.py |
| I-07 | **[FIXED]** | — | Lazy KB title fetching via `get_kb_title()` instance method with 7-day TTL cache | collectors.py |
| I-06 | **[FIXED]** | Low | Merged process priming loops (3→2 iterations on first call) | collectors.py |

**Sequence:** B-09 (registry N+1) → I-07/B-10 (lazy KB fetch) → I-06 (merge priming)

---

## Escalation 6: Data Correctness

> These are independent bugs where collected data is wrong or missing.
> Each needs its own fix but they share the theme of data accuracy.

| ID | Status | Sev | Description | File(s) |
|----|--------|-----|-------------|---------|
| B-06 | **[FIXED]** | High | Disk usage → physical disk matching — multiple partitions per disk, none dropped | collectors.py |
| B-20 | **[FIXED]** | Medium | `_collect_directx_info` — D3D12 check now independent of D3D11 success (`d3d11_ok` flag) | collectors.py |
| B-26 | **[FIXED]** | Low | `collect_wifi_info` — position-based parsing (locale-independent) | collectors.py |
| B-28 | **[FIXED]** | Medium | Defensive `.get()` on all collector data access (32+ locations in gui.py) | gui.py |

**Sequence:** B-28 (defensive `.get()`) → B-06 (disk partition mapping) → B-20 (D3D12 logic) → B-26 (wifi localization)

---

## Escalation 7: GUI Robustness

> Widget lifecycle issues where background workers reference deleted widgets.

| ID | Status | Sev | Description | File(s) |
|----|--------|-----|-------------|---------|
| B-14 | **[FIXED]** | High | Disk benchmark worker guarded with `try/except RuntimeError` for deleted widgets | gui.py |
| B-29 | **[FIXED]** | Low | `_on_nav_clicked` now clears search on nav click (exits search mode) | gui.py |

**Sequence:** B-14 (benchmark worker safety) → B-29 (nav title)

---

## Escalation 8: Code Deduplication

> Large-scale refactors that reduce line count and improve maintainability.

| ID | Status | Sev | Description | File(s) |
|----|--------|-----|-------------|---------|
| I-05 | **[FIXED]** | Low | Extracted export rendering to shared `_iter_export_sections()` generator (~355 lines removed) | gui.py |
| I-16 | **[FIXED]** | Low | Removed redundant in-function imports + moved movable ones to module level | collectors.py, gui.py |

**Sequence:** I-16 (remove redundant imports) → I-05 (export refactor)

---

## Escalation 9: Tools Page Accessibility

> UX improvements for the Tools page.

| ID | Status | Sev | Description | File(s) |
|----|--------|-----|-------------|---------|
| I-22 | **[FIXED]** | Low | Added keyboard accessibility to `_ToolCard` (Enter/Space activation + `StrongFocus`) | gui.py |
| I-23 | **[FIXED]** | Low | Tool card mode badge shows tooltip with all mode labels | gui.py |

**Sequence:** I-22 (keyboard) → I-23 (badge tooltip)

---

## Already Fixed During Audit (16 items)

| ID | Sev | Description |
|----|-----|-------------|
| B-01 | Critical | Restored `_collect_uefi_info()` method definition (UEFI/Secure Boot/TPM now collected) |
| B-02 | Critical | Cleared `_sensor_value_labels` + `_sensor_minmax` in `_populate_sensors` (crash fix) |
| B-04 | Medium | Cleared `_sensor_minmax` on manual refresh (stale min/max) |
| B-05 | Low | Version string 4.7→4.8 in About dialog |
| B-12 | High | LHM initialization lock (double-init race) |
| B-15 | Medium | Pruned stale PIDs from `_process_io_prev` |
| B-16 | Low | Removed duplicate IAD entry in `_CLOUDFLARE_COLOS` |
| B-17 | Medium | Removed dead power plan sub-settings block |
| B-19 | Medium | Added HTTP status check to ext_ip collection |
| B-22 | High | Lazy page re-render after settings (was rebuilding all 13 pages) |
| B-23 | Medium | Reused single QTimer for refresh dot pulse |
| B-24 | Low | Removed dead `QSS =` line |
| B-25 | Low | Removed dead `QTableWidgetItem` creation |
| B-27 | Medium | Stored tool card name/desc as attributes (eliminated `findChild` per keystroke) |
| I-08 | — | Store tool card name/desc as instance attributes (= B-27) |
| I-09 | — | Prune `_process_io_prev` dict (= B-15) |
| I-13 | — | Reuse refresh dot QTimer (= B-23) |
| I-15 | — | Moved Sparkline `paintEvent` imports to module level |
| I-18 | — | HTTP status check ext_ip (= B-19) |

---

## Summary

| Status | Count |
|--------|-------|
| **[FIXED]** | 53 (all items resolved) |
| **[OPEN]** | 0 |
| **Total** | 53 |

| Escalation | Open Items | Priority |
|------------|-----------|----------|
| 1. Thread Safety & COM | 0 ✅ | High |
| 2. Resource Handle Safety | 0 ✅ | High |
| 3. Table UX | 0 ✅ | High |
| 4. Settings & Theme | 0 ✅ | High |
| 5. Collector Performance | 0 ✅ | High |
| 6. Data Correctness | 0 ✅ | Medium |
| 7. GUI Robustness | 0 ✅ | Medium |
| 8. Code Deduplication | 0 ✅ | Low |
| 9. Tools Page Accessibility | 0 ✅ | Low |

---

## v4.17 Audit (post-v4.14 follow-up)

> Full codebase re-audit conducted after v4.14. Found 25 new items (2 High,
> 14 Medium, 9 Low) across gui.py, collectors.py, and tools.py.

### High

| ID | Sev | Description | File(s) |
|----|-----|-------------|---------|
| A-01 | High | Bufferbloat streaming HTTP response (`_req.get(..., stream=True)`) never closed in `_run_bufferbloat_with_progress` — used `with` | gui.py:2917 |
| A-02 | High | `_fetch_kb_title` HTTP response never closed — used `with` | collectors.py:2444 |
| A-03 | High | `run_speed_test` Cloudflare meta lookup response never closed — used `with` | collectors.py:2748 |
| A-04 | High | `run_speed_test` upload `requests.post()` Response discarded without `with`/`close()` — used `with` | collectors.py:2800 |
| A-05 | High | `run_bufferbloat_test` upload `requests.post()` Response discarded — used `with` | collectors.py:2949 |
| A-06 | High | `_TRIM_SSD` false-negative on non-numeric `Get-PhysicalDisk.DeviceId` (NVMe storage spaces) — added type check + try/catch fallback | tools.py:574 |
| A-07 | High | `_CHECK_HDD` (chkdsk /f, /r) lacked `confirm=True` — added | tools.py:1796 |

### Medium

| ID | Sev | Description | File(s) |
|----|-----|-------------|---------|
| A-08 | Medium | `_make_card` ordering bug — `insertWidget(count-1)` scrambled card order on pages without trailing stretch (Speed Test, Network Adapters). Rewrote to insert before last stretch item, or append if no stretch | gui.py:1944 |
| A-09 | Medium | Process tree dropped orphaned processes when any PPID was None — changed to always use comprehensive orphan scan | gui.py:5190 |
| A-10 | Medium | PDH query state accessed without lock from two threads (`_read_amd_per_core_freqs`) — added `_pdh_lock` | collectors.py:959 |
| A-11 | Medium | `_AUTOPILOT_HASH` UTF-8/Default encoding mismatch (wrote UTF-8, read Default) + fragile CSV parsing — fixed to read UTF-8 + bounds-check | tools.py:915,972 |
| A-12 | Medium | `_WU_INSTALL` (Windows Update install) lacked `confirm=True` — added | tools.py:1896 |
| A-13 | Medium | `_HIBERNATE_OFF`/`_HIBERNATE_ON` locale-dependent regex on `powercfg /a` output — replaced with `Test-Path hiberfil.sys` | tools.py:1591,1615 |
| A-14 | Medium | `D3D11CreateDevice` COM objects could leak on `ArgumentError` (argtypes not set) — moved COM release to `finally` block, broadened `except` to `Exception` | collectors.py:3834 |
| A-15 | Medium | `updates.sort` sorted `Installed On` as locale string, not chronological — added `_parse_date` with multiple format fallbacks | collectors.py:2429 |

### Low

| ID | Sev | Description | File(s) |
|----|-----|-------------|---------|
| A-16 | Low | `_on_sensor_refresh_tick` missing `_closing` guard — could create new QTimer after closeEvent, crash on deleted widget | gui.py:2412 |
| A-17 | Low | `_on_tool_reboot` `subprocess.Popen(["shutdown",...])` not wrapped in try/except — added error handling | gui.py:4041 |
| A-18 | Low | Missing `setSortingEnabled(True)` on 6 tables: Active Connections, Event Log (System + Application), BSOD History, Restore Points, Environment Variables, 5 device tables via `_make_device_table` — added to all | gui.py |
| A-19 | Low | `_sensor_spark_data` retained stale sensor keys (not cleared in `_populate_sensors`) — added `.clear()` call | gui.py:4600 |
| A-20 | Low | PDH query handle never closed on app exit — added `Collector.close()` method, called from `closeEvent` | collectors.py:969 |
| A-21 | Low | `collect_ext_ip` HTTP responses (ipify + ipinfo) not closed with `with` — fixed | collectors.py:1822,1830 |
| A-22 | Low | `_RESET_SPOOLER` lacked `confirm=True` (loses pending print jobs) — added | tools.py:1759 |
| A-23 | Low | `_REMOVE_HID_ERRORS` lacked `confirm=True` — added for consistency | tools.py:1807 |
| A-24 | Low | `_WIFI_PASSWORD` didn't escape `"` in profile name passed to netsh — added `-replace '"', '`"'` | tools.py:816 |
| A-25 | Low | `_INSTALL_SCAN`/`_INSTALL_FIX` substituted `__LIB__`/`__BACKUP__` into double-quoted PowerShell strings — changed to single-quoted | tools.py:431,457 |

### Dead code removed

| ID | File(s) | Description |
|----|---------|-------------|
| A-26 | collectors.py:235 | `del conn` in `_wmi_namespace` `finally` was a no-op (only cleared local alias, not caller's reference) — replaced with `conn = None` + explanatory comment |
| A-27 | collectors.py:295 | Dead `static_fields = {}` assignment (reassigned without being read) — removed |
| A-28 | collectors.py:2358 | Redundant `except (FileNotFoundError, Exception)` (FileNotFoundError is subclass of Exception) — simplified to `except Exception` |

### Patterns verified correct (not reported as issues)

- `_SelBlackItem` / `_NumericItem` applied to all color-coded cells ✓
- `_setup_table_copy` called right before `addWidget` on all tables ✓
- `setSortingEnabled(True)` called AFTER population on tables that already had it ✓
- Tab + scroll persistence applied to `_populate_network` and `_populate_processes` ✓
- `_sensor_value_labels` + `_sensor_minmax` + `_sensor_sparklines` cleared at top of `_populate_sensors` and in `_on_refresh_clicked` ✓
- `__INPUT__` single-quote escaping in `_collect_text_input` ✓
- Defensive `.get()` used on all collector data access in populate methods ✓
- No `QTimer.singleShot` from worker threads ✓
- No mutable default arguments ✓
- All `winreg.OpenKey` calls use `with` ✓
- All event log handles use `try/finally` ✓
- All ad-hoc WMI namespaces use `with self._wmi_namespace(...)` ✓
- `_com_context()` pairs `CoInitialize`/`CoUninitialize` in `finally` ✓

### Summary

| Status | Count |
|--------|-------|
| **[FIXED]** | 28 (all items resolved) |
| **[OPEN]** | 0 |
| **Total** | 28 |
