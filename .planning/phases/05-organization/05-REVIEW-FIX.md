---
phase: 05-organization
fixed_at: 2026-05-17T21:09:00+03:00
review_path: .planning/phases/05-organization/05-REVIEW.md
iteration: 1
findings_in_scope: 7
fixed: 6
skipped: 1
status: partial
---

# Phase 5: Code Review Fix Report

**Fixed at:** 2026-05-17T21:09:00+03:00
**Source review:** .planning/phases/05-organization/05-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 7 (CR-01, CR-02, WR-01, WR-02, WR-03, WR-04, WR-05)
- Fixed: 6
- Skipped: 1 (WR-01 resolved by CR-01 — no separate change needed)

## Fixed Issues

### CR-01: Dual I/O execution — every row processed twice

**Files modified:** `tunebridge.py`
**Commit:** 3d4762b
**Applied fix:** Deleted the entire try/except I/O block (move/unlink/emit/`_on_folder_row_finished`) from `_folder_worker`. The method now ends after releasing `_dialog_lock`. All I/O remains exclusively in `_show_folder_dialog` on the main thread. Updated docstring to reflect new single-responsibility design.

---

### CR-02: Folder batch counters never reset between processing runs

**Files modified:** `tunebridge.py`
**Commit:** 3d4762b
**Applied fix:** Added resets for `_folder_total`, `_folder_done`, `_folder_skipped`, `_folder_failed` immediately after the download counter resets in `_start_processing`.

---

### WR-02: `_temp_paths[row_id]` direct subscript — KeyError risk in save path

**Files modified:** `tunebridge.py`
**Commit:** 3d4762b
**Applied fix:** Changed `self._temp_paths[row_id]` to `self._temp_paths.get(row_id)` in the save branch of `_show_folder_dialog`. Added early-return guard: if `temp is None`, logs a warning, emits `FAILED_SAVE`, calls `_on_folder_row_finished`, and returns — preventing the `KeyError` from propagating silently.

---

### WR-03: `FAILURE_STATUSES` missing `SongStatus.FAILED_SAVE`

**Files modified:** `tunebridge.py`
**Commit:** 3d4762b
**Applied fix:** Added `"Failed — save"` to the `FAILURE_STATUSES` frozenset. `BatchTable.update_row_status` now calls `_on_row_failed()` for Phase 5 save failures, keeping stat cards accurate.

---

### WR-04: `folder_requested` signal connected without `QueuedConnection`

**Files modified:** `tunebridge.py`
**Commit:** 3d4762b
**Applied fix:** Added `Qt` to the top-level `from PySide6.QtCore import` line. Changed the `folder_requested.connect` call to pass `Qt.ConnectionType.QueuedConnection` as the second argument, ensuring `_show_folder_dialog` always runs on the main thread event loop even when emitted from a worker thread.

---

### WR-05: `_show_folder_dialog` accesses private `self.table._table` directly

**Files modified:** `tunebridge.py`
**Commit:** 3d4762b
**Applied fix:**
- Step A: Added `get_row_title(self, row_id: int) -> str` public method to `BatchTable` after `update_row_metadata`.
- Step B: Replaced `title_item = self.table._table.item(row_id, 0); title = title_item.text() if title_item else f"Row {row_id}"` with `title = self.table.get_row_title(row_id)` in `_show_folder_dialog`.

---

## Skipped Issues

### WR-01: `_on_folder_row_finished` called from worker thread — Qt thread-safety

**File:** `tunebridge.py:1197-1230`
**Reason:** Resolved by CR-01 fix — no additional change needed. After removing the I/O block from `_folder_worker`, `_on_folder_row_finished` is only ever called from `_show_folder_dialog` on the main thread. The thread-safety concern no longer exists.
**Original issue:** `showMessage` and direct signal emit called from worker thread — undefined behavior on some platforms.

---

## Test Results

All 76 tests passed after fixes (`python -m pytest tests/ -q --tb=short -p no:warnings`).
No tests required updating — `test_organization.py` tests already exercised `_show_folder_dialog` (the correct call site) and were unaffected by the CR-01 removal.

---

_Fixed: 2026-05-17T21:09:00+03:00_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
