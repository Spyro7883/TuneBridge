---
phase: "02-input-detection"
plan: "02"
subsystem: "UI / Input Layer"
tags: ["pyside6", "migration", "liquid-glass", "stat-cards", "url-classification"]

dependency_graph:
  requires: ["02-01"]
  provides: ["tunebridge.py PySide6", "classify_url", "StatCard", "PasteTextEdit", "_Dispatcher"]
  affects: ["Phase 3 processing pipeline (uses BatchTable row ids + _Dispatcher)"]

tech_stack:
  added: ["PySide6 6.11.1", "QMainWindow", "QTableWidget", "QTextEdit", "Signal/Slot"]
  patterns: ["Qt Signal/Slot thread bridge", "Bento Grid StatCard", "QSS Liquid Glass theme"]

key_files:
  created: []
  modified:
    - tunebridge.py
    - tests/test_tunebridge.py

decisions:
  - "SongStatus values use plain 'Done'/'Failed' (no checkmarks) per plan spec"
  - "_on_clear callback pattern used on BatchTable so table.clear() resets StatCards on TuneBridgeApp"
  - "_start_demo method retained for test_worker_count_formula backward-compat"
  - "Test file fully rewritten from tkinter to PySide6 (31 tests)"

metrics:
  duration: "~20 min"
  completed: "2026-05-13T11:42:00Z"
  tasks_completed: 1
  tasks_total: 1
---

# Phase 02 Plan 02: PySide6 Migration + Phase 2 Features + StatCards Summary

**One-liner:** Full PySide6 migration of tunebridge.py — Liquid Glass QSS, classify_url(), _Dispatcher Signal bridge, StatCard Bento Grid, PasteTextEdit paste-and-classify, BatchTable._on_clear callback.

---

## Tasks Completed

| Task | Description | Commit | Status |
|------|-------------|--------|--------|
| 1 | Write tunebridge.py PySide6 + rewrite tests | 588b711 | Done |

---

## What Was Built

### tunebridge.py — complete rewrite

- **TUNEBRIDGE_QSS** — Liquid Glass dark theme with `#121212` background, rgba borders, Segoe UI typography, custom scrollbar.
- **SongStatus(Enum)** — 9 values (QUEUED through FAILED), plain "Done"/"Failed" (no checkmarks per plan spec).
- **classify_url(url)** — Module-level function, importable without PySide6. Returns "Spotify" / "YouTube" / None via compiled regex.
- **_Dispatcher(QObject)** — `row_status_changed = Signal(int, str)`. Connects to `BatchTable.update_row_status` on init. Replaces Phase 1 queue+after polling pattern.
- **StatCard(QWidget)** — `count() -> int`, `set_count(n) -> None`. Bento Grid card with rgba tint border matching color_hex. Two instances: `_card_valid` (#1DB954 green) and `_card_invalid` (#EF4444 red).
- **BatchTable(QWidget)** — Wraps `QTableWidget`. `add_row(url, title, url_type) -> int`. `update_row_status(row_id, status)` updates cols 0+2, never touches col 1 (Type). `clear()` calls `_on_clear` callback after emptying.
- **PasteTextEdit(QTextEdit)** — `urls_pasted = Signal(str)`. `insertFromMimeData` emits signal, suppresses default insertion (widget stays empty, placeholder visible).
- **TuneBridgeApp(QMainWindow)** — `_MAX_WORKERS = 4`. Wires `_paste_box.urls_pasted → _process_urls`. Sets `table._on_clear` lambda to reset both StatCards. `_start_demo()` retained for test backward-compat.

### tests/test_tunebridge.py — full rewrite (31 tests)

Replaced tkinter-based test file with PySide6 tests covering:
- `classify_url` (9 tests: Spotify track/album/playlist/artist, YouTube watch/short, invalid, empty, blank)
- `SongStatus` enum values
- `StatCard` widget count API (3 tests)
- `TuneBridgeApp` window properties (6 tests)
- `BatchTable` row management (6 tests including `_on_clear` reset)
- `_process_urls` stat card wiring + status bar messages (4 tests)
- `_start_demo` min() worker cap formula (1 test)

**Result: 31 passed, 0 failed**

---

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] PySide6 not installed**
- **Found during:** Task 1 (first test run)
- **Issue:** `ModuleNotFoundError: No module named 'PySide6'`
- **Fix:** `pip install PySide6` (installed 6.11.1)
- **Commit:** included in 588b711

**2. [Rule 2 - Missing functionality] Test file rewrite required**
- **Found during:** Task 1 (reading test file)
- **Issue:** Existing `tests/test_tunebridge.py` used tkinter/ttk fixtures incompatible with PySide6 migration. Plan lists `tests/test_tunebridge.py` under `files_modified`.
- **Fix:** Completely rewrote test file for PySide6. 31 tests covering all plan behavior requirements.
- **Files modified:** `tests/test_tunebridge.py`
- **Commit:** 588b711

**3. [Rule 1 - Bug] classify_url("   ") edge case**
- **Found during:** Test design
- **Issue:** classify_url strips whitespace in regex search but empty/blank strings need None.
- **Fix:** `if not url` guard catches empty string; blank-only URLs don't match any regex — return None naturally. Added explicit test.

### No Architectural Changes

All work completed within original file scope. No new tables, services, or infrastructure.

---

## Known Stubs

None. All data flows are wired: PasteTextEdit → _process_urls → BatchTable + StatCards. No placeholder or TODO values in rendered UI paths.

---

## Threat Flags

None. All STRIDE mitigations from plan threat model are implemented:
- T-02-05 (DoS / insertFromMimeData): `if raw.strip()` guard present.
- No new network endpoints, auth paths, or file access patterns introduced.

---

## Self-Check

**Files exist:**
- tunebridge.py: FOUND
- tests/test_tunebridge.py: FOUND
- .planning/phases/02-input-detection/02-02-SUMMARY.md: FOUND

**Commits exist:**
- 588b711: feat(02-02): migrate tunebridge.py to PySide6 — FOUND

**Test result:** 31 passed, 0 failed

## Self-Check: PASSED
