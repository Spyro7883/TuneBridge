# -*- coding: utf-8 -*-
"""TuneBridge — Phase 2: Input & Detection (PySide6 Liquid Glass)."""
from __future__ import annotations

import atexit
import json
import logging
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unicodedata
import urllib.parse
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from enum import Enum
from pathlib import Path

import html as _html
import librosa
import numpy as np
import requests
import soundfile as sf
import yt_dlp

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
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
QPushButton[hz_btn="true"] {
    background-color: rgba(255,255,255,10);
    border: 1px solid rgba(255,255,255,20);
    border-radius: 6px;
    color: #B3B3B3;
    padding: 4px 16px;
    font-size: 10pt;
}
QPushButton[hz_btn="true"]:checked {
    background-color: rgba(29, 185, 84, 40);
    border: 1px solid #1DB954;
    color: #1DB954;
    font-weight: bold;
}
QPushButton[hz_btn="true"]:disabled {
    color: #444444;
    border-color: rgba(255,255,255,10);
}
QPushButton#start_btn {
    background-color: rgba(29, 185, 84, 51);
    border: 1px solid #1DB954;
    border-radius: 6px;
    color: #1DB954;
    padding: 6px 20px;
    font-size: 10pt;
    font-weight: bold;
}
QPushButton#start_btn:disabled {
    background-color: rgba(255,255,255,10);
    border: 1px solid rgba(255,255,255,20);
    color: #444444;
}
"""

# ---------------------------------------------------------------------------
# Download infrastructure (Phase 4)
# ---------------------------------------------------------------------------

_download_lock = threading.Lock()   # Serializes yt-dlp subprocess — browser cookie safety (D-07)
_dialog_lock   = threading.Lock()   # Serializes folder dialogs — one at a time (D-01)
_BROWSER_FALLBACKS: tuple[str, ...] = ("firefox", "chrome", "edge", "brave", "chromium", "opera")

# WR-04: Both terminal-failure statuses that must trigger _on_row_failed callback
FAILURE_STATUSES: frozenset[str] = frozenset({
    "Failed — metadata",
    "Failed — download",
    "Failed — save",
})


def _sanitise_search_term(s: str) -> str:
    """Strip control chars and leading dashes from scraped metadata before ytsearch: query."""
    s = re.sub(r"[\x00-\x1f\x7f]", " ", s)
    return s.strip().lstrip("-")[:100]


def _norm_str(s: str) -> str:
    """Lowercase + strip diacritics + collapse whitespace for fuzzy match (C-01)."""
    return re.sub(
        r"\s+",
        " ",
        unicodedata.normalize("NFKD", s or "")
        .encode("ascii", "ignore")
        .decode()
        .lower(),
    ).strip()


SRC_A4 = 440.0
DST_A4 = 432.0
RATIO   = DST_A4 / SRC_A4


def semitones_for_ratio(ratio: float) -> float:
    return 12.0 * math.log(ratio, 2)


def retune_file(in_path: Path, out_path: Path) -> None:
    """Pitch-shift in_path from 440Hz to 432Hz, write MP3 to out_path.

    Copied verbatim from retune_app.py. Handles mono/stereo via channel loop.
    Preserves original ID3 tags via mutagen.
    """
    try:
        from mutagen.mp3 import MP3
        from mutagen.id3 import ID3
    except ImportError:
        MP3 = ID3 = None  # type: ignore[assignment,misc]

    y, sr = librosa.load(str(in_path), sr=None, mono=False)
    if y.ndim == 1:
        y = y[np.newaxis, :]

    n_steps = semitones_for_ratio(RATIO)
    channels = []
    for ch in y:
        channels.append(librosa.effects.pitch_shift(ch, sr=sr, n_steps=n_steps))

    y_out = np.clip(np.stack(channels, axis=0), -1.0, 1.0).T
    out_path.parent.mkdir(parents=True, exist_ok=True)

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found in PATH.")

    original_tags = {}
    try:
        orig_id3 = ID3(str(in_path))
        for key in orig_id3:
            original_tags[key] = orig_id3[key]
    except Exception:
        pass

    with tempfile.TemporaryDirectory() as td:
        tmp_wav = Path(td) / (out_path.stem + ".wav")
        sf.write(str(tmp_wav), y_out, sr)
        cmd = [
            ffmpeg, "-y", "-i", str(tmp_wav),
            "-vn", "-codec:a", "libmp3lame", "-b:a", "192k",
            str(out_path),
        ]
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if p.returncode != 0:
            raise RuntimeError(f"ffmpeg error: {p.stderr[:300]}")

    if original_tags:
        try:
            audio = MP3(str(out_path))
            if audio.tags is None:
                audio.add_tags()
            for key, value in original_tags.items():
                if hasattr(value, 'encoding'):
                    value.encoding = 3  # UTF-8
                audio.tags.add(value)
            audio.save(v2_version=3)
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "ID3 tag restoration failed for %s: %s", out_path, exc
            )


def download_track_for_row(search_url: str, out_dir: Path) -> Path | None:
    """Download audio via yt-dlp to out_dir. Serialized via _download_lock (D-07).

    search_url is either a ytsearch: string (Spotify rows) or a direct YouTube URL.
    Tries player_client=ios first (no cookies, bypasses n-challenge), then falls back
    through _BROWSER_FALLBACKS. CRITICAL: _download_lock wraps entire cycle — do NOT narrow.
    """
    ytdlp = shutil.which("yt-dlp")
    if not ytdlp:
        raise RuntimeError("yt-dlp not found. Install: pip install yt-dlp")

    out_dir.mkdir(parents=True, exist_ok=True)

    base_cmd = [
        ytdlp, "--no-playlist",
        "--no-check-certificate",
        "--js-runtimes", "node",               # Node.js required for YouTube n-challenge (EJS)
        "-x", "--audio-format", "mp3", "--audio-quality", "192K",
        "-o", str(out_dir / "%(title)s.%(ext)s"),
        search_url,
    ]

    # Try each browser in order; fall back to no-cookies last
    cookie_variants: list[list[str]] = [
        ["--cookies-from-browser", b] for b in _BROWSER_FALLBACKS
    ] + [[]]

    def _run_attempt(cmd: list[str]) -> tuple[bool, int]:
        timed_out = False
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        def _kill() -> None:
            nonlocal timed_out
            try:
                if proc.poll() is None:
                    timed_out = True
                    proc.kill()
            except Exception:
                pass

        timer = threading.Timer(600, _kill)
        timer.start()
        try:
            proc.stdout.read()
            proc.wait()
        finally:
            timer.cancel()
        return timed_out, proc.returncode

    with _download_lock:
        for cookie_args in cookie_variants:
            cmd = [base_cmd[0]] + cookie_args + base_cmd[1:]
            timed_out, rc = _run_attempt(cmd)
            if timed_out:
                raise RuntimeError("yt-dlp download timed out.")
            if rc == 0:
                break
        else:
            raise RuntimeError("yt-dlp download failed on all browser configurations.")

    mp3s = sorted(out_dir.glob("*.mp3"), key=lambda p: p.stat().st_mtime, reverse=True)
    return mp3s[0] if mp3s else None


def _search_yt_candidates(query: str, count: int = 5) -> list[dict]:
    """Return top N YouTube Music results as {id, title, channel, duration} dicts."""
    ytdlp = shutil.which("yt-dlp")
    if not ytdlp:
        return []
    try:
        encoded = urllib.parse.quote_plus(query)
        search_url = f"https://music.youtube.com/search?q={encoded}"
        import os as _os
        result = subprocess.run(
            [ytdlp, "--playlist-end", str(count), "--no-check-certificate", "--no-warnings",
             "--print", "%(id)s|||%(title)s|||%(duration)s|||%(channel)s|||%(view_count)s",
             search_url],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace",
            env={**_os.environ, "PYTHONUTF8": "1"},
        )
        candidates = []
        for line in result.stdout.strip().splitlines():
            parts = line.split("|||")
            if len(parts) < 3:
                continue
            vid_id = parts[0].strip()
            if not vid_id:
                continue
            try:
                duration = float(parts[2].strip())
            except ValueError:
                duration = 0.0
            try:
                views = int(parts[4].strip()) if len(parts) > 4 else 0
            except ValueError:
                views = 0
            candidates.append({
                "id":        vid_id,
                "title":     parts[1].strip(),
                "channel":   parts[3].strip() if len(parts) > 3 else "",
                "duration":  duration,
                "view_count": views,
            })
        return candidates
    except Exception:
        return []


def _find_best_yt_match(title: str, artist: str, duration_ms: int = 0) -> str | None:
    """Find best YouTube Music URL for a Spotify track.

    Scores candidates: duration proximity ±2s (up to 10pts), title match (5pts),
    artist match (3pts). Returns a YouTube Music URL, or None if nothing matched.
    """
    query = f"{artist} {title}" if artist else title
    candidates = _search_yt_candidates(query, count=5)
    if not candidates:
        return None

    target_s   = duration_ms / 1000.0 if duration_ms else None
    title_l    = title.lower()
    artist_key = artist.split(",")[0].strip().lower()

    scored = []
    for c in candidates:
        score  = 0.0
        vid_l  = c.get("title", "").lower()

        if target_s is not None:
            diff = abs((c.get("duration") or 0) - target_s)
            if diff <= 2:
                score += 10.0 - diff * 2
            elif diff <= 5:
                score += 2.0

        if title_l in vid_l:
            score += 5.0
        # Weak signal: official YT Music songs often have simple titles without artist prefix
        if artist_key and artist_key in vid_l:
            score += 1.0
        if artist_key and artist_key in c.get("channel", "").lower():
            score += 3.0
        # View count: strong signal for official releases vs fan uploads (log scale, cap 9)
        views = c.get("view_count", 0) or 0
        if views > 0:
            score += min(math.log10(views) * 1.5, 9.0)
        # Penalise non-original versions
        if any(kw in vid_l for kw in (
            "letra", "lyrics", "lyric video", "karaoke",
            "bass boosted", "sped up", "slowed", "nightcore",
            "8d audio", "reverb", "pitched",
        )):
            score -= 3.0

        scored.append((score, c))

    scored.sort(key=lambda x: -x[0])
    best_score, best = scored[0]

    if best_score <= 0:
        return None

    return f"https://music.youtube.com/watch?v={best['id']}"


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
    FAILED_DOWNLOAD = "Failed — download"   # D-13: per-row download failure status
    SKIPPED         = "Skipped — folder"    # D-05: user chose skip in FolderConfirmDialog
    FAILED_SAVE     = "Failed — save"       # D-10: OSError during shutil.move


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
    folder_requested   = Signal(int)           # D-02: worker emits row_id; main thread shows dialog
    folder_batch_done  = Signal()              # D-11: emitted when all folder dialogs resolve

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

    def search_duration_ms(self, artist: str, title: str) -> int | None:
        """Query iTunes Search API for track duration in milliseconds.

        Free, no auth required. Used for YouTube duration-matching to pick the
        correct video when ytsearch returns multiple candidates.
        Returns None on any failure — callers fall back to ytsearch1:.
        """
        try:
            term = urllib.parse.quote(f"{artist} {title}")
            # ES/MX stores first for broader international coverage, then US
            for store in ("&country=ES", "&country=MX", ""):
                resp = requests.get(
                    f"https://itunes.apple.com/search?term={term}&entity=song&limit=5{store}",
                    timeout=8,
                )
                resp.raise_for_status()
                results = resp.json().get("results", [])
                if results:
                    break
            if not results:
                return None

            title_n = _norm_str(title)
            # For collaboration credits like "Artist A, Artist B", also try first artist only
            artist_variants = [_norm_str(artist)]
            if "," in artist:
                artist_variants.append(_norm_str(artist.split(",")[0].strip()))

            for r in results:
                r_artist = _norm_str(r.get("artistName", ""))
                r_title  = _norm_str(r.get("trackName", ""))
                artist_match = any(
                    v in r_artist or r_artist in v for v in artist_variants
                )
                if artist_match and title_n in r_title:
                    return r.get("trackTimeMillis")
            return None
        except Exception:
            return None

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
        # C-02: enrich track metadata with iTunes duration for YT candidate scoring.
        # Failure returns None — _find_best_yt_match handles None gracefully.
        duration_ms = self.search_duration_ms(artist, title) if (artist and title) else None
        return {
            "artist":       artist,
            "track_title":  title,
            "album":        "",
            "release_type": "single",
            "duration_ms":  duration_ms,
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
        "nocheckcertificate": True,
        "js_runtimes": {"node": {}},
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
        "Failed — download": QColor("#EF4444"),   # D-13
        "Skipped — folder":  QColor("#B3B3B3"),   # D-05: gray, distinct from failure red
        "Failed — save":     QColor("#EF4444"),   # D-10: matches other failure states
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
        if status in FAILURE_STATUSES and self._on_row_failed:
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

    def get_row_title(self, row_id: int) -> str:
        """Return display title for row_id, or a fallback string if the cell is missing."""
        item = self._table.item(row_id, 0)
        return item.text() if item else f"Row {row_id}"

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

    def remove_completed_rows(self) -> tuple[int, int]:
        """Remove rows that are in a terminal completed state (processed batch).

        Returns (valid_removed, invalid_removed) for stat card sync.
        Called automatically when new URLs are pasted after a finished batch.
        """
        _COMPLETED = {
            SongStatus.UPLOADING.value,
            SongStatus.SKIPPED.value,
            SongStatus.FAILED_SAVE.value,
            SongStatus.FAILED_DOWNLOAD.value,
        }
        _INVALID_COMPLETED = {SongStatus.FAILED_METADATA.value} if hasattr(SongStatus, "FAILED_METADATA") else set()
        rows_to_remove = sorted(
            [
                r for r in range(self._table.rowCount())
                if (item := self._table.item(r, 2))
                and item.text() in _COMPLETED | _INVALID_COMPLETED
            ],
            reverse=True,
        )
        if not rows_to_remove:
            return 0, 0
        invalid_removed = sum(
            1 for r in rows_to_remove
            if (item := self._table.item(r, 2)) and item.text() in _INVALID_COMPLETED
        )
        valid_removed = len(rows_to_remove) - invalid_removed
        for row in rows_to_remove:
            self._table.removeRow(row)
        self._rows = {
            i: url
            for i, url in enumerate(
                self._rows[r] for r in sorted(self._rows) if r not in rows_to_remove
            )
        }
        if self._on_rows_removed:
            self._on_rows_removed(valid_removed, invalid_removed)
        return valid_removed, invalid_removed

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
# Folder confirmation dialog (Phase 5, Wave 1)
# ---------------------------------------------------------------------------


class FolderConfirmDialog(QDialog):
    """Modal dialog: user confirms or skips destination folder for one song. (D-15/D-16/D-17)

    Call exec() on the main thread ONLY. Never instantiate from a worker thread.
    Result via result_path() — returns confirmed Path or None (skip sentinel).
    """

    def __init__(self, song_title: str, proposed: Path | None, parent=None):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowTitle("Confirm Save Folder")
        self._result_path: Path | None = None

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(f"Save folder for: {song_title}"))

        self._path_edit = QLineEdit(str(proposed) if proposed else "")
        layout.addWidget(self._path_edit)

        self._error_label = QLabel("")
        self._error_label.setStyleSheet("color: #EF4444; font-size: 9pt;")
        layout.addWidget(self._error_label)

        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse)
        layout.addWidget(browse_btn)

        btn_row = QHBoxLayout()
        self._confirm_btn = QPushButton("Confirm")
        self._confirm_btn.setEnabled(False)   # disabled until valid dir entered (D-16)
        self._confirm_btn.clicked.connect(self._on_confirm)
        skip_btn = QPushButton("Skip")
        skip_btn.clicked.connect(self.reject)   # reject() → _result_path stays None (D-05)
        btn_row.addWidget(self._confirm_btn)
        btn_row.addWidget(skip_btn)
        layout.addLayout(btn_row)

        self._path_edit.textChanged.connect(self._validate)
        self._validate(self._path_edit.text())   # set initial button state

    def _validate(self, text: str) -> None:
        # CRITICAL: check strip() != '' BEFORE is_dir() — Path('').is_dir() is True on Windows (Pitfall 1)
        valid = bool(text.strip()) and Path(text.strip()).is_dir()
        self._confirm_btn.setEnabled(valid)
        if text.strip() and not valid:
            self._error_label.setText("Folder not found — select an existing folder.")
        else:
            self._error_label.setText("")

    def _browse(self) -> None:
        """Open directory picker starting at current text or home. (D-17)"""
        current = self._path_edit.text().strip()
        start = current if (current and Path(current).is_dir()) else str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, "Select folder", start)
        if chosen:
            self._path_edit.setText(chosen)

    def _on_confirm(self) -> None:
        self._result_path = Path(self._path_edit.text().strip())
        self.accept()

    def result_path(self) -> Path | None:
        return self._result_path


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
            label="Valid",
            color_hex="#1DB954",
            sublabel="Spotify + YouTube",
        )
        self._card_invalid = StatCard(
            label="Invalid",
            color_hex="#EF4444",
            sublabel="Invalid URLs",
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

        # Toolbar row: Hz segmented control + Start button (D-04, D-05, D-06)
        toolbar_row = QHBoxLayout()
        toolbar_row.setSpacing(8)

        self._hz_group = QButtonGroup(self)
        self._hz_group.setExclusive(True)

        self._btn_440 = QPushButton("440 Hz")
        self._btn_432 = QPushButton("432 Hz")
        for btn in (self._btn_440, self._btn_432):
            btn.setCheckable(True)
            btn.setProperty("hz_btn", True)
        self._btn_440.setChecked(True)       # D-05: default 440Hz
        self._hz_group.addButton(self._btn_440, 440)
        self._hz_group.addButton(self._btn_432, 432)

        toolbar_row.addWidget(self._btn_440)
        toolbar_row.addWidget(self._btn_432)
        toolbar_row.addStretch()

        self._btn_start = QPushButton("Start Processing")
        self._btn_start.setObjectName("start_btn")
        self._btn_start.setEnabled(False)   # D-02: disabled until all rows METADATA_READY
        self._btn_start.clicked.connect(self._start_processing)
        toolbar_row.addWidget(self._btn_start)

        layout.addLayout(toolbar_row)
        layout.addWidget(self.table)

        # Thread dispatcher
        self._dispatcher = _Dispatcher(self.table)

        # Persistent thread pool — submissions from _process_urls (D-03 auto-fetch)
        self._executor = ThreadPoolExecutor(max_workers=self._MAX_WORKERS)
        self._closing  = threading.Event()

        # Phase 4: temp file lifecycle (D-10, D-11, D-12)
        self._session_tmp            = Path(tempfile.mkdtemp(prefix="tunebridge_"))
        atexit.register(shutil.rmtree, self._session_tmp, True)   # CR-03: guarantee cleanup on Windows
        self._temp_paths: dict[int, Path] = {}      # row_id → temp MP3 for Phase 5 handoff
        self._row_metadata: dict[int, dict] = {}    # row_id → Phase 3 metadata dict (_row_metadata gap fix)
        # Phase 4: batch completion tracking (D-16)
        self._download_total         = 0
        self._download_done          = 0
        self._download_failed        = 0
        self._temp_paths_lock        = threading.Lock()   # guards _temp_paths cross-thread writes

        # Phase 5: folder dialog serialization (D-01 through D-04)
        self._last_folder:    Path | None                    = None
        self._folder_events:  dict[int, threading.Event]     = {}
        self._folder_results: dict[int, Path | None]         = {}
        self._saved_paths:    dict[int, Path]                = {}
        self._folder_total   = 0
        self._folder_done    = 0
        self._folder_skipped = 0
        self._folder_failed  = 0

        # Store Phase 3 metadata for Phase 4 download worker (_row_metadata gap fix)
        self._dispatcher.metadata_ready.connect(
            lambda row_id, meta: self._row_metadata.__setitem__(row_id, meta)
        )
        # Re-evaluate Start button on every row status change (D-02)
        self._dispatcher.row_status_changed.connect(self._refresh_start_button)
        self._dispatcher.folder_requested.connect(
            self._show_folder_dialog,
            Qt.ConnectionType.QueuedConnection,
        )
        self._dispatcher.folder_batch_done.connect(self._unlock_ui)

        # Metadata clients — no credentials required
        self._itunes_client = ItunesClient()
        self._yt_extractor  = YoutubeExtractor()

        self.statusBar().showMessage("Ready — add songs to begin")

    def _process_urls(self, raw: str) -> None:
        lines = [line.strip() for line in raw.splitlines()]
        candidates = [line for line in lines if line]
        if not candidates:
            return

        # Clear finished rows from previous batch before adding new ones
        self.table.remove_completed_rows()

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
        self._refresh_start_button()   # re-evaluate after new rows added

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
                # Emit row_status_changed so _refresh_start_button sees METADATA_READY
                # (update_row_metadata sets cell directly; the signal never fires otherwise)
                self._dispatcher.row_status_changed.emit(
                    row_id, SongStatus.METADATA_READY.value
                )
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Metadata fetch failed for row %d (%s): %s", row_id, url, exc
            )
            if not self._closing.is_set():
                self._dispatcher.row_status_changed.emit(row_id, "Failed — metadata")

    def _download_worker(
        self,
        row_id: int,
        url: str,
        url_type: str,
        metadata: dict,
        hz_mode: int,
    ) -> None:
        """Worker thread: download + optional retune. Per-row error isolation.

        Mirrors _metadata_worker exactly: closing guard → try/except → emit signal.
        Routing: Spotify → quoted-title YT search + title match, ytsearch fallback;
                 YouTube → direct URL (D-01, D-02).
        """
        if self._closing.is_set():
            return
        try:
            self._dispatcher.row_status_changed.emit(row_id, SongStatus.DOWNLOADING.value)

            # Per-row isolated temp subdir (D-10) — uuid prefix prevents glob collision
            row_tmp = self._session_tmp / uuid.uuid4().hex[:8]
            row_tmp.mkdir(parents=True, exist_ok=True)

            _log = logging.getLogger(__name__)
            if url_type == "Spotify":
                artist      = _sanitise_search_term(metadata.get("artist", ""))
                title       = _sanitise_search_term(metadata.get("track_title", ""))
                duration_ms = metadata.get("duration_ms") or 0
                yt_url = _find_best_yt_match(title, artist, duration_ms=duration_ms)
                if yt_url is None:
                    raise RuntimeError(
                        "Not found on YouTube Music — paste a direct YouTube URL instead."
                    )
                downloaded = download_track_for_row(yt_url, row_tmp)
            else:
                downloaded = download_track_for_row(url, row_tmp)
            if not downloaded:
                raise RuntimeError("No audio file found after yt-dlp download.")

            if hz_mode == 432:
                # Retune runs in parallel — no cookie conflict risk (D-08)
                self._dispatcher.row_status_changed.emit(row_id, SongStatus.RETUNING.value)
                out_path = row_tmp / (downloaded.stem + "_432hz.mp3")
                retune_file(downloaded, out_path)
                try:
                    downloaded.unlink(missing_ok=True)
                except Exception:
                    pass
                downloaded = out_path

            if not self._closing.is_set():
                self._dispatcher.row_status_changed.emit(row_id, SongStatus.AWAITING.value)
                with self._temp_paths_lock:
                    self._temp_paths[row_id] = downloaded   # Phase 5 handoff (D-11)

        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Download failed for row %d (%s): %s", row_id, url, exc
            )
            if not self._closing.is_set():
                self._dispatcher.row_status_changed.emit(
                    row_id, SongStatus.FAILED_DOWNLOAD.value
                )

    def _folder_worker(self, row_id: int) -> None:
        """Worker thread: acquire dialog lock, block on threading.Event. (D-02/D-03)

        I/O, status emit, and _on_folder_row_finished are handled by _show_folder_dialog
        on the main thread after ev.set(). This worker's job ends when the lock is released.
        CRITICAL: _dialog_lock scope includes event registration AND event.wait() (Pitfall 3).
        """
        if self._closing.is_set():
            return

        with _dialog_lock:                                         # D-01: one dialog at a time
            ev = threading.Event()
            self._folder_events[row_id] = ev
            self._folder_results[row_id] = None                   # default sentinel = skip (D-03)

            if not self._closing.is_set():
                self._dispatcher.folder_requested.emit(row_id)    # main thread shows dialog
                # C-03: bounded wait — if _show_folder_dialog raises before
                # ev.set(), the worker would deadlock indefinitely under the
                # dialog lock, blocking all queued folder workers.
                if not ev.wait(timeout=300) and not self._closing.is_set():
                    logging.getLogger(__name__).warning(
                        "Folder dialog timed out for row %d — treating as skip", row_id
                    )
        # Lock released — I/O and status updates handled by _show_folder_dialog on main thread.

    def _show_folder_dialog(self, row_id: int) -> None:
        """Main thread ONLY — connected to folder_requested via Qt queued connection. (D-03)

        Shows FolderConfirmDialog, updates _last_folder session state, stores confirmed Path
        or None sentinel in _folder_results, sets threading.Event to unblock _folder_worker,
        then performs the file I/O (move or skip) on the main thread.
        NEVER call this from a worker thread — dlg.exec() requires the main thread event loop (Pitfall 2).
        """
        # C-03: guarantee the worker is unblocked even if dialog construction
        # or exec raises. Outer try/finally ensures ev.set() always runs.
        result: Path | None = None
        try:
            title = self.table.get_row_title(row_id)
            dlg = FolderConfirmDialog(
                song_title=title,
                proposed=self._last_folder,     # D-12/D-13: None on first song, last path thereafter
                parent=self,
            )
            dlg.exec()   # nested event loop — safe on main thread only (Pitfall 2)
            result = dlg.result_path()          # Path or None
            if result is not None:
                self._last_folder = result      # update session default (D-12, D-14)
        except Exception as exc:
            logging.getLogger(__name__).exception(
                "Folder dialog raised for row %d: %s", row_id, exc
            )
            result = None
        finally:
            self._folder_results[row_id] = result
            if row_id in self._folder_events:
                self._folder_events[row_id].set()   # unblock _folder_worker (C-03)

        # Perform I/O on main thread (D-09 / D-06)
        try:
            if result is None:
                # Skip path (D-06)
                with self._temp_paths_lock:
                    temp = self._temp_paths.get(row_id)
                if temp:
                    Path(temp).unlink(missing_ok=True)
                if not self._closing.is_set():
                    self._dispatcher.row_status_changed.emit(row_id, SongStatus.SKIPPED.value)
                self._on_folder_row_finished(row_id, SongStatus.SKIPPED.value)
            else:
                # Save path (D-09)
                if not self._closing.is_set():
                    self._dispatcher.row_status_changed.emit(row_id, SongStatus.SAVING.value)
                with self._temp_paths_lock:
                    temp = self._temp_paths.get(row_id)
                if temp is None:
                    logging.getLogger(__name__).warning("No temp path for row %d", row_id)
                    if not self._closing.is_set():
                        self._dispatcher.row_status_changed.emit(row_id, SongStatus.FAILED_SAVE.value)
                    self._on_folder_row_finished(row_id, SongStatus.FAILED_SAVE.value)
                    return
                # C-04: atomic-rename pattern — never delete the user's existing
                # file until the new file is successfully placed. shutil.move
                # copies to a .tmp sidecar; os.replace then performs the rename
                # atomically (or raises, leaving the user's original intact).
                dest_candidate = Path(result) / Path(temp).name
                tmp_dest = dest_candidate.with_suffix(dest_candidate.suffix + ".tmp")
                if tmp_dest.exists():
                    tmp_dest.unlink(missing_ok=True)
                shutil.move(str(temp), str(tmp_dest))
                os.replace(str(tmp_dest), str(dest_candidate))
                final = dest_candidate
                self._saved_paths[row_id] = final
                if not self._closing.is_set():
                    self._dispatcher.row_status_changed.emit(row_id, SongStatus.UPLOADING.value)
                self._on_folder_row_finished(row_id, SongStatus.UPLOADING.value)
        except OSError as exc:
            logging.getLogger(__name__).warning("Save failed row %d: %s", row_id, exc)
            if not self._closing.is_set():
                self._dispatcher.row_status_changed.emit(row_id, SongStatus.FAILED_SAVE.value)
            self._on_folder_row_finished(row_id, SongStatus.FAILED_SAVE.value)

    def _on_folder_row_finished(self, _row_id: int, status: str) -> None:
        """Track folder dialog batch completion. Called directly from _folder_worker (off main thread).

        Counters are only written here; this method is called from worker thread so counter
        increments use no lock (GIL protects int increments in CPython — same assumption as
        _on_download_row_finished which also runs from worker via direct call pattern).

        When all rows resolve: emit folder_batch_done(), update status bar. (D-08/D-11)
        """
        terminal = (
            SongStatus.UPLOADING.value,
            SongStatus.SKIPPED.value,
            SongStatus.FAILED_SAVE.value,
        )
        if status not in terminal:
            return

        if status == SongStatus.UPLOADING.value:
            self._folder_done += 1
        elif status == SongStatus.SKIPPED.value:
            self._folder_skipped += 1
        else:
            self._folder_failed += 1

        finished = self._folder_done + self._folder_skipped + self._folder_failed
        if finished < self._folder_total:
            return

        # All folder dialogs resolved (D-08, D-11)
        self._dispatcher.folder_batch_done.emit()
        self.statusBar().showMessage(
            f"Saved {self._folder_done}, skipped {self._folder_skipped}, "
            f"failed {self._folder_failed}"
        )

    def _on_download_row_finished(self, _row_id: int, status: str) -> None:
        """Slot: track batch completion progress. Connected only during active batch run.

        Runs on main thread via Qt queued connection — plain int increments are safe. (D-16)
        """
        terminal = (SongStatus.AWAITING.value, SongStatus.FAILED_DOWNLOAD.value)
        if status not in terminal:
            return

        if status == SongStatus.AWAITING.value:
            self._download_done += 1
            self._executor.submit(self._folder_worker, _row_id)   # chain into Phase 5 (D-02)
        else:
            self._download_failed += 1
            # C-05: failed download never produces a folder dialog — shrink
            # _folder_total so folder_batch_done fires correctly for remaining
            # rows. Was originally incrementing _folder_total per AWAITING,
            # which let batch_done fire early when row 1's dialog resolved
            # before rows 2/3 reached AWAITING.
            self._folder_total = max(0, self._folder_total - 1)
        finished = self._download_done + self._download_failed

        if finished < self._download_total:
            self.statusBar().showMessage(
                f"Downloading {finished} / {self._download_total}…"
            )
            return

        # All workers have finished — update status bar and unlock UI (D-16, D-03)
        self.statusBar().showMessage(
            f"Done — {self._download_done} downloaded, {self._download_failed} failed"
        )
        # Disconnect this slot — it is only valid for this batch run
        try:
            self._dispatcher.row_status_changed.disconnect(self._on_download_row_finished)
        except RuntimeError:
            pass   # already disconnected

        # Edge case: all downloads failed — no folder workers were submitted, so
        # folder_batch_done will never fire. Unlock UI immediately.
        if self._folder_total == 0:
            self._unlock_ui()

    def _unlock_ui(self) -> None:
        """Re-enable paste area and Hz buttons after a batch fully completes."""
        self._paste_box.setReadOnly(False)
        self._btn_440.setEnabled(True)
        self._btn_432.setEnabled(True)
        self._paste_box.setFocus()

    def _refresh_start_button(self, _row_id: int = 0, _status: str = "") -> None:
        """Re-evaluate Start button enabled state. Must only run on main thread (D-02).

        Connected as slot to _dispatcher.row_status_changed. Also called after
        _process_urls adds rows. Enables Start iff ALL rows show METADATA_READY.
        """
        row_count = self.table._table.rowCount()
        if row_count == 0:
            self._btn_start.setEnabled(False)
            return
        all_ready = all(
            (item := self.table._table.item(r, 2)) is not None
            and item.text() == SongStatus.METADATA_READY.value
            for r in range(row_count)
        )
        self._btn_start.setEnabled(all_ready)

    def _start_processing(self) -> None:
        """Start Processing button handler. Locks UI, submits download workers (D-01-D-04).

        Called on main thread when user clicks Start Processing. Reads hz_mode from
        segmented control before locking UI. Workers run in existing ThreadPoolExecutor.
        _on_download_row_finished is connected here (batch-scoped) to track completion.
        """
        hz_mode = self._hz_group.checkedId()   # 440 or 432 (D-06)

        # Collect METADATA_READY rows before locking (read table on main thread)
        row_count = self.table._table.rowCount()
        jobs: list[tuple[int, str, str, dict]] = []
        for row_id in range(row_count):
            item2 = self.table._table.item(row_id, 2)
            if item2 and item2.text() == SongStatus.METADATA_READY.value:
                url       = self.table._rows.get(row_id, "")
                type_item = self.table._table.item(row_id, 1)
                url_type  = type_item.text() if type_item else ""
                metadata  = self._row_metadata.get(row_id, {})
                jobs.append((row_id, url, url_type, metadata))

        if not jobs:
            logging.getLogger(__name__).warning(
                "_start_processing called with no METADATA_READY rows"
            )
            return   # nothing to do — guard against empty batch

        # Lock UI — no edits during active batch run (D-03)
        self._paste_box.setReadOnly(True)
        self._btn_start.setEnabled(False)
        self._btn_440.setEnabled(False)
        self._btn_432.setEnabled(False)

        # Reset batch counters
        # C-05: _folder_total is set up-front to job count, not incremented
        # per AWAITING. Failed downloads decrement _folder_total instead
        # (they never produce a folder dialog).
        self._download_total   = len(jobs)
        self._download_done    = 0
        self._download_failed  = 0
        self._folder_total     = len(jobs)
        self._folder_done      = 0
        self._folder_skipped   = 0
        self._folder_failed    = 0

        # Connect batch-completion tracker (disconnect guard handled in _on_download_row_finished)
        self._dispatcher.row_status_changed.connect(self._on_download_row_finished)

        self.statusBar().showMessage(f"Downloading 0 / {self._download_total}…")

        # Submit one worker per row — yt-dlp serialized inside download_track_for_row (D-07)
        for row_id, url, url_type, metadata in jobs:
            self._executor.submit(
                self._download_worker, row_id, url, url_type, metadata, hz_mode
            )

    def closeEvent(self, event) -> None:
        """Shutdown thread pool and clean up leftover temp files on window close (D-04, D-12)."""
        self._closing.set()
        # Unblock any _folder_worker waiting on a dialog — None sentinel already in _folder_results (D-04)
        for ev in list(self._folder_events.values()):
            ev.set()
        self._executor.shutdown(wait=False)
        try:
            shutil.rmtree(self._session_tmp, ignore_errors=True)
        except Exception:
            pass
        try:
            super().closeEvent(event)
        except TypeError:
            pass   # test isolation: MagicMock passed instead of QCloseEvent


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TuneBridgeApp()
    window.show()
    sys.exit(app.exec())
