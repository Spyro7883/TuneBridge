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
    mock_find.assert_called_once_with("Glory Box", "Portishead", duration_ms=0)


def test_spotify_emits_failed_when_no_yt_music_match(window):
    """DL-01b: When _find_best_yt_match returns None, row gets FAILED_DOWNLOAD status."""
    metadata = {"artist": "Portishead", "track_title": "Glory Box", "source": "Spotify"}
    emitted = []
    window._dispatcher.row_status_changed.connect(lambda r, s: emitted.append((r, s)))
    with patch("tunebridge._find_best_yt_match", return_value=None), \
         patch("pathlib.Path.mkdir"), \
         patch("tunebridge.uuid.uuid4") as mock_uuid:
        mock_uuid.return_value.hex = "abcdef1234567890"
        window._download_worker(0, "https://open.spotify.com/track/abc", "Spotify", metadata, 440)
    failed = [s for r, s in emitted if r == 0 and s == SongStatus.FAILED_DOWNLOAD.value]
    assert failed, f"Expected FAILED_DOWNLOAD status, got: {emitted}"


def test_find_best_yt_match_picks_by_duration_and_title(tmp_path):
    """_find_best_yt_match returns YouTube Music URL for candidate matching duration + title."""
    candidates = [
        {"id": "wrong1", "title": "Artist One - Other Song", "channel": "", "duration": 200},
        {"id": "correct", "title": "Artist One - Song Alpha (Official Audio)", "channel": "", "duration": 183},
    ]
    with patch("tunebridge._search_yt_candidates", return_value=candidates):
        # duration_ms=183000 → 183s; candidate "correct" is within ±2s
        url = _find_best_yt_match("Song Alpha", "Artist One", duration_ms=183000)
    assert url == "https://music.youtube.com/watch?v=correct"


def test_find_best_yt_match_returns_none_when_no_candidate_matches(tmp_path):
    """_find_best_yt_match returns None when no candidate matches title or artist."""
    candidates = [
        {"id": "x", "title": "Completely Unrelated Video", "channel": "", "duration": 0},
    ]
    with patch("tunebridge._search_yt_candidates", return_value=candidates):
        assert _find_best_yt_match("Song Alpha", "Artist One") is None


def test_find_best_yt_match_penalises_spanish_portuguese_live(tmp_path):
    """WR-07: live videos with ES/PT keywords (concierto, en directo, ao vivo,
    en gira) must lose to official audio uploads even when their view counts
    are higher. Regression for high-view show recordings outranking studio audio."""
    candidates = [
        # High-view live recording with non-English live indicator
        {"id": "live_es", "title": "Artist One - Song Alpha (En Concierto)",
         "channel": "Some Label LA", "duration": 230, "view_count": 50_000_000},
        # Official audio: lower views, exact duration match
        {"id": "audio_ok", "title": "Song Alpha (Audio)",
         "channel": "Some Label VEVO", "duration": 215, "view_count": 100_000},
    ]
    with patch("tunebridge._search_yt_candidates", return_value=candidates):
        url = _find_best_yt_match("Song Alpha", "Artist One",
                                  duration_ms=215_000)
    assert url == "https://music.youtube.com/watch?v=audio_ok", (
        f"WR-07 regression: live (ES keyword) outranked official audio → {url}"
    )


def test_find_best_yt_match_allows_live_when_spotify_title_is_live(tmp_path):
    """WR-07: penalty must NOT apply if the Spotify track itself is a live
    recording (e.g. 'Song (En Vivo)')."""
    candidates = [
        {"id": "live_match", "title": "Artist - Song (En Vivo)",
         "channel": "Artist Official", "duration": 200, "view_count": 1_000_000},
        {"id": "studio", "title": "Artist - Song",
         "channel": "Artist Official", "duration": 200, "view_count": 1_000_000},
    ]
    with patch("tunebridge._search_yt_candidates", return_value=candidates):
        url = _find_best_yt_match("Song (En Vivo)", "Artist", duration_ms=200_000)
    assert url == "https://music.youtube.com/watch?v=live_match", (
        f"WR-07: live YT result wrongly penalised for live Spotify title → {url}"
    )


def test_download_worker_spotify_uses_yt_music_url(window):
    """DL-01: Spotify path calls download_track_for_row with a YouTube Music URL."""
    metadata = {"artist": "Massive Attack", "track_title": "Teardrop", "source": "Spotify"}
    fake_url = "https://music.youtube.com/watch?v=abc123"
    with patch("tunebridge._find_best_yt_match", return_value=fake_url), \
         patch("tunebridge.download_track_for_row") as mock_dl, \
         patch("tunebridge.uuid.uuid4") as mock_uuid:
        mock_dl.return_value = Path("/tmp/tb_test/track.mp3")
        mock_uuid.return_value.hex = "aabbccdd11223344"
        window._download_worker(0, "https://open.spotify.com/track/xyz", "Spotify", metadata, 440)
    called_url = mock_dl.call_args[0][0]
    assert called_url == fake_url, f"Expected YT Music URL, got: {called_url!r}"


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
    assert not called_url.startswith(("ytsearch:", "ytmsearch:")), \
        "YouTube path must use direct URL, not a search query"


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
    fake_url = "https://music.youtube.com/watch?v=fake123"
    with patch("tunebridge._find_best_yt_match", return_value=fake_url), \
         patch("tunebridge.download_track_for_row") as mock_dl, \
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
    fake_url = "https://music.youtube.com/watch?v=fake"
    with patch("tunebridge._find_best_yt_match", return_value=fake_url), \
         patch("tunebridge.download_track_for_row") as mock_dl, \
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


def test_download_returns_correct_file_when_multiple_mp3s_present(tmp_path):
    """C-06: download_track_for_row globs only its own per-call token, not all mp3s in out_dir."""
    from unittest.mock import patch, MagicMock

    out_dir = tmp_path
    # Pre-existing unrelated mp3 from a previous (failed/stale) download.
    stale = out_dir / "old_song.mp3"
    stale.write_bytes(b"stale")

    captured_token = {}

    def fake_popen(cmd, **kwargs):
        idx = cmd.index("-o")
        template = cmd[idx + 1]
        # Template like "<out_dir>/tb_XXXXXXXX_%(title)s.%(ext)s"
        name_template = Path(template).name
        token = name_template.split("_%")[0]   # "tb_XXXXXXXX"
        captured_token["t"] = token
        produced = out_dir / f"{token}_Real Track.mp3"
        produced.write_bytes(b"new")
        proc = MagicMock()
        proc.stdout.read.return_value = ""
        proc.wait.return_value = 0
        proc.poll.return_value = 0
        proc.returncode = 0
        return proc

    with patch("tunebridge.shutil.which", return_value="yt-dlp"), \
         patch("tunebridge.subprocess.Popen", side_effect=fake_popen):
        result = download_track_for_row("ytsearch1:foo", out_dir)

    assert result is not None
    assert result.name.startswith(captured_token["t"]), \
        f"Got {result.name} but should have started with the per-call token"
    assert stale.exists(), "stale unrelated mp3 must not be returned"


def test_failed_save_preserves_valid_card_count(window):
    """C-08: 'Failed — save' must NOT flip a row from valid → invalid.

    Save failures occur after the URL was already classified as valid (it
    fetched metadata and downloaded successfully); only metadata failures
    should reclassify a row in the stat cards.
    """
    window._card_valid.set_count(3)
    window._card_invalid.set_count(0)
    # Add a row with a known status item so update_row_status can flip it.
    from PySide6.QtWidgets import QTableWidgetItem
    window.table._table.setRowCount(1)
    window.table._table.setItem(0, 0, QTableWidgetItem("Some Track"))
    window.table._table.setItem(0, 1, QTableWidgetItem("Spotify"))
    window.table._table.setItem(0, 2, QTableWidgetItem("Saving"))

    window.table.update_row_status(0, SongStatus.FAILED_SAVE.value)

    assert window._card_valid.count() == 3, (
        f"valid count must remain 3 after Failed — save, got {window._card_valid.count()}"
    )
    assert window._card_invalid.count() == 0, (
        f"invalid count must remain 0 after Failed — save, got {window._card_invalid.count()}"
    )

    # Sanity check the inverse: Failed — metadata SHOULD flip the cards.
    window.table._table.setItem(0, 2, QTableWidgetItem("Fetching metadata"))
    window.table.update_row_status(0, "Failed — metadata")
    assert window._card_valid.count() == 2, "Failed — metadata must decrement valid"
    assert window._card_invalid.count() == 1, "Failed — metadata must increment invalid"
