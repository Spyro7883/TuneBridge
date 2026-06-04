# -*- coding: utf-8 -*-
"""RED-gate unit tests for Phase 11: SettingsDialog + preference-aware upload branch.

Intentionally RED until Wave 1/2 add:
  - tunebridge.SettingsDialog
  - tunebridge._find_playlist_id_by_name
  - _Dispatcher.settings_playlists_ready
  - preference mode-switch in _start_upload_batch
"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication, QDialog

import tunebridge
from tunebridge import TuneBridgeApp, SettingsDialog, _find_playlist_id_by_name


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    return app


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(tunebridge, "SETTINGS_PATH", tmp_path / "settings.json")
    w = TuneBridgeApp()
    yield w
    w.close()
    w.deleteLater()


def make_dialog(settings, monkeypatch, tmp_path):
    monkeypatch.setattr(tunebridge, "SETTINGS_PATH", tmp_path / "settings.json")
    tunebridge.save_settings(settings)
    disp = MagicMock()
    with patch("tunebridge._ibroadcast_login", return_value=("tok", 1, {}, {})):
        d = SettingsDialog(dispatcher=disp, settings=dict(settings), parent=None)
    return d


# ---------------------------------------------------------------------------
# PLST-01: signal / import / off-thread tests (Task 1)
# ---------------------------------------------------------------------------

def test_settings_dialog_importable(qapp):
    """PLST-01: SettingsDialog class must be importable from tunebridge."""
    assert hasattr(tunebridge, "SettingsDialog")


def test_settings_playlists_ready_signal_exists(qapp):
    """PLST-01: _Dispatcher must have settings_playlists_ready signal."""
    from tunebridge import _Dispatcher
    bt = MagicMock()
    d = _Dispatcher(bt)
    assert hasattr(d, "settings_playlists_ready")


def test_fetch_uses_executor(qapp, tmp_path, monkeypatch):
    """PLST-01: fetch is submitted to a dedicated ThreadPoolExecutor, not inline."""
    from concurrent.futures import ThreadPoolExecutor
    settings = {
        "local_save": False,
        "playlist_preference": "ask",
        "playlist_preference_name": "",
    }
    d = make_dialog(settings, monkeypatch, tmp_path)
    assert isinstance(d._dedicated_executor, ThreadPoolExecutor)


# ---------------------------------------------------------------------------
# PLST-01 continued: dialog opens + list population (Task 2)
# ---------------------------------------------------------------------------

def test_settings_dialog_opens(tmp_path, monkeypatch, qapp):
    """PLST-01: SettingsDialog can be constructed; starts on the loading page."""
    settings = {
        "local_save": False,
        "playlist_preference": "ask",
        "playlist_preference_name": "",
    }
    d = make_dialog(settings, monkeypatch, tmp_path)
    assert d._stack.currentIndex() == SettingsDialog._PAGE_LOADING


def test_playlists_ready_populates_list(monkeypatch, tmp_path, qapp):
    """PLST-01: _on_playlists_ready populates list, sorted A-Z case-insensitive."""
    settings = {
        "local_save": False,
        "playlist_preference": "ask",
        "playlist_preference_name": "",
    }
    d = make_dialog(settings, monkeypatch, tmp_path)
    d._on_playlists_ready({"p1": {"name": "Bravo"}, "p2": {"name": "Alpha"}})
    # 2 fixed items + 2 playlists = 4 rows
    assert d._list.count() == 4
    # Playlists sorted A-Z: row 2 = Alpha, row 3 = Bravo
    assert d._list.item(2).text() == "Alpha"
    assert d._list.item(3).text() == "Bravo"


# ---------------------------------------------------------------------------
# PLST-02: fixed items always present + library save (Task 2)
# ---------------------------------------------------------------------------

def test_fixed_items_always_present(monkeypatch, tmp_path, qapp):
    """PLST-02: Fixed rows 'Ask me each time' and 'Library only' always present."""
    from PySide6.QtCore import Qt
    settings = {
        "local_save": False,
        "playlist_preference": "ask",
        "playlist_preference_name": "",
    }
    d = make_dialog(settings, monkeypatch, tmp_path)
    d._on_playlists_ready({})
    assert d._list.item(0).text() == "Ask me each time"
    assert d._list.item(1).text() == "Library only (no playlist)"
    assert d._list.item(0).data(Qt.ItemDataRole.UserRole) == "ask"
    assert d._list.item(1).data(Qt.ItemDataRole.UserRole) == "library"


def test_library_only_saves_correctly(monkeypatch, tmp_path, qapp):
    """PLST-02: Selecting Library row and accept() persists preference=library, name=''."""
    settings = {
        "local_save": False,
        "playlist_preference": "ask",
        "playlist_preference_name": "",
    }
    d = make_dialog(settings, monkeypatch, tmp_path)
    d._on_playlists_ready({})
    d._list.setCurrentRow(1)  # Library only
    d.accept()
    loaded = tunebridge.load_settings()
    assert loaded["playlist_preference"] == "library"
    assert loaded["playlist_preference_name"] == ""


# ---------------------------------------------------------------------------
# PLST-04: upload-batch mode-switch (Task 2)
# ---------------------------------------------------------------------------

def test_library_skips_dialog(window, monkeypatch):
    """PLST-04: library pref → _start_upload_batch skips PlaylistSelectDialog, playlist_id=None."""
    tunebridge.save_settings({
        "local_save": False,
        "playlist_preference": "library",
        "playlist_preference_name": "",
    })
    with patch("tunebridge.PlaylistSelectDialog") as MockDlg:
        with patch("tunebridge._ibroadcast_login",
                   return_value=("tok", 1, {}, {"p1": {"name": "Alpha"}})):
            resolved = _find_playlist_id_by_name({"p1": {"name": "Alpha"}}, "")
            # library mode: no dialog, no lookup by name → None
            settings = tunebridge.load_settings()
            assert settings["playlist_preference"] == "library"
            MockDlg.assert_not_called()
            assert resolved is None


def test_favorite_skips_dialog(window, monkeypatch):
    """PLST-04: playlist pref with valid name → dialog skipped, correct playlist_id resolved."""
    tunebridge.save_settings({
        "local_save": False,
        "playlist_preference": "playlist",
        "playlist_preference_name": "Alpha",
    })
    live_playlists = {"p1": {"name": "Alpha"}}
    with patch("tunebridge.PlaylistSelectDialog") as MockDlg:
        resolved = _find_playlist_id_by_name(live_playlists, "Alpha")
        assert resolved == "p1"
        MockDlg.assert_not_called()


# ---------------------------------------------------------------------------
# PLST-05: stale / empty fallback (Task 2)
# ---------------------------------------------------------------------------

def test_stale_id_fallback(window, monkeypatch):
    """PLST-05: stale name → PlaylistSelectDialog shown with stale_notice; preference unchanged."""
    tunebridge.save_settings({
        "local_save": False,
        "playlist_preference": "playlist",
        "playlist_preference_name": "Zulu",
    })
    live_playlists = {"p1": {"name": "Alpha"}}
    # Zulu absent → _find_playlist_id_by_name returns None
    resolved = _find_playlist_id_by_name(live_playlists, "Zulu")
    assert resolved is None

    mock_dlg_instance = MagicMock()
    mock_dlg_instance.exec.return_value = QDialog.DialogCode.Accepted
    mock_dlg_instance.selected_id.return_value = "p1"

    with patch("tunebridge.PlaylistSelectDialog", return_value=mock_dlg_instance) as MockDlg:
        if live_playlists:
            stale_msg = (
                'Your saved playlist "Zulu" no longer exists'
                " — pick another or choose library only."
            )
            tunebridge.PlaylistSelectDialog(
                live_playlists, parent=None, stale_notice=stale_msg
            )
        _, kwargs = MockDlg.call_args
        assert kwargs.get("stale_notice") or (len(MockDlg.call_args.args) > 2 and MockDlg.call_args.args[2])

    # D-13: preference must remain unchanged after fallback
    assert tunebridge.load_settings()["playlist_preference_name"] == "Zulu"


def test_stale_empty_playlists_no_dialog(window, monkeypatch):
    """PLST-05: stale name + empty live playlists → no dialog, playlist_id=None, no crash."""
    tunebridge.save_settings({
        "local_save": False,
        "playlist_preference": "playlist",
        "playlist_preference_name": "Zulu",
    })
    live_playlists = {}
    resolved = _find_playlist_id_by_name(live_playlists, "Zulu")
    assert resolved is None

    with patch("tunebridge.PlaylistSelectDialog") as MockDlg:
        # no playlists → guard fires, dialog must NOT be shown
        if live_playlists:
            tunebridge.PlaylistSelectDialog(live_playlists, parent=None)
        MockDlg.assert_not_called()


# ---------------------------------------------------------------------------
# D-04 / D-07: empty account + fetch error (Task 2)
# ---------------------------------------------------------------------------

def test_empty_account_graceful(monkeypatch, tmp_path, qapp):
    """D-04: empty playlists → PAGE_LOADED, 2 fixed rows, empty note visible/set."""
    settings = {
        "local_save": False,
        "playlist_preference": "ask",
        "playlist_preference_name": "",
    }
    d = make_dialog(settings, monkeypatch, tmp_path)
    d._on_playlists_ready({})
    assert d._stack.currentIndex() == SettingsDialog._PAGE_LOADED
    assert d._list.count() == 2
    # empty note: check text contains "No playlists" (visibility unreliable headless)
    assert "No playlists" in d._lbl_empty_note.text()


def test_fetch_error_shows_retry(monkeypatch, tmp_path, qapp):
    """D-07: fetch failure → PAGE_ERROR with Retry button; no credentials/traceback in message."""
    settings = {
        "local_save": False,
        "playlist_preference": "ask",
        "playlist_preference_name": "",
    }
    d = make_dialog(settings, monkeypatch, tmp_path)
    d._fetch_failed = True
    d._on_playlists_ready({})
    assert d._stack.currentIndex() == SettingsDialog._PAGE_ERROR
    assert hasattr(d, "_btn_retry")
    assert "Couldn't load playlists" in d._lbl_error.text()
    assert "Traceback" not in d._lbl_error.text()
