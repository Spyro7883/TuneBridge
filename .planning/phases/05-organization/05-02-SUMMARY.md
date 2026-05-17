---
phase: "05-organization"
plan: "02"
subsystem: "static-symbols"
tags: ["tdd", "wave-1", "organization", "folder-dialog", "pyside6"]
dependency_graph:
  requires: ["tests/test_organization.py — 14 RED-gate tests"]
  provides: ["FolderConfirmDialog", "_dialog_lock", "SongStatus.SKIPPED", "SongStatus.FAILED_SAVE", "_Dispatcher.folder_requested", "_Dispatcher.folder_batch_done"]
  affects: ["tunebridge.py — Wave 2 adds threading wiring on top of these symbols"]
tech_stack:
  added: ["QDialog", "QFileDialog", "QLineEdit"]
  patterns: ["QDialog modal pattern", "Path.is_dir() Windows-safe guard (empty-string check before is_dir)", "Signal(int) dispatcher pattern"]
key_files:
  created: []
  modified:
    - tunebridge.py
    - tests/test_tunebridge.py
decisions:
  - "_dialog_lock at module level (not class level) — shared singleton across all executor threads"
  - "FolderConfirmDialog._validate: bool(text.strip()) and Path(text.strip()).is_dir() — empty string MUST be checked before is_dir() on Windows (Pitfall 1)"
  - "FolderConfirmDialog placed above TuneBridgeApp class — import contract resolved, RED-gate ImportError eliminated"
  - "test_status_enum_values updated to include SKIPPED + FAILED_SAVE — enum exhaustiveness check maintained"
metrics:
  duration: "5 minutes"
  completed: "2026-05-17"
  tasks_completed: 2
  tasks_total: 2
  files_created: 0
  files_modified: 2
---

# Phase 5 Plan 02: Wave 1 Static Symbols Summary

## One-liner

All Phase 5 static symbols added to tunebridge.py; FolderConfirmDialog fully functional as standalone dialog; 4 dialog unit tests GREEN.

## What Was Built

**tunebridge.py** — 5 new symbols:
- `_dialog_lock = threading.Lock()` at module level (after `_download_lock`)
- `SongStatus.SKIPPED = "Skipped — folder"` and `SongStatus.FAILED_SAVE = "Failed — save"`
- `_STATUS_COLORS` entries for both new statuses
- `_Dispatcher.folder_requested = Signal(int)` and `_Dispatcher.folder_batch_done = Signal()`
- `FolderConfirmDialog(QDialog)` class above `TuneBridgeApp` — full implementation with `_validate`, `_browse`, `_on_confirm`, `result_path`

**tests/test_tunebridge.py** — `test_status_enum_values` updated with 2 new enum values.

## Tasks

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add _dialog_lock, SongStatus/colors/signals | 6a1ee4f | tunebridge.py |
| 2 | Add FolderConfirmDialog class + fix enum test | c476678 | tunebridge.py, tests/test_tunebridge.py |

## Verification Results

- Dialog tests GREEN: `test_confirm_disabled_empty_text`, `test_confirm_disabled_nonexistent_path`, `test_confirm_enabled_valid_dir`, `test_browse_calls_get_existing_directory` — 4 passed
- Regression gate: `pytest tests/ --ignore=tests/test_organization.py` → **62 passed**
- Symbol import: `from tunebridge import FolderConfirmDialog, SongStatus, _dialog_lock` → OK
- `SongStatus.SKIPPED.value` → `"Skipped — folder"`, `SongStatus.FAILED_SAVE.value` → `"Failed — save"`

## Deviations from Plan

- `test_status_enum_values` required update (not explicitly listed in plan tasks) — enum exhaustiveness test was strict; added SKIPPED + FAILED_SAVE entries.

## Known Stubs

- `FolderConfirmDialog` is fully functional as a standalone dialog. Threading wiring (_folder_worker, _show_folder_dialog slot, closeEvent extension) deferred to Wave 2 (Plan 05-03).
- Remaining 10 tests in test_organization.py still fail (expected — Wave 2/3 items).

## Threat Flags

- T-05-W1-01 (Tampering / _validate): mitigated — `bool(text.strip()) and Path(text.strip()).is_dir()` prevents Windows `Path('').is_dir() == True` bypass.

## Self-Check: PASSED

- tunebridge.py contains `_dialog_lock`: CONFIRMED
- tunebridge.py contains `FolderConfirmDialog` above `TuneBridgeApp`: CONFIRMED
- SongStatus.SKIPPED + FAILED_SAVE: CONFIRMED
- _Dispatcher.folder_requested + folder_batch_done: CONFIRMED
- 4 dialog unit tests GREEN: CONFIRMED
- 62-test regression suite passing: CONFIRMED
