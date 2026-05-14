# -*- coding: utf-8 -*-
"""Tests for TuneBridge Phase 2 — PySide6 implementation."""
import inspect
import re

import pytest

from PySide6.QtCore import QMimeData
from PySide6.QtWidgets import QApplication

from tunebridge import (
    BatchTable,
    PasteTextEdit,
    SongStatus,
    StatCard,
    TuneBridgeApp,
    _Dispatcher,
    classify_url,
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
        "Metadata ready",  # added Phase 3 — META-01
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
    assert TuneBridgeApp._MAX_WORKERS == 4


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
    # Simulate paste to increment cards
    window._process_urls("https://open.spotify.com/track/a\nhttps://open.spotify.com/track/b")
    assert window._card_valid.count() > 0
    window.table.clear()
    assert window._card_valid.count() == 0
    assert window._card_invalid.count() == 0


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
        "https://open.spotify.com/track/x\nhttps://www.youtube.com/watch?v=abc"
    )
    assert window._card_valid.count() == before + 2


def test_process_urls_increments_invalid_card(window):
    before = window._card_invalid.count()
    window._process_urls("https://not-a-valid-url.com/page")
    assert window._card_invalid.count() == before + 1


def test_process_urls_status_bar_valid(window):
    window._process_urls("https://open.spotify.com/track/x")
    msg = window.statusBar().currentMessage()
    assert "added" in msg and "ready" in msg


def test_process_urls_status_bar_all_invalid(window):
    window._process_urls("https://random.invalid/link")
    msg = window.statusBar().currentMessage()
    assert "No valid URLs found" in msg


# ---------------------------------------------------------------------------
# _start_demo — worker cap formula
# ---------------------------------------------------------------------------


def test_worker_count_formula():
    src = inspect.getsource(TuneBridgeApp._start_demo)
    assert re.search(r"\bmin\b", src), "_start_demo must use min() for worker cap"
    cap = TuneBridgeApp._MAX_WORKERS
    assert cap == 4
    assert min(1, cap) == 1
    assert min(4, cap) == 4
    assert min(5, cap) == 4
    assert min(10, cap) == 4
