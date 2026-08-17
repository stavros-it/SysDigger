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
