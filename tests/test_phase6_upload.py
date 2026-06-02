# -*- coding: utf-8 -*-
"""Tests for Phase 6 — iBroadcast upload helpers and batch wiring."""
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from tunebridge import (
    TuneBridgeApp,
    _ibroadcast_add_to_playlist,
    _ibroadcast_login,
    _ibroadcast_upload,
    _is_duplicate,
)


# ---------------------------------------------------------------------------
# _ibroadcast_login tests (3)
# ---------------------------------------------------------------------------

def test_ibroadcast_login_success():
    payload = {
        "result": True,
        "user": {"token": "abc123", "id": 42},
        "library": {
            "tracks": {"1": {"title": "T", "artist": "A"}},
            "playlists": {"99": {"name": "Favs", "tracks": []}},
        },
    }
    mock_resp = MagicMock()
    mock_resp.json.return_value = payload
    with patch("tunebridge.requests.post", return_value=mock_resp):
        token, user_id, library, playlists = _ibroadcast_login("user@test.com", "pass")
    assert token == "abc123"
    assert user_id == 42
    assert library == {"1": {"title": "T", "artist": "A"}}
    assert playlists == {"99": {"name": "Favs", "tracks": []}}


def test_ibroadcast_login_wrong_password():
    payload = {"result": False, "message": "Invalid credentials"}
    mock_resp = MagicMock()
    mock_resp.json.return_value = payload
    with patch("tunebridge.requests.post", return_value=mock_resp):
        token, user_id, library, playlists = _ibroadcast_login("user@test.com", "wrong")
    assert token is None
    assert user_id is None
    assert library == {}
    assert playlists == {}


def test_ibroadcast_login_network_error():
    with patch("tunebridge.requests.post", side_effect=requests.ConnectionError("timeout")):
        token, user_id, library, playlists = _ibroadcast_login("user@test.com", "pass")
    assert token is None
    assert user_id is None
    assert library == {}
    assert playlists == {}


# ---------------------------------------------------------------------------
# _is_duplicate tests (3)
# ---------------------------------------------------------------------------

_LIBRARY = {"1": {"title": "Bohemian Rhapsody", "artist": "Queen"}}


def test_is_duplicate_match():
    assert _is_duplicate("Bohemian Rhapsody", "Queen", _LIBRARY) is True


def test_is_duplicate_no_match():
    assert _is_duplicate("Another Song", "Queen", _LIBRARY) is False


def test_is_duplicate_case_insensitive():
    assert _is_duplicate("BOHEMIAN RHAPSODY", "queen", _LIBRARY) is True


# ---------------------------------------------------------------------------
# _ibroadcast_upload tests (3) — now returns (bool, track_id|None)
# ---------------------------------------------------------------------------

def test_ibroadcast_upload_success(tmp_path):
    mp3 = tmp_path / "song.mp3"
    mp3.write_bytes(b"FAKE_MP3")
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {"result": True, "id": 9999}
    with patch("tunebridge.requests.post", return_value=mock_resp):
        success, track_id = _ibroadcast_upload(mp3, 42, "abc123")
    assert success is True
    assert track_id == 9999


def test_ibroadcast_upload_server_failure(tmp_path):
    mp3 = tmp_path / "song.mp3"
    mp3.write_bytes(b"FAKE_MP3")
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {"result": False}
    with patch("tunebridge.requests.post", return_value=mock_resp):
        success, track_id = _ibroadcast_upload(mp3, 42, "abc123")
    assert success is False
    assert track_id is None


def test_ibroadcast_upload_network_error(tmp_path):
    mp3 = tmp_path / "song.mp3"
    mp3.write_bytes(b"FAKE_MP3")
    with patch("tunebridge.requests.post", side_effect=requests.Timeout):
        success, track_id = _ibroadcast_upload(mp3, 42, "abc123")
    assert success is False
    assert track_id is None


# ---------------------------------------------------------------------------
# _ibroadcast_add_to_playlist tests (2)
# ---------------------------------------------------------------------------

def test_ibroadcast_add_to_playlist_success():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"result": True}
    with patch("tunebridge.requests.post", return_value=mock_resp) as mock_post:
        result = _ibroadcast_add_to_playlist("99", [1, 2], [3], 42, "tok")
    assert result is True
    posted = mock_post.call_args[1]["json"]
    assert posted["playlist_id"] == 99
    assert set(posted["tracks"]) == {1, 2}


def test_ibroadcast_add_to_playlist_failure():
    with patch("tunebridge.requests.post", side_effect=requests.ConnectionError):
        result = _ibroadcast_add_to_playlist("99", [1], [], 42, "tok")
    assert result is False


# ---------------------------------------------------------------------------
# _start_upload_batch guard path tests (3) — Plan 06-02
# ---------------------------------------------------------------------------

def test_start_upload_batch_empty_guard():
    app = MagicMock()
    app._upload_paths = {}
    TuneBridgeApp._start_upload_batch(app)
    app._unlock_ui.assert_called_once()


def test_start_upload_batch_missing_credentials(monkeypatch):
    monkeypatch.delenv("IBROADCAST_USERNAME", raising=False)
    monkeypatch.delenv("IBROADCAST_PASSWORD", raising=False)
    app = MagicMock()
    app._upload_paths = {1: Path("song.mp3")}
    TuneBridgeApp._start_upload_batch(app)
    app._dispatcher.row_status_changed.emit.assert_called_with(1, "Done")
    app._unlock_ui.assert_called_once()


def test_start_upload_batch_auth_failure(monkeypatch):
    monkeypatch.setenv("IBROADCAST_USERNAME", "user@test.com")
    monkeypatch.setenv("IBROADCAST_PASSWORD", "wrong")
    app = MagicMock()
    app._upload_paths = {1: Path("song.mp3")}
    with patch("tunebridge._ibroadcast_login", return_value=(None, None, {}, {})):
        TuneBridgeApp._start_upload_batch(app)
    app._dispatcher.row_status_changed.emit.assert_called_with(1, "Failed — upload")
    app._unlock_ui.assert_called_once()


# ---------------------------------------------------------------------------
# _upload_worker + _on_upload_row_finished tests (4) — Plan 06-03
# ---------------------------------------------------------------------------

def test_upload_worker_duplicate_skips_upload():
    app = MagicMock()
    app._closing.is_set.return_value = False
    app._row_metadata = {1: {"title": "Song", "artist": "Band"}}
    app._upload_paths = {1: Path("song.mp3")}
    with patch("tunebridge._is_duplicate", return_value=True), \
         patch("tunebridge._ibroadcast_upload") as mock_upload:
        TuneBridgeApp._upload_worker(app, 1, "token", 42, {})
    app._dispatcher.row_status_changed.emit.assert_called_with(1, "Already uploaded")
    mock_upload.assert_not_called()


def test_upload_worker_success():
    app = MagicMock()
    app._closing.is_set.return_value = False
    app._upload_playlist_id = None
    app._row_metadata = {1: {"title": "Song", "artist": "Band"}}
    app._upload_paths = {1: Path("song.mp3")}
    with patch("tunebridge._is_duplicate", return_value=False), \
         patch("tunebridge._ibroadcast_upload", return_value=(True, 9999)):
        TuneBridgeApp._upload_worker(app, 1, "token", 42, {})
    app._dispatcher.row_status_changed.emit.assert_called_with(1, "Done")


def test_upload_worker_failure():
    app = MagicMock()
    app._closing.is_set.return_value = False
    app._upload_playlist_id = None
    app._row_metadata = {1: {"title": "Song", "artist": "Band"}}
    app._upload_paths = {1: Path("song.mp3")}
    with patch("tunebridge._is_duplicate", return_value=False), \
         patch("tunebridge._ibroadcast_upload", return_value=(False, None)):
        TuneBridgeApp._upload_worker(app, 1, "token", 42, {})
    app._dispatcher.row_status_changed.emit.assert_called_with(1, "Failed — upload")


def test_on_upload_row_finished_batch_counter():
    app = MagicMock()
    app._upload_total = 2
    app._upload_done = 0
    app._upload_existed = 0
    app._upload_failed = 0
    app._upload_playlist_id = None
    app._upload_track_ids = []

    # First call — batch not yet complete
    TuneBridgeApp._on_upload_row_finished(app, 1, "Done")
    assert app._upload_done == 1
    app._dispatcher.upload_batch_done.emit.assert_not_called()

    # Second call — batch complete
    TuneBridgeApp._on_upload_row_finished(app, 2, "Already uploaded")
    assert app._upload_existed == 1
    app._dispatcher.upload_batch_done.emit.assert_called_once()
    # Pitfall 12: final summary routes through status_message signal, not statusBar() directly.
    msg = app._dispatcher.status_message.emit.call_args[0][0]
    assert "1 uploaded" in msg
    assert "1 already existed" in msg
