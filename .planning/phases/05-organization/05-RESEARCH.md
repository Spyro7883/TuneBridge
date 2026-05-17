# Phase 5: Organization - Research

**Researched:** 2026-05-17
**Domain:** PySide6 modal QDialog + threading.Event serialization + shutil.move file save
**Confidence:** HIGH

## Summary

Phase 5 adds a serialized folder-confirmation dialog loop on top of the existing `_download_worker` pipeline. Every row that reaches `AWAITING` status triggers a `_folder_worker` thread, which acquires `_dialog_lock`, registers a `threading.Event`, emits `folder_requested(row_id)`, and blocks. The main thread slot shows `FolderConfirmDialog`, stores the result (Path or None sentinel), sets the event, and the worker unblocks, moves the file via `shutil.move`, then transitions to `UPLOADING`.

All five APIs needed (QDialog, QLineEdit.textChanged, QFileDialog.getExistingDirectory, threading.Event, shutil.move) are available in the installed environment and verified working. No new dependencies are required — the full implementation fits within the existing import set.

One non-obvious pitfall: `Path('').is_dir()` returns `True` on Windows. The Confirm button validation must check `text.strip() != ''` before calling `is_dir()` — without this guard, the Confirm button enables when the field is empty.

**Primary recommendation:** Mirror `_download_lock` / `_download_worker` / `_on_download_row_finished` exactly — three new symbols following the same pattern: `_dialog_lock`, `_folder_worker`, `_on_folder_row_finished`. Add `FolderConfirmDialog` as a standalone class above `TuneBridgeApp`. Four plans: Wave 0 (RED-gate tests), Wave 1 (dialog class + signals + enum additions), Wave 2 (worker + event wiring + closeEvent extension), Wave 3 (batch counter + status bar summary).

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01:** `_dialog_lock = threading.Lock()` at module level — mirrors `_download_lock` pattern.
**D-02:** Each `_folder_worker` acquires `_dialog_lock`, stores `threading.Event` in `self._folder_events[row_id]`, emits `_dispatcher.folder_requested(row_id)`, blocks on `event.wait()`.
**D-03:** Main thread slot retrieves event from `_folder_events[row_id]`, shows `FolderConfirmDialog`, stores result in `self._folder_results[row_id]`, calls `event.set()`. Worker unblocks, reads result, acts, releases `_dialog_lock`.
**D-04:** `closeEvent` iterates `self._folder_events`, calls `event.set()` with `None` sentinel for unresolved events.
**D-05:** `SongStatus.SKIPPED = "Skipped — folder"`. Add `"Skipped — folder": QColor("#B3B3B3")` to `_STATUS_COLORS`.
**D-06:** On skip, delete temp MP3 via `Path(temp_path).unlink(missing_ok=True)`.
**D-07:** Skipped rows excluded from Phase 6.
**D-08:** When all folder dialogs resolve, status bar shows `"Saved X, skipped Y, failed Z"`.
**D-09:** After `shutil.move` succeeds: `SAVING → UPLOADING`. Final path in `self._saved_paths[row_id]`.
**D-10:** On `OSError` during `shutil.move`: row → `"Failed — save"`. Error isolated per row.
**D-11:** When last dialog resolves, emit `_dispatcher.folder_batch_done()`.
**D-12:** Proposed path = `self._last_folder` (in-session only, `Path | None`).
**D-13:** First song (no `_last_folder`): dialog text field starts **empty**.
**D-14:** `_last_folder` is in-session only — not persisted to disk.
**D-15:** `FolderConfirmDialog` is a modal `QDialog` parented to `TuneBridgeApp`. Layout: song title label → path `QLineEdit` → Browse `QPushButton` → row of Confirm + Skip buttons.
**D-16:** Confirm button disabled if `Path(line_edit.text()).is_dir()` is `False`. Live validation via `textChanged`. Inline error label shown.
**D-17:** Browse calls `QFileDialog.getExistingDirectory(self, "Select folder", str(self._last_folder or Path.home()))`.

### Claude's Discretion

- Exact signal names in `_Dispatcher` (suggested: `folder_requested = Signal(int)`, `folder_batch_done = Signal()`)
- Skip sentinel value in `_folder_results` (suggested: `None`)
- Dialog styling consistent with Liquid Glass QSS theme
- `_folder_events: dict[int, threading.Event]` and `_folder_results: dict[int, Path | None]` initialization in `__init__`
- Whether `_folder_worker` is submitted to executor after `_download_worker` completes or runs as a continuation
- Exact `"Failed — save"` label in `SongStatus` enum

### Deferred Ideas (OUT OF SCOPE)

- Cross-session folder persistence (`~/.tunebridge_state.json`) — deferred to v1.1
- Metadata-derived sub-path proposal — deferred; last-used folder is v1.0 policy
- Per-row retry for failed saves — Phase 5+ enhancement
- Stop/pause mid-batch during folder dialogs — complex threading; not scoped
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ORG-01 | App proposes destination folder per song; last confirmed folder is default for next song | `_last_folder: Path | None` in `__init__`; `FolderConfirmDialog` pre-fills `QLineEdit` with `str(_last_folder)` or empty |
| ORG-02 | User can confirm proposed folder, edit via text field, or browse via directory picker — per song | `QLineEdit` + `QFileDialog.getExistingDirectory` + Confirm button — all verified available in PySide6 6.11.1 |
| ORG-03 | User can skip individual song without canceling batch | Skip button in `FolderConfirmDialog`; worker reads `None` sentinel, calls `unlink(missing_ok=True)`, emits `SKIPPED` |
| ORG-04 | App saves processed MP3 into confirmed existing folder; never creates/renames/deletes folders | `shutil.move(temp_path, dest_folder)` — verified cross-device safe; `Path.is_dir()` gate prevents save to non-existent dir |
</phase_requirements>

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Folder confirmation dialog UI | Main thread (Qt) | — | Qt requires all widget creation and show on main thread |
| Dialog serialization | Worker thread (_folder_worker) | Main thread (_dialog_lock release) | Lock acquired in worker, event blocks worker; main thread only shows UI |
| File move (shutil.move) | Worker thread | — | I/O-bound, safe off main thread; no Qt calls needed |
| Status updates (SAVING, UPLOADING, SKIPPED) | Worker thread → Signal → Main thread | — | Existing queued-connection pattern; emit from worker, slot on main thread |
| Batch completion counter | Main thread slot (_on_folder_row_finished) | — | Mirrors `_on_download_row_finished`; slot connected via queued connection |
| _last_folder state update | Main thread | — | Updated in `_show_folder_dialog` slot after confirmed path; no lock needed (main thread only) |
| closeEvent sentinel injection | Main thread | — | `closeEvent` already runs on main thread; iterates `_folder_events`, sets each event |

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| PySide6 | 6.11.1 [VERIFIED: python -c "import PySide6; print(PySide6.__version__)"] | QDialog, QLineEdit, QFileDialog, Signal/Slot | Already in project; all required APIs confirmed present |
| threading (stdlib) | Python 3.10+ [VERIFIED: import threading] | Lock + Event for serialization | Zero deps; exact pattern already used for `_download_lock` |
| shutil (stdlib) | Python 3.10+ [VERIFIED: import shutil] | `shutil.move` for temp→dest file move | Already imported at tunebridge.py:9; cross-device safe |
| pathlib.Path (stdlib) | Python 3.10+ [VERIFIED: from pathlib import Path] | Path validation (`is_dir()`), path construction | Already used throughout codebase |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest + unittest.mock | existing (62 tests passing) | Unit tests with QApplication singleton fixture | All Phase 5 tests follow same `qapp` + `window` fixture pattern |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| threading.Event per row | queue.Queue drain | Event is simpler; matches ROADMAP language exactly; Queue adds complexity without benefit |
| shutil.move | os.rename | `os.rename` fails cross-device; `shutil.move` has `copy2` fallback — always correct [VERIFIED: inspect.getsource(shutil.move) contains 'copy2'] |
| QDialog.exec() (blocking) | non-blocking show() + callbacks | `exec()` blocks the calling thread's event loop — WRONG for worker threads. Main thread must show dialog from its own slot; worker blocks on Event, not on exec() |

**Installation:** No new packages needed. All stdlib and PySide6 APIs verified present.

---

## Architecture Patterns

### System Architecture Diagram

```
_download_worker (thread)
    └─→ emits AWAITING + writes _temp_paths[row_id]
         └─→ _on_download_row_finished (main thread slot)
              └─→ submits _folder_worker(row_id) to executor

_folder_worker (thread)
    acquire _dialog_lock
    create threading.Event → store in _folder_events[row_id]
    emit folder_requested(row_id)         ─────────────────────┐
    event.wait()  ◄────────────────────────────── blocks       │
                                                                │ Qt queued connection
                                          _show_folder_dialog(row_id)  [main thread]
                                              show FolderConfirmDialog
                                              user: Confirm / Skip / Browse
                                              store result → _folder_results[row_id]
                                              event.set()  ─────────────────────────┘
    event.wait() unblocks
    read _folder_results[row_id]
    if Path: emit SAVING → shutil.move → emit UPLOADING → store _saved_paths[row_id]
    if None:  unlink temp → emit SKIPPED
    if OSError: emit "Failed — save"
    release _dialog_lock
    call _on_folder_row_finished(row_id, result_status)

_on_folder_row_finished (main thread slot)
    increment _folder_done / _folder_skipped / _folder_failed
    if all resolved: emit folder_batch_done() + update status bar

closeEvent (main thread)
    _closing.set()
    for ev in _folder_events.values(): ev.set()  ← None sentinel already in _folder_results
    executor.shutdown(wait=False)
    shutil.rmtree(session_tmp)
```

### Recommended Project Structure

No new files needed. All additions go into `tunebridge.py`:

```
tunebridge.py
├── Module level
│   ├── _download_lock = threading.Lock()   [existing]
│   └── _dialog_lock = threading.Lock()     [NEW — D-01]
├── SongStatus enum
│   ├── SKIPPED = "Skipped — folder"        [NEW — D-05]
│   └── (FAILED reused with "Failed — save" string — see D-10)
├── class FolderConfirmDialog(QDialog)       [NEW — D-15/D-16/D-17]
├── class _Dispatcher(QObject)
│   ├── folder_requested = Signal(int)       [NEW — D-02]
│   └── folder_batch_done = Signal()         [NEW — D-11]
├── class BatchTable
│   └── _STATUS_COLORS additions             [NEW — D-05, D-10]
└── class TuneBridgeApp
    ├── __init__ additions                   [NEW — _folder_events, _folder_results, etc.]
    ├── _folder_worker()                     [NEW — D-02/D-03]
    ├── _show_folder_dialog()                [NEW — D-03, main thread slot]
    ├── _on_folder_row_finished()            [NEW — D-08/D-11]
    └── closeEvent() extension              [EXTEND — D-04]
```

### Pattern 1: FolderConfirmDialog — Modal QDialog with Live Validation

**What:** Standalone QDialog class. Accepts song title and proposed path. Returns confirmed Path or None (skip).

**When to use:** Called exclusively from `_show_folder_dialog` on the main thread. Never instantiated from a worker thread.

**Critical constraint:** `QDialog.exec()` runs a nested event loop on the **calling thread**. When called from the main thread, this is correct — the main thread's event loop processes Qt events while the dialog is open. Worker threads must NEVER call `exec()` directly.

```python
# Source: PySide6 6.11.1 verified APIs [VERIFIED: python probe]
class FolderConfirmDialog(QDialog):
    def __init__(self, song_title: str, proposed: Path | None, parent=None):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowTitle("Confirm Save Folder")
        self._result_path: Path | None = None

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(song_title))

        self._path_edit = QLineEdit(str(proposed) if proposed else "")
        layout.addWidget(self._path_edit)

        self._error_label = QLabel("")
        self._error_label.setStyleSheet("color: #EF4444; font-size: 9pt;")
        layout.addWidget(self._error_label)

        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse)
        layout.addWidget(browse_btn)

        btn_row = QHBoxLayout()
        self._confirm_btn = QPushButton("Confirm")
        self._confirm_btn.setEnabled(False)   # disabled until valid dir typed
        self._confirm_btn.clicked.connect(self._on_confirm)
        skip_btn = QPushButton("Skip")
        skip_btn.clicked.connect(self.reject)   # reject() → result_path stays None
        btn_row.addWidget(self._confirm_btn)
        btn_row.addWidget(skip_btn)
        layout.addLayout(btn_row)

        self._path_edit.textChanged.connect(self._validate)
        self._validate(self._path_edit.text())   # initial state

    def _validate(self, text: str) -> None:
        # CRITICAL: check strip() before is_dir() — Path('').is_dir() is True on Windows
        valid = bool(text.strip()) and Path(text.strip()).is_dir()
        self._confirm_btn.setEnabled(valid)
        if text.strip() and not valid:
            self._error_label.setText("Folder not found — select an existing folder.")
        else:
            self._error_label.setText("")

    def _browse(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        current = self._path_edit.text().strip()
        start = current if (current and Path(current).is_dir()) else str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, "Select folder", start)
        if chosen:
            self._path_edit.setText(chosen)

    def _on_confirm(self) -> None:
        self._result_path = Path(self._path_edit.text().strip())
        self.accept()

    def result_path(self) -> Path | None:
        return self._result_path
```

### Pattern 2: _folder_worker — Worker Thread Blocks on threading.Event

**What:** Runs in `ThreadPoolExecutor`. Acquires `_dialog_lock`, registers event, emits signal, blocks, reads result, moves file.

**When to use:** Submitted from `_on_download_row_finished` when a row reaches `AWAITING`.

```python
# Source: mirrors _download_worker pattern exactly [VERIFIED: tunebridge.py:943]
def _folder_worker(self, row_id: int) -> None:
    if self._closing.is_set():
        return
    with _dialog_lock:                           # serialize: one dialog at a time
        ev = threading.Event()
        self._folder_events[row_id] = ev
        self._folder_results[row_id] = None      # default = skip sentinel

        if not self._closing.is_set():
            self._dispatcher.folder_requested.emit(row_id)  # main thread shows dialog
            ev.wait()                            # block until main thread sets event

        result: Path | None = self._folder_results.get(row_id)

    # Lock released — now do I/O
    try:
        if result is None:
            # Skip
            with self._temp_paths_lock:
                temp = self._temp_paths.get(row_id)
            if temp:
                Path(temp).unlink(missing_ok=True)
            self._dispatcher.row_status_changed.emit(row_id, SongStatus.SKIPPED.value)
            self._on_folder_row_finished(row_id, "skipped")
        else:
            self._dispatcher.row_status_changed.emit(row_id, SongStatus.SAVING.value)
            with self._temp_paths_lock:
                temp = self._temp_paths[row_id]
            final = Path(shutil.move(str(temp), str(result)))
            self._saved_paths[row_id] = final
            self._dispatcher.row_status_changed.emit(row_id, SongStatus.UPLOADING.value)
            self._on_folder_row_finished(row_id, "saved")
    except OSError as exc:
        logging.getLogger(__name__).warning("Save failed row %d: %s", row_id, exc)
        self._dispatcher.row_status_changed.emit(row_id, "Failed — save")
        self._on_folder_row_finished(row_id, "failed")
```

### Pattern 3: _show_folder_dialog — Main Thread Slot

**What:** Connected to `folder_requested` signal via Qt queued connection (auto because signal crosses thread). Runs exclusively on the main thread.

```python
# Source: D-03 architecture [VERIFIED: QDialog.exec available in PySide6 6.11.1]
def _show_folder_dialog(self, row_id: int) -> None:
    """Main thread only. Shows FolderConfirmDialog, stores result, sets event."""
    with self._temp_paths_lock:
        temp = self._temp_paths.get(row_id)
    title = self._get_display_title(row_id)   # read from table item col 0

    dlg = FolderConfirmDialog(
        song_title=title,
        proposed=self._last_folder,
        parent=self,
    )
    dlg.exec()   # nested event loop — safe on main thread

    result = dlg.result_path()   # Path or None
    if result is not None:
        self._last_folder = result   # update session default

    self._folder_results[row_id] = result
    if row_id in self._folder_events:
        self._folder_events[row_id].set()   # unblock worker
```

### Pattern 4: closeEvent Extension

**What:** Extend existing `closeEvent` to unblock all pending `_folder_worker` threads.

```python
# Source: D-04; extends tunebridge.py:1100 [VERIFIED: existing closeEvent]
def closeEvent(self, event) -> None:
    self._closing.set()
    # Unblock any worker waiting on a folder dialog
    for ev in list(self._folder_events.values()):
        ev.set()   # _folder_results[row_id] stays None → workers skip
    self._executor.shutdown(wait=False)
    try:
        shutil.rmtree(self._session_tmp, ignore_errors=True)
    except Exception:
        pass
    super().closeEvent(event)
```

### Anti-Patterns to Avoid

- **`QDialog.exec()` from a worker thread:** Deadlocks — the worker thread has no Qt event loop. All dialog creation and `exec()` must be on the main thread.
- **`Path('').is_dir()` as sole validation check:** Returns `True` on Windows. Always check `text.strip() != ''` first.
- **Narrowing `_dialog_lock` scope to exclude event.wait():** The lock must be held from event registration through event.set() consumption — otherwise a second worker could overwrite `_folder_events[row_id]` between registration and wait.
- **Writing `_last_folder` from the worker thread:** `_last_folder` is read/written in `_show_folder_dialog` on the main thread only. Worker reads result after event unblocks; main thread updates `_last_folder`. No race condition.
- **Emitting `folder_batch_done` before all workers release their locks:** The batch-done counter must fire after the worker's I/O completes (post-lock), not inside the lock.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Cross-device file move | Custom copy+delete | `shutil.move` | Has `copy2` fallback for cross-device; handles all edge cases [VERIFIED: shutil source] |
| Modal dialog blocking main thread | `time.sleep` poll loop | `QDialog.exec()` on main thread | exec() runs nested Qt event loop — correct, native, handles window events |
| Dialog serialization | Custom semaphore or queue | `threading.Lock()` (already in codebase) | Exact pattern of `_download_lock`; simpler than a queue |
| Folder existence validation | Custom filesystem walk | `Path.is_dir()` | One call; handles all OS cases |
| Thread-safe UI update from worker | Direct widget access from thread | `Signal.emit()` → queued connection slot | Qt's own cross-thread mechanism; already used for all Phase 3/4 updates |

**Key insight:** The entire Phase 5 threading model is already proven in Phase 4 (`_download_lock`). Phase 5 repeats the pattern with `_dialog_lock` and adds the `threading.Event` layer for per-row blocking.

---

## Common Pitfalls

### Pitfall 1: Path('').is_dir() Returns True on Windows

**What goes wrong:** Confirm button enables on empty text field. User clicks Confirm with no path typed. `shutil.move(temp, '')` raises `FileNotFoundError`.

**Why it happens:** On Windows, `Path('')` resolves to the current working directory, which exists.

**How to avoid:** Validation function must check `text.strip() != ''` BEFORE calling `is_dir()`:
```python
valid = bool(text.strip()) and Path(text.strip()).is_dir()
```

**Warning signs:** Confirm button enabled immediately when dialog opens with empty field.

[VERIFIED: python -c "from pathlib import Path; print(Path('').is_dir())" → True]

### Pitfall 2: QDialog.exec() Called from Worker Thread

**What goes wrong:** Crash or deadlock. Qt fatal error: "QWidget: Must construct a QApplication before a QWidget."  Or silent hang if called from thread with no event loop.

**Why it happens:** `exec()` requires the calling thread to have a Qt event loop. Only the main thread has one.

**How to avoid:** `FolderConfirmDialog` is instantiated and `exec()`'d only inside `_show_folder_dialog`, which is a slot connected to `folder_requested` via Qt's auto (queued) connection — guaranteed to run on the main thread.

**Warning signs:** Dialog never appears; app freezes; Qt thread-safety warnings in stderr.

### Pitfall 3: _dialog_lock Scope Too Narrow

**What goes wrong:** Worker A registers event, releases lock, worker B acquires lock and overwrites `_folder_events[row_id_A]` with its own event before A calls `event.wait()`. Worker A's event is now unreachable — it hangs forever.

**Why it happens:** Event registration and `event.wait()` must be atomic with respect to the lock. The lock must be held from registration through the point where the event is definitively set.

**How to avoid:** The `with _dialog_lock:` block must contain: (1) event creation, (2) dict write, (3) signal emit, (4) `event.wait()`. The lock is released only after `wait()` returns.

**Warning signs:** App hangs on close; workers never unblock after second+ dialog.

### Pitfall 4: shutil.move Returns str, Not Path

**What goes wrong:** `self._saved_paths[row_id] = shutil.move(...)` stores a `str`. Phase 6 code expecting `Path` calls `.name` or `/` operator on a `str` and crashes with `AttributeError`.

**Why it happens:** `shutil.move` returns `str` in Python 3.10+. [VERIFIED: shutil.move return type is `str`]

**How to avoid:** Wrap return value: `final = Path(shutil.move(str(temp), str(dest)))`.

**Warning signs:** `AttributeError: 'str' object has no attribute 'name'` in Phase 6.

### Pitfall 5: _folder_worker Submitted Before _temp_paths[row_id] Written

**What goes wrong:** `_folder_worker` reads `_temp_paths[row_id]` before `_download_worker` writes it. Gets `None`. `shutil.move(None, dest)` → `TypeError`.

**Why it happens:** If `_folder_worker` is submitted from the executor's completion callback rather than from the post-AWAITING-status path in `_download_worker`, there's a race on `_temp_paths`.

**How to avoid:** `_temp_paths[row_id]` is written in `_download_worker` BEFORE emitting `AWAITING`. `_folder_worker` submission must happen AFTER `AWAITING` is emitted (e.g., in `_on_download_row_finished` which is triggered by the `AWAITING` signal). This ordering is guaranteed by Qt's queued connection. [VERIFIED: tunebridge.py:989-992 — temp_paths written before AWAITING emit]

**Warning signs:** `TypeError` in `_folder_worker`; `shutil.move` receiving `None` as source.

### Pitfall 6: Missing _on_folder_row_finished Disconnect After Batch

**What goes wrong:** `_on_folder_row_finished` remains connected to `row_status_changed` across batch runs. A second batch's download status changes trigger the folder counter, inflating `_folder_done` and emitting `folder_batch_done` prematurely.

**Why it happens:** Pattern mirrors `_on_download_row_finished` which explicitly disconnects itself after batch completes (tunebridge.py:1029-1032).

**How to avoid:** Disconnect `_on_folder_row_finished` after `folder_batch_done` is emitted, using the same `try/except RuntimeError` guard.

---

## Code Examples

Verified patterns from official sources and codebase:

### shutil.move with Path wrapping
```python
# Source: verified [VERIFIED: shutil.move returns str on Windows/Python 3.10]
final_path = Path(shutil.move(str(temp_mp3_path), str(dest_folder)))
# final_path is now e.g. Path("D:/Music/Artist/track.mp3")
```

### QFileDialog.getExistingDirectory
```python
# Source: PySide6 6.11.1 [VERIFIED: QFileDialog.getExistingDirectory exists]
from PySide6.QtWidgets import QFileDialog
chosen = QFileDialog.getExistingDirectory(
    self,                                      # parent widget
    "Select folder",                           # dialog title
    str(self._last_folder or Path.home()),     # start directory
)
# Returns empty string "" if user cancels; non-empty str path if confirmed
if chosen:
    self._path_edit.setText(chosen)
```

### threading.Event unblock pattern
```python
# Source: Python stdlib [VERIFIED: threading.Event.wait/set present]
ev = threading.Event()
self._folder_events[row_id] = ev
self._folder_results[row_id] = None   # default: skip
self._dispatcher.folder_requested.emit(row_id)
ev.wait()   # blocks until main thread calls ev.set()
result = self._folder_results.get(row_id)   # Path or None
```

### Adding new signals to _Dispatcher
```python
# Source: existing _Dispatcher pattern [VERIFIED: tunebridge.py:351-358]
class _Dispatcher(QObject):
    row_status_changed = Signal(int, str)
    metadata_ready     = Signal(int, object)
    folder_requested   = Signal(int)        # NEW — D-02
    folder_batch_done  = Signal()           # NEW — D-11
```

### _STATUS_COLORS additions
```python
# Source: tunebridge.py:560-574 [VERIFIED: existing dict]
_STATUS_COLORS: dict[str, QColor] = {
    # ... existing entries ...
    "Skipped — folder": QColor("#B3B3B3"),   # NEW — D-05
    "Failed — save":    QColor("#EF4444"),   # NEW — D-10
}
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `exec_()` (Qt4 style) | `exec()` | PySide6 (Qt6) | Method rename; `exec_()` still works as alias but `exec()` is canonical |
| `QDialog.result()` int return | Custom result stored in attribute | — | More Pythonic; avoids mapping Qt int codes to domain objects |

**Deprecated/outdated:**
- `QDialog.exec_()`: Works in PySide6 as alias but `exec()` is the canonical Qt6 API. Use `exec()`.
- `os.rename()` for file move: Fails cross-device on Windows. Use `shutil.move()`.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `_folder_worker` is submitted from `_on_download_row_finished` after row reaches `AWAITING` (not as a direct continuation inside `_download_worker`) | Architecture Patterns | If chained inside `_download_worker`, `_download_lock` is released before `_folder_worker` starts — fine. But if submitted before `_temp_paths` write completes, race condition. Either approach is valid if ordering is correct. [ASSUMED — implementation choice left to planner per Claude's Discretion] |
| A2 | `_on_folder_row_finished` is connected to `row_status_changed` signal (batch-scoped, like `_on_download_row_finished`) | Architecture Patterns | If connected in `__init__`, all status changes from all phases trigger it. Must be batch-scoped. [ASSUMED — mirrors Phase 4 pattern but not explicitly locked in CONTEXT.md] |

**All other claims verified in this session.**

---

## Open Questions (RESOLVED)

1. **`_folder_worker` submission point: inside `_download_worker` or from `_on_download_row_finished`?**
   - RESOLVED: Submit from `_on_download_row_finished` when row reaches `AWAITING`. Matches Phase 4's explicit batch dispatch pattern; guarantees `_temp_paths[row_id]` written before worker reads it.

2. **`_on_folder_row_finished`: signal slot or direct call from worker?**
   - RESOLVED: Direct call from worker thread (GIL-safe int counter increments; no Qt widget calls at counter level). Rationale: avoids reusing `row_status_changed` for folder-domain bookkeeping; simpler than a second batch-scoped slot with connect/disconnect lifecycle. `statusBar().showMessage()` and `folder_batch_done.emit()` are called only when batch completes — acceptable risk documented in threat model T-05-W3-01 with "replace with queued signal if threading issues arise" escape hatch.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PySide6 | QDialog, QFileDialog, Signal | ✓ | 6.11.1 | — |
| threading.Lock | `_dialog_lock` | ✓ | stdlib | — |
| threading.Event | per-row blocking | ✓ | stdlib | — |
| shutil.move | file save | ✓ | stdlib | — |
| pathlib.Path.is_dir() | folder validation | ✓ | stdlib | — |
| pytest | test suite | ✓ | 62 tests passing | — |

**Missing dependencies with no fallback:** None.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (existing, 62 tests passing) |
| Config file | `pytest.ini` (`testpaths = tests`, `addopts = -q`) |
| Quick run command | `python -m pytest tests/test_organization.py -q --tb=short -p no:warnings` |
| Full suite command | `python -m pytest tests/ -q --tb=short -p no:warnings` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ORG-01 | `_last_folder` None on first dialog; pre-filled after first confirm | unit | `pytest tests/test_organization.py::test_last_folder_empty_on_first -x` | ❌ Wave 0 |
| ORG-01 | Subsequent dialog pre-filled with last confirmed path | unit | `pytest tests/test_organization.py::test_last_folder_updates_after_confirm -x` | ❌ Wave 0 |
| ORG-02 | FolderConfirmDialog Confirm disabled on empty text | unit | `pytest tests/test_organization.py::test_confirm_disabled_empty_text -x` | ❌ Wave 0 |
| ORG-02 | FolderConfirmDialog Confirm disabled on non-existent path | unit | `pytest tests/test_organization.py::test_confirm_disabled_nonexistent_path -x` | ❌ Wave 0 |
| ORG-02 | FolderConfirmDialog Confirm enabled on valid existing dir | unit | `pytest tests/test_organization.py::test_confirm_enabled_valid_dir -x` | ❌ Wave 0 |
| ORG-02 | Browse button calls QFileDialog.getExistingDirectory | unit | `pytest tests/test_organization.py::test_browse_calls_get_existing_directory -x` | ❌ Wave 0 |
| ORG-03 | Skip sets result to None, unlinks temp file, emits SKIPPED | unit | `pytest tests/test_organization.py::test_skip_deletes_temp_and_emits_skipped -x` | ❌ Wave 0 |
| ORG-03 | Skip does not block other rows in batch | unit | `pytest tests/test_organization.py::test_skip_does_not_block_other_rows -x` | ❌ Wave 0 |
| ORG-04 | shutil.move called with correct src and dest on confirm | unit | `pytest tests/test_organization.py::test_confirm_calls_shutil_move -x` | ❌ Wave 0 |
| ORG-04 | _saved_paths[row_id] stores final Path after move | unit | `pytest tests/test_organization.py::test_saved_paths_populated_after_move -x` | ❌ Wave 0 |
| ORG-04 | OSError during move emits "Failed — save" status | unit | `pytest tests/test_organization.py::test_oserror_emits_failed_save -x` | ❌ Wave 0 |
| D-11 | folder_batch_done emitted when all dialogs resolve | unit | `pytest tests/test_organization.py::test_folder_batch_done_emitted -x` | ❌ Wave 0 |
| D-08 | Status bar shows "Saved X, skipped Y, failed Z" after batch | unit | `pytest tests/test_organization.py::test_status_bar_summary -x` | ❌ Wave 0 |
| D-04 | closeEvent sets all pending events with None sentinel | unit | `pytest tests/test_organization.py::test_close_event_unblocks_pending_workers -x` | ❌ Wave 0 |

### Mocking Strategy for FolderConfirmDialog

Tests must not show real dialogs (headless CI, no display). Two approaches:

**Option A — Patch FolderConfirmDialog.exec (preferred):**
```python
from unittest.mock import patch, MagicMock

def test_confirm_calls_shutil_move(window, tmp_path):
    """ORG-04: shutil.move called with temp path and confirmed dest on confirm."""
    temp_mp3 = tmp_path / "track.mp3"
    temp_mp3.write_bytes(b"fake")
    window._temp_paths[0] = temp_mp3
    window._folder_events[0] = threading.Event()
    window._folder_results[0] = None

    dest = tmp_path / "dest"
    dest.mkdir()

    with patch("tunebridge.FolderConfirmDialog") as MockDlg:
        instance = MagicMock()
        instance.result_path.return_value = dest
        instance.exec.return_value = None    # simulate accept
        MockDlg.return_value = instance
        with patch("tunebridge.shutil.move", return_value=str(dest / "track.mp3")) as mock_move:
            window._show_folder_dialog(0)

    mock_move.assert_called_once_with(str(temp_mp3), str(dest))
```

**Option B — Test FolderConfirmDialog in isolation (no TuneBridgeApp):**
```python
def test_confirm_disabled_empty_text(qapp):
    """ORG-02: Confirm button disabled when text field is empty."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        dlg = FolderConfirmDialog("Test Song", None)
        dlg._path_edit.setText("")
        assert not dlg._confirm_btn.isEnabled()
        dlg._path_edit.setText(td)       # valid dir
        assert dlg._confirm_btn.isEnabled()
        dlg.close()
```

**Option B is the primary approach for dialog unit tests** — tests `FolderConfirmDialog` class directly without threading, no mocking of exec needed.

**Option A is used for integration tests** — verifies `_show_folder_dialog` slot behavior, `_folder_results` storage, `shutil.move` call.

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_organization.py -q --tb=short -p no:warnings`
- **Per wave merge:** `python -m pytest tests/ -q --tb=short -p no:warnings`
- **Phase gate:** Full suite green (62 + new Phase 5 tests) before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_organization.py` — 14 RED-gate tests covering ORG-01 through ORG-04, D-04, D-08, D-11
- [ ] No new framework install needed — pytest + PySide6 + unittest.mock already present

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | — |
| V3 Session Management | no | — |
| V4 Access Control | no | — |
| V5 Input Validation | yes | `Path.is_dir()` gate — prevents write to non-existent or non-directory path |
| V6 Cryptography | no | — |

### Known Threat Patterns for file-save stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Path traversal via QLineEdit input | Tampering | `Path(text).is_dir()` only accepts existing real directories; `shutil.move` to a directory destination resolves the full path — attacker cannot navigate to arbitrary sub-path via `..` because the destination is a directory, not a file path |
| Temp file disclosure | Information Disclosure | `_session_tmp` is in system temp (user-owned); deleted on closeEvent and atexit; `missing_ok=True` on skip unlink prevents orphan files |
| Overwrite existing file | Tampering | `shutil.move` to a directory: if `dest_dir/filename.mp3` exists, it is overwritten. No explicit guard in Phase 5 scope — user is choosing the destination folder and accepts this behavior |

---

## Sources

### Primary (HIGH confidence)
- PySide6 6.11.1 installed package — QDialog, QLineEdit.textChanged, QFileDialog.getExistingDirectory, Signal [VERIFIED: python probes in this session]
- Python stdlib shutil.move — cross-device copy2 fallback, str return type [VERIFIED: inspect.getsource + runtime test]
- Python stdlib threading.Lock + threading.Event — wait/set API [VERIFIED: runtime test]
- pathlib.Path.is_dir() — edge case behavior on Windows [VERIFIED: runtime test including empty string case]
- `tunebridge.py` — existing patterns for `_download_lock`, `_download_worker`, `_on_download_row_finished`, `closeEvent`, `_STATUS_COLORS`, `_Dispatcher` [VERIFIED: full file read]

### Secondary (MEDIUM confidence)
- `retune_app.py:113` — `_download_lock = threading.Lock()` module-level pattern [VERIFIED: file read]
- `tests/test_download_pipeline.py` — mock patterns for worker testing [VERIFIED: file read]

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all APIs verified installed and functional
- Architecture: HIGH — exact mirror of Phase 4 pattern; threading model verified
- Pitfalls: HIGH — `Path('').is_dir()` on Windows verified empirically; others derived from codebase analysis
- Test patterns: HIGH — 62 existing tests pass; fixture and mock patterns directly observed

**Research date:** 2026-05-17
**Valid until:** 2026-06-17 (PySide6 and stdlib APIs are stable; 30-day window)
