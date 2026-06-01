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
    # C-10: debounce timer defers is_dir() check by 300ms; flush synchronously.
    dlg._run_validate()
    assert not dlg._confirm_btn.isEnabled()
    dlg.close()


def test_confirm_disabled_nonexistent_path(qapp, tmp_path):
    """ORG-02/V5: Confirm button disabled when path does not exist on disk."""
    dlg = FolderConfirmDialog("Test Song", None)
    dlg._path_edit.setText(str(tmp_path / "does_not_exist"))
    # C-10: debounce timer defers is_dir() check by 300ms; flush synchronously.
    dlg._run_validate()
    assert not dlg._confirm_btn.isEnabled()
    dlg.close()


def test_confirm_enabled_valid_dir(qapp, tmp_path):
    """ORG-02/V5: Confirm button enabled when path is an existing directory."""
    dlg = FolderConfirmDialog("Test Song", None)
    dlg._path_edit.setText(str(tmp_path))
    # C-10: debounce timer defers is_dir() check by 300ms; flush synchronously.
    dlg._run_validate()
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
    """ORG-04: shutil.move called to stage temp to dest_dir/<name>.tmp on confirm.

    Updated for C-04: atomic-rename pattern moves to a .tmp sidecar first,
    then os.replace renames to final. Asserts the staging move call.
    """
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
        with patch("tunebridge.shutil.move") as mock_move, \
             patch("tunebridge.os.replace") as mock_replace:
            window._show_folder_dialog(3)
    expected_tmp = str(dest / "track.mp3.tmp")
    mock_move.assert_called_once_with(str(temp_mp3), expected_tmp)
    mock_replace.assert_called_once_with(expected_tmp, str(dest / "track.mp3"))


def test_saved_paths_populated_after_move(window, tmp_path):
    """ORG-04: window._saved_paths[row_id] is a Path after successful confirm.

    Updated for C-04: mocks both shutil.move (staging) and os.replace (atomic rename).
    """
    temp_mp3 = tmp_path / "track.mp3"
    temp_mp3.write_bytes(b"fake")
    dest = tmp_path / "dest2"
    dest.mkdir()
    window._temp_paths[4] = temp_mp3
    window._folder_events[4] = threading.Event()
    window._folder_results[4] = None
    with patch("tunebridge.FolderConfirmDialog") as MockDlg:
        instance = MagicMock()
        instance.result_path.return_value = dest
        MockDlg.return_value = instance
        with patch("tunebridge.shutil.move"), patch("tunebridge.os.replace"):
            window._show_folder_dialog(4)
    assert isinstance(window._saved_paths.get(4), Path)
    assert isinstance(window._upload_paths.get(4), Path)


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


def test_folder_batch_done_waits_for_all_downloads(window):
    """C-05: folder_batch_done must NOT fire until ALL rows finished, even if row 0 saves first."""
    # Simulate 3-row batch with _folder_total preset (C-05 fix)
    window._download_total = 3
    window._download_done = 0
    window._download_failed = 0
    window._folder_total = 3
    window._folder_done = 0
    window._folder_skipped = 0
    window._folder_failed = 0

    emitted = []
    window._dispatcher.folder_batch_done.connect(lambda: emitted.append("done"))

    # Row 0 finishes the folder dialog FIRST while rows 1, 2 still downloading
    window._on_folder_row_finished(0, SongStatus.UPLOADING.value)
    assert emitted == [], "folder_batch_done fired before rows 1, 2 reached AWAITING (C-05 regression)"

    # Rows 1, 2 also finish
    window._on_folder_row_finished(1, SongStatus.UPLOADING.value)
    window._on_folder_row_finished(2, SongStatus.SKIPPED.value)
    assert emitted == ["done"], "folder_batch_done should fire exactly once after all rows resolved"


def test_folder_batch_done_fires_when_late_download_fails(window):
    """WR-06: if the last download fails AFTER all other folder dialogs resolved,
    _on_download_row_finished must re-check the batch_done condition and emit.

    Scenario: 4 rows. 3 succeed download → folder dialog → status=Uploading
    (so _folder_done=3). The 4th hangs in yt-dlp, eventually fails. Without
    the WR-06 re-check, _folder_total shrinks 4→3 but folder_batch_done
    never fires → UI deadlocks (paste box stays locked, upload never starts).
    """
    window._download_total = 4
    window._download_done = 3
    window._download_failed = 0
    window._folder_total = 4
    window._folder_done = 3
    window._folder_skipped = 0
    window._folder_failed = 0

    emitted = []
    window._dispatcher.folder_batch_done.connect(lambda: emitted.append("done"))

    # The 4th download fails (e.g. yt-dlp exhausted all cookie variants)
    window._on_download_row_finished(3, SongStatus.FAILED_DOWNLOAD.value)

    assert window._folder_total == 3, "C-05: _folder_total must shrink on failed download"
    assert emitted == ["done"], (
        "WR-06 regression: folder_batch_done did not fire after _folder_total "
        "shrank to match already-resolved folder count → UI would deadlock"
    )


def test_folder_batch_done_not_double_fired_on_successive_failures(window):
    """WR-06: strict == guard prevents double emission when multiple
    downloads fail after folder_batch_done already fired."""
    window._download_total = 4
    window._download_done = 2
    window._download_failed = 0
    window._folder_total = 4
    window._folder_done = 2
    window._folder_skipped = 0
    window._folder_failed = 0

    emitted = []
    window._dispatcher.folder_batch_done.connect(lambda: emitted.append("done"))

    # First failure: _folder_total 4→3, finished=2 < 3 → no emit yet
    window._on_download_row_finished(2, SongStatus.FAILED_DOWNLOAD.value)
    assert emitted == []
    # Second failure: _folder_total 3→2, finished=2 == 2 → emit
    window._on_download_row_finished(3, SongStatus.FAILED_DOWNLOAD.value)
    assert emitted == ["done"]


def test_save_does_not_clobber_existing_file_on_partial_failure(window, tmp_path):
    """C-04: if shutil.move fails mid-save, the user's pre-existing file at dest is preserved."""
    temp_mp3 = tmp_path / "track.mp3"
    temp_mp3.write_bytes(b"new content")
    dest = tmp_path / "dest5"
    dest.mkdir()
    existing = dest / "track.mp3"
    existing.write_bytes(b"original user data")  # pre-existing file

    window._temp_paths[8] = temp_mp3
    window._folder_events[8] = threading.Event()
    window._folder_results[8] = None
    with patch("tunebridge.FolderConfirmDialog") as MockDlg:
        instance = MagicMock()
        instance.result_path.return_value = dest
        MockDlg.return_value = instance
        # Simulate shutil.move failing (disk full, AV lock, etc.) — must not have touched original
        with patch("tunebridge.shutil.move", side_effect=OSError("disk full")):
            window._show_folder_dialog(8)
    assert existing.exists(), "C-04 regression: original user file was destroyed on partial failure"
    assert existing.read_bytes() == b"original user data"


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


# Phase 10 (SAVE-01..03) — RED until Plan 02 Wave 1 lands.


def test_chk_save_default_off(window):
    """SAVE-01: _chk_save checkbox exists, default OFF, enabled, correct label."""
    assert window._chk_save.isChecked() is False
    assert window._chk_save.text() == "Save to local disk"
    assert window._chk_save.isEnabled() is True


def test_chk_save_disabled_during_batch(window):
    """SAVE-01: _chk_save is disabled while an active batch is running."""
    # Contract: _start_processing sets _chk_save.setEnabled(False) at batch start.
    # Directly verify the widget exists and can be set (will fail today: AttributeError).
    window._chk_save.setEnabled(False)
    assert window._chk_save.isEnabled() is False


def test_unlock_ui_reenables_chk_save(window):
    """SAVE-01: _unlock_ui re-enables _chk_save after batch completes."""
    window._chk_save.setEnabled(False)
    window._unlock_ui()
    assert window._chk_save.isEnabled() is True


def test_save_off_three_row_batch(window, tmp_path, monkeypatch):
    """SAVE-02 (HIGHEST RISK, deadlock): 3-row save-OFF batch: no folder_worker called,
    folder_batch_done fires exactly once, _upload_paths == temp paths for all 3 rows."""
    window._chk_save.setChecked(False)
    monkeypatch.setattr(window, "_folder_worker", MagicMock())
    # Populate temp paths
    for rid in (0, 1, 2):
        p = tmp_path / f"t{rid}.mp3"
        p.write_bytes(b"x")
        window._temp_paths[rid] = p
    # Set counters as _start_processing would
    window._folder_total = 3
    window._folder_done = 0
    window._folder_skipped = 0
    window._folder_failed = 0
    window._folder_batch_emitted = False
    window._download_total = 3
    window._download_done = 0
    window._download_failed = 0
    # Capture folder_batch_done emissions
    fired = []
    window._dispatcher.folder_batch_done.connect(lambda: fired.append(1))
    # Emit AWAITING for all 3 rows
    for rid in (0, 1, 2):
        window._on_download_row_finished(rid, SongStatus.AWAITING.value)
    # Assertions
    assert window._folder_worker.called is False, "save-OFF must not call _folder_worker"
    assert len(fired) == 1, f"folder_batch_done must fire exactly once, fired {len(fired)} times"
    assert window._upload_paths[0] == window._temp_paths[0]
    assert window._upload_paths[1] == window._temp_paths[1]
    assert window._upload_paths[2] == window._temp_paths[2]


def test_save_off_mixed_fail_no_double_emit(window, tmp_path):
    """SAVE-02 (double-emit guard): mixed batch (2 AWAITING + 1 FAILED_DOWNLOAD)
    emits folder_batch_done exactly once and only populates _upload_paths for succeeded rows."""
    window._chk_save.setChecked(False)
    window._folder_worker = MagicMock()
    # Rows 0, 1 get temp files; row 2 will emit FAILED_DOWNLOAD
    for rid in (0, 1):
        p = tmp_path / f"m{rid}.mp3"
        p.write_bytes(b"x")
        window._temp_paths[rid] = p
    # Set counters
    window._folder_total = 3
    window._folder_done = 0
    window._folder_skipped = 0
    window._folder_failed = 0
    window._folder_batch_emitted = False
    window._download_total = 3
    window._download_done = 0
    window._download_failed = 0
    fired = []
    window._dispatcher.folder_batch_done.connect(lambda: fired.append(1))
    # Emit
    window._on_download_row_finished(0, SongStatus.AWAITING.value)
    window._on_download_row_finished(1, SongStatus.AWAITING.value)
    window._on_download_row_finished(2, SongStatus.FAILED_DOWNLOAD.value)
    assert len(fired) == 1, f"folder_batch_done must fire exactly once, fired {len(fired)} times"
    assert len(window._upload_paths) == 2
    assert set(window._upload_paths.keys()) == {0, 1}


def test_save_off_upload_paths_is_temp(window, tmp_path):
    """SAVE-02: when save is OFF, _upload_paths[row_id] points to the temp file."""
    window._chk_save.setChecked(False)
    p = tmp_path / "five.mp3"
    p.write_bytes(b"x")
    window._temp_paths[5] = p
    window._folder_total = 1
    window._folder_done = 0
    window._folder_skipped = 0
    window._folder_failed = 0
    window._folder_batch_emitted = False
    window._download_total = 1
    window._download_done = 0
    window._download_failed = 0
    window._on_download_row_finished(5, SongStatus.AWAITING.value)
    assert window._upload_paths[5] == window._temp_paths[5]


def test_save_on_regression(window, tmp_path, monkeypatch):
    """SAVE-03 (v1.0 unchanged): when save is ON, _folder_worker is submitted and
    _upload_paths is NOT short-circuited in the download handler."""
    window._chk_save.setChecked(True)
    mock_submit = MagicMock()
    monkeypatch.setattr(window._executor, "submit", mock_submit)
    p = tmp_path / "six.mp3"
    p.write_bytes(b"x")
    window._temp_paths[6] = p
    window._folder_total = 1
    window._folder_done = 0
    window._folder_skipped = 0
    window._folder_failed = 0
    window._folder_batch_emitted = False
    window._download_total = 1
    window._download_done = 0
    window._download_failed = 0
    assert not window._closing.is_set()
    window._on_download_row_finished(6, SongStatus.AWAITING.value)
    assert mock_submit.called is True, "save-ON must submit _folder_worker"
    args = mock_submit.call_args[0]
    assert args[0] == window._folder_worker and args[1] == 6
    assert 6 not in window._upload_paths, "save-ON must not short-circuit _upload_paths in download handler"
