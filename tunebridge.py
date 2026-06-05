# -*- coding: utf-8 -*-
"""TuneBridge — Phase 2: Input & Detection (PySide6 Liquid Glass)."""
from __future__ import annotations

import atexit
import copy
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
from dotenv import load_dotenv
import librosa
import mutagen
import numpy as np
import requests
import soundfile as sf
import yt_dlp

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
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
QPushButton#settings_btn {
    background-color: transparent;
    border: none;
    color: #B3B3B3;
    font-size: 16pt;
    padding: 0px 4px;
    min-width: 24px;
    max-width: 32px;
}
QPushButton#settings_btn:hover   { color: #FFFFFF; }
QPushButton#settings_btn:pressed { color: #B3B3B3; }
"""

# ---------------------------------------------------------------------------
# Settings persistence layer (Phase 9, PLST-03)
# ---------------------------------------------------------------------------

SETTINGS_PATH = Path.home() / ".tunebridge" / "settings.json"
DEFAULT_SETTINGS = {
    "local_save": False,
    "playlist_preference": "ask",
    "playlist_preference_name": "",
}


def load_settings() -> dict:
    """Read settings.json defensively. Never raises; always returns a complete dict.

    Missing/corrupt/non-dict file → defaults. Partial dict → missing keys filled
    from DEFAULT_SETTINGS. (Pitfall 7)
    """
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return dict(DEFAULT_SETTINGS)
    if not isinstance(data, dict):
        return dict(DEFAULT_SETTINGS)
    return {**DEFAULT_SETTINGS, **data}


def save_settings(settings: dict) -> None:
    """Atomically persist settings to settings.json. (Pitfall 8, Pitfall 14)

    Creates ~/.tunebridge/ if absent. Writes to a .tmp sibling then os.replace
    (atomic same-volume rename). On OSError: clean the tmp, do NOT raise.
    """
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_PATH.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(settings, indent=2), encoding="utf-8")
        os.replace(tmp, SETTINGS_PATH)
    except OSError:
        tmp.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Download infrastructure (Phase 4)
# ---------------------------------------------------------------------------

_download_lock = threading.Lock()   # Serializes yt-dlp subprocess — browser cookie safety (D-07)
_dialog_lock   = threading.Lock()   # Serializes folder dialogs — one at a time (D-01)
_BROWSER_FALLBACKS: tuple[str, ...] = ("firefox", "chrome", "edge", "brave", "chromium", "opera")

# C-11: live yt-dlp subprocesses, so closeEvent can taskkill /T the whole tree
# before executor.shutdown(wait=True) — otherwise rmtree of _session_tmp races
# the still-writing ffmpeg children and leaks files in %TEMP%.
_active_procs: set[subprocess.Popen] = set()

# C-08: Only metadata failures should reclassify a row from valid -> invalid.
# Download and save failures occur AFTER the URL was confirmed valid, so flipping
# the stat-card category corrupts the user-facing "Invalid URLs" semantic.
# Sole caller is BatchTable.update_row_status, which invokes _on_row_failed when
# a status hits this set — wired to decrement valid + increment invalid.
FAILURE_STATUSES: frozenset[str] = frozenset({
    "Failed — metadata",
})


def _sanitise_search_term(s: str) -> str:
    """Strip control chars and leading dashes from scraped metadata before ytsearch: query."""
    s = re.sub(r"[\x00-\x1f\x7f]", " ", s)
    return s.strip().lstrip("-")[:100]


def _sanitise_filename(s: str) -> str:
    """Remove characters illegal in Windows/macOS filenames and trim length."""
    s = re.sub(r'[\\/:*?"<>|]', "_", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:80]


_MAX_COVER_BYTES = 5 * 1024 * 1024  # 5 MB cap (D-03)
_JPEG_MAGIC = b"\xff\xd8\xff"       # D-04
_PNG_MAGIC  = b"\x89PNG\r\n\x1a\n"  # D-04


def _fetch_cover_bytes(url: str) -> bytes | None:
    """Download cover image bytes with bounded timeout and size cap (ART-04/ART-05).

    Returns bytes on success, None on any failure. Uses stream=True so an
    oversized body is never fully buffered before rejection (D-02/D-03).
    """
    if not url.startswith(("https://", "http://")):
        return None  # reject file://, data:, relative paths from a broken scrape
    try:
        with requests.get(url, timeout=5, stream=True) as resp:
            if not resp.ok:
                return None
            chunks: list[bytes] = []
            total = 0
            for chunk in resp.iter_content(chunk_size=65536):
                total += len(chunk)
                if total > _MAX_COVER_BYTES:
                    return None
                chunks.append(chunk)
        return b"".join(chunks)
    except Exception:
        return None


def _sniff_mime(data: bytes) -> str | None:
    """Return JPEG or PNG mime string based on magic bytes, None if unrecognised (D-04)."""
    if data[:3] == _JPEG_MAGIC:
        return "image/jpeg"
    if data[:8] == _PNG_MAGIC:
        return "image/png"
    return None


def _write_id3_tags(file_path: "Path", meta: dict) -> None:
    """Write ID3 title/artist/album tags to an MP3 using mutagen."""
    try:
        from mutagen.id3 import ID3, TIT2, TPE1, TALB, APIC, ID3NoHeaderError
        try:
            tags = ID3(str(file_path))
        except ID3NoHeaderError:
            tags = ID3()
        title  = str(meta.get("track_title", "") or meta.get("title", "") or "")
        artist = str(meta.get("artist", "") or "")
        album  = str(meta.get("album", "") or "")
        if not album:
            album = title  # ART-03: TALB never blank — fall back to track title
        if title:
            tags["TIT2"] = TIT2(encoding=3, text=title)
        if artist:
            tags["TPE1"] = TPE1(encoding=3, text=artist)
        if album:
            tags["TALB"] = TALB(encoding=3, text=album)
        # ART-01: embed cover only when no art exists
        cover_url = meta.get("cover_url") or ""
        if cover_url and not tags.getall("APIC"):
            cover_bytes = _fetch_cover_bytes(cover_url)
            if cover_bytes:
                mime = _sniff_mime(cover_bytes)
                if mime:
                    tags.add(APIC(encoding=3, mime=mime, type=3, desc="", data=cover_bytes))
        tags.save(str(file_path))
    except Exception as exc:
        logging.getLogger(__name__).warning("ID3 tag write failed for %s: %s", file_path.name, exc)


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
                # W-05: original_tags stores live references to the source
                # ID3 frames. Mutating .encoding on the reference would mutate
                # the source frame singleton (and any other view of it).
                # Copy first, then mutate the copy.
                value = copy.copy(value)
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

    # C-06: prefix every output file with a per-call token so we can identify
    # the exact file produced by this invocation. Avoids relying on mtime
    # (Windows 16ms resolution → tied/out-of-order mtimes possible) and
    # ignores any unrelated mp3s already present in out_dir.
    out_token = f"tb_{uuid.uuid4().hex[:8]}"
    base_cmd = [
        ytdlp, "--no-playlist",
        "--no-check-certificate",
        "--js-runtimes", "node",               # Node.js required for YouTube n-challenge (EJS)
        "-x", "--audio-format", "mp3", "--audio-quality", "192K",
        "-o", str(out_dir / f"{out_token}_%(title)s.%(ext)s"),
        search_url,
    ]

    # Try each browser in order; fall back to no-cookies last
    cookie_variants: list[list[str]] = [
        ["--cookies-from-browser", b] for b in _BROWSER_FALLBACKS
    ] + [[]]

    def _run_attempt(cmd: list[str]) -> tuple[bool, int]:
        timed_out = False
        popen_kwargs = dict(
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        # C-07: Windows-specific — hide the console window for spawned yt-dlp
        # (also matches I-01) and let taskkill /T traverse the process tree.
        if sys.platform == "win32":
            popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        proc = subprocess.Popen(cmd, **popen_kwargs)
        # C-11: register Popen so closeEvent can taskkill /T the tree before
        # executor shutdown. Module-level set; we add/remove inside _run_attempt.
        _active_procs.add(proc)

        def _force_kill() -> None:
            """Kill yt-dlp + entire child process tree (C-07).

            WR-05: log warnings and fall back to `proc.kill()` on Windows
            when taskkill is unavailable (e.g. stripped Server Core / Nano
            images). The prior `except Exception: pass` silently leaked
            zombie subprocesses into _active_procs.
            """
            try:
                if sys.platform == "win32":
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                        capture_output=True,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                else:
                    proc.kill()
            except FileNotFoundError:
                # taskkill not on PATH — fall back to direct kill (no tree walk).
                logging.getLogger(__name__).warning(
                    "taskkill missing; falling back to proc.kill() for PID %s", proc.pid
                )
                try:
                    proc.kill()
                except Exception as exc2:  # pragma: no cover — defensive
                    logging.getLogger(__name__).warning(
                        "proc.kill() fallback failed for PID %s: %s",
                        proc.pid, type(exc2).__name__,
                    )
            except Exception as exc:
                logging.getLogger(__name__).warning(
                    "_force_kill failed for PID %s: %s", proc.pid, type(exc).__name__
                )
                try:
                    proc.kill()
                except Exception:
                    pass

        try:
            proc.communicate(timeout=90)
        except subprocess.TimeoutExpired:
            timed_out = True
            _force_kill()
            try:
                proc.communicate(timeout=5)  # drain pipes after kill
            except subprocess.TimeoutExpired:
                pass
        finally:
            _active_procs.discard(proc)
        return timed_out, proc.returncode

    with _download_lock:
        for cookie_args in cookie_variants:
            cmd = [base_cmd[0]] + cookie_args + base_cmd[1:]
            timed_out, rc = _run_attempt(cmd)
            if timed_out:
                raise RuntimeError("yt-dlp download timed out.")
            # W-04: yt-dlp can return rc=0 on ytsearch1: with no results
            # (prints "no results" to stderr, produces no file). Only treat
            # as success when an mp3 actually landed in out_dir — otherwise
            # fall through to the next cookie variant.
            if rc == 0 and any(out_dir.glob(f"{out_token}_*.mp3")):
                break
        else:
            raise RuntimeError("yt-dlp download failed on all browser configurations.")

    # C-06: glob only files we produced this call. Mtime-based newest-wins was
    # non-deterministic on Windows and could shadow prior files in out_dir.
    mp3s = sorted(out_dir.glob(f"{out_token}_*.mp3"))
    return mp3s[0] if mp3s else None


def _search_yt_candidates(query: str, count: int = 5) -> list[dict]:
    """Return top N YouTube search results as {id, title, channel, duration} dicts.

    Uses ytsearch: (regular YouTube) for broad version/remix coverage.
    """
    ytdlp = shutil.which("yt-dlp")
    if not ytdlp:
        return []
    try:
        import os as _os
        result = subprocess.run(
            [ytdlp, f"ytsearch{count}:{query}", "--no-check-certificate", "--no-warnings",
             "--print", "%(id)s|||%(title)s|||%(duration)s|||%(channel)s|||%(view_count)s",
             "--no-playlist"],
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
    target_s   = duration_ms / 1000.0 if duration_ms else None
    # More candidates when no duration data — increases chance of finding audio version
    candidate_count = 5 if target_s else 8
    candidates = _search_yt_candidates(query, count=candidate_count)
    # When no duration data, also search with 'audio' appended to guarantee
    # audio-only uploads appear in the candidate pool (they can rank lower in
    # the default search vs music videos with high view counts).
    if target_s is None:
        audio_cands = _search_yt_candidates(f"{query} audio", count=4)
        seen_ids = {c["id"] for c in candidates}
        candidates = candidates + [c for c in audio_cands if c["id"] not in seen_ids]
    if not candidates:
        return None
    title_l    = title.lower()
    title_n    = _norm_str(title)   # accent-stripped for YT title matching
    artist_key = artist.split(",")[0].strip().lower()

    scored = []
    for c in candidates:
        score  = 0.0
        vid_l  = c.get("title", "").lower()

        if target_s is not None:
            vid_dur = (c.get("duration") or 0)
            diff = abs(vid_dur - target_s)
            if diff <= 2:
                score += 10.0 - diff * 2
            elif diff <= 5:
                score += 2.0
            # Penalise videos significantly longer than the Spotify track —
            # these are typically music videos with intros/outros not in the song.
            if vid_dur > target_s + 15:
                score -= 4.0
            if vid_dur > target_s + 30:
                score -= 4.0  # cumulative: -8 total for 30s+ overage

        # W-03: word-boundary match so short titles like "Run" don't match
        # "Running"/"Marathon Runner"/"Rerun".
        # Strip feat. credits first so long titles like "La Curiosidad (feat. DJ Nelson,
        # ...) - Red Grand Prix Remi" don't break version-qualifier parsing when truncated.
        _feat_strip  = re.sub(r"\s*[\(\[](feat|ft)\..*", "", title_n, flags=re.IGNORECASE).strip()
        _version_m   = re.search(r"\s*\(([^)]+)\)\s*$", _feat_strip)
        _base_title  = _feat_strip[: _version_m.start()].strip() if _version_m else _feat_strip
        _version_kw  = _norm_str(_version_m.group(1)) if _version_m else None
        vid_n        = _norm_str(c.get("title", ""))   # accent-stripped YT title
        if _base_title and re.search(rf"\b{re.escape(_base_title)}\b", vid_n):
            score += 5.0
        # If Spotify track has a version qualifier (remix, edition), reward match / penalise absence
        if _version_kw:
            if _version_kw in vid_n:
                score += 4.0
            else:
                score -= 5.0
        # Weak signal: official YT Music songs often have simple titles without artist prefix
        # W-03: same word-boundary fix for short artist keys ("Bee", "Yes", "Air").
        if artist_key and re.search(rf"\b{re.escape(artist_key)}\b", vid_n):
            score += 1.0
        if artist_key and _norm_str(artist_key) in _norm_str(c.get("channel", "")):
            score += 3.0
        # View count: tiebreaker, capped lower when no duration to stop viral
        # music videos from dominating audio-only uploads.
        views = c.get("view_count", 0) or 0
        view_cap = 3.0 if target_s is None else 5.0
        if views > 0:
            score += min(math.log10(views), view_cap)
        # Penalise non-original versions and music videos (which have intros/outros)
        if any(kw in vid_l for kw in (
            "letra", "lyrics", "lyric video", "karaoke",
            "bass boosted", "sped up", "slowed", "nightcore",
            "8d audio", "reverb", "pitched",
        )):
            score -= 3.0
        # Music videos typically have visual intros/outros making them longer than the song
        if any(kw in vid_l for kw in (
            "official video", "video oficial", "official music video",
            "videoclip", "video clip", "official mv", "(mv)",
        )):
            score -= 4.0
        # Prefer audio-only uploads — these match the Spotify track length
        if any(kw in vid_l for kw in (
            "official audio", "audio oficial", "audio only", "full song",
            "(audio)", "[audio]", "| audio",
        )):
            score += 4.0
        # Penalise remix/live versions when the Spotify title has no such qualifier.
        # WR-07: extended keyword list with ES/PT live indicators (en directo,
        # ao vivo, concierto, en gira) — show/tour-recorded videos bypassed the
        # English-only check and outranked official audio uploads. Penalty
        # raised -3 -> -5 so high view-count live videos can't overcome it via
        # the log10(views) bonus (capped at +5).
        _LIVE_KWS = (
            "remix", "live", "en vivo", "en directo", "ao vivo",
            "concert", "concierto", "en concierto", "en gira",
            "behind the scenes",
        )
        _SPOTIFY_LIVE_KWS = (
            "remix", "live", "en vivo", "en directo", "ao vivo",
            "concierto", "en concierto",
        )
        if _version_kw is None and any(kw in vid_l for kw in _LIVE_KWS) \
                and not any(kw in title_l for kw in _SPOTIFY_LIVE_KWS):
            score -= 5.0

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
    ALREADY_UPLOADED = "Already uploaded"   # D-07: duplicate on iBroadcast
    FAILED_UPLOAD    = "Failed — upload"    # D-14: upload HTTP/network failure
    CANCELLED        = "Cancelled — upload" # PLST-06: user cancelled at playlist-select step


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
    if Path(url).suffix.lower() in (".mp3", ".flac", ".wav") and Path(url).exists():
        return "Local File"
    return None


# ---------------------------------------------------------------------------
# iBroadcast API helpers (Phase 6) — module level, pure functions, no Qt
# ---------------------------------------------------------------------------

# CR-01: TLS verification is on by default. Power users behind corporate
# MITM proxies that re-sign TLS can opt out with TUNEBRIDGE_INSECURE_TLS=1.
# A startup warning is logged when this flag is set (see __main__).
def _ibroadcast_tls_verify() -> bool:
    return os.environ.get("TUNEBRIDGE_INSECURE_TLS", "").strip() not in ("1", "true", "yes")


def _ib_collection_to_dict(raw: dict, fields: list) -> dict:
    """Convert an iBroadcast library collection to {id: named-field dict}.

    iBroadcast prefixes each collection (tracks, playlists, …) with a 'map'
    field-legend entry — e.g. {"name": 0, "tracks": 1, …} — describing the
    positional-array column order. It is NOT a real item: left in place it
    renders as a phantom playlist named '0' (str(map["name"]) == "0"). Strip it
    here, at the source, so every downstream consumer sees real items only.
    """
    if not isinstance(raw, dict):
        return {}
    items = {iid: item for iid, item in raw.items() if iid != "map"}
    if not fields:
        return items
    return {
        iid: dict(zip(fields, item)) if isinstance(item, list) else item
        for iid, item in items.items()
    }


def _ibroadcast_login(
    username: str, password: str
) -> tuple[str | None, int | None, dict, dict]:
    """Authenticate; return (token, user_id, library_tracks, playlists) or (None, None, {}, {})."""
    try:
        resp = requests.post(
            "https://api.ibroadcast.com/s/JSON/",
            json={
                "mode": "status",
                "email_address": username,
                "password": password,
                "version": "0.0",
                "client": "tunebridge",
                "supported_types": 1,
            },
            verify=_ibroadcast_tls_verify(),
            timeout=15,
        )
        data = resp.json()
        _log = logging.getLogger(__name__)
        if not data.get("result"):
            return None, None, {}, {}
        token     = data["user"]["token"]
        user_id   = data["user"]["id"]
        # Second call: fetch library (tracks + playlists) using token
        _base = {
            "user_id": user_id,
            "token": token,
            "client": "tunebridge",
            "supported_types": 1,
            "version": "0.0",
        }
        lib_resp = requests.post(
            "https://api.ibroadcast.com/s/JSON/",
            json={**_base, "mode": "library"},
            verify=_ibroadcast_tls_verify(),
            timeout=30,
        )
        lib_data  = lib_resp.json()
        # supported may be a list of audio formats (not field schema) — guard both cases
        supported = lib_data.get("supported", {})
        lib_sect  = lib_data.get("library", {})

        if isinstance(supported, dict):
            track_fields    = supported.get("tracks",    {}).get("fields", [])
            playlist_fields = supported.get("playlists", {}).get("fields", [])
        else:
            track_fields    = []
            playlist_fields = []

        raw_tracks    = lib_sect.get("tracks",    {}) if isinstance(lib_sect, dict) else {}
        raw_playlists = lib_sect.get("playlists", {}) if isinstance(lib_sect, dict) else {}
        library   = _ib_collection_to_dict(raw_tracks,    track_fields)
        playlists = _ib_collection_to_dict(raw_playlists, playlist_fields)
        _log.warning("iBroadcast library: %d tracks, %d playlists", len(library), len(playlists))

        return token, user_id, library, playlists
    except Exception as exc:
        # WR-01: never log the exception object — some requests/SSL adapter
        # stacks include the POST body (which contains the user's password)
        # in __str__. Log only the exception type name.
        logging.getLogger(__name__).warning(
            "iBroadcast login failed: %s", type(exc).__name__
        )
        return None, None, {}, {}


def _is_duplicate(title: str, artist: str, library: dict) -> bool:
    """Case-insensitive title+artist exact match against fetched library (D-05).

    Handles both named-field dicts and raw positional arrays from the iBroadcast
    library response. Positional arrays: index 2 = title, index 12 = artist.
    Returns False (no duplicate) when the format is unrecognized.
    """
    t = str(title).strip().casefold()
    a = str(artist).strip().casefold()
    for track in library.values():
        if isinstance(track, dict):
            if str(track.get("title", "")).strip().casefold() == t and \
               str(track.get("artist", "")).strip().casefold() == a:
                return True
        elif isinstance(track, list) and len(track) > 12:
            if str(track[2]).strip().casefold() == t and \
               str(track[12]).strip().casefold() == a:
                return True
    return False


def _ibroadcast_upload(file_path: "Path", user_id: int, token: str, playlist_id: str | None = None) -> tuple[bool, int | None]:
    """Upload a single MP3 to iBroadcast. Returns (success, track_id) — track_id may be None (UPL-01)."""
    try:
        upload_data = {
            "user_id": user_id,
            "token": token,
            "file_path": file_path.name,
            "method": "manual",
            "client": "tunebridge",
            "supported_types": 1,
        }
        if playlist_id:
            upload_data["playlist_id"] = int(playlist_id)
        with open(file_path, "rb") as f:
            resp = requests.post(
                "https://upload.ibroadcast.com/",
                data=upload_data,
                files={"file": (file_path.name, f, "audio/mpeg")},
                verify=_ibroadcast_tls_verify(),
                timeout=120,
            )
        data     = resp.json()
        # WR-02: log only documented, non-sensitive keys. Legacy iBroadcast
        # endpoints can echo user_id / session data in upload responses,
        # which would land in DEBUG logs that public-release users may paste
        # in bug reports.
        success  = resp.ok and bool(data.get("result", False))
        track_id = data.get("id") or data.get("track_id")
        logging.getLogger(__name__).debug(
            "iBroadcast upload: result=%s id=%s", data.get("result"), track_id
        )
        return success, (int(track_id) if track_id is not None else None)
    except Exception as exc:
        logging.getLogger(__name__).warning("Upload failed %s: %s", file_path.name, exc)
        return False, None


def _ibroadcast_add_to_playlist(
    playlist_id: str,
    new_track_ids: list[int],
    current_tracks: list,
    user_id: int,
    token: str,
    playlist_name: str = "",
) -> bool:
    """Append new_track_ids to an existing iBroadcast playlist via appendplaylist mode."""
    try:
        _log = logging.getLogger(__name__)
        _log.debug("Playlist add: playlist_id=%r, new_ids=%s", playlist_id, new_track_ids)
        resp = requests.post(
            "https://api.ibroadcast.com/s/JSON/",
            json={
                "mode": "appendplaylist",
                "user_id": user_id,
                "token": token,
                "playlist_id": int(playlist_id),
                "tracks": new_track_ids,
            },
            verify=_ibroadcast_tls_verify(),
            timeout=15,
        )
        data = resp.json()
        _log.debug("appendplaylist response: result=%s", data.get('result'))
        return bool(data.get("result", False))
    except Exception as exc:
        logging.getLogger(__name__).warning("Playlist update failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Thread-safe dispatcher (replaces Phase 1 queue+after pattern)
# ---------------------------------------------------------------------------


class _Dispatcher(QObject):
    row_status_changed = Signal(int, str)
    metadata_ready     = Signal(int, object)   # (row_id, metadata_dict) — crosses thread boundary
    folder_requested   = Signal(int)           # D-02: worker emits row_id; main thread shows dialog
    folder_batch_done  = Signal()              # D-11: emitted when all folder dialogs resolve
    upload_batch_done  = Signal()              # Phase 6: emitted when all upload workers resolve
    status_message     = Signal(str)           # thread-safe status bar update
    start_playlist_poll = Signal()             # triggers QTimer on main thread from worker
    settings_playlists_ready = Signal(dict)   # {} on error/failure

    def __init__(self, table: "BatchTable"):
        super().__init__()
        self.row_status_changed.connect(table.update_row_status)
        self.metadata_ready.connect(table.update_row_metadata)


# ---------------------------------------------------------------------------
# Spotify metadata client (public page scraping — no credentials)
# ---------------------------------------------------------------------------


class SpotifyClient:
    """Fetch Spotify track/album metadata via Spotify's public page OG tags.

    No API key or credentials required. og:title gives the track/album name;
    og:description gives "Artist · Album · Type · Year" for tracks.
    Duration is extracted from the page HTML (MM:SS span).
    """

    _OG_TITLE_RE = re.compile(r'<meta property="og:title" content="([^"]+)"')
    _OG_DESC_RE  = re.compile(r'<meta property="og:description" content="([^"]+)"')
    _OG_IMAGE_RE = re.compile(r'<meta property="og:image" content="([^"]+)"')
    _JSONLD_RE   = re.compile(
        r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>',
        re.DOTALL,
    )
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
        m_img = self._OG_IMAGE_RE.search(html)
        cover_url = _html.unescape(m_img.group(1)) if m_img else ""

        album = ""
        for m_ld in self._JSONLD_RE.finditer(html):
            try:
                ld = json.loads(m_ld.group(1))
                if ld.get("@type") == "MusicRecording":
                    in_album = ld.get("inAlbum")
                    if isinstance(in_album, dict):
                        album = in_album.get("name", "") or ""
                        break  # stop only once the album is found (WR-01)
            except (json.JSONDecodeError, AttributeError, TypeError):
                continue

        duration_ms = None
        m_dur = re.search(r">(\d{1,2}):(\d{2})</span>", html)
        if m_dur:
            duration_ms = (int(m_dur.group(1)) * 60 + int(m_dur.group(2))) * 1000
        return {
            "artist":       artist,
            "track_title":  title,
            "album":        album,
            "release_type": "single",
            "duration_ms":  duration_ms,
            "cover_url":    cover_url,
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
            # No 'Artist - Title' separator: fall back to the channel/uploader
            # name so iBroadcast shows it instead of "Unknown Artist".
            if result["channel"]:
                result["artist"] = result["channel"]
        # YouTube Music / "- Topic" / Art Track uploads carry a real album in the
        # info dict. Use it when present; plain videos omit it, leaving album empty
        # so _write_id3_tags falls back to the track title.
        album = info.get("album") or ""
        if album:
            result["album"] = album
        result["cover_url"] = info.get("thumbnail") or ""
        return result


# ---------------------------------------------------------------------------
# Metadata routing — Spotify vs YouTube
# ---------------------------------------------------------------------------

# Resource extractor for fetch_metadata_for_row. Handles locale prefixes:
#   /track/{id}, /album/{id}, /en/track/{id}, /intl-ro/track/{id}, etc.
_SPOTIFY_RESOURCE_RE = re.compile(
    r"open\.spotify\.com/" + _LOCALE_PREFIX + r"(track|album)/([A-Za-z0-9]+)"
)


def fetch_local_metadata(path: str) -> dict:
    """Read ID3/format tags from a local audio file via mutagen.

    Returns the same dict shape as Spotify/YouTube metadata. Never raises:
    falls back to the filename stem (empty artist) when tags are absent (D-05).
    """
    track_title = ""
    artist = ""
    album = ""
    duration_ms = 0
    try:
        audio = mutagen.File(path, easy=True)
        if audio is not None:
            def _first(key: str) -> str:
                val = audio.get(key)
                if isinstance(val, list):
                    return str(val[0]) if val else ""
                return str(val) if val else ""
            track_title = _first("title")
            artist = _first("artist")
            album = _first("album")
            info = getattr(audio, "info", None)
            if info is not None and getattr(info, "length", 0):
                duration_ms = int(info.length * 1000)
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "Local metadata read failed for %s: %s", path, exc
        )
    if not track_title:
        track_title = Path(path).stem
    return {
        "track_title": track_title,
        "artist": artist,
        "album": album,
        "duration_ms": duration_ms,
        "source": "local",
    }


def fetch_metadata_for_row(
    url: str,
    url_type: str,
    spotify_client: "SpotifyClient",
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
        metadata = spotify_client.get_metadata(url, resource_type)
        metadata["source"] = "Spotify"
        return metadata
    elif url_type == "Local File":
        return fetch_local_metadata(url)
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


class _DeleteAwareTableWidget(QTableWidget):
    """QTableWidget that routes the Delete key to a configurable callback.

    W-11: replaces the prior monkey-patch (`self._table.keyPressEvent = ...`)
    which relied on PySide6 honouring Python attribute lookup for typed event
    dispatch — fragile and silently breakable across PySide6 releases.
    """

    def __init__(self, rows: int, cols: int, parent: QWidget | None = None) -> None:
        super().__init__(rows, cols, parent)
        self._on_delete: Callable[[], None] | None = None

    def set_delete_handler(self, handler: Callable[[], None]) -> None:
        self._on_delete = handler

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Delete and self._on_delete is not None:
            self._on_delete()
            return
        super().keyPressEvent(event)


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
        "Already uploaded":  QColor("#14B8A6"),   # D-07: muted teal, distinct from Done green
        "Failed — upload":   QColor("#EF4444"),   # D-14: same red as other failures
        "Cancelled — upload": QColor("#B3B3B3"),  # PLST-06: gray neutral, mirrors Skipped
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

        self._table = _DeleteAwareTableWidget(0, 3)
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
        # W-11: subclass routes Delete to remove_selected_rows; no monkey-patch.
        self._table.set_delete_handler(self.remove_selected_rows)
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
        # C-09: SongStatus has no FAILED_METADATA member; the value is the literal
        # string set by the metadata worker. The previous hasattr() check always
        # evaluated False so invalid_removed was permanently 0 — invalid card drifted.
        _INVALID_COMPLETED = {"Failed — metadata"}
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


def _playlist_display_name(pid, pdata) -> str:
    """Human-readable name for an iBroadcast playlist entry.

    Handles both shapes: a named-field dict ({"name": ...}) and a positional
    array (name at index 0). Falls back to "Playlist {pid}" when neither yields
    a usable name. Shared by SettingsDialog and PlaylistSelectDialog so both
    render and sort names identically.
    """
    if isinstance(pdata, dict):
        return str(pdata.get("name", f"Playlist {pid}"))
    if isinstance(pdata, list) and pdata:
        return str(pdata[0])
    return f"Playlist {pid}"


def _find_playlist_id_by_name(playlists: dict, name: str) -> str | None:
    """Return the first playlist ID whose name matches `name`, or None.

    Matches by human-readable name (not ID): iBroadcast may reuse IDs, so
    name-match is the correct stale-detection semantics. Name collisions match
    the first found (documented known limitation).
    """
    for pid, pdata in playlists.items():
        if isinstance(pdata, dict):
            pname = pdata.get("name", "")
        elif isinstance(pdata, list) and pdata:
            pname = pdata[0]
        else:
            pname = ""
        if str(pname) == name:
            return str(pid)
    return None


class PlaylistSelectDialog(QDialog):
    """Modal dialog: pick an iBroadcast playlist for the current upload batch.

    Shown once per batch in _start_upload_batch (main thread only).
    Returns selected playlist_id via selected_id(), or None if 'No playlist' chosen.
    """

    _NO_PLAYLIST = "__none__"

    def __init__(self, playlists: dict, parent=None, stale_notice: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Add to playlist")
        self.setModal(True)
        self.setMinimumWidth(320)

        layout = QVBoxLayout(self)
        if stale_notice:
            banner = QLabel(stale_notice)
            banner.setWordWrap(True)
            banner.setStyleSheet("color: #EF4444; font-size: 9pt; padding: 4px 0px;")
            layout.addWidget(banner)
        layout.addWidget(QLabel("Choose an iBroadcast playlist for these tracks:"))

        self._list = QListWidget()
        none_item = QListWidgetItem("— No playlist (upload to library only)")
        none_item.setData(Qt.ItemDataRole.UserRole, self._NO_PLAYLIST)
        self._list.addItem(none_item)

        for pid, pdata in sorted(
            playlists.items(), key=lambda kv: _playlist_display_name(*kv).lower()
        ):
            item = QListWidgetItem(_playlist_display_name(pid, pdata))
            item.setData(Qt.ItemDataRole.UserRole, str(pid))
            self._list.addItem(item)

        self._list.setCurrentRow(0)
        layout.addWidget(self._list)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_id(self) -> str | None:
        item = self._list.currentItem()
        if item is None:
            return None
        val = item.data(Qt.ItemDataRole.UserRole)
        return None if val == self._NO_PLAYLIST else val


class SettingsDialog(QDialog):
    """Modal dialog: manage playlist preference setting.

    Opens instantly on a loading page, fetches playlists off-thread via a
    dedicated executor, and populates a list with two fixed items + sorted
    playlists on settings_playlists_ready.
    """

    _PAGE_LOADING = 0
    _PAGE_LOADED  = 1
    _PAGE_ERROR   = 2

    def __init__(self, dispatcher, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setMinimumWidth(360)

        self._dispatcher = dispatcher
        self._settings = settings          # live dict reference from caller
        self._fetch_failed = False
        self._torn_down = False            # CR-02: idempotent teardown guard
        self._dedicated_executor = ThreadPoolExecutor(max_workers=1)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Playlist preference:"))

        # --- QStackedWidget with three pages ---
        self._stack = QStackedWidget()

        # PAGE_LOADING (idx 0)
        loading_page = QWidget()
        loading_layout = QVBoxLayout(loading_page)
        lbl_loading = QLabel("Loading playlists…")
        lbl_loading.setStyleSheet("color: #B3B3B3; font-size: 9pt;")
        lbl_loading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loading_layout.addWidget(lbl_loading)
        self._stack.addWidget(loading_page)  # index 0

        # PAGE_LOADED (idx 1)
        loaded_page = QWidget()
        loaded_layout = QVBoxLayout(loaded_page)
        self._list = QListWidget()
        loaded_layout.addWidget(self._list)
        self._lbl_empty_note = QLabel("No playlists on your account yet.")
        self._lbl_empty_note.setStyleSheet("color: #B3B3B3; font-size: 9pt;")
        self._lbl_empty_note.setVisible(False)
        loaded_layout.addWidget(self._lbl_empty_note)
        self._stack.addWidget(loaded_page)   # index 1

        # PAGE_ERROR (idx 2)
        error_page = QWidget()
        error_layout = QVBoxLayout(error_page)
        _err_msg = "Couldn" + "\x27" + "t load playlists - check your connection or iBroadcast login."
        self._lbl_error = QLabel(_err_msg)
        self._lbl_error.setStyleSheet("color: #B3B3B3; font-size: 9pt;")
        self._lbl_error.setWordWrap(True)
        error_layout.addWidget(self._lbl_error)
        self._btn_retry = QPushButton("Retry")
        self._btn_retry.clicked.connect(self._start_fetch)
        error_layout.addWidget(self._btn_retry)
        self._stack.addWidget(error_page)    # index 2

        layout.addWidget(self._stack)

        # --- Button box ---
        btn_box = QDialogButtonBox()
        self._btn_save = btn_box.addButton("Save Preference", QDialogButtonBox.ButtonRole.AcceptRole)
        btn_box.addButton("Discard", QDialogButtonBox.ButtonRole.RejectRole)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

        dispatcher.settings_playlists_ready.connect(self._on_playlists_ready)
        self._start_fetch()

    def _start_fetch(self) -> None:
        self._fetch_failed = False
        self._stack.setCurrentIndex(self._PAGE_LOADING)
        self._btn_save.setEnabled(False)
        username = os.environ.get("IBROADCAST_USERNAME", "").strip()
        password = os.environ.get("IBROADCAST_PASSWORD", "").strip()
        self._dedicated_executor.submit(self._fetch_worker, username, password)

    def _fetch_worker(self, username: str, password: str) -> None:
        """Worker thread — never touches widgets directly."""
        try:
            _, _, _, playlists = _ibroadcast_login(username, password)
            self._dispatcher.settings_playlists_ready.emit(playlists or {})
        except Exception:
            self._fetch_failed = True
            self._dispatcher.settings_playlists_ready.emit({})

    def _on_playlists_ready(self, playlists: dict) -> None:
        """Main-thread slot: populate list or show error page."""
        if self._fetch_failed:
            self._stack.setCurrentIndex(self._PAGE_ERROR)
            self._btn_save.setEnabled(False)   # WR-03: no Save on error page
            return
        self._list.clear()
        ask_item = QListWidgetItem("Ask me each time")
        ask_item.setData(Qt.ItemDataRole.UserRole, "ask")
        self._list.addItem(ask_item)
        lib_item = QListWidgetItem("Library only (no playlist)")
        lib_item.setData(Qt.ItemDataRole.UserRole, "library")
        self._list.addItem(lib_item)

        for pid, pdata in sorted(
            playlists.items(), key=lambda kv: _playlist_display_name(*kv).lower()
        ):
            item = QListWidgetItem(_playlist_display_name(pid, pdata))
            item.setData(Qt.ItemDataRole.UserRole, str(pid))
            self._list.addItem(item)

        self._lbl_empty_note.setVisible(len(playlists) == 0)
        self._restore_selection()
        self._stack.setCurrentIndex(self._PAGE_LOADED)
        self._btn_save.setEnabled(True)

    def _restore_selection(self) -> None:
        """Preselect the saved preference."""
        pref = self._settings.get("playlist_preference", "ask")
        name = self._settings.get("playlist_preference_name", "")
        for i in range(self._list.count()):
            item = self._list.item(i)
            val = item.data(Qt.ItemDataRole.UserRole)
            if pref in ("ask", "library") and val == pref:
                self._list.setCurrentRow(i)
                return
            if pref == "playlist" and item.text() == name:
                self._list.setCurrentRow(i)
                return
        self._list.setCurrentRow(0)

    def accept(self) -> None:
        """Write settings on OK only — main thread, never from worker."""
        item = self._list.currentItem()
        if item is not None:
            val = item.data(Qt.ItemDataRole.UserRole)
            if val in ("ask", "library"):
                self._settings["playlist_preference"] = val
                self._settings["playlist_preference_name"] = ""
            else:
                self._settings["playlist_preference"] = "playlist"
                self._settings["playlist_preference_name"] = item.text()
            save_settings(self._settings)
        super().accept()

    def _teardown(self) -> None:
        """Idempotently disconnect the shared-dispatcher slot and stop the executor.

        CR-02: the slot lives on the long-lived `_Dispatcher`, so it MUST be
        disconnected on every exit path — not just window close. accept()/reject()
        route through done(), which closeEvent does NOT fire; leaving the slot
        connected to a soon-to-be-GC'd dialog crashes the next fetch.
        """
        if self._torn_down:
            return
        self._torn_down = True
        try:
            self._dispatcher.settings_playlists_ready.disconnect(self._on_playlists_ready)
        except (RuntimeError, TypeError):
            pass
        self._dedicated_executor.shutdown(wait=False, cancel_futures=True)

    def done(self, result: int) -> None:
        """accept()/reject() both funnel through done() — tear down here."""
        self._teardown()
        super().done(result)

    def closeEvent(self, event) -> None:
        """Window-close path (no accept/reject) — tear down here too."""
        self._teardown()
        super().closeEvent(event)


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

        # C-10: debounce is_dir() check via single-shot timer. Every textChanged
        # restarts the 300ms timer; only the last keystroke triggers the
        # synchronous SMB/UNC stat. Without this, typing \\offline-server\share
        # freezes the dialog for the full SMB timeout (~21s) per character.
        self._validate_timer = QTimer(self)
        self._validate_timer.setSingleShot(True)
        self._validate_timer.setInterval(300)
        self._validate_timer.timeout.connect(self._run_validate)
        self._path_edit.textChanged.connect(self._validate)
        self._run_validate()   # set initial button state without waiting on timer

    def _validate(self, _text: str = "") -> None:
        """Restart debounce timer; the actual is_dir() check runs in _run_validate."""
        self._validate_timer.start()

    def _run_validate(self) -> None:
        text = self._path_edit.text()
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
    _MAX_WORKERS = 6

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

        # Title row with top-right settings gear (D-08)
        title = QLabel("TuneBridge")
        title.setObjectName("title_label")

        self._btn_settings = QPushButton("⚙")          # U+2699 gear glyph
        self._btn_settings.setObjectName("settings_btn")
        self._btn_settings.setToolTip("Playlist settings")
        self._btn_settings.clicked.connect(self._open_settings_dialog)

        header_row = QHBoxLayout()
        header_row.addWidget(title)
        header_row.addStretch()
        header_row.addWidget(self._btn_settings)
        layout.addLayout(header_row)

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
        # Wire row deletion to decrement stat cards AND re-evaluate the Start
        # button — otherwise deleting a completed row leaves Start stuck disabled
        # while the remaining rows are all METADATA_READY (UI-01).
        self.table._on_rows_removed = lambda v, i: (
            self._card_valid.set_count(max(0, self._card_valid.count() - v)),
            self._card_invalid.set_count(max(0, self._card_invalid.count() - i)),
            self._refresh_start_button(),
        )
        # Wire metadata failure to move row from valid → invalid
        self.table._on_row_failed = lambda: (
            self._card_valid.set_count(max(0, self._card_valid.count() - 1)),
            self._card_invalid.set_count(self._card_invalid.count() + 1),
        )

        # Phase 9/10: load persisted settings before any settings-bound widget is built
        self._settings = load_settings()

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

        self._btn_add_files = QPushButton("Add Files")
        self._btn_add_files.setObjectName("add_files_btn")
        self._btn_add_files.clicked.connect(self._on_add_files_clicked)
        toolbar_row.addWidget(self._btn_add_files)

        # Phase 10: local-save toggle (SAVE-01), default OFF, persisted via settings
        self._chk_save = QCheckBox("Save to local disk")
        self._chk_save.setToolTip(
            "OFF: upload to iBroadcast only — no local copy kept.\n"
            "ON: show folder dialog per song and save a local copy."
        )
        self._chk_save.setChecked(bool(self._settings.get("local_save", False)))
        self._chk_save.stateChanged.connect(self._on_save_toggled)
        toolbar_row.addWidget(self._chk_save)

        toolbar_row.addStretch()

        # Near-Start playlist preference indicator (D-10/D-11)
        self._lbl_playlist_pref = QLabel()
        self._lbl_playlist_pref.setObjectName("playlist_pref_label")
        self._lbl_playlist_pref.setMaximumWidth(180)
        self._lbl_playlist_pref.setCursor(Qt.CursorShape.PointingHandCursor)
        self._lbl_playlist_pref.mousePressEvent = lambda _e: self._open_settings_dialog()
        toolbar_row.addWidget(self._lbl_playlist_pref)
        self._refresh_playlist_pref_label()

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
        self._upload_paths:   dict[int, Path]                = {}
        self._folder_total   = 0
        self._folder_done    = 0
        self._folder_skipped = 0
        self._folder_failed  = 0
        self._folder_batch_emitted = False   # Pitfall 4: guard against double folder_batch_done

        # Phase 6: upload batch tracking (D-04, D-11, D-12)
        self._upload_total    = 0
        self._upload_done     = 0
        self._upload_existed  = 0
        self._upload_failed   = 0
        # Phase 6: playlist state (set in _start_upload_batch, used in _on_upload_row_finished)
        self._upload_playlist_id:   str | None  = None
        self._upload_playlist_name: str        = ""
        self._playlist_pending:     bool       = False
        self._upload_token:        str | None  = None
        self._upload_user_id:      int | None  = None
        self._upload_playlists:    dict        = {}
        self._upload_track_ids:    list[int]   = []
        self._upload_track_ids_lock = threading.Lock()

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
        self._dispatcher.folder_batch_done.connect(self._start_upload_batch)
        self._dispatcher.status_message.connect(self.statusBar().showMessage)
        self._dispatcher.start_playlist_poll.connect(self._on_start_playlist_poll)
        self._dispatcher.upload_batch_done.connect(self._unlock_ui)

        # Metadata clients — no credentials required
        self._spotify_client = SpotifyClient()
        self._yt_extractor   = YoutubeExtractor()

        cred_ok = bool(
            os.environ.get("IBROADCAST_USERNAME") and
            os.environ.get("IBROADCAST_PASSWORD")
        )
        self.statusBar().showMessage(
            "Ready — add songs to begin" if cred_ok
            else "iBroadcast credentials not configured — upload will be skipped"
        )

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

    def _on_add_files_clicked(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Add local audio files",
            "",
            "Audio Files (*.mp3 *.flac *.wav)",
        )
        if paths:
            self._process_local_files(paths)

    def _on_save_toggled(self, state: int) -> None:
        """Persist the local-save toggle to settings (Phase 9 layer). SAVE-01."""
        self._settings["local_save"] = bool(self._chk_save.isChecked())
        save_settings(self._settings)

    def _open_settings_dialog(self) -> None:
        """Open SettingsDialog (from _btn_settings or _lbl_playlist_pref click)."""
        # CR-02: a queued second click during the modal exec() nested loop must
        # not spawn a second dialog (each connects its own shared-dispatcher slot).
        if getattr(self, "_settings_dialog_active", False):
            return
        self._settings_dialog_active = True
        try:
            dlg = SettingsDialog(
                dispatcher=self._dispatcher,
                settings=self._settings,
                parent=self,
            )
            if dlg.exec() == QDialog.DialogCode.Accepted:
                self._settings = load_settings()
                self._refresh_playlist_pref_label()
        finally:
            self._settings_dialog_active = False

    def _refresh_playlist_pref_label(self) -> None:
        """Update the near-Start preference indicator label from current settings."""
        pref = self._settings.get("playlist_preference", "ask")
        name = self._settings.get("playlist_preference_name", "")
        if pref == "ask":
            text = '<span style="color:#B3B3B3;">Playlist: Ask each time</span>'
        elif pref == "library":
            text = ('<span style="color:#B3B3B3;">Playlist: </span>'
                    '<span style="color:#1DB954;">Library only</span>')
        else:
            # WR-01: truncate the raw name first, then escape — escaping before
            # truncating measures entity-expanded length and can cut mid-entity.
            display = name[:22] + "…" if len(name) > 22 else name
            safe = _html.escape(display)
            text = ('<span style="color:#B3B3B3;">Playlist: </span>'
                    f'<span style="color:#1DB954;">{safe}</span>')
        self._lbl_playlist_pref.setText(text)

    def _process_local_files(self, paths: list[str]) -> None:
        """Inject local audio files as 'Local File' rows (mirrors _process_urls, D-09)."""
        if not paths:
            return
        self.table.remove_completed_rows()
        valid_count = 0
        invalid_count = 0
        for path in paths:
            url_type = classify_url(path)
            if url_type == "Local File":
                row_id = self.table.add_row(url=path, url_type=url_type)
                valid_count += 1
                self._dispatcher.row_status_changed.emit(
                    row_id, SongStatus.FETCHING.value
                )
                self._executor.submit(
                    self._metadata_worker, row_id, path, "Local File"
                )
            else:
                self.table.add_row(url=path, url_type="Invalid URL")
                invalid_count += 1
        self._card_valid.set_count(self._card_valid.count() + valid_count)
        self._card_invalid.set_count(self._card_invalid.count() + invalid_count)
        if valid_count > 0:
            self.statusBar().showMessage(
                f"{valid_count} added — add more or start processing"
            )
        self._refresh_start_button()

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
                spotify_client = self._spotify_client,
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
                # Use only first artist for YT search — long multi-artist strings
                # produce poor YouTube Music results (e.g. remixes with 8 features).
                artist_raw  = metadata.get("artist", "")
                artist      = _sanitise_search_term(artist_raw.split(",")[0].strip())
                title       = _sanitise_search_term(metadata.get("track_title", ""))
                duration_ms = metadata.get("duration_ms") or 0
                yt_url = _find_best_yt_match(title, artist, duration_ms=duration_ms)
                if yt_url is None:
                    raise RuntimeError(
                        "Not found on YouTube Music — paste a direct YouTube URL instead."
                    )
                downloaded = download_track_for_row(yt_url, row_tmp)
            elif url_type == "Local File":
                dst = row_tmp / Path(url).name
                shutil.copy2(url, dst)
                downloaded = dst
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

            # Tag the working temp file here (worker thread — the cover fetch is
            # network I/O and must not run on the main thread). Doing it now means
            # BOTH save modes upload correct metadata: save-OFF uploads this temp
            # file directly, save-ON moves it to the folder (already tagged).
            _write_id3_tags(downloaded, metadata)

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
            # W-07: no lock around _folder_results write. Happens-before is
            # established by Event.set() (here) → Event.wait() (in _folder_worker);
            # the worker only reads _folder_results[row_id] after wait() returns.
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
                #
                # Build clean filename from metadata (strip tb_xxxx_ temp prefix).
                meta       = self._row_metadata.get(row_id, {})
                _raw_artist = str(meta.get("artist", "") or "")
                _artist    = _sanitise_filename(_raw_artist.split(",")[0].strip())
                _track     = _sanitise_filename(str(meta.get("track_title", "") or meta.get("title", "") or ""))
                _suffix    = "_432hz" if "_432hz" in Path(temp).name else ""
                if _artist and _track:
                    _clean = f"{_artist} - {_track}{_suffix}.mp3"
                else:
                    # fallback: strip tb_xxxxxxxx_ prefix only
                    _clean = re.sub(r"^tb_[0-9a-f]{8}_", "", Path(temp).name)
                dest_candidate = Path(result) / _clean
                # CR-03: never silently overwrite the user's existing file.
                # If a file with the computed name already exists in the
                # destination folder (e.g. user downloaded the same Spotify
                # track in 440 Hz mode last week and may have re-tagged it),
                # append " (2)", " (3)" until a free name is found.
                if dest_candidate.exists():
                    _stem, _suf = dest_candidate.stem, dest_candidate.suffix
                    _i = 2
                    while True:
                        _alt = dest_candidate.with_name(f"{_stem} ({_i}){_suf}")
                        if not _alt.exists():
                            dest_candidate = _alt
                            break
                        _i += 1
                tmp_dest = dest_candidate.with_suffix(dest_candidate.suffix + ".tmp")
                if tmp_dest.exists():
                    tmp_dest.unlink(missing_ok=True)
                # WR-06: if shutil.move succeeds but os.replace raises
                # (destination read-only, disk full, permission flip), the
                # `.tmp` sidecar would otherwise stay in the user's folder
                # forever. Clean it up on any OSError, then re-raise so the
                # outer handler still surfaces FAILED_SAVE.
                try:
                    shutil.move(str(temp), str(tmp_dest))
                    os.replace(str(tmp_dest), str(dest_candidate))
                except OSError:
                    try:
                        Path(tmp_dest).unlink(missing_ok=True)
                    except OSError:
                        pass
                    raise
                # Write ID3 tags so iBroadcast shows correct title/artist/album
                _write_id3_tags(dest_candidate, meta)
                final = dest_candidate
                self._saved_paths[row_id] = final
                self._upload_paths[row_id] = final
                if not self._closing.is_set():
                    self._dispatcher.row_status_changed.emit(row_id, SongStatus.UPLOADING.value)
                self._on_folder_row_finished(row_id, SongStatus.UPLOADING.value)
        except OSError as exc:
            logging.getLogger(__name__).warning("Save failed row %d: %s", row_id, exc)
            if not self._closing.is_set():
                self._dispatcher.row_status_changed.emit(row_id, SongStatus.FAILED_SAVE.value)
            self._on_folder_row_finished(row_id, SongStatus.FAILED_SAVE.value)

    def _on_folder_row_finished(self, _row_id: int, status: str) -> None:
        """Track folder dialog batch completion. Called from _show_folder_dialog on the main thread.

        W-08: prior docstring claimed worker-thread invocation and cited a GIL
        argument. Both wrong — every call site is _show_folder_dialog, which is
        a Qt slot connected via QueuedConnection and therefore runs on the main
        thread. No cross-thread access on these counters.

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

        # All folder dialogs resolved (D-08, D-11) — guard against double emit (Pitfall 4)
        if not self._folder_batch_emitted:
            self._folder_batch_emitted = True
            self._dispatcher.folder_batch_done.emit()
            self.statusBar().showMessage(
                f"Saved {self._folder_done}, skipped {self._folder_skipped}, "
                f"failed {self._folder_failed}"
            )

    def _abort_upload_batch(self, rows) -> None:
        """User cancelled playlist selection — abort upload, mark rows cancelled. (PLST-06)

        Mirrors the empty-batch guard: no workers submitted, UI unlocked.
        "Cancelled — upload" is a neutral terminal (not in FAILURE_STATUSES).
        """
        for row_id in rows:
            self._dispatcher.row_status_changed.emit(row_id, SongStatus.CANCELLED.value)
        # In save-OFF mode this runs synchronously inside _on_download_row_finished,
        # which then emits "Done — N downloaded" and would clobber this message.
        # Defer to the event loop so the cancel feedback is shown last.
        msg = f"Upload cancelled — {len(rows)} track(s) not uploaded."
        QTimer.singleShot(0, lambda: self._dispatcher.status_message.emit(msg))
        self._unlock_ui()

    def _start_upload_batch(self) -> None:
        """Slot connected to folder_batch_done. Authenticates once, submits upload workers. (D-04/D-09/D-13)

        Guard order:
        1. Empty _upload_paths → unlock immediately (D-13)
        2. Missing credentials → emit Done for all rows, unlock (D-02)
        3. Auth failure → emit FAILED_UPLOAD for all rows, unlock (D-03)
        4. Normal path → set _upload_total, submit _upload_worker per row (D-10)
        """
        uploading_rows = list(self._upload_paths.keys())

        # D-13: empty batch guard — all rows were skipped or failed before saving
        if not uploading_rows:
            self._unlock_ui()
            return

        # D-02: missing credentials — no-op upload, treat rows as Done
        username = os.environ.get("IBROADCAST_USERNAME", "").strip()
        password = os.environ.get("IBROADCAST_PASSWORD", "").strip()
        if not username or not password:
            for row_id in uploading_rows:
                self._dispatcher.row_status_changed.emit(row_id, SongStatus.DONE.value)
            self._unlock_ui()
            return

        # D-04: authenticate once per batch
        token, user_id, library, playlists = _ibroadcast_login(username, password)
        if token is None:
            # D-03: auth failure — mark all rows as failed
            for row_id in uploading_rows:
                self._dispatcher.row_status_changed.emit(row_id, SongStatus.FAILED_UPLOAD.value)
            self._unlock_ui()
            return

        # PLST-04/05: preference-aware playlist routing (replaces unconditional dialog)
        settings  = load_settings()
        pref_mode = settings.get("playlist_preference", "ask")
        pref_name = settings.get("playlist_preference_name", "")
        playlist_id = None

        if pref_mode == "library":
            # PLST-02: library-only — skip dialog, upload to library root
            playlist_id = None

        elif pref_mode == "playlist":
            # Pitfall 6 / PLST-05: validate saved name against the live list
            saved_id = _find_playlist_id_by_name(playlists, pref_name)
            if saved_id is not None:
                playlist_id = saved_id          # PLST-04: skip dialog, use favorite
            else:
                # D-12: stale — fall back with a visible banner (D-13: pref untouched)
                stale_msg = (
                    'Your saved playlist "' + _html.escape(pref_name) + '" no longer exists'
                    " — pick another or choose library only."
                )
                if playlists:                   # Pitfall 10: never open an empty dialog
                    dlg = PlaylistSelectDialog(playlists, parent=self,
                                               stale_notice=stale_msg)
                    if dlg.exec() == QDialog.DialogCode.Accepted:
                        playlist_id = dlg.selected_id()
                    else:                       # PLST-06: Cancel aborts the whole batch
                        self._abort_upload_batch(uploading_rows)
                        return
                # else: no playlists at all -> library root (playlist_id stays None)

        else:  # "ask" or unrecognized -> existing v1.0 behavior
            if playlists:
                dlg = PlaylistSelectDialog(playlists, parent=self)
                if dlg.exec() == QDialog.DialogCode.Accepted:
                    playlist_id = dlg.selected_id()
                else:                           # PLST-06: Cancel aborts the whole batch
                    self._abort_upload_batch(uploading_rows)
                    return

        # Store playlist state for workers and _on_upload_row_finished
        self._upload_playlist_id      = playlist_id
        self._upload_token            = token
        self._upload_user_id          = user_id
        self._upload_playlists        = playlists
        self._upload_track_ids        = []
        # Snapshot of library track IDs before upload — used to detect new tracks after processing
        self._pre_upload_library_ids  = set(library.keys())
        # Store playlist name for status messages
        if playlist_id:
            pdata = playlists.get(playlist_id, {})
            if isinstance(pdata, list):
                self._upload_playlist_name = str(pdata[0]) if pdata else playlist_id
            else:
                self._upload_playlist_name = str(pdata.get("name", playlist_id)) if isinstance(pdata, dict) else playlist_id
        else:
            self._upload_playlist_name = ""

        # D-10: submit parallel upload workers (one per saved row)
        self._upload_total = len(uploading_rows)
        self._upload_done = 0
        self._upload_existed = 0
        self._upload_failed = 0
        for row_id in uploading_rows:
            self._executor.submit(self._upload_worker, row_id, token, user_id, library)

    def _upload_worker(self, row_id: int, token: str, user_id: int, library: dict) -> None:
        """Worker thread: duplicate check then upload. Per-row isolated (D-16).

        Arguments are passed by _start_upload_batch — no auth call inside worker (D-04).
        All status transitions via row_status_changed signal (thread-safe Qt queued path).
        """
        if self._closing.is_set():
            return
        try:
            meta      = self._row_metadata.get(row_id, {})
            # CR-02: Spotify metadata stores the song title under "track_title"
            # (see lines 821, 831); only YouTube uses "title" (line 863).
            # Reading just "title" silently broke duplicate detection for every
            # Spotify URL — the primary documented input format.
            title     = meta.get("track_title", "") or meta.get("title", "")
            artist    = meta.get("artist", "")
            # WR-03: defensive read — _upload_paths can be cleared between
            # batches; if our row was already wiped, abort this upload silently.
            file_path = self._upload_paths.get(row_id)
            if file_path is None:
                return

            if _is_duplicate(title, artist, library):
                self._dispatcher.row_status_changed.emit(
                    row_id, SongStatus.ALREADY_UPLOADED.value
                )
                self._on_upload_row_finished(row_id, SongStatus.ALREADY_UPLOADED.value)
                return

            success, track_id = _ibroadcast_upload(file_path, user_id, token, self._upload_playlist_id)
            if success and track_id and self._upload_playlist_id:
                with self._upload_track_ids_lock:
                    self._upload_track_ids.append(track_id)
            status = SongStatus.DONE if success else SongStatus.FAILED_UPLOAD
            self._dispatcher.row_status_changed.emit(row_id, status.value)
            self._on_upload_row_finished(row_id, status.value)
        except Exception as exc:
            logging.getLogger(__name__).warning("Upload worker failed row %d: %s", row_id, exc)
            if not self._closing.is_set():
                self._dispatcher.row_status_changed.emit(
                    row_id, SongStatus.FAILED_UPLOAD.value
                )
            self._on_upload_row_finished(row_id, SongStatus.FAILED_UPLOAD.value)

    def _on_upload_row_finished(self, _row_id: int, status: str) -> None:
        """Track upload batch completion. Called from _upload_worker threads.

        _upload_total is written once before any worker starts → safe read.
        Counter increments (_upload_done/_existed/_failed) are mutually exclusive
        and protected by CPython GIL for v1.0 (max 4 threads). (D-11/D-12)
        When all rows resolve: emit upload_batch_done, update status bar.
        """
        terminal = (
            SongStatus.DONE.value,
            SongStatus.ALREADY_UPLOADED.value,
            SongStatus.FAILED_UPLOAD.value,
        )
        if status not in terminal:
            return

        if status == SongStatus.DONE.value:
            self._upload_done += 1
        elif status == SongStatus.ALREADY_UPLOADED.value:
            self._upload_existed += 1
        else:
            self._upload_failed += 1

        finished = self._upload_done + self._upload_existed + self._upload_failed
        if finished < self._upload_total:
            # Pitfall 12: called from worker thread — marshal to main thread via signal.
            self._dispatcher.status_message.emit(
                f"Uploading {finished} of {self._upload_total}…"
            )
            return

        # All upload rows resolved (D-11, D-12)
        self._dispatcher.upload_batch_done.emit()

        base_msg = (
            f"Done — {self._upload_done} uploaded, "
            f"{self._upload_existed} already existed, "
            f"{self._upload_failed} failed"
        )

        if self._upload_playlist_id and self._upload_done > 0:
            pdata = self._upload_playlists.get(self._upload_playlist_id, {})
            if isinstance(pdata, list):
                playlist_name = str(pdata[0]) if pdata else "playlist"
            else:
                playlist_name = str(pdata.get("name", "playlist")) if isinstance(pdata, dict) else "playlist"
            self._dispatcher.status_message.emit(
                f"{base_msg} — waiting for iBroadcast to process, then adding to '{playlist_name}'…"
            )
            # iBroadcast upload API returns no track_id — tracks appear after async processing.
            # Schedule a library re-fetch after 30s to find new track IDs and add them to playlist.
            self._playlist_pending = True
            self._dispatcher.start_playlist_poll.emit()
        else:
            self._dispatcher.status_message.emit(base_msg)

    def _on_start_playlist_poll(self) -> None:
        """Main-thread slot: start QTimer for delayed playlist update (safe from main thread)."""
        QTimer.singleShot(5_000, lambda: self._delayed_playlist_update(
            self._upload_playlist_id,
            self._upload_playlist_name,
            set(self._pre_upload_library_ids),
            self._upload_user_id,
            self._upload_token,
        ))

    def _delayed_playlist_update(
        self,
        playlist_id: str,
        playlist_name: str,
        pre_ids: set,
        user_id: int,
        token: str,
        attempt: int = 1,
    ) -> None:
        """Main-thread slot (QTimer): dispatch playlist polling to background thread."""
        self._executor.submit(
            self._playlist_update_worker,
            playlist_id, playlist_name, pre_ids, user_id, token,
            self._upload_done,
        )

    def _playlist_update_worker(
        self,
        playlist_id: str,
        playlist_name: str,
        pre_ids: set,
        user_id: int,
        token: str,
        expected_count: int = 1,
    ) -> None:
        """Background worker: poll library until new tracks appear, then add to playlist.

        Retries up to 3 times with 60s sleep between attempts.
        All network calls stay in this thread — no QTimer from worker thread.
        """
        import time
        username = os.environ.get("IBROADCAST_USERNAME", "").strip()
        password = os.environ.get("IBROADCAST_PASSWORD", "").strip()
        for attempt in range(1, 4):
            new_token, new_user_id, new_library, new_playlists = _ibroadcast_login(username, password)
            new_ids = [int(k) for k in new_library if k not in pre_ids]
            # Wait until all expected tracks appear (avoid missing slow-processed ones)
            if len(new_ids) >= expected_count:
                break
            if new_ids and attempt == 1:
                # Found some but not all — retry once more after short wait
                time.sleep(15)
                continue
            if attempt < 3:
                self._dispatcher.status_message.emit(
                    f"Waiting for iBroadcast to process… (check {attempt}/3, retry in 60s)"
                )
                time.sleep(60)
            else:
                self._playlist_pending = False
                self._dispatcher.status_message.emit(
                    f"Could not add to '{playlist_name}' — iBroadcast still processing. Add manually."
                )
                return
        pdata = new_playlists.get(playlist_id, {})
        if isinstance(pdata, list):
            current = pdata[1] if len(pdata) > 1 and isinstance(pdata[1], list) else []
        else:
            current = pdata.get("tracks", []) if isinstance(pdata, dict) else []
        ok = _ibroadcast_add_to_playlist(playlist_id, new_ids, current, new_user_id or user_id, new_token or token, playlist_name)
        self._playlist_pending = False
        if ok:
            self._dispatcher.status_message.emit(
                f"Added {len(new_ids)} track(s) to playlist '{playlist_name}'."
            )
        else:
            self._dispatcher.status_message.emit(
                f"Playlist add failed for '{playlist_name}'."
            )
        logging.getLogger(__name__).debug(
            "Playlist update: new_ids=%s, ok=%s", new_ids, ok
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
            # WR-04: queued row_status_changed signals can land here after
            # closeEvent has begun shutting the executor down. Guard against
            # `RuntimeError: cannot schedule new futures after shutdown`
            # which would otherwise crash a second batch in the same session.
            if self._closing.is_set():
                return
            if self._chk_save.isChecked():          # save ON — v1.0 path unchanged (SAVE-03)
                try:
                    self._executor.submit(self._folder_worker, _row_id)   # chain into Phase 5 (D-02)
                except RuntimeError:
                    # Executor already shut down during close — nothing to do.
                    return
            else:                                   # save OFF — bypass folder stage (SAVE-02)
                with self._temp_paths_lock:
                    temp = self._temp_paths.get(_row_id)
                if temp is not None:
                    self._upload_paths[_row_id] = temp
                # Drive the gate counter directly; folder_batch_done fires via the normal path.
                self._on_folder_row_finished(_row_id, SongStatus.UPLOADING.value)
        else:
            self._download_failed += 1
            # C-05: failed download never produces a folder dialog — shrink
            # _folder_total so folder_batch_done fires correctly for remaining
            # rows. Was originally incrementing _folder_total per AWAITING,
            # which let batch_done fire early when row 1's dialog resolved
            # before rows 2/3 reached AWAITING.
            self._folder_total = max(0, self._folder_total - 1)
            # WR-06: if all surviving folder dialogs already resolved before
            # this download failed, _on_folder_row_finished returned early
            # (finished < old _folder_total) and never emitted
            # folder_batch_done. After shrinking, re-check the equality and
            # fire so the upload batch can start. Strict == guards against
            # double-emission when multiple downloads fail in succession.
            folder_finished = (
                self._folder_done + self._folder_skipped + self._folder_failed
            )
            if self._folder_total > 0 and folder_finished == self._folder_total:
                if not self._folder_batch_emitted:
                    self._folder_batch_emitted = True
                    self._dispatcher.folder_batch_done.emit()
                    self.statusBar().showMessage(
                        f"Saved {self._folder_done}, skipped {self._folder_skipped}, "
                        f"failed {self._folder_failed}"
                    )
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
        self._btn_add_files.setEnabled(True)
        self._chk_save.setEnabled(True)
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

        # Reset per-batch state — prevents stale _saved_paths / _upload_paths entries
        # from previous batches being re-uploaded if user deleted rows and started a new batch.
        self._saved_paths.clear()
        self._upload_paths.clear()

        # Lock UI — no edits during active batch run (D-03)
        self._paste_box.setReadOnly(True)
        self._btn_start.setEnabled(False)
        self._btn_440.setEnabled(False)
        self._btn_432.setEnabled(False)
        self._btn_add_files.setEnabled(False)
        self._chk_save.setEnabled(False)   # D-07: locked for batch duration

        # W-09: if setup raises (e.g. _executor.submit hits a shutdown executor
        # from a parallel closeEvent), unwind UI lock so the user isn't trapped.
        try:
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
            self._folder_batch_emitted = False   # Pitfall 4: fresh guard per batch

            # Connect batch-completion tracker (disconnect guard handled in _on_download_row_finished)
            self._dispatcher.row_status_changed.connect(self._on_download_row_finished)

            self.statusBar().showMessage(f"Downloading 0 / {self._download_total}…")

            # Submit one worker per row — yt-dlp serialized inside download_track_for_row (D-07)
            for row_id, url, url_type, metadata in jobs:
                self._executor.submit(
                    self._download_worker, row_id, url, url_type, metadata, hz_mode
                )
        except Exception as exc:
            logging.getLogger(__name__).exception(
                "_start_processing setup failed; unlocking UI: %s", exc
            )
            try:
                self._dispatcher.row_status_changed.disconnect(self._on_download_row_finished)
            except (TypeError, RuntimeError):
                pass   # was never connected
            self._paste_box.setReadOnly(False)
            self._btn_start.setEnabled(True)
            self._btn_440.setEnabled(True)
            self._btn_432.setEnabled(True)
            self.statusBar().showMessage("Failed to start — see log")

    def closeEvent(self, event) -> None:
        """Shutdown thread pool and clean up leftover temp files on window close (D-04, D-12)."""
        if self._playlist_pending:
            from PySide6.QtWidgets import QMessageBox
            reply = QMessageBox.question(
                self, "Playlist update in progress",
                "Tracks are being added to the playlist. Close anyway and skip playlist update?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return
        self._closing.set()
        # Unblock any _folder_worker waiting on a dialog — None sentinel already in _folder_results (D-04)
        for ev in list(self._folder_events.values()):
            ev.set()
        # C-11: kill yt-dlp + ffmpeg trees BEFORE shutdown(wait=True). Without this,
        # workers block on proc.stdout.read() until ffmpeg post-processing finishes
        # (potentially minutes), and rmtree races writes into _session_tmp.
        for proc in list(_active_procs):
            try:
                if proc.poll() is None:
                    if sys.platform == "win32":
                        subprocess.run(
                            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                            capture_output=True,
                            creationflags=subprocess.CREATE_NO_WINDOW,
                        )
                    else:
                        proc.kill()
            except Exception:
                pass
        # C-11: wait=True + cancel_futures prevents the race where workers hold
        # _temp_paths_lock / _dialog_lock while rmtree runs.
        self._executor.shutdown(wait=True, cancel_futures=True)
        try:
            shutil.rmtree(self._session_tmp, ignore_errors=True)
        except Exception:
            pass
        try:
            super().closeEvent(event)
        except TypeError:
            pass   # test isolation: MagicMock passed instead of QCloseEvent


if __name__ == "__main__":
    load_dotenv()
    # CR-01: warn loudly if the user has opted out of TLS verification.
    if not _ibroadcast_tls_verify():
        import warnings as _warnings
        try:
            from urllib3.exceptions import InsecureRequestWarning as _InsecureRequestWarning
            _warnings.simplefilter("ignore", _InsecureRequestWarning)
        except Exception:
            pass
        logging.getLogger(__name__).warning(
            "TUNEBRIDGE_INSECURE_TLS=1 set — TLS certificate verification is DISABLED. "
            "Credentials may be exposed to on-path attackers. Unset this variable to restore security."
        )
    app = QApplication(sys.argv)
    window = TuneBridgeApp()
    window.show()
    sys.exit(app.exec())
