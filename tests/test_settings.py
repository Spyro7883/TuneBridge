# -*- coding: utf-8 -*-
"""RED-gate unit tests for the settings layer (PLST-03).

These tests are intentionally RED until Wave 1 creates:
  - tunebridge.SETTINGS_PATH
  - tunebridge.load_settings()
  - tunebridge.save_settings()
"""
import json
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

import tunebridge


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    return app


def test_load_missing_returns_defaults(tmp_path, monkeypatch):
    """load_settings returns full DEFAULT_SETTINGS when file does not exist."""
    monkeypatch.setattr(tunebridge, "SETTINGS_PATH", tmp_path / "settings.json")
    result = tunebridge.load_settings()
    assert result == {
        "local_save": False,
        "playlist_preference": "ask",
        "playlist_preference_name": "",
    }


def test_load_corrupt_returns_defaults(tmp_path, monkeypatch):
    """load_settings returns full DEFAULT_SETTINGS on corrupt JSON — no raise."""
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(tunebridge, "SETTINGS_PATH", settings_path)
    settings_path.write_text("{not valid json", encoding="utf-8")
    result = tunebridge.load_settings()
    assert result == {
        "local_save": False,
        "playlist_preference": "ask",
        "playlist_preference_name": "",
    }


def test_load_partial_merges_defaults(tmp_path, monkeypatch):
    """load_settings fills missing keys from DEFAULT_SETTINGS when file is partial."""
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(tunebridge, "SETTINGS_PATH", settings_path)
    settings_path.write_text(json.dumps({"local_save": True}), encoding="utf-8")
    result = tunebridge.load_settings()
    assert result == {
        "local_save": True,
        "playlist_preference": "ask",
        "playlist_preference_name": "",
    }


def test_load_nondict_returns_defaults(tmp_path, monkeypatch):
    """load_settings returns full DEFAULT_SETTINGS when JSON root is non-dict — no raise."""
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(tunebridge, "SETTINGS_PATH", settings_path)
    settings_path.write_text(json.dumps([]), encoding="utf-8")
    result = tunebridge.load_settings()
    assert result == {
        "local_save": False,
        "playlist_preference": "ask",
        "playlist_preference_name": "",
    }


def test_save_load_roundtrip(tmp_path, monkeypatch):
    """save_settings then load_settings returns the exact same dict."""
    monkeypatch.setattr(tunebridge, "SETTINGS_PATH", tmp_path / "settings.json")
    payload = {
        "local_save": True,
        "playlist_preference": "always",
        "playlist_preference_name": "Chill",
    }
    tunebridge.save_settings(payload)
    result = tunebridge.load_settings()
    assert result == payload


def test_save_creates_dir(tmp_path, monkeypatch):
    """save_settings creates the parent directory when it does not exist."""
    new_path = tmp_path / "newdir" / "settings.json"
    monkeypatch.setattr(tunebridge, "SETTINGS_PATH", new_path)
    assert not new_path.parent.exists()
    tunebridge.save_settings(
        {"local_save": False, "playlist_preference": "ask", "playlist_preference_name": ""}
    )
    assert new_path.exists()
    assert new_path.parent.is_dir()


def test_save_atomic_failure_preserves(tmp_path, monkeypatch):
    """Failed os.replace leaves original file intact, cleans tmp orphan, does not raise."""
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(tunebridge, "SETTINGS_PATH", settings_path)
    # Pre-write a known valid settings file
    original_bytes = json.dumps(
        {"local_save": False, "playlist_preference": "ask", "playlist_preference_name": ""}
    ).encode("utf-8")
    settings_path.write_bytes(original_bytes)

    # Monkeypatch os.replace to simulate a mid-write failure
    monkeypatch.setattr(tunebridge.os, "replace", lambda src, dst: (_ for _ in ()).throw(OSError("simulated failure")))

    # save_settings must NOT raise
    tunebridge.save_settings(
        {"local_save": True, "playlist_preference": "always", "playlist_preference_name": "X"}
    )

    # Original file bytes must be unchanged
    assert settings_path.read_bytes() == original_bytes

    # No *.tmp orphan must remain
    assert list(tmp_path.glob("*.tmp")) == []


def test_chk_save_persists(tmp_path, monkeypatch, qapp):
    """SAVE-01: toggling _chk_save writes local_save to settings; a fresh app reads it back."""
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(tunebridge, "SETTINGS_PATH", settings_path)
    # Start from a clean settings file (default OFF)
    tunebridge.save_settings({
        "local_save": False,
        "playlist_preference": "ask",
        "playlist_preference_name": "",
    })

    from tunebridge import TuneBridgeApp
    w1 = TuneBridgeApp()
    try:
        assert w1._chk_save.isChecked() is False          # default OFF read from settings
        w1._chk_save.setChecked(True)                      # user toggles ON → stateChanged → save_settings
        # Persisted to disk
        assert tunebridge.load_settings()["local_save"] is True
    finally:
        w1.close()
        w1.deleteLater()

    # A fresh app instance restores the persisted ON state
    w2 = TuneBridgeApp()
    try:
        assert w2._chk_save.isChecked() is True
    finally:
        w2.close()
        w2.deleteLater()
