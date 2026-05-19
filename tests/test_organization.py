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


def test_last_folder_empty_on_first(window):
    """ORG-01: _last_folder is None on a fresh window — no pre-fill for first dialog."""
    assert window._last_folder is None


def test_last_folder_updates_after_confirm(window, tmp_path):
    """ORG-01: _last_folder updated to confirmed path after _show_folder_dialog confirms."""
    dest = tmp_path / "music"
    dest.mkdir()
    window._temp_paths[0] = tmp_path / "track.mp3"
    window._folder_events[0] = threading.Event()
    window._folder_results[0] = None
    with patch("tunebridge.FolderConfirmDialog") as MockDlg:
        instance = MagicMock()
        instance.result_path.return_value = dest
        MockDlg.return_value = instance
        window._show_folder_dialog(0)
    assert window._last_folder == dest


def test_confirm_disabled_empty_text(qapp):
    """ORG-02/V5: Confirm button disabled when QLineEdit is empty."""
    dlg = FolderConfirmDialog("Test Song", None)
    dlg._path_edit.setText("")
    assert not dlg._confirm_btn.isEnabled()
    dlg.close()


def test_confirm_disabled_nonexistent_path(qapp, tmp_path):
    """ORG-02/V5: Confirm button disabled when path does not exist on disk."""
    dlg = FolderConfirmDialog("Test Song", None)
    dlg._path_edit.setText(str(tmp_path / "does_not_exist"))
    assert not dlg._confirm_btn.isEnabled()
    dlg.close()


def test_confirm_enabled_valid_dir(qapp, tmp_path):
    """ORG-02/V5: Confirm button enabled when path is an existing directory."""
    dlg = FolderConfirmDialog("Test Song", None)
    dlg._path_edit.setText(str(tmp_path))
    assert dlg._confirm_btn.isEnabled()
    dlg.close()


def test_browse_calls_get_existing_directory(qapp, tmp_path):
    """ORG-02: Browse button calls QFileDialog.getExistingDirectory."""
    dlg = FolderConfirmDialog("Test Song", None)
    with patch("tunebridge.QFileDialog.getExistingDirectory", return_value="") as mock_fd:
        dlg._browse()
    mock_fd.assert_called_once()
    dlg.close()


def test_skip_deletes_temp_and_emits_skipped(window, tmp_path):
    """ORG-03: Skipping deletes temp MP3 and emits SongStatus.SKIPPED status."""
    temp_mp3 = tmp_path / "track.mp3"
    temp_mp3.write_bytes(b"fake")
    window._temp_paths[1] = temp_mp3
    window._folder_events[1] = threading.Event()
    window._folder_results[1] = None
    emitted = []
    window._dispatcher.row_status_changed.connect(
        lambda rid, st: emitted.append((rid, st))
    )
    with patch("tunebridge.FolderConfirmDialog") as MockDlg:
        instance = MagicMock()
        instance.result_path.return_value = None   # skip sentinel
        MockDlg.return_value = instance
        window._show_folder_dialog(1)
    assert not temp_mp3.exists()
    assert any(st == SongStatus.SKIPPED.value for _, st in emitted)


def test_skip_does_not_block_other_rows(window, tmp_path):
    """ORG-03: Skip completes synchronously without blocking; _folder_events entry is set."""
    window._folder_events[2] = threading.Event()
    window._folder_results[2] = None
    window._temp_paths[2] = tmp_path / "nonexistent.mp3"
    with patch("tunebridge.FolderConfirmDialog") as MockDlg:
        instance = MagicMock()
        instance.result_path.return_value = None
        MockDlg.return_value = instance
        window._show_folder_dialog(2)
    assert window._folder_events[2].is_set()


def test_confirm_calls_shutil_move(window, tmp_path):
    """ORG-04: shutil.move called with str(temp_path) and str(dest_folder) on confirm."""
    temp_mp3 = tmp_path / "track.mp3"
    temp_mp3.write_bytes(b"fake")
    dest = tmp_path / "dest"
    dest.mkdir()
    window._temp_paths[3] = temp_mp3
    window._folder_events[3] = threading.Event()
    window._folder_results[3] = None
    with patch("tunebridge.FolderConfirmDialog") as MockDlg:
        instance = MagicMock()
        instance.result_path.return_value = dest
        MockDlg.return_value = instance
        with patch("tunebridge.shutil.move", return_value=str(dest / "track.mp3")) as mock_move:
            window._show_folder_dialog(3)
    mock_move.assert_called_once_with(str(temp_mp3), str(dest))


def test_saved_paths_populated_after_move(window, tmp_path):
    """ORG-04: window._saved_paths[row_id] is a Path after successful confirm."""
    temp_mp3 = tmp_path / "track.mp3"
    temp_mp3.write_bytes(b"fake")
    dest = tmp_path / "dest2"
    dest.mkdir()
    final = dest / "track.mp3"
    window._temp_paths[4] = temp_mp3
    window._folder_events[4] = threading.Event()
    window._folder_results[4] = None
    with patch("tunebridge.FolderConfirmDialog") as MockDlg:
        instance = MagicMock()
        instance.result_path.return_value = dest
        MockDlg.return_value = instance
        with patch("tunebridge.shutil.move", return_value=str(final)):
            window._show_folder_dialog(4)
    assert isinstance(window._saved_paths.get(4), Path)


def test_oserror_emits_failed_save(window, tmp_path):
    """ORG-04: OSError during shutil.move causes row to emit 'Failed — save' status."""
    temp_mp3 = tmp_path / "track.mp3"
    temp_mp3.write_bytes(b"fake")
    dest = tmp_path / "dest3"
    dest.mkdir()
    window._temp_paths[5] = temp_mp3
    window._folder_events[5] = threading.Event()
    window._folder_results[5] = None
    emitted = []
    window._dispatcher.row_status_changed.connect(
        lambda rid, st: emitted.append((rid, st))
    )
    with patch("tunebridge.FolderConfirmDialog") as MockDlg:
        instance = MagicMock()
        instance.result_path.return_value = dest
        MockDlg.return_value = instance
        with patch("tunebridge.shutil.move", side_effect=OSError("disk full")):
            window._show_folder_dialog(5)
    assert any(st == SongStatus.FAILED_SAVE.value for _, st in emitted)


def test_folder_batch_done_emitted(window):
    """D-11: folder_batch_done signal emitted when all folder dialogs resolve."""
    window._folder_total = 1
    window._folder_done = 0
    window._folder_skipped = 0
    window._folder_failed = 0
    fired = []
    window._dispatcher.folder_batch_done.connect(lambda: fired.append(True))
    window._on_folder_row_finished(0, SongStatus.UPLOADING.value)
    assert fired, "folder_batch_done was not emitted after all rows resolved"


def test_status_bar_summary(window):
    """D-08: Status bar shows 'Saved X, skipped Y, failed Z' after all dialogs resolve."""
    window._folder_total = 3
    window._folder_done = 0
    window._folder_skipped = 0
    window._folder_failed = 0
    window._on_folder_row_finished(0, SongStatus.UPLOADING.value)
    window._on_folder_row_finished(1, SongStatus.SKIPPED.value)
    window._on_folder_row_finished(2, SongStatus.FAILED_SAVE.value)
    msg = window.statusBar().currentMessage()
    assert "Saved 1" in msg
    assert "skipped 1" in msg
    assert "failed 1" in msg


def test_close_event_unblocks_pending_workers(window):
    """D-04: closeEvent calls ev.set() for all entries in _folder_events."""
    ev1 = threading.Event()
    ev2 = threading.Event()
    window._folder_events[10] = ev1
    window._folder_events[11] = ev2
    mock_close_event = MagicMock()
    window.closeEvent(mock_close_event)
    assert ev1.is_set(), "closeEvent did not unblock ev1"
    assert ev2.is_set(), "closeEvent did not unblock ev2"


def test_dialog_lock_blocks_concurrent_acquisition():
    """SC-5: _dialog_lock is a real mutex — second acquire blocks while first is held."""
    lock_held = threading.Event()
    proceed = threading.Event()

    def hold():
        with _dialog_lock:
            lock_held.set()
            proceed.wait(timeout=2)

    t = threading.Thread(target=hold, daemon=True)
    t.start()
    lock_held.wait(timeout=1)

    # Non-blocking acquire must fail while t holds the lock
    acquired = _dialog_lock.acquire(blocking=False)
    if acquired:
        _dialog_lock.release()
    proceed.set()
    t.join(timeout=2)

    assert not acquired, "Lock was acquirable while held by another thread — no mutual exclusion"


def test_folder_dialog_unblocks_worker_on_exception(window, tmp_path):
    """C-03: if FolderConfirmDialog raises, _show_folder_dialog must still set the event."""
    window._temp_paths[7] = tmp_path / "nope.mp3"
    ev = threading.Event()
    window._folder_events[7] = ev
    window._folder_results[7] = None
    with patch("tunebridge.FolderConfirmDialog", side_effect=RuntimeError("boom")):
        window._show_folder_dialog(7)
    assert ev.is_set(), "Worker would deadlock — event was not set after dialog raised"
    assert window._folder_results[7] is None
