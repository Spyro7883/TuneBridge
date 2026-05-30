# -*- coding: utf-8 -*-
"""Tests for TuneBridge Phase 2 — PySide6 implementation."""
import inspect
import re

import pytest

from PySide6.QtCore import QMimeData
from PySide6.QtWidgets import QApplication

from unittest.mock import MagicMock, patch
from pathlib import Path

from mutagen.id3 import ID3, APIC

from tunebridge import (
    BatchTable,
    PasteTextEdit,
    SongStatus,
    StatCard,
    TuneBridgeApp,
    _Dispatcher,
    classify_url,
    _write_id3_tags,
    _fetch_cover_bytes,
    _sniff_mime,
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
# classify_url — pure function, no fixtures needed
# ---------------------------------------------------------------------------


def test_classify_spotify_track():
    assert classify_url("https://open.spotify.com/track/abc123") == "Spotify"


def test_classify_spotify_album():
    assert classify_url("https://open.spotify.com/album/xyz789") == "Spotify"


def test_classify_spotify_playlist():
    assert classify_url("https://open.spotify.com/playlist/pl123") == "Spotify"


def test_classify_spotify_artist():
    assert classify_url("https://open.spotify.com/artist/ar123") == "Spotify"


def test_classify_spotify_intl_locale():
    assert classify_url("https://open.spotify.com/intl-es/track/0RrwwLDXmvCGXXzuDgwvO") == "Spotify"
    assert classify_url("https://open.spotify.com/intl-ro/album/abc123") == "Spotify"


def test_classify_youtube_watch():
    assert classify_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "YouTube"


def test_classify_youtube_short():
    assert classify_url("https://youtu.be/dQw4w9WgXcQ") == "YouTube"


def test_classify_invalid_returns_none():
    assert classify_url("https://example.com/song") is None


def test_classify_empty_string():
    assert classify_url("") is None


def test_classify_none_like_blank():
    assert classify_url("   ") is None


# ---------------------------------------------------------------------------
# SongStatus enum
# ---------------------------------------------------------------------------


def test_status_enum_values():
    expected = [
        "Queued",
        "Fetching metadata",
        "Downloading",
        "Retuning",
        "Awaiting folder",
        "Saving",
        "Uploading",
        "Done",
        "Failed",
        "Metadata ready",       # added Phase 3 — META-01
        "Failed — download",  # added Phase 4 — D-13
        "Skipped — folder",   # added Phase 5 — D-05
        "Failed — save",      # added Phase 5 — D-10
        "Already uploaded",   # added Phase 6 — D-07
        "Failed — upload",    # added Phase 6 — D-14
    ]
    assert [s.value for s in SongStatus] == expected


# ---------------------------------------------------------------------------
# StatCard widget
# ---------------------------------------------------------------------------


def test_stat_card_initial_count(qapp):
    card = StatCard(label="Valid", color_hex="#1DB954", sublabel="test")
    assert card.count() == 0


def test_stat_card_set_count(qapp):
    card = StatCard(label="Valid", color_hex="#1DB954", sublabel="test")
    card.set_count(7)
    assert card.count() == 7


def test_stat_card_set_count_zero(qapp):
    card = StatCard(label="Valid", color_hex="#1DB954", sublabel="test")
    card.set_count(5)
    card.set_count(0)
    assert card.count() == 0


# ---------------------------------------------------------------------------
# TuneBridgeApp — window-level tests
# ---------------------------------------------------------------------------


def test_app_window_title(window):
    assert window.windowTitle() == "TuneBridge"


def test_app_stylesheet_contains_theme(window):
    assert "#121212" in window.styleSheet()


def test_app_max_workers(window):
    assert TuneBridgeApp._MAX_WORKERS == 6


def test_app_has_table(window):
    assert isinstance(window.table, BatchTable)


def test_app_has_stat_cards(window):
    assert isinstance(window._card_valid, StatCard)
    assert isinstance(window._card_invalid, StatCard)


def test_app_stat_cards_initial_zero(window):
    assert window._card_valid.count() == 0
    assert window._card_invalid.count() == 0


# ---------------------------------------------------------------------------
# BatchTable
# ---------------------------------------------------------------------------


def test_batch_table_add_row_returns_int(window):
    row_id = window.table.add_row(url="https://open.spotify.com/track/x", url_type="Spotify")
    assert isinstance(row_id, int)


def test_batch_table_add_row_increments(window):
    r0 = window.table.add_row(url="https://open.spotify.com/track/a", url_type="Spotify")
    r1 = window.table.add_row(url="https://open.spotify.com/track/b", url_type="Spotify")
    assert r1 == r0 + 1


def test_batch_table_update_row_status(window):
    row_id = window.table.add_row(url="https://open.spotify.com/track/x", url_type="Spotify")
    window.table.update_row_status(row_id, "Done")
    item = window.table._table.item(row_id, 2)
    assert item is not None
    assert item.text() == "Done"


def test_batch_table_update_row_status_does_not_touch_type(window):
    row_id = window.table.add_row(url="https://open.spotify.com/track/x", url_type="Spotify")
    type_text_before = window.table._table.item(row_id, 1).text()
    window.table.update_row_status(row_id, "Done")
    type_text_after = window.table._table.item(row_id, 1).text()
    assert type_text_before == type_text_after == "Spotify"


def test_batch_table_clear_empties_rows(window):
    window.table.add_row(url="https://open.spotify.com/track/x", url_type="Spotify")
    window.table.clear()
    assert window.table._table.rowCount() == 0


def test_batch_table_clear_resets_stat_cards(window):
    window._process_urls("https://www.youtube.com/watch?v=a\nhttps://www.youtube.com/watch?v=b")
    assert window._card_valid.count() > 0
    window.table.clear()
    assert window._card_valid.count() == 0
    assert window._card_invalid.count() == 0


def test_remove_selected_rows_decrements_valid_stat_card(window):
    row_id = window.table.add_row(url="https://open.spotify.com/track/a", url_type="Spotify")
    window._card_valid.set_count(window._card_valid.count() + 1)
    before = window._card_valid.count()
    window.table._table.selectRow(row_id)
    window.table.remove_selected_rows()
    assert window._card_valid.count() == before - 1


def test_remove_selected_rows_decrements_invalid_stat_card(window):
    row_id = window.table.add_row(url="https://www.youtube.com/watch?v=bad", url_type="YouTube")
    window.table.update_row_status(row_id, "Failed — metadata")
    before = window._card_invalid.count()
    window.table._table.selectRow(row_id)
    window.table.remove_selected_rows()
    assert window._card_invalid.count() == before - 1


def test_batch_table_invalid_url_row(window):
    row_id = window.table.add_row(url="https://bad.example.com", url_type="Invalid URL")
    type_item = window.table._table.item(row_id, 1)
    status_item = window.table._table.item(row_id, 2)
    assert type_item.text() == "Invalid URL"
    assert status_item.text() == "Skipped — bad URL"


# ---------------------------------------------------------------------------
# _process_urls — stat card wiring
# ---------------------------------------------------------------------------


def test_process_urls_increments_valid_card(window):
    before = window._card_valid.count()
    window._process_urls(
        "https://www.youtube.com/watch?v=abc\nhttps://www.youtube.com/watch?v=xyz"
    )
    assert window._card_valid.count() == before + 2


def test_process_urls_increments_invalid_card(window):
    before = window._card_invalid.count()
    window._process_urls("https://not-a-valid-url.com/page")
    assert window._card_invalid.count() == before + 1


def test_process_urls_status_bar_valid(window):
    window._process_urls("https://www.youtube.com/watch?v=abc")
    msg = window.statusBar().currentMessage()
    assert "added" in msg


def test_process_urls_status_bar_all_invalid(window):
    window._process_urls("https://random.invalid/link")
    msg = window.statusBar().currentMessage()
    assert "No valid URLs found" in msg


# ---------------------------------------------------------------------------
# _start_demo — worker cap formula
# ---------------------------------------------------------------------------


def test_worker_count_formula():
    cap = TuneBridgeApp._MAX_WORKERS
    assert cap >= 1
    assert min(1, cap) == 1
    assert min(cap, cap) == cap
    assert min(cap + 1, cap) == cap
    assert min(cap + 100, cap) == cap


# ---------------------------------------------------------------------------
# Phase 8 — Cover Art & Album Metadata (ART-01, ART-03, ART-04, ART-05)
# RED-gate: _fetch_cover_bytes / _sniff_mime do not exist yet → ImportError
# ---------------------------------------------------------------------------

_FAKE_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16
_FAKE_PNG  = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def _make_empty_mp3(path: Path) -> None:
    from mutagen.id3 import ID3
    ID3().save(str(path))


def _mock_streaming_get(chunks, ok=True):
    """Build a MagicMock matching `with requests.get(...) as resp:` + iter_content."""
    resp = MagicMock()
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    resp.ok = ok
    resp.iter_content.return_value = list(chunks)
    return resp


def test_write_id3_tags_embeds_apic(tmp_path):
    mp3 = tmp_path / "track.mp3"
    _make_empty_mp3(mp3)
    with patch("tunebridge.requests.get") as mock_get:
        mock_get.return_value = _mock_streaming_get([_FAKE_JPEG])
        _write_id3_tags(mp3, {
            "track_title": "Sample Track",
            "artist": "Sample Artist",
            "album": "Sample Album",
            "cover_url": "https://i.scdn.co/image/x",
        })
    apics = ID3(str(mp3)).getall("APIC")
    assert len(apics) == 1
    assert apics[0].type == 3
    assert apics[0].data[:3] == b"\xff\xd8\xff"


def test_write_id3_tags_preserves_existing_apic(tmp_path):
    mp3 = tmp_path / "track.mp3"
    _make_empty_mp3(mp3)
    t = ID3(str(mp3))
    t.add(APIC(encoding=3, mime="image/png", type=3, desc="", data=_FAKE_PNG))
    t.save(str(mp3))
    with patch("tunebridge.requests.get") as mock_get:
        mock_get.return_value = _mock_streaming_get([_FAKE_JPEG])
        _write_id3_tags(mp3, {
            "track_title": "Sample Track",
            "artist": "Sample Artist",
            "album": "Sample Album",
            "cover_url": "https://i.scdn.co/image/x",
        })
        mock_get.assert_not_called()
    reloaded = ID3(str(mp3)).getall("APIC")
    assert len(reloaded) == 1
    assert reloaded[0].data == _FAKE_PNG


def test_write_id3_tags_no_cover_url_no_apic(tmp_path):
    mp3 = tmp_path / "track.mp3"
    _make_empty_mp3(mp3)
    _write_id3_tags(mp3, {
        "track_title": "Sample Track",
        "artist": "Sample Artist",
        "album": "Sample Album",
    })
    assert ID3(str(mp3)).getall("APIC") == []


def test_write_id3_tags_album_fallback_to_title(tmp_path):
    mp3 = tmp_path / "track.mp3"
    _make_empty_mp3(mp3)
    _write_id3_tags(mp3, {
        "track_title": "Sample Track",
        "artist": "Sample Artist",
        "album": "",
    })
    assert str(ID3(str(mp3))["TALB"].text[0]) == "Sample Track"


def test_write_id3_tags_talb_never_empty(tmp_path):
    mp3 = tmp_path / "track.mp3"
    _make_empty_mp3(mp3)
    _write_id3_tags(mp3, {
        "track_title": "Sample Track",
        "artist": "Sample Artist",
        "album": "Sample Album",
    })
    talb = str(ID3(str(mp3))["TALB"].text[0])
    assert talb == "Sample Album"
    assert talb != ""


def test_write_id3_tags_cover_download_failure_no_raise(tmp_path):
    mp3 = tmp_path / "track.mp3"
    _make_empty_mp3(mp3)
    with patch("tunebridge.requests.get", side_effect=RuntimeError("network down")):
        _write_id3_tags(mp3, {
            "track_title": "Sample Track",
            "artist": "Sample Artist",
            "album": "Sample Album",
            "cover_url": "https://i.scdn.co/image/x",
        })
    tags = ID3(str(mp3))
    assert str(tags["TIT2"].text[0]) == "Sample Track"
    assert tags.getall("APIC") == []


def test_fetch_cover_bytes_uses_timeout():
    with patch("tunebridge.requests.get") as mock_get:
        mock_get.return_value = _mock_streaming_get([_FAKE_JPEG])
        _fetch_cover_bytes("https://i.scdn.co/image/x")
    assert mock_get.call_args.kwargs.get("timeout") == 5
    assert mock_get.call_args.kwargs.get("stream") is True


def test_write_id3_tags_non_200_cover_no_apic(tmp_path):
    mp3 = tmp_path / "track.mp3"
    _make_empty_mp3(mp3)
    with patch("tunebridge.requests.get") as mock_get:
        mock_get.return_value = _mock_streaming_get([_FAKE_JPEG], ok=False)
        _write_id3_tags(mp3, {
            "track_title": "Sample Track",
            "artist": "Sample Artist",
            "album": "Sample Album",
            "cover_url": "https://i.scdn.co/image/x",
        })
    tags = ID3(str(mp3))
    assert tags.getall("APIC") == []
    assert str(tags["TIT2"].text[0]) == "Sample Track"
    assert str(tags["TPE1"].text[0]) == "Sample Artist"
    assert str(tags["TALB"].text[0]) == "Sample Album"
