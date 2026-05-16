---
phase: 4
plan: "04-03"
subsystem: toolbar-ui
tags: [pyside6, toolbar, segmented-control, start-button, qbuttongroup, wave-2]
dependency_graph:
  requires: ["04-02"]
  provides: ["toolbar-row-ui", "refresh-start-button", "hz-toggle"]
  affects: ["tunebridge.py"]
tech_stack:
  added: ["QButtonGroup", "QPushButton"]
  patterns: ["segmented-control-via-QButtonGroup", "all-rows-gate-pattern"]
key_files:
  modified: ["tunebridge.py"]
decisions:
  - "toolbar_row inserted after BatchTable wiring so _on_clear/_on_rows_removed already set before Start button is evaluated"
  - "_refresh_start_button uses self.table._table (QTableWidget) not self._table — BatchTable exposes private _table attribute"
  - "_start_processing added as pass stub to avoid AttributeError on clicked.connect at __init__ time"
metrics:
  duration: "~15 minutes"
  completed: "2026-05-16"
  tasks_completed: 2
  files_modified: 1
---

# Phase 4 Plan 03: Toolbar UI (Wave 2) Summary

Toolbar row with Hz segmented control and Start Processing button. 440Hz/432Hz mutual-exclusion via QButtonGroup. Start button disabled until all-rows-METADATA_READY gate. 3 DL-03 tests GREEN.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add QButtonGroup/QPushButton imports and hz_btn/start_btn QSS | e471be7 | tunebridge.py |
| 2 | Build toolbar row, implement _refresh_start_button, wire signals | 78258d7 | tunebridge.py |

## What Was Built

- `QButtonGroup` and `QPushButton` added to PySide6.QtWidgets import block (alphabetical order)
- `TUNEBRIDGE_QSS` gains `QPushButton[hz_btn="true"]` and `QPushButton#start_btn` QSS rules (default, checked, disabled states)
- `toolbar_row` QHBoxLayout inserted between stat cards and batch table in `TuneBridgeApp.__init__`
- `_btn_440` / `_btn_432` checkable QPushButtons with `hz_btn=True` property; 440Hz checked by default
- `_hz_group` QButtonGroup with `setExclusive(True)` enforcing mutual exclusion; button IDs 440 and 432
- `_btn_start` QPushButton with objectName `start_btn`, starts disabled
- `_refresh_start_button` method: disabled if 0 rows; enabled iff ALL rows show `SongStatus.METADATA_READY.value`
- `_dispatcher.row_status_changed` connected to `_refresh_start_button` so every status change re-evaluates gate
- `_refresh_start_button()` called at end of `_process_urls` after new rows are added
- `_start_processing` stub (Wave 3 replaces body)

## Verification Results

```
python -m pytest tests/test_download_pipeline.py::test_hz_toggle_default_440 \
  tests/test_download_pipeline.py::test_start_button_disabled_on_mixed_status \
  tests/test_download_pipeline.py::test_start_button_enabled_all_ready -v
```
Result: **3 passed**

Full regression:
```
python -m pytest -q
```
Result: **55 passed, 7 failed** — 7 failures are the Wave 3 tests (`_download_worker` not yet implemented, expected RED until 04-04).

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

| Stub | File | Line | Reason |
|------|------|------|--------|
| `_start_processing` — `pass` body | tunebridge.py | ~903 | Wave 3 (04-04-PLAN.md) replaces with download dispatch logic |

## Threat Flags

None — no new network endpoints, auth paths, or trust boundaries introduced. UI-only changes.

## Self-Check: PASSED

- tunebridge.py exists and imports cleanly
- Commits e471be7 and 78258d7 present in git log
- 3 DL-03 tests GREEN confirmed
- 55 prior + new tests GREEN (no regressions)
