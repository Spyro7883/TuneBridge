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
