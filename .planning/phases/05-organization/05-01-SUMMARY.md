---
phase: "05-organization"
plan: "01"
subsystem: "test-scaffold"
tags: ["tdd", "red-gate", "wave-0", "organization", "folder-dialog"]
dependency_graph:
  requires: []
  provides: ["tests/test_organization.py — 14 RED-gate tests"]
  affects: ["tunebridge.py — Wave 1/2/3 must turn RED tests GREEN"]
tech_stack:
  added: []
  patterns: ["pytest fixture (session-scoped qapp, function-scoped window)", "unittest.mock patch on tunebridge namespace", "threading.Event RED-gate pattern"]
key_files:
  created:
    - tests/test_organization.py
  modified: []
decisions:
  - "14 tests import FolderConfirmDialog and _dialog_lock — both missing from tunebridge.py until Wave 1 (intentional RED gate)"
  - "Option B (dialog in isolation) for tests 3/4/5 — no TuneBridgeApp needed for button state tests"
  - "Option A (patch FolderConfirmDialog + shutil.move on window) for tests 7-13 — exercises _show_folder_dialog slot"
  - "Row IDs 0-11 used across window-fixture tests to avoid collision (session-scoped qapp reuses same window)"
metrics:
  duration: "4 minutes"
  completed: "2026-05-17"
  tasks_completed: 1
  tasks_total: 1
  files_created: 1
  files_modified: 0
---

# Phase 5 Plan 01: Wave 0 RED-Gate Test Scaffold Summary

## One-liner

14 failing pytest tests establishing the Nyquist contract for FolderConfirmDialog, _dialog_lock, and folder-pipeline methods.

## What Was Built

`tests/test_organization.py` — 220-line test file with exactly 14 test functions covering all Phase 5 requirements (ORG-01 through ORG-04) and critical decisions (D-04, D-08, D-11). All 14 tests fail at import time with `ImportError: cannot import name 'FolderConfirmDialog' from 'tunebridge'` until Wave 1 adds the missing symbols.

## Tasks

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Write 14 RED-gate tests for Phase 5 organization | c3e8dec | tests/test_organization.py |

## Verification Results

- RED gate: `pytest tests/test_organization.py` → 1 ERROR (ImportError on FolderConfirmDialog) — CONFIRMED
- Regression gate: `pytest tests/ --ignore=tests/test_organization.py` → 62 passed — CONFIRMED
- Test count: `grep -c "^def test_" tests/test_organization.py` → 14 — CONFIRMED

## Test Coverage Map

| Test | Requirement | Strategy |
|------|-------------|----------|
| test_last_folder_empty_on_first | ORG-01 | Option A — window fixture |
| test_last_folder_updates_after_confirm | ORG-01 | Option A — patch FolderConfirmDialog |
| test_confirm_disabled_empty_text | ORG-02/V5 | Option B — dialog in isolation |
| test_confirm_disabled_nonexistent_path | ORG-02/V5 | Option B — dialog in isolation |
| test_confirm_enabled_valid_dir | ORG-02/V5 | Option B — dialog in isolation |
| test_browse_calls_get_existing_directory | ORG-02 | Option B — patch QFileDialog |
| test_skip_deletes_temp_and_emits_skipped | ORG-03 | Option A — patch + signal capture |
| test_skip_does_not_block_other_rows | ORG-03 | Option A — assert event set |
| test_confirm_calls_shutil_move | ORG-04 | Option A — patch shutil.move |
| test_saved_paths_populated_after_move | ORG-04 | Option A — assert _saved_paths Path |
| test_oserror_emits_failed_save | ORG-04 | Option A — OSError side_effect |
| test_folder_batch_done_emitted | D-11 | Direct call _on_folder_row_finished |
| test_status_bar_summary | D-08 | Direct call × 3, assert statusBar message |
| test_close_event_unblocks_pending_workers | D-04 | Set _folder_events, call closeEvent |

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — this is a test-only plan. No production code modified.

## Threat Flags

None — no new network endpoints, auth paths, or file access patterns introduced. Test file imports intentionally missing symbols (T-05-W0-01: accepted disposition).

## Self-Check: PASSED

- tests/test_organization.py: FOUND
- Commit c3e8dec: FOUND
- 14 test functions: CONFIRMED
- RED gate (ImportError): CONFIRMED
- Regression (62 passed): CONFIRMED
