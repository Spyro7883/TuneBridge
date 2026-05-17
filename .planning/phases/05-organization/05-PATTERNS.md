# Phase 5: Organization - Pattern Map

**Mapped:** 2026-05-17
**Files analyzed:** 2 (1 modified: `tunebridge.py`, 1 new: `tests/test_organization.py`)
**Analogs found:** 2 / 2

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `tunebridge.py` — `FolderConfirmDialog` class | component (QDialog) | request-response | `TuneBridgeApp` (QMainWindow, same file) — widget with signals, layout, slots | role-match |
| `tunebridge.py` — `_dialog_lock` module var | utility (lock) | event-driven | `_download_lock` in `retune_app.py:113` | exact |
| `tunebridge.py` — `_Dispatcher` signal additions | utility (signal bus) | event-driven | `_Dispatcher` class at `tunebridge.py:351-358` | exact |
| `tunebridge.py` — `SongStatus` enum additions | model (enum) | — | `SongStatus` enum at `tunebridge.py:312-323` | exact |
| `tunebridge.py` — `_STATUS_COLORS` additions | config (dict) | — | `_STATUS_COLORS` at `tunebridge.py:560-574` | exact |
| `tunebridge.py` — `TuneBridgeApp.__init__` additions | config (instance vars) | — | `__init__` Phase 4 block at `tunebridge.py:848-857` | exact |
| `tunebridge.py` — `_folder_worker()` | service (worker thread) | event-driven | `_download_worker()` at `tunebridge.py:943-1001` | exact |
| `tunebridge.py` — `_show_folder_dialog()` slot | controller (main-thread slot) | request-response | `_on_download_row_finished` at `tunebridge.py:1003-1032` | role-match |
| `tunebridge.py` — `_on_folder_row_finished()` slot | controller (batch tracker) | event-driven | `_on_download_row_finished` at `tunebridge.py:1003-1032` | exact |
| `tunebridge.py` — `closeEvent()` extension | middleware (lifecycle) | event-driven | `closeEvent` at `tunebridge.py:1100-1108` | exact |
| `tests/test_organization.py` | test | request-response | `tests/test_download_pipeline.py` | exact |

---

## Pattern Assignments

### `_dialog_lock` — module-level threading.Lock

**Analog:** `retune_app.py:113` / `tunebridge.py:150`

**Imports pattern** (`tunebridge.py:13`):
```python
import threading
```

**Core pattern** (`retune_app.py:111-113`):
```python
# Global lock: serialize yt-dlp calls to avoid Firefox cookie DB conflicts.
# Retune still runs in parallel (that's the slow part anyway).
_download_lock = threading.Lock()
```

**Copy exactly — new symbol** (`tunebridge.py:150`, after `_download_lock`):
```python
_dialog_lock = threading.Lock()   # Serializes folder dialogs — one at a time (D-01)
```

---

### `SongStatus` enum additions

**Analog:** `tunebridge.py:312-323`

**Existing enum** (`tunebridge.py:312-323`):
```python
class SongStatus(Enum):
    QUEUED          = "Queued"
    FETCHING        = "Fetching metadata"
    DOWNLOADING     = "Downloading"
    RETUNING        = "Retuning"
    AWAITING        = "Awaiting folder"
    SAVING          = "Saving"
    UPLOADING       = "Uploading"
    DONE            = "Done"
    FAILED          = "Failed"
    METADATA_READY  = "Metadata ready"
    FAILED_DOWNLOAD = "Failed — download"   # D-13: per-row download failure status
```

**Add two entries** (append after `FAILED_DOWNLOAD`):
```python
    SKIPPED         = "Skipped — folder"    # D-05: user chose skip in FolderConfirmDialog
    FAILED_SAVE     = "Failed — save"       # D-10: OSError during shutil.move
```

---

### `_STATUS_COLORS` additions

**Analog:** `tunebridge.py:560-574`

**Existing dict** (`tunebridge.py:560-574`):
```python
_STATUS_COLORS: dict[str, QColor] = {
    "Queued":            QColor("#B3B3B3"),
    "Fetching metadata": QColor("#FFFFFF"),
    "Downloading":       QColor("#FFFFFF"),
    "Retuning":          QColor("#FFFFFF"),
    "Awaiting folder":   QColor("#F59E0B"),
    "Saving":            QColor("#FFFFFF"),
    "Uploading":         QColor("#FFFFFF"),
    "Done":              QColor("#1DB954"),
    "Failed":            QColor("#EF4444"),
    "Skipped — bad URL": QColor("#EF4444"),
    "Metadata ready":    QColor("#1DB954"),
    "Failed — metadata": QColor("#EF4444"),
    "Failed — download": QColor("#EF4444"),   # D-13
}
```

**Add two entries** (after `"Failed — download"` line):
```python
    "Skipped — folder":  QColor("#B3B3B3"),   # D-05: gray, distinct from failure red
    "Failed — save":     QColor("#EF4444"),   # D-10: matches other failure states
```

---

### `_Dispatcher` signal additions

**Analog:** `tunebridge.py:351-358`

**Existing class** (`tunebridge.py:351-358`):
```python
class _Dispatcher(QObject):
    row_status_changed = Signal(int, str)
    metadata_ready     = Signal(int, object)   # (row_id, metadata_dict) — crosses thread boundary

    def __init__(self, table: "BatchTable"):
        super().__init__()
        self.row_status_changed.connect(table.update_row_status)
        self.metadata_ready.connect(table.update_row_metadata)
```

**Add two signals** (after `metadata_ready` line, no `__init__` changes needed):
```python
    folder_requested   = Signal(int)           # D-02: worker emits row_id; main thread shows dialog
    folder_batch_done  = Signal()              # D-11: emitted when all folder dialogs resolve
```

**Import already present** (`tunebridge.py:27`):
```python
from PySide6.QtCore import QObject, Signal
```

---

### `TuneBridgeApp.__init__` additions

**Analog:** `tunebridge.py:848-857` (Phase 4 block)

**Existing Phase 4 block** (`tunebridge.py:848-857`):
```python
# Phase 4: temp file lifecycle (D-10, D-11, D-12)
self._session_tmp            = Path(tempfile.mkdtemp(prefix="tunebridge_"))
atexit.register(shutil.rmtree, self._session_tmp, True)
self._temp_paths: dict[int, Path] = {}
self._row_metadata: dict[int, dict] = {}
# Phase 4: batch completion tracking (D-16)
self._download_total         = 0
self._download_done          = 0
self._download_failed        = 0
self._temp_paths_lock        = threading.Lock()
```

**Add Phase 5 block** (immediately after Phase 4 block):
```python
# Phase 5: folder dialog serialization (D-01 through D-04)
self._last_folder:    Path | None          = None
self._folder_events:  dict[int, threading.Event]     = {}
self._folder_results: dict[int, Path | None]         = {}
self._saved_paths:    dict[int, Path]                = {}
self._folder_total   = 0
self._folder_done    = 0
self._folder_skipped = 0
self._folder_failed  = 0
```

**Connect new signal** (in `__init__`, after existing `connect` calls):
```python
self._dispatcher.folder_requested.connect(self._show_folder_dialog)
```

---

### `FolderConfirmDialog(QDialog)` — new class

**Analog:** `TuneBridgeApp` QMainWindow layout patterns (same file); no exact QDialog analog exists in codebase.

**PySide6 imports needed** — add to existing import block (`tunebridge.py:29-43`):
```python
from PySide6.QtWidgets import (
    # ... existing ...
    QDialog,
    QFileDialog,
    QLineEdit,
)
```

**New class** (place above `TuneBridgeApp` class definition, below `_Dispatcher`):
```python
class FolderConfirmDialog(QDialog):
    """Modal dialog: user confirms or skips destination folder for one song. (D-15/D-16/D-17)

    Call exec() on the main thread only. Result via result_path() — Path or None.
    """

    def __init__(self, song_title: str, proposed: Path | None, parent=None):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowTitle("Confirm Save Folder")
        self._result_path: Path | None = None

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(f"Save folder for: {song_title}"))

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
        self._confirm_btn.setEnabled(False)
        self._confirm_btn.clicked.connect(self._on_confirm)
        skip_btn = QPushButton("Skip")
        skip_btn.clicked.connect(self.reject)   # reject() → _result_path stays None
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

---

### `_folder_worker()` — worker thread

**Analog:** `_download_worker()` at `tunebridge.py:943-1001`

**Pattern from analog** (`tunebridge.py:957-1001`):
```python
def _download_worker(self, row_id, url, url_type, metadata, hz_mode):
    if self._closing.is_set():          # closing guard — same in _folder_worker
        return
    try:
        self._dispatcher.row_status_changed.emit(row_id, SongStatus.DOWNLOADING.value)
        # ... work ...
        if not self._closing.is_set():
            self._dispatcher.row_status_changed.emit(row_id, SongStatus.AWAITING.value)
            with self._temp_paths_lock:
                self._temp_paths[row_id] = downloaded
    except Exception as exc:
        logging.getLogger(__name__).warning("Download failed for row %d (%s): %s", row_id, url, exc)
        if not self._closing.is_set():
            self._dispatcher.row_status_changed.emit(row_id, SongStatus.FAILED_DOWNLOAD.value)
```

**New method** (mirror exactly, adapt for folder domain):
```python
def _folder_worker(self, row_id: int) -> None:
    """Worker thread: acquire dialog lock, block on threading.Event, move file. (D-02/D-03)

    Mirrors _download_worker: closing guard → lock acquire → emit signal → wait → I/O → emit result.
    _dialog_lock wraps event registration through event.wait() — must NOT be narrowed (Pitfall 3).
    """
    if self._closing.is_set():
        return

    with _dialog_lock:                                    # serialize: one dialog at a time (D-01)
        ev = threading.Event()
        self._folder_events[row_id] = ev
        self._folder_results[row_id] = None              # default sentinel = skip (D-03)

        if not self._closing.is_set():
            self._dispatcher.folder_requested.emit(row_id)  # main thread shows dialog
            ev.wait()                                    # block until _show_folder_dialog sets event

        result: Path | None = self._folder_results.get(row_id)
    # Lock released — now do I/O outside the lock

    try:
        if result is None:
            # Skip path (D-06)
            with self._temp_paths_lock:
                temp = self._temp_paths.get(row_id)
            if temp:
                Path(temp).unlink(missing_ok=True)
            self._dispatcher.row_status_changed.emit(row_id, SongStatus.SKIPPED.value)
            self._on_folder_row_finished(row_id, SongStatus.SKIPPED.value)
        else:
            # Save path (D-09)
            self._dispatcher.row_status_changed.emit(row_id, SongStatus.SAVING.value)
            with self._temp_paths_lock:
                temp = self._temp_paths[row_id]
            final = Path(shutil.move(str(temp), str(result)))   # wrap str return (Pitfall 4)
            self._saved_paths[row_id] = final
            self._dispatcher.row_status_changed.emit(row_id, SongStatus.UPLOADING.value)
            self._on_folder_row_finished(row_id, SongStatus.UPLOADING.value)
    except OSError as exc:
        logging.getLogger(__name__).warning("Save failed row %d: %s", row_id, exc)
        self._dispatcher.row_status_changed.emit(row_id, SongStatus.FAILED_SAVE.value)
        self._on_folder_row_finished(row_id, SongStatus.FAILED_SAVE.value)
```

---

### `_show_folder_dialog()` — main thread slot

**Analog:** `_on_metadata_ready` / `_on_download_row_finished` (main-thread slots connected via queued connection). No exact slot-shows-dialog analog exists — pattern from RESEARCH.md applies.

**Pattern: main-thread slot structure** (`tunebridge.py:1003-1032`):
```python
def _on_download_row_finished(self, _row_id: int, status: str) -> None:
    """Slot: ... Connected only during active batch run. Runs on main thread via Qt queued connection."""
    terminal = (SongStatus.AWAITING.value, SongStatus.FAILED_DOWNLOAD.value)
    if status not in terminal:
        return
    # ... update counters, status bar ...
```

**New method** (D-03 architecture):
```python
def _show_folder_dialog(self, row_id: int) -> None:
    """Main thread only — connected to folder_requested via Qt queued connection. (D-03)

    Shows FolderConfirmDialog, stores confirmed Path or None sentinel in _folder_results,
    updates _last_folder session state, sets threading.Event to unblock _folder_worker.
    """
    # Read song title for dialog label (col 0 of table)
    title_item = self.table._table.item(row_id, 0)
    title = title_item.text() if title_item else f"Row {row_id}"

    dlg = FolderConfirmDialog(
        song_title=title,
        proposed=self._last_folder,
        parent=self,
    )
    dlg.exec()   # nested event loop — safe on main thread only (Pitfall 2)

    result = dlg.result_path()   # Path or None
    if result is not None:
        self._last_folder = result   # update session default (D-12, D-14)

    self._folder_results[row_id] = result
    if row_id in self._folder_events:
        self._folder_events[row_id].set()   # unblock _folder_worker
```

---

### `_on_folder_row_finished()` — batch completion tracker

**Analog:** `_on_download_row_finished` at `tunebridge.py:1003-1032` — exact mirror.

**Pattern from analog** (`tunebridge.py:1003-1032`):
```python
def _on_download_row_finished(self, _row_id: int, status: str) -> None:
    terminal = (SongStatus.AWAITING.value, SongStatus.FAILED_DOWNLOAD.value)
    if status not in terminal:
        return

    if status == SongStatus.AWAITING.value:
        self._download_done += 1
    else:
        self._download_failed += 1
    finished = self._download_done + self._download_failed

    if finished < self._download_total:
        self.statusBar().showMessage(f"Downloading {finished} / {self._download_total}…")
        return

    # All done — update status bar, disconnect slot
    self.statusBar().showMessage(
        f"Done — {self._download_done} downloaded, {self._download_failed} failed"
    )
    try:
        self._dispatcher.row_status_changed.disconnect(self._on_download_row_finished)
    except RuntimeError:
        pass
```

**New method** (adapt for folder domain — D-08/D-11):
```python
def _on_folder_row_finished(self, _row_id: int, status: str) -> None:
    """Track folder dialog batch completion. Called directly from _folder_worker (off main thread).

    Counters are only written here; this method is called from worker thread so counter
    increments use no lock (GIL protects int increments in CPython — same assumption as
    _on_download_row_finished which also runs from worker via direct call pattern).

    When all rows resolve: emit folder_batch_done(), update status bar. (D-08/D-11)
    """
    terminal = (
        SongStatus.UPLOADING.value,
        SongStatus.SKIPPED.value,
        SongStatus.FAILED_SAVE.value,
    )
    if status not in terminal:
        return

    if status == SongStatus.UPLOADING.value:
        self._folder_done += 1
    elif status == SongStatus.SKIPPED.value:
        self._folder_skipped += 1
    else:
        self._folder_failed += 1

    finished = self._folder_done + self._folder_skipped + self._folder_failed
    if finished < self._folder_total:
        return

    # All folder dialogs resolved (D-08, D-11)
    self._dispatcher.folder_batch_done.emit()
    self.statusBar().showMessage(
        f"Saved {self._folder_done}, skipped {self._folder_skipped}, "
        f"failed {self._folder_failed}"
    )
```

---

### `closeEvent()` extension

**Analog:** `tunebridge.py:1100-1108` — extend, do not replace.

**Existing closeEvent** (`tunebridge.py:1100-1108`):
```python
def closeEvent(self, event) -> None:
    """Shutdown thread pool and clean up leftover temp files on window close (D-12)."""
    self._closing.set()
    self._executor.shutdown(wait=False)
    try:
        shutil.rmtree(self._session_tmp, ignore_errors=True)
    except Exception:
        pass
    super().closeEvent(event)
```

**Extended version** (insert D-04 block after `self._closing.set()`):
```python
def closeEvent(self, event) -> None:
    """Shutdown thread pool and clean up leftover temp files on window close (D-04, D-12)."""
    self._closing.set()
    # Unblock any _folder_worker waiting on a dialog — None sentinel already in _folder_results (D-04)
    for ev in list(self._folder_events.values()):
        ev.set()
    self._executor.shutdown(wait=False)
    try:
        shutil.rmtree(self._session_tmp, ignore_errors=True)
    except Exception:
        pass
    super().closeEvent(event)
```

---

### `_on_download_row_finished` — submit `_folder_worker`

**Where:** Inside `_on_download_row_finished`, after incrementing `_download_done`, submit `_folder_worker` for rows that reached `AWAITING`.

**Pattern from analog** (`tunebridge.py:1012-1016`):
```python
if status == SongStatus.AWAITING.value:
    self._download_done += 1
else:
    self._download_failed += 1
```

**Extended block** (add executor submit when AWAITING):
```python
if status == SongStatus.AWAITING.value:
    self._download_done += 1
    self._folder_total += 1
    self._executor.submit(self._folder_worker, _row_id)   # chain into Phase 5 (D-02)
else:
    self._download_failed += 1
```

---

### `tests/test_organization.py` — new test file

**Analog:** `tests/test_download_pipeline.py:1-42` — exact fixture pattern.

**Fixture pattern** (`tests/test_download_pipeline.py:1-42`):
```python
# -*- coding: utf-8 -*-
"""TuneBridge Phase 4 — Download Pipeline tests (RED gate)."""
from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
from PySide6.QtWidgets import QApplication

from tunebridge import (
    TuneBridgeApp,
    SongStatus,
    _download_lock,
    download_track_for_row,
    retune_file,
)

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    return app

@pytest.fixture
def window(qapp):
    w = TuneBridgeApp()
    yield w
    w.close()
    w.deleteLater()
```

**New file header** (copy structure, adapt imports):
```python
# -*- coding: utf-8 -*-
"""TuneBridge Phase 5 — Organization tests (RED gate).

All tests MUST fail before Wave 1/2/3 implementation. They exercise
FolderConfirmDialog, _dialog_lock, _folder_worker, _show_folder_dialog,
_on_folder_row_finished, closeEvent extension, and SongStatus.SKIPPED/FAILED_SAVE.
"""
from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication

from tunebridge import (
    TuneBridgeApp,
    FolderConfirmDialog,
    SongStatus,
    _dialog_lock,
)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    return app


@pytest.fixture
def window(qapp):
    w = TuneBridgeApp()
    yield w
    w.close()
    w.deleteLater()
```

**Test patterns — Option B (dialog in isolation)** (`05-RESEARCH.md` lines 603-615):
```python
def test_confirm_disabled_empty_text(qapp):
    """ORG-02: Confirm button disabled when text field is empty."""
    dlg = FolderConfirmDialog("Test Song", None)
    dlg._path_edit.setText("")
    assert not dlg._confirm_btn.isEnabled()
    dlg.close()
```

**Test patterns — Option A (integration with mock)** (`05-RESEARCH.md` lines 580-601):
```python
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
        instance.exec.return_value = None
        MockDlg.return_value = instance
        with patch("tunebridge.shutil.move", return_value=str(dest / "track.mp3")) as mock_move:
            window._show_folder_dialog(0)

    mock_move.assert_called_once_with(str(temp_mp3), str(dest))
```

---

## Shared Patterns

### Closing guard
**Source:** `tunebridge.py:957-958`
**Apply to:** `_folder_worker` (first line of method body)
```python
if self._closing.is_set():
    return
```

### Per-row error isolation
**Source:** `tunebridge.py:994-1001`
**Apply to:** `_folder_worker` I/O section (OSError catch)
```python
except OSError as exc:
    logging.getLogger(__name__).warning("Save failed row %d: %s", row_id, exc)
    if not self._closing.is_set():
        self._dispatcher.row_status_changed.emit(row_id, SongStatus.FAILED_SAVE.value)
```

### Slot disconnect guard
**Source:** `tunebridge.py:1029-1032`
**Apply to:** `_on_folder_row_finished` if connected as signal slot (not needed for direct-call pattern)
```python
try:
    self._dispatcher.row_status_changed.disconnect(self._on_folder_row_finished)
except RuntimeError:
    pass   # already disconnected
```

### Thread-safe temp path read
**Source:** `tunebridge.py:991-992`
**Apply to:** `_folder_worker` whenever reading `_temp_paths[row_id]`
```python
with self._temp_paths_lock:
    temp = self._temp_paths.get(row_id)
```

### shutil.move Path wrapping
**Source:** `05-RESEARCH.md` Pitfall 4
**Apply to:** `_folder_worker` save path — shutil.move returns `str` on Python 3.10+
```python
final = Path(shutil.move(str(temp), str(result)))   # wrap: shutil.move returns str
```

### Windows empty-string is_dir guard
**Source:** `05-RESEARCH.md` Pitfall 1
**Apply to:** `FolderConfirmDialog._validate`
```python
valid = bool(text.strip()) and Path(text.strip()).is_dir()
# NOT: Path(text).is_dir() alone — Path('').is_dir() is True on Windows
```

---

## No Analog Found

| File/Symbol | Role | Data Flow | Reason |
|-------------|------|-----------|--------|
| `FolderConfirmDialog` (QDialog subclass) | component | request-response | No existing QDialog subclass in codebase; TuneBridgeApp is a QMainWindow. RESEARCH.md Pattern 1 is the primary reference. |
| `_show_folder_dialog` (shows dialog + sets Event) | controller slot | request-response | No existing slot both shows a dialog AND interacts with `threading.Event`. Composite of two patterns (slot structure from `_on_download_row_finished` + dialog exec pattern from RESEARCH.md). |

---

## Critical Pitfall Index

| Pitfall | Guard | Source |
|---------|-------|--------|
| `Path('').is_dir()` is `True` on Windows | `bool(text.strip()) and Path(text.strip()).is_dir()` | `05-RESEARCH.md` Pitfall 1 |
| `QDialog.exec()` from worker thread = deadlock | `FolderConfirmDialog` only instantiated/exec'd in `_show_folder_dialog` slot | `05-RESEARCH.md` Pitfall 2 |
| `_dialog_lock` scope too narrow → worker hang | Lock held from event creation through `event.wait()` return | `05-RESEARCH.md` Pitfall 3 |
| `shutil.move` returns `str` not `Path` | `final = Path(shutil.move(...))` | `05-RESEARCH.md` Pitfall 4 |
| `_folder_worker` submitted before `_temp_paths` written | Submit from `_on_download_row_finished` only (after AWAITING status guarantees write) | `05-RESEARCH.md` Pitfall 5 |

---

## Metadata

**Analog search scope:** `tunebridge.py`, `retune_app.py`, `tests/test_download_pipeline.py`
**Files scanned:** 3
**Pattern extraction date:** 2026-05-17
