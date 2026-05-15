# -*- coding: utf-8 -*-
"""TuneBridge — Phase 2: Input & Detection (PySide6 Liquid Glass)."""
from __future__ import annotations

import logging
import re
import sys
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from enum import Enum

import html as _html
import requests
import yt_dlp

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# ---------------------------------------------------------------------------
# Liquid Glass QSS theme
# ---------------------------------------------------------------------------

TUNEBRIDGE_QSS = """
QMainWindow, QWidget {
    background-color: #121212;
    color: #FFFFFF;
    font-family: "Segoe UI";
    font-size: 10pt;
}
QLabel#title_label {
    color: #1DB954;
    font-size: 18pt;
    font-weight: bold;
    padding: 8px 0px 4px 0px;
}
QTableWidget {
    background-color: rgba(26, 26, 26, 220);
    border: 1px solid rgba(255, 255, 255, 20);
    border-radius: 8px;
    gridline-color: rgba(255, 255, 255, 10);
    outline: none;
}
QTableWidget::item {
    padding: 4px 8px;
    color: #B3B3B3;
    border: none;
}
QTableWidget::item:selected {
    background-color: rgba(29, 185, 84, 51);
}
QHeaderView::section {
    background-color: rgba(26, 26, 26, 200);
    color: #B3B3B3;
    border: none;
    border-bottom: 1px solid rgba(255, 255, 255, 20);
    padding: 6px 8px;
    font-weight: bold;
    font-size: 9pt;
}
QTextEdit {
    background-color: rgba(26, 26, 26, 153);
    border: 1px solid rgba(255, 255, 255, 25);
    border-radius: 6px;
    color: #555555;
    padding: 8px;
    selection-background-color: rgba(29, 185, 84, 76);
}
QStatusBar {
    background-color: #121212;
    color: #B3B3B3;
    font-size: 9pt;
}
QScrollBar:vertical {
    background: #1A1A1A;
    width: 8px;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #555555;
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
"""

# ---------------------------------------------------------------------------
# Domain
# ---------------------------------------------------------------------------


class SongStatus(Enum):
    QUEUED          = "Queued"
    FETCHING        = "Fetching metadata"
    DOWNLOADING     = "Downloading"
    RETUNING        = "Retuning"
    AWAITING        = "Awaiting folder"
    SAVING          = "Saving"
    UPLOADING       = "Uploading"
    DONE            = "Done"
    FAILED          = "Failed"
    METADATA_READY  = "Metadata ready"


# ---------------------------------------------------------------------------
# URL classification
# ---------------------------------------------------------------------------

_LOCALE_PREFIX = r"(?:[a-z]{2}/)?(?:intl-[a-z]+/)?"
_SPOTIFY_RE = re.compile(r"open\.spotify\.com/" + _LOCALE_PREFIX + r"(track|album|playlist|artist)/")
_YOUTUBE_RE = re.compile(r"(youtube\.com/watch\?.*v=|youtu\.be/)")


def classify_url(url: str) -> str | None:
    """Return 'Spotify', 'YouTube', or None."""
    if not url:
        return None
    if _SPOTIFY_RE.search(url):
        return "Spotify"
    if _YOUTUBE_RE.search(url):
        return "YouTube"
    return None


# ---------------------------------------------------------------------------
# Thread-safe dispatcher (replaces Phase 1 queue+after pattern)
# ---------------------------------------------------------------------------


class _Dispatcher(QObject):
    row_status_changed = Signal(int, str)
    metadata_ready     = Signal(int, object)   # (row_id, metadata_dict) — crosses thread boundary

    def __init__(self, table: "BatchTable"):
        super().__init__()
        self.row_status_changed.connect(table.update_row_status)
        self.metadata_ready.connect(table.update_row_metadata)


# ---------------------------------------------------------------------------
# iTunes metadata client (Spotify oEmbed + iTunes Search API — no credentials)
# ---------------------------------------------------------------------------


class ItunesClient:
    """Fetch Spotify track/album metadata via Spotify's public page OG tags.

    No API key or credentials required. og:title gives the track/album name;
    og:description gives "Artist · Album · Type · Year" for tracks.
    """

    _OG_TITLE_RE = re.compile(r'<meta property="og:title" content="([^"]+)"')
    _OG_DESC_RE  = re.compile(r'<meta property="og:description" content="([^"]+)"')
    _HEADERS     = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    def get_metadata(self, spotify_url: str, resource_type: str) -> dict:
        """Return metadata dict for a Spotify URL (track or album)."""
        # Strip locale prefix (e.g. /intl-es/, /en/) — Spotify returns 400 on locale URLs
        m = _SPOTIFY_RESOURCE_RE.search(spotify_url)
        url = (
            f"https://open.spotify.com/{m.group(1)}/{m.group(2)}"
            if m else spotify_url
        )
        resp = requests.get(url, headers=self._HEADERS, timeout=10)
        resp.raise_for_status()
        html = resp.text

        m_title = self._OG_TITLE_RE.search(html)
        m_desc  = self._OG_DESC_RE.search(html)

        title  = _html.unescape(m_title.group(1)) if m_title else ""
        artist = ""
        if m_desc:
            parts  = _html.unescape(m_desc.group(1)).split(" · ")
            artist = parts[0] if parts else ""

        if resource_type == "album":
            return {
                "artist":       artist,
                "track_title":  title,
                "album":        title,
                "release_type": "album",
            }
        return {
            "artist":       artist,
            "track_title":  title,
            "album":        "",
            "release_type": "single",
        }


# ---------------------------------------------------------------------------
# YouTube metadata extractor (yt-dlp info extraction, no download)
# ---------------------------------------------------------------------------


class YoutubeExtractor:
    """Extract video metadata via yt-dlp without downloading.

    Title is parsed for artist/track_title using ' - ' separator (D-08, D-09).
    Parsed fields are labeled '(guessed)' — never presented as confirmed (META-03).
    """

    _YDL_OPTS = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "noplaylist": True,
    }

    def extract_metadata(self, url: str) -> dict:
        with yt_dlp.YoutubeDL(self._YDL_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)
        result = {
            "title":   info.get("title", ""),
            "channel": info.get("channel") or info.get("uploader", ""),
        }
        raw_title = info.get("title", "")
        if " - " in raw_title:
            artist_part, track_part = raw_title.split(" - ", 1)
            result["artist"]      = artist_part
            result["track_title"] = track_part
        else:
            result["track_title"] = raw_title
        return result


# ---------------------------------------------------------------------------
# Metadata routing — Spotify vs YouTube
# ---------------------------------------------------------------------------

# Resource extractor for fetch_metadata_for_row. Handles locale prefixes:
#   /track/{id}, /album/{id}, /en/track/{id}, /intl-ro/track/{id}, etc.
_SPOTIFY_RESOURCE_RE = re.compile(
    r"open\.spotify\.com/" + _LOCALE_PREFIX + r"(track|album)/([A-Za-z0-9]+)"
)


def fetch_metadata_for_row(
    url: str,
    url_type: str,
    itunes_client: "ItunesClient",
    yt_extractor: "YoutubeExtractor",
) -> dict:
    """Route metadata fetch to the correct service based on url_type.

    Returns a dict with a 'source' key added ('Spotify' or 'YouTube').
    """
    if url_type == "Spotify":
        m = _SPOTIFY_RESOURCE_RE.search(url)
        if not m:
            raise ValueError(f"Cannot parse Spotify resource from URL: {url!r}")
        resource_type = m.group(1)
        metadata = itunes_client.get_metadata(url, resource_type)
        metadata["source"] = "Spotify"
        return metadata
    else:  # YouTube
        metadata = yt_extractor.extract_metadata(url)
        metadata["source"] = "YouTube"
        return metadata


# ---------------------------------------------------------------------------
# Bento Grid — stat card
# ---------------------------------------------------------------------------


class StatCard(QWidget):
    def __init__(
        self,
        label: str,
        color_hex: str,
        sublabel: str,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._color = color_hex
        r, g, b = self._hex_to_rgb(color_hex)

        self.setStyleSheet(
            f"StatCard {{"
            f"background-color: rgba({r}, {g}, {b}, 15);"
            f"border: 1px solid rgba({r}, {g}, {b}, 46);"
            f"border-radius: 8px;"
            f"}}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        self._count_label = QLabel("0")
        self._count_label.setStyleSheet(
            f"color: {color_hex}; font-size: 26pt; font-weight: bold;"
            " background: transparent; border: none;"
        )

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        name_lbl = QLabel(label)
        name_lbl.setStyleSheet(
            f"color: {color_hex}; font-size: 11pt; font-weight: 600;"
            " background: transparent; border: none;"
        )
        sub_lbl = QLabel(sublabel)
        sub_lbl.setStyleSheet(
            "color: #555555; font-size: 9pt;"
            " background: transparent; border: none;"
        )
        text_col.addWidget(name_lbl)
        text_col.addWidget(sub_lbl)

        layout.addWidget(self._count_label)
        layout.addLayout(text_col)
        layout.addStretch()

    def count(self) -> int:
        return int(self._count_label.text())

    def set_count(self, n: int) -> None:
        self._count_label.setText(str(n))

    @staticmethod
    def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
        h = hex_color.lstrip("#")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


# ---------------------------------------------------------------------------
# Batch table
# ---------------------------------------------------------------------------


class BatchTable(QWidget):
    COLUMNS = ["Title", "Type", "Status"]

    _STATUS_COLORS: dict[str, QColor] = {
        "Queued":            QColor("#B3B3B3"),
        "Fetching metadata": QColor("#FFFFFF"),
        "Downloading":       QColor("#FFFFFF"),
        "Retuning":          QColor("#FFFFFF"),
        "Awaiting folder":   QColor("#F59E0B"),
        "Saving":            QColor("#FFFFFF"),
        "Uploading":         QColor("#FFFFFF"),
        "Done":              QColor("#1DB954"),
        "Failed":            QColor("#EF4444"),
        "Skipped — bad URL": QColor("#EF4444"),
        "Metadata ready":    QColor("#1DB954"),
        "Failed — metadata": QColor("#EF4444"),
    }

    _TYPE_COLORS: dict[str, QColor] = {
        "Spotify":     QColor("#1DB954"),
        "YouTube":     QColor("#EF4444"),
        "Invalid URL": QColor("#EF4444"),
    }

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(self.COLUMNS)
        self._table.verticalHeader().hide()
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.verticalHeader().setDefaultSectionSize(28)
        self._table.keyPressEvent = self._handle_key
        layout.addWidget(self._table)

        self._rows: dict[int, str] = {}

        # Callbacks set by TuneBridgeApp to sync stat cards
        self._on_clear:        Callable[[], None] | None = None
        self._on_rows_removed: Callable[[int, int], None] | None = None
        self._on_row_failed:   Callable[[], None] | None = None

    def add_row(self, url: str, title: str = "", url_type: str = "") -> int:
        """Add a row and return its int row index."""
        display = title or ((url[:60] + "…") if len(url) > 60 else url)
        row = self._table.rowCount()
        self._table.insertRow(row)

        is_invalid = url_type == "Invalid URL"
        status_text = "Skipped — bad URL" if is_invalid else "Queued"
        status_color = self._STATUS_COLORS.get(status_text, QColor("#B3B3B3"))
        type_color = self._TYPE_COLORS.get(url_type)

        title_item = QTableWidgetItem(display)
        title_item.setForeground(QBrush(status_color))

        type_item = QTableWidgetItem(url_type)
        if type_color:
            type_item.setForeground(QBrush(type_color))

        status_item = QTableWidgetItem(status_text)
        status_item.setForeground(QBrush(status_color))

        self._table.setItem(row, 0, title_item)
        self._table.setItem(row, 1, type_item)
        self._table.setItem(row, 2, status_item)
        self._rows[row] = url
        return row

    def update_row_status(self, row_id: int, status: str) -> None:
        """Update Status column text and color. Does NOT touch Type column."""
        if row_id >= self._table.rowCount():
            return
        color = self._STATUS_COLORS.get(status, QColor("#FFFFFF"))
        # Update title foreground (col 0)
        item0 = self._table.item(row_id, 0)
        if item0:
            item0.setForeground(QBrush(color))
        # Update status text+foreground (col 2)
        item2 = self._table.item(row_id, 2)
        if item2:
            item2.setText(status)
            item2.setForeground(QBrush(color))
        if status == "Failed — metadata" and self._on_row_failed:
            self._on_row_failed()

    def update_row_metadata(self, row_id: int, metadata: dict) -> None:
        """Write human-readable display label to col 0, update status to 'Metadata ready'.

        Called on main thread via queued Signal connection (Pattern 5).
        """
        if row_id >= self._table.rowCount():
            return
        source = metadata.get("source", "")
        if source == "Spotify":
            artist = metadata.get("artist", "")
            if metadata.get("release_type") == "album":
                label = f"{artist} — {metadata.get('album', '')} [album]"
            else:
                label = f"{artist} — {metadata.get('track_title', '')}"
        else:  # YouTube
            artist = metadata.get("artist", "")
            track  = metadata.get("track_title", metadata.get("title", ""))
            if artist:
                label = f"{artist} — {track}"
            else:
                label = track

        color = self._STATUS_COLORS.get("Metadata ready", QColor("#1DB954"))
        item0 = self._table.item(row_id, 0)
        if item0:
            item0.setText(label)
            item0.setForeground(QBrush(color))

        self.update_row_status(row_id, SongStatus.METADATA_READY.value)

    def remove_selected_rows(self) -> int:
        """Delete selected rows. Returns count removed."""
        rows = sorted(
            {idx.row() for idx in self._table.selectedIndexes()},
            reverse=True,
        )
        _INVALID_STATUSES = {"Skipped — bad URL", "Failed — metadata"}
        invalid_removed = sum(
            1 for r in rows
            if (item := self._table.item(r, 2)) and item.text() in _INVALID_STATUSES
        )
        valid_removed = len(rows) - invalid_removed
        for row in rows:
            self._table.removeRow(row)
        self._rows = {
            i: url
            for i, url in enumerate(
                self._rows[r] for r in sorted(self._rows) if r not in rows
            )
        }
        if self._on_rows_removed:
            self._on_rows_removed(valid_removed, invalid_removed)
        return len(rows)

    def _handle_key(self, event) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QTableWidget
        if event.key() == Qt.Key.Key_Delete:
            self.remove_selected_rows()
        else:
            QTableWidget.keyPressEvent(self._table, event)

    def clear(self) -> None:
        self._table.setRowCount(0)
        self._rows.clear()
        if self._on_clear:
            self._on_clear()


# ---------------------------------------------------------------------------
# Paste input widget
# ---------------------------------------------------------------------------


class PasteTextEdit(QTextEdit):
    PLACEHOLDER = "Paste Spotify or YouTube URLs here (one per line)"
    urls_pasted = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setPlaceholderText(self.PLACEHOLDER)
        self.setFixedHeight(88)
        self.setAcceptRichText(False)

    def insertFromMimeData(self, source) -> None:
        raw = source.text() if source.hasText() else ""
        if raw.strip():
            self.urls_pasted.emit(raw)
        # No super() call — widget stays empty, placeholder remains visible


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------


class TuneBridgeApp(QMainWindow):
    _MAX_WORKERS = 4

    def __init__(self):
        super().__init__()
        self.setWindowTitle("TuneBridge")
        self.setMinimumSize(800, 520)
        self.setStyleSheet(TUNEBRIDGE_QSS)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 16, 20, 8)
        layout.setSpacing(8)

        # Title
        title = QLabel("TuneBridge")
        title.setObjectName("title_label")
        layout.addWidget(title)

        # Paste area
        self._paste_box = PasteTextEdit(self)
        self._paste_box.urls_pasted.connect(self._process_urls)
        layout.addWidget(self._paste_box)

        # Bento Grid stat cards
        cards_row = QHBoxLayout()
        cards_row.setSpacing(8)
        self._card_valid = StatCard(
            label="Valide",
            color_hex="#1DB954",
            sublabel="Spotify + YouTube",
        )
        self._card_invalid = StatCard(
            label="Invalide",
            color_hex="#EF4444",
            sublabel="URL-uri eronate",
        )
        cards_row.addWidget(self._card_valid)
        cards_row.addWidget(self._card_invalid)
        layout.addLayout(cards_row)

        # Batch table
        self.table = BatchTable(self)
        # Wire clear() to reset both stat cards
        self.table._on_clear = lambda: (
            self._card_valid.set_count(0),
            self._card_invalid.set_count(0),
        )
        # Wire row deletion to decrement stat cards
        self.table._on_rows_removed = lambda v, i: (
            self._card_valid.set_count(max(0, self._card_valid.count() - v)),
            self._card_invalid.set_count(max(0, self._card_invalid.count() - i)),
        )
        # Wire metadata failure to move row from valid → invalid
        self.table._on_row_failed = lambda: (
            self._card_valid.set_count(max(0, self._card_valid.count() - 1)),
            self._card_invalid.set_count(self._card_invalid.count() + 1),
        )
        layout.addWidget(self.table)

        # Thread dispatcher
        self._dispatcher = _Dispatcher(self.table)

        # Persistent thread pool — submissions from _process_urls (D-03 auto-fetch)
        self._executor = ThreadPoolExecutor(max_workers=self._MAX_WORKERS)
        self._closing  = threading.Event()

        # Metadata clients — no credentials required
        self._itunes_client = ItunesClient()
        self._yt_extractor  = YoutubeExtractor()

        self.statusBar().showMessage("Ready — add songs to begin")

    def _process_urls(self, raw: str) -> None:
        lines = [line.strip() for line in raw.splitlines()]
        candidates = [line for line in lines if line]
        if not candidates:
            return

        valid_count = 0
        invalid_count = 0
        for url in candidates:
            url_type = classify_url(url)
            if url_type is not None:
                row_id = self.table.add_row(url=url, url_type=url_type)
                valid_count += 1
                self._dispatcher.row_status_changed.emit(
                    row_id, SongStatus.FETCHING.value
                )
                self._executor.submit(
                    self._metadata_worker, row_id, url, url_type
                )
            else:
                self.table.add_row(url=url, url_type="Invalid URL")
                invalid_count += 1

        self._card_valid.set_count(self._card_valid.count() + valid_count)
        self._card_invalid.set_count(self._card_invalid.count() + invalid_count)

        if valid_count > 0:
            self.statusBar().showMessage(
                f"{valid_count} added — paste more or start processing"
            )
        else:
            self.statusBar().showMessage(
                "No valid URLs found — check your links"
            )

        self._paste_box.setFocus()

    def _clear_all(self) -> None:
        """Explicit clear — also triggered via table._on_clear."""
        self.table.clear()

    def _metadata_worker(self, row_id: int, url: str, url_type: str) -> None:
        """Worker thread: fetch metadata for a row, emit result or failure (D-07).

        Catches ALL exceptions — per-row error isolation. Other rows in the
        batch are unaffected.
        """
        if self._closing.is_set():
            return
        try:
            metadata = fetch_metadata_for_row(
                url            = url,
                url_type       = url_type,
                itunes_client  = self._itunes_client,
                yt_extractor   = self._yt_extractor,
            )
            if not self._closing.is_set():
                self._dispatcher.metadata_ready.emit(row_id, metadata)
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Metadata fetch failed for row %d (%s): %s", row_id, url, exc
            )
            if not self._closing.is_set():
                self._dispatcher.row_status_changed.emit(row_id, "Failed — metadata")

    def closeEvent(self, event) -> None:
        """Shutdown the persistent thread pool on window close."""
        self._closing.set()
        self._executor.shutdown(wait=False)
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TuneBridgeApp()
    window.show()
    sys.exit(app.exec())
