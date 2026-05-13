---
phase: 02-input-detection
plan: 01
subsystem: testing
tags: [pyside6, pytest, tdd, red-state, classify_url, batch-table, stat-card]

requires:
  - phase: 01-foundation
    provides: SongStatus enum, BatchTable, TuneBridgeApp (tkinter Phase 1 baseline)

provides:
  - PySide6 test scaffold with 25 test functions covering Phase 1 behavior and Phase 2 paste/classify/StatCard behavior
  - TDD RED gate: all Phase 2 tests fail until 02-02 implements PySide6 rewrite

affects:
  - 02-02 (GREEN gate — implement PySide6 TuneBridgeApp to make tests pass)

tech-stack:
  added: [PySide6 (QApplication, QMimeData, QColor), pytest fixtures with session-scoped qapp]
  patterns:
    - session-scoped QApplication fixture to avoid multiple-init errors
    - QMimeData simulation for paste input testing
    - window fixture yields TuneBridgeApp, calls close() on teardown

key-files:
  created: []
  modified:
    - tests/test_tunebridge.py

key-decisions:
  - "Test count is 25 (not 20 as stated in plan prose) — plan code block is authoritative; prose count was imprecise"
  - "Phase 1 enum tests check 'Done'/'Failed' (no symbols) — this ensures RED state on current tunebridge.py which has 'Done checkmark'/'Failed cross' values"
  - "classify_url imported at module level — allows unit tests to run without QApplication"

patterns-established:
  - "QMimeData simulation: create QMimeData(), setText(), call insertFromMimeData() on PasteTextEdit"
  - "BatchTable accessed via window.table._table (QTableWidget) at row_id, column_index"
  - "StatCard counts via window._card_valid.count() and window._card_invalid.count()"

requirements-completed:
  - INP-01
  - INP-02
  - INP-03

duration: 5min
completed: 2026-05-13
---

# Phase 2 Plan 01: PySide6 Test Scaffold Summary

**25-test PySide6 scaffold replacing tkinter tests — all Phase 2 classify/paste/StatCard tests in RED state pending 02-02 rewrite**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-05-13T00:00:00Z
- **Completed:** 2026-05-13T00:05:00Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Completely replaced tkinter-based `tests/test_tunebridge.py` with PySide6 API
- 25 test functions: 8 Phase 1 behavior + 6 classify_url unit + 8 paste integration + 2 StatCard + 1 type-color preservation
- No tkinter imports anywhere in the test file
- All Phase 2 tests are in RED state (tunebridge.py still tkinter-based, no classify_url, no PasteTextEdit, no StatCard)

## Task Commits

1. **Task 1: Rewrite tests/test_tunebridge.py for PySide6** - `bf50353` (test)

## Files Created/Modified

- `tests/test_tunebridge.py` - Complete rewrite: PySide6 fixtures, 25 test functions, no tkinter

## Decisions Made

- Test count is 25 (plan prose says "20" but the code block in the plan is the authoritative specification and contains 25 functions)
- `SongStatus.DONE` and `FAILED` tested against `"Done"` and `"Failed"` (no Unicode symbols) — this ensures RED state on the current codebase which has `"Done ✓"` and `"Failed ✗"`
- `classify_url` imported at module level so unit tests run without QApplication fixture

## Deviations from Plan

None — plan code block executed exactly as written. Test count discrepancy (prose "20" vs actual 25) was in the plan itself; the code block is authoritative.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Known Stubs

None — this is a test-only file. No data stubs.

## Threat Flags

None — test file only, no new network endpoints or auth paths.

## Next Phase Readiness

- TDD RED gate satisfied: 25 tests exist, all Phase 2 tests will fail against current tkinter implementation
- Ready for 02-02 (GREEN gate): implement PySide6 TuneBridgeApp with classify_url, PasteTextEdit, BatchTable (QTableWidget), StatCard
- Phase 1 tests (test_song_status_values etc.) will also fail RED until 02-02 updates SongStatus enum values

---

## Self-Check: PASSED

- `tests/test_tunebridge.py` exists and contains 25 test functions
- Commit `bf50353` present in git log
- No tkinter imports in test file

---
*Phase: 02-input-detection*
*Completed: 2026-05-13*
