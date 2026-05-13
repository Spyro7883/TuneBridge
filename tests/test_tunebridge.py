import sys
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QMimeData
from PySide6.QtGui import QColor

from tunebridge import SongStatus, classify_url


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    return app


@pytest.fixture
def window(qapp):
    from tunebridge import TuneBridgeApp
    win = TuneBridgeApp()
    win.table.clear()
    yield win
    win.close()


# ---------------------------------------------------------------------------
# Phase 1 — SongStatus enum (must not change)
# ---------------------------------------------------------------------------

def test_song_status_values():
    assert SongStatus.QUEUED.value == "Queued"
    assert SongStatus.FETCHING.value == "Fetching metadata"
    assert SongStatus.DOWNLOADING.value == "Downloading"
    assert SongStatus.RETUNING.value == "Retuning"
    assert SongStatus.AWAITING.value == "Awaiting folder"
    assert SongStatus.SAVING.value == "Saving"
    assert SongStatus.UPLOADING.value == "Uploading"
    assert SongStatus.DONE.value == "Done"
    assert SongStatus.FAILED.value == "Failed"


def test_add_row_returns_int(window):
    row_id = window.table.add_row(url="https://open.spotify.com/track/abc", url_type="Spotify")
    assert isinstance(row_id, int)


def test_add_row_type_column(window):
    row_id = window.table.add_row(url="https://youtu.be/xyz", url_type="YouTube")
    assert window.table._table.item(row_id, 1).text() == "YouTube"


def test_update_row_status(window):
    row_id = window.table.add_row(url="https://open.spotify.com/track/abc", url_type="Spotify")
    window.table.update_row_status(row_id, "Downloading")
    assert window.table._table.item(row_id, 2).text() == "Downloading"


def test_window_title(window):
    assert window.windowTitle() == "TuneBridge"


def test_dark_background_applied(window):
    assert "#121212" in window.styleSheet()


def test_worker_cap_max_four(window):
    assert window._MAX_WORKERS == 4


def test_clear_empties_table(window):
    window.table.add_row(url="https://youtu.be/abc", url_type="YouTube")
    window.table.clear()
    assert window.table._table.rowCount() == 0


# ---------------------------------------------------------------------------
# Phase 2 — classify_url() unit tests
# ---------------------------------------------------------------------------

def test_classify_url_spotify_track():
    assert classify_url("https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT") == "Spotify"


def test_classify_url_spotify_all_types():
    for path in ["track", "album", "playlist", "artist"]:
        assert classify_url(f"https://open.spotify.com/{path}/abc123") == "Spotify"


def test_classify_url_youtube_watch():
    assert classify_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "YouTube"


def test_classify_url_youtube_short():
    assert classify_url("https://youtu.be/dQw4w9WgXcQ") == "YouTube"


def test_classify_url_youtube_with_list_param():
    assert classify_url("https://youtube.com/watch?v=abc&list=xyz") == "YouTube"


def test_classify_url_invalid_returns_none():
    assert classify_url("https://bad-url.com/whatever") is None
    assert classify_url("not a url") is None
    assert classify_url("") is None


# ---------------------------------------------------------------------------
# Phase 2 — paste → row integration tests
# ---------------------------------------------------------------------------

def test_paste_populates_one_row_per_url(window):
    window.table.clear()
    mime = QMimeData()
    mime.setText(
        "https://open.spotify.com/track/abc\n"
        "https://youtu.be/xyz\n"
        "bad-url"
    )
    window._paste_box.insertFromMimeData(mime)
    assert window.table._table.rowCount() == 3


def test_paste_skips_blank_lines(window):
    window.table.clear()
    mime = QMimeData()
    mime.setText(
        "https://open.spotify.com/track/abc\n"
        "\n"
        "https://youtu.be/xyz\n"
        "\n"
    )
    window._paste_box.insertFromMimeData(mime)
    assert window.table._table.rowCount() == 2


def test_type_badges_after_paste(window):
    window.table.clear()
    mime = QMimeData()
    mime.setText(
        "https://open.spotify.com/track/abc\n"
        "https://youtu.be/xyz"
    )
    window._paste_box.insertFromMimeData(mime)
    assert window.table._table.item(0, 1).text() == "Spotify"
    assert window.table._table.item(1, 1).text() == "YouTube"


def test_invalid_url_shows_error_row(window):
    window.table.clear()
    mime = QMimeData()
    mime.setText("bad-url")
    window._paste_box.insertFromMimeData(mime)
    assert window.table._table.rowCount() == 1
    assert window.table._table.item(0, 1).text() == "Invalid URL"
    assert window.table._table.item(0, 2).text() == "Skipped — bad URL"


def test_invalid_row_does_not_block_valid_rows(window):
    window.table.clear()
    mime = QMimeData()
    mime.setText(
        "https://open.spotify.com/track/abc\n"
        "bad-url\n"
        "https://youtu.be/xyz"
    )
    window._paste_box.insertFromMimeData(mime)
    assert window.table._table.rowCount() == 3
    assert window.table._table.item(0, 2).text() == "Queued"
    assert window.table._table.item(2, 2).text() == "Queued"
    assert window.table._table.item(1, 1).text() == "Invalid URL"
    assert window.table._table.item(1, 2).text() == "Skipped — bad URL"


def test_paste_box_cleared_after_paste(window):
    window.table.clear()
    mime = QMimeData()
    mime.setText("https://open.spotify.com/track/abc")
    window._paste_box.insertFromMimeData(mime)
    assert "open.spotify.com" not in window._paste_box.toPlainText()


def test_status_bar_valid_batch(window):
    window.table.clear()
    mime = QMimeData()
    mime.setText(
        "https://open.spotify.com/track/abc\n"
        "https://youtu.be/xyz"
    )
    window._paste_box.insertFromMimeData(mime)
    assert "2 URL(s) added" in window.statusBar().currentMessage()


def test_status_bar_all_invalid(window):
    window.table.clear()
    mime = QMimeData()
    mime.setText("bad-url-1\nbad-url-2")
    window._paste_box.insertFromMimeData(mime)
    assert "No valid URLs found" in window.statusBar().currentMessage()


def test_type_color_preserved_after_status_update(window):
    window.table.clear()
    row_id = window.table.add_row(
        url="https://open.spotify.com/track/abc",
        url_type="Spotify"
    )
    window.table.update_row_status(row_id, "Downloading")
    type_item = window.table._table.item(row_id, 1)
    assert type_item.foreground().color() == QColor("#1DB954")


# ---------------------------------------------------------------------------
# Phase 2 — StatCard Bento Grid tests
# ---------------------------------------------------------------------------

def test_stat_cards_after_paste(window):
    """Bento Grid cards show correct valid/invalid counts after paste."""
    window.table.clear()
    mime = QMimeData()
    mime.setText(
        "https://open.spotify.com/track/abc\n"
        "https://youtu.be/xyz\n"
        "bad-url"
    )
    window._paste_box.insertFromMimeData(mime)
    assert window._card_valid.count() == 2
    assert window._card_invalid.count() == 1


def test_stat_cards_reset_on_clear(window):
    """Both StatCards show 0 after table.clear()."""
    mime = QMimeData()
    mime.setText("https://open.spotify.com/track/abc")
    window._paste_box.insertFromMimeData(mime)
    window.table.clear()
    assert window._card_valid.count() == 0
    assert window._card_invalid.count() == 0
