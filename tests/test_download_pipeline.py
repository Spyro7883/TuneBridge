# -*- coding: utf-8 -*-
"""TuneBridge Phase 4 — Download Pipeline tests (RED gate).

All tests MUST fail before Wave 1/2/3 implementation. They exercise
download_track_for_row, retune_file, _download_lock, SongStatus.FAILED_DOWNLOAD,
and TuneBridgeApp attributes that do not exist until Wave 1+.
"""
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
    _find_best_yt_match,
    download_track_for_row,
    retune_file,
)


# ---------------------------------------------------------------------------
# QApplication singleton for all tests
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_spotify_uses_quoted_title_search(window):
    """DL-01: Spotify path calls _find_best_yt_match with title and artist."""
    metadata = {"artist": "Portishead", "track_title": "Glory Box", "source": "Spotify"}
    fake_mp3 = window._session_tmp / "abcdef12" / "track.mp3"
    fake_url = "https://www.youtube.com/watch?v=abc123"
    with patch("tunebridge._find_best_yt_match", return_value=fake_url) as mock_find, \
         patch("tunebridge.download_track_for_row", return_value=fake_mp3), \
         patch("pathlib.Path.mkdir"), \
         patch("tunebridge.uuid.uuid4") as mock_uuid:
        mock_uuid.return_value.hex = "abcdef1234567890"
        window._download_worker(0, "https://open.spotify.com/track/abc", "Spotify", metadata, 440)
    mock_find.assert_called_once_with("Glory Box", "Portishead")


def test_spotify_falls_back_to_ytsearch_when_no_match(window):
    """DL-01b: When _find_best_yt_match returns None, ytsearch fallback is used."""
    metadata = {"artist": "Portishead", "track_title": "Glory Box", "source": "Spotify"}
    fake_mp3 = window._session_tmp / "abcdef12" / "track.mp3"
    with patch("tunebridge._find_best_yt_match", return_value=None), \
         patch("tunebridge.download_track_for_row", return_value=fake_mp3) as mock_dl, \
         patch("pathlib.Path.mkdir"), \
         patch("tunebridge.uuid.uuid4") as mock_uuid:
        mock_uuid.return_value.hex = "abcdef1234567890"
        window._download_worker(0, "https://open.spotify.com/track/abc", "Spotify", metadata, 440)
    called_url = mock_dl.call_args[0][0]
    assert called_url.startswith("ytsearch:"), f"Expected ytsearch fallback, got: {called_url!r}"


def test_find_best_yt_match_picks_title_and_artist_match(tmp_path):
    """_find_best_yt_match returns URL for first candidate with artist+title in video title."""
    candidates = [
        {"id": "wrong1", "title": "Artist One - Other Song (Audio)", "channel": ""},
        {"id": "correct", "title": "Artist One - Song Alpha (Official Audio)", "channel": ""},
    ]
    with patch("tunebridge._search_yt_candidates", return_value=candidates):
        url = _find_best_yt_match("Song Alpha", "Artist One")
    assert url == "https://www.youtube.com/watch?v=correct"


def test_find_best_yt_match_returns_none_when_no_candidate_matches(tmp_path):
    """_find_best_yt_match returns None when no candidate has artist+title in title."""
    candidates = [
        {"id": "x", "title": "Completely Unrelated Video", "channel": ""},
    ]
    with patch("tunebridge._search_yt_candidates", return_value=candidates):
        assert _find_best_yt_match("Song Alpha", "Artist One") is None


def test_download_worker_spotify_path_calls_ytsearch(window):
    """DL-01: When no YT match found, Spotify falls back to ytsearch with artist+title."""
    metadata = {"artist": "Massive Attack", "track_title": "Teardrop", "source": "Spotify"}
    with patch("tunebridge._find_best_yt_match", return_value=None), \
         patch("tunebridge.download_track_for_row") as mock_dl, \
         patch("tunebridge.uuid.uuid4") as mock_uuid:
        mock_dl.return_value = Path("/tmp/tb_test/track.mp3")
        mock_uuid.return_value.hex = "aabbccdd11223344"
        window._download_worker(0, "https://open.spotify.com/track/xyz", "Spotify", metadata, 440)
    called_url = mock_dl.call_args[0][0]
    assert called_url.startswith("ytsearch:"), f"Expected ytsearch prefix, got: {called_url!r}"
    assert "Massive Attack" in called_url
    assert "Teardrop" in called_url
    assert "audio" in called_url


def test_download_worker_youtube_path_uses_direct_url(window):
    """DL-02: YouTube row _download_worker calls download_track_for_row with the raw YouTube URL."""
    yt_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    metadata = {"title": "Rick Astley - Never Gonna Give You Up", "source": "YouTube"}
    with patch("tunebridge.download_track_for_row") as mock_dl, \
         patch("tunebridge.uuid.uuid4") as mock_uuid:
        mock_dl.return_value = Path("/tmp/tb_test/track.mp3")
        mock_uuid.return_value.hex = "1234567890abcdef"
        window._download_worker(1, yt_url, "YouTube", metadata, 440)
    called_url = mock_dl.call_args[0][0]
    assert called_url == yt_url, f"Expected direct YouTube URL, got: {called_url!r}"
    assert not called_url.startswith("ytsearch:"), "YouTube path must not use ytsearch"


def test_failed_download_isolation(window):
    """DL-01/02: Failed row gets 'Failed — download'; second row is unaffected."""
    emitted = []
    window._dispatcher.row_status_changed.connect(
        lambda r, s: emitted.append((r, s))
    )
    with patch("tunebridge.download_track_for_row", side_effect=RuntimeError("yt-dlp failed")), \
         patch("tunebridge.uuid.uuid4") as mock_uuid:
        mock_uuid.return_value.hex = "deadbeef12345678"
        window._download_worker(2, "https://www.youtube.com/watch?v=fail", "YouTube", {}, 440)
    failed_statuses = [s for r, s in emitted if r == 2]
    assert "Failed — download" in failed_statuses, (
        f"Expected 'Failed — download' in emitted statuses for row 2, got: {emitted}"
    )
    # Other rows must not have received a failure signal
    other_failures = [(r, s) for r, s in emitted if r != 2 and s == "Failed — download"]
    assert other_failures == [], f"Other rows incorrectly received failure: {other_failures}"


def test_hz_toggle_default_440(window):
    """DL-03: 440Hz button is checked by default; QButtonGroup reports id=440."""
    assert window._btn_440.isChecked(), "440Hz button must be checked by default (D-05)"
    assert not window._btn_432.isChecked(), "432Hz button must not be checked by default"
    assert window._hz_group.checkedId() == 440, (
        f"QButtonGroup.checkedId() must return 440, got {window._hz_group.checkedId()}"
    )


def test_start_button_disabled_on_mixed_status(window, qapp):
    """DL-03: Start button disabled when not all rows are METADATA_READY (D-02)."""
    # Add two rows: one ready, one still fetching
    window.table._table.clearContents()
    window.table._table.setRowCount(0)
    from PySide6.QtWidgets import QTableWidgetItem
    window.table._table.setRowCount(2)
    window.table._table.setItem(0, 2, QTableWidgetItem("Metadata ready"))
    window.table._table.setItem(1, 2, QTableWidgetItem("Fetching metadata"))
    window._refresh_start_button()
    assert not window._btn_start.isEnabled(), (
        "Start button must be disabled when at least one row is not METADATA_READY"
    )


def test_start_button_enabled_all_ready(window, qapp):
    """DL-03: Start button enabled only when ALL rows have status 'Metadata ready' (D-02)."""
    from PySide6.QtWidgets import QTableWidgetItem
    window.table._table.clearContents()
    window.table._table.setRowCount(0)
    window.table._table.setRowCount(2)
    window.table._table.setItem(0, 2, QTableWidgetItem("Metadata ready"))
    window.table._table.setItem(1, 2, QTableWidgetItem("Metadata ready"))
    window._refresh_start_button()
    assert window._btn_start.isEnabled(), (
        "Start button must be enabled when all rows are METADATA_READY"
    )


def test_retune_called_on_432(window):
    """DL-04: retune_file() called when hz_mode=432; not called when hz_mode=440."""
    metadata = {"artist": "Portishead", "track_title": "Roads", "source": "Spotify"}
    with patch("tunebridge.download_track_for_row") as mock_dl, \
         patch("tunebridge.retune_file") as mock_retune, \
         patch("tunebridge.uuid.uuid4") as mock_uuid:
        mock_dl.return_value = Path("/tmp/tb_test/track.mp3")
        mock_uuid.return_value.hex = "cafebabe12345678"
        # 432Hz — retune must be called
        window._download_worker(0, "https://open.spotify.com/track/abc", "Spotify", metadata, 432)
        mock_retune.assert_called_once()
        mock_retune.reset_mock()
        # 440Hz — retune must NOT be called
        window._download_worker(0, "https://open.spotify.com/track/abc", "Spotify", metadata, 440)
        mock_retune.assert_not_called()


def test_status_transitions_432hz(window):
    """DL-04: 432Hz path emits Downloading → Retuning → Awaiting folder."""
    emitted = []
    window._dispatcher.row_status_changed.connect(
        lambda r, s: emitted.append((r, s))
    )
    metadata = {"artist": "Portishead", "track_title": "Roads", "source": "Spotify"}
    with patch("tunebridge.download_track_for_row") as mock_dl, \
         patch("tunebridge.retune_file"), \
         patch("tunebridge.uuid.uuid4") as mock_uuid:
        mock_dl.return_value = Path("/tmp/tb_test/track.mp3")
        mock_uuid.return_value.hex = "feedface12345678"
        window._download_worker(3, "https://open.spotify.com/track/abc", "Spotify", metadata, 432)
    statuses = [s for r, s in emitted if r == 3]
    assert "Downloading" in statuses, f"Expected 'Downloading' in {statuses}"
    assert "Retuning" in statuses, f"Expected 'Retuning' in {statuses}"
    assert "Awaiting folder" in statuses, f"Expected 'Awaiting folder' in {statuses}"
    dl_idx = statuses.index("Downloading")
    ret_idx = statuses.index("Retuning")
    aw_idx  = statuses.index("Awaiting folder")
    assert dl_idx < ret_idx < aw_idx, (
        f"Status order wrong: Downloading={dl_idx}, Retuning={ret_idx}, Awaiting={aw_idx}"
    )


def test_status_transitions_440hz(window):
    """DL-02: 440Hz path emits Downloading → Awaiting folder (no Retuning step)."""
    emitted = []
    window._dispatcher.row_status_changed.connect(
        lambda r, s: emitted.append((r, s))
    )
    yt_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    with patch("tunebridge.download_track_for_row") as mock_dl, \
         patch("tunebridge.retune_file") as mock_retune, \
         patch("tunebridge.uuid.uuid4") as mock_uuid:
        mock_dl.return_value = Path("/tmp/tb_test/track.mp3")
        mock_uuid.return_value.hex = "beefdead12345678"
        window._download_worker(4, yt_url, "YouTube", {}, 440)
    statuses = [s for r, s in emitted if r == 4]
    assert "Downloading" in statuses, f"Expected 'Downloading' in {statuses}"
    assert "Retuning" not in statuses, f"'Retuning' must NOT appear in 440Hz path, got: {statuses}"
    assert "Awaiting folder" in statuses, f"Expected 'Awaiting folder' in {statuses}"
    mock_retune.assert_not_called()
