---
phase: 05-organization
reviewed: 2026-05-17T17:58:00Z
depth: standard
files_reviewed: 3
files_reviewed_list:
  - tunebridge.py
  - tests/test_organization.py
  - tests/test_tunebridge.py
findings:
  critical: 2
  warning: 5
  info: 1
  total: 8
status: issues_found
---

# Phase 5: Code Review Report

**Reviewed:** 2026-05-17T17:58:00Z
**Depth:** standard
**Files Reviewed:** 3
**Status:** issues_found

## Summary

Phase 5 introduces `FolderConfirmDialog`, `_dialog_lock`, `SongStatus.SKIPPED/FAILED_SAVE`,
`_folder_worker`, `_show_folder_dialog`, `_on_folder_row_finished`, and a `threading.Event`
queue pattern. The dialog and validation logic are clean. Two critical structural bugs exist
in the I/O orchestration: every row's file operations are performed **twice** (once in
`_show_folder_dialog`, once redundantly in `_folder_worker`), and batch counters for the
folder phase are never reset between runs.

---

## Critical Issues

### CR-01: Dual I/O execution — every row processed twice

**File:** `tunebridge.py:1116-1141` and `tunebridge.py:1170-1195`

**Issue:** Both `_folder_worker` and `_show_folder_dialog` contain an identical I/O block
(shutil.move / Path.unlink / emit status / call `_on_folder_row_finished`). The execution
sequence per row is:

1. Worker emits `folder_requested` → main thread runs `_show_folder_dialog`
2. `_show_folder_dialog` sets the threading.Event, **then immediately runs the full I/O block**
   — moves/deletes the file and calls `_on_folder_row_finished`
3. `_folder_worker` unblocks, reads `result`, and **runs the full I/O block again** on the
   same (now-missing) temp file

Consequences:
- `_on_folder_row_finished` is invoked **twice per row**, doubling counter increments.
  With `_folder_total = N`, the batch-done condition `finished >= _folder_total` is met at
  `N/2` rows, firing `folder_batch_done` prematurely.
- On the save path, `shutil.move` is called twice on the same source path. The second call
  raises `OSError` (file not found), causing the row to also emit `FAILED_SAVE` — so a
  successfully saved row ends up with a failure status.
- On the skip path, `Path.unlink` is called twice; the second call raises on Python < 3.8
  or silently no-ops with `missing_ok=True`.

The design intent (per docstring) is that `_show_folder_dialog` performs I/O on the main
thread (required by test contract). The I/O block in `_folder_worker` must be removed.

**Fix:** Delete lines 1116–1141 of `_folder_worker` entirely — the I/O, status emit, and
`_on_folder_row_finished` call. The worker's responsibility ends after releasing
`_dialog_lock`. `_show_folder_dialog` already handles all downstream work.

```python
def _folder_worker(self, row_id: int) -> None:
    if self._closing.is_set():
        return

    with _dialog_lock:
        ev = threading.Event()
        self._folder_events[row_id] = ev
        self._folder_results[row_id] = None

        if not self._closing.is_set():
            self._dispatcher.folder_requested.emit(row_id)
            ev.wait()
    # Lock released. I/O, status emit, and counter update are handled
    # by _show_folder_dialog on the main thread. Nothing more to do here.
```

---

### CR-02: Folder batch counters never reset between processing runs

**File:** `tunebridge.py:1315-1319` (`_start_processing`)

**Issue:** `_start_processing` resets `_download_total`, `_download_done`, and
`_download_failed` before each batch (lines 1316–1318), but **does not reset**
`_folder_total`, `_folder_done`, `_folder_skipped`, or `_folder_failed`. A second batch
run accumulates on top of the first run's values. If run 1 had 3 successful saves
(`_folder_done = 3`, `_folder_total = 3`) and run 2 has 2 rows, after run 2's first
row finishes `finished = 4 >= _folder_total = 5` — the batch-done condition is never met,
and after the second row `finished = 5 = _folder_total` fires correctly, but the status
bar will show `Saved 5` instead of `Saved 2`.

**Fix:** Reset all folder counters in `_start_processing`:

```python
# Reset batch counters
self._download_total   = len(jobs)
self._download_done    = 0
self._download_failed  = 0
# Reset folder phase counters for this batch
self._folder_total     = 0
self._folder_done      = 0
self._folder_skipped   = 0
self._folder_failed    = 0
```

---

## Warnings

### WR-01: `_on_folder_row_finished` called from worker thread performs non-thread-safe Qt operations

**File:** `tunebridge.py:1197-1230`

**Issue:** The docstring states this method is "Called directly from _folder_worker (off
main thread)" and relies on GIL protection for counter increments. However, at lines
1226–1230 the method calls `self._dispatcher.folder_batch_done.emit()` and
`self.statusBar().showMessage(...)` directly. Qt widget operations (`showMessage`) are
not thread-safe and must only be called on the main thread. `emit()` on a signal is
thread-safe only if the connection type is `QueuedConnection`; a direct call to
`showMessage` from a worker thread is undefined behavior and can crash on some platforms.

After applying the CR-01 fix (removing worker I/O), this method will only be called from
`_show_folder_dialog` on the main thread, eliminating the problem. If the dual-call
architecture is intentionally retained, the emit and showMessage calls must be marshalled
to the main thread via a signal.

**Fix:** Apply CR-01 fix. If `_on_folder_row_finished` must remain callable from workers,
add a dedicated signal:
```python
# In _Dispatcher:
folder_row_finished = Signal(int, str)
# Connect: self._dispatcher.folder_row_finished.connect(self._on_folder_row_finished)
# Call: self._dispatcher.folder_row_finished.emit(row_id, status)  # thread-safe
```

---

### WR-02: `_folder_worker` save path uses `self._temp_paths[row_id]` without `.get()` — KeyError risk

**File:** `tunebridge.py:1131`

**Issue:** The save branch (result is not None) accesses `self._temp_paths[row_id]`
with a direct dict subscript. If `_temp_paths` does not contain `row_id` (e.g., the
download worker failed silently and never populated it, or a prior skip cleared it),
this raises `KeyError`. `KeyError` is not caught by the `except OSError` block at line
1137, so the exception propagates out of the thread pool worker, silently terminating
the thread with no status update on the row — the row stays at "Awaiting folder"
indefinitely.

This is a secondary consequence of CR-01 (the block is dead code after the fix), but
it is independently dangerous if the block is kept.

**Fix:** Use `.get()` with an early return:
```python
with self._temp_paths_lock:
    temp = self._temp_paths.get(row_id)
if temp is None:
    logging.getLogger(__name__).warning("No temp path for row %d", row_id)
    self._dispatcher.row_status_changed.emit(row_id, SongStatus.FAILED_SAVE.value)
    self._on_folder_row_finished(row_id, SongStatus.FAILED_SAVE.value)
    return
final = Path(shutil.move(str(temp), str(result)))
```

---

### WR-03: `FAILURE_STATUSES` does not include `SongStatus.FAILED_SAVE` — stat card not updated on Phase 5 failures

**File:** `tunebridge.py:157-158`

**Issue:** `FAILURE_STATUSES` is used in `BatchTable.update_row_status` (line 663) to
call `_on_row_failed()` — which decrements the valid stat card and increments the invalid
stat card. It only contains `"Failed — metadata"` and `"Failed — download"`. Phase 5
introduced `SongStatus.FAILED_SAVE` ("Failed — save"), but this status is not in
`FAILURE_STATUSES`. When a save fails in Phase 5, the stat cards are not updated —
the row counts misrepresent the actual result to the user.

**Fix:**
```python
FAILURE_STATUSES: frozenset[str] = frozenset({
    "Failed — metadata",
    "Failed — download",
    "Failed — save",    # D-10: Phase 5 save failure
})
```

---

### WR-04: `folder_requested` signal connected without `Qt.QueuedConnection` — potential direct-call from worker thread

**File:** `tunebridge.py:956`

**Issue:**
```python
self._dispatcher.folder_requested.connect(self._show_folder_dialog)
```
No `Qt.ConnectionType.QueuedConnection` argument is passed. PySide6 chooses the
connection type based on whether the emitter and receiver are in the same thread at
connect time. Since `_Dispatcher` is created on the main thread and `TuneBridgeApp` is
also on the main thread, PySide6 will use `DirectConnection`. When `_folder_worker`
(running on a thread-pool thread) emits `folder_requested`, a `DirectConnection` will
invoke `_show_folder_dialog` **synchronously on the worker thread** — exactly the
threading violation the docstring at line 1149 warns against ("NEVER call this from a
worker thread — dlg.exec() requires the main thread event loop").

**Fix:** Explicitly request a queued connection:
```python
from PySide6.QtCore import Qt
self._dispatcher.folder_requested.connect(
    self._show_folder_dialog,
    Qt.ConnectionType.QueuedConnection,
)
```

---

### WR-05: `_show_folder_dialog` accesses `self.table._table` directly — bypasses encapsulation and is fragile under table refactoring

**File:** `tunebridge.py:1151`

**Issue:**
```python
title_item = self.table._table.item(row_id, 0)
```
`_table` is a private attribute of `BatchTable`. This cross-object private access creates
tight coupling: any internal refactor of `BatchTable` silently breaks `_show_folder_dialog`
with an `AttributeError`. `BatchTable` already has `update_row_status` and
`update_row_metadata` public methods; a `get_row_title(row_id)` accessor should be added.

**Fix:** Add a public accessor to `BatchTable`:
```python
def get_row_title(self, row_id: int) -> str:
    item = self._table.item(row_id, 0)
    return item.text() if item else f"Row {row_id}"
```
Then in `_show_folder_dialog`:
```python
title = self.table.get_row_title(row_id)
```

---

## Info

### IN-01: `classify_url` empty-string guard does not cover whitespace-only strings

**File:** `tunebridge.py:342`

**Issue:** The guard `if not url: return None` returns early for `""` but not for `"   "`.
A whitespace-only string passes both regex searches (both return `None` by fallthrough),
so the function happens to return `None` correctly — but only by accident. The test
`test_classify_none_like_blank` passes, but a reader or future maintainer cannot rely on
the guard. The intent of the guard is to reject empty-or-blank input.

**Fix:**
```python
if not url or not url.strip():
    return None
```

---

_Reviewed: 2026-05-17T17:58:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
