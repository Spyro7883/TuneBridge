---
phase: 04-download-pipeline
verified: 2026-05-16T23:05:00+03:00
status: passed
score: 9/9 must-haves verified
overrides_applied: 0
re_verification: false
---

# Phase 4: Download Pipeline Verification Report

**Phase Goal:** Every song in the batch downloads as an audio-only MP3, with optional 432Hz retune applied, using the correct path for its URL type.
**Verified:** 2026-05-16T23:05:00+03:00
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Spotify rows build `ytsearch:{artist} {title} audio` and call `download_track_for_row` with that URL | VERIFIED | `_download_worker` lines 940-943: `if url_type == "Spotify": search_url = f"ytsearch:{artist} {title} audio"`. `test_spotify_search_query_uses_artist_and_title` + `test_download_worker_spotify_path_calls_ytsearch` both GREEN |
| 2 | YouTube rows pass the raw URL directly to `download_track_for_row` (no ytsearch prefix) | VERIFIED | `_download_worker` lines 944-945: `else: search_url = url`. `test_download_worker_youtube_path_uses_direct_url` GREEN |
| 3 | 440Hz toggle is checked by default; 432Hz is unchecked; `QButtonGroup.checkedId()` returns 440 | VERIFIED | `__init__` lines 802-804: `_btn_440.setChecked(True)`, `_hz_group.addButton(_btn_440, 440)`. `test_hz_toggle_default_440` GREEN |
| 4 | Start button disabled when any row is not METADATA_READY; enabled when all rows are METADATA_READY | VERIFIED | `_refresh_start_button` lines 1013-1022; wired to `row_status_changed` signal line 842 and called after `_process_urls` line 886. Tests `test_start_button_disabled_on_mixed_status` + `test_start_button_enabled_all_ready` GREEN |
| 5 | 432Hz mode calls `retune_file()`; 440Hz mode does not | VERIFIED | `_download_worker` lines 951-960: `if hz_mode == 432: retune_file(downloaded, out_path)`. `test_retune_called_on_432` GREEN |
| 6 | 432Hz path emits status transitions: Downloading → Retuning → Awaiting folder (in order) | VERIFIED | `_download_worker` emits DOWNLOADING (line 933), RETUNING (line 953), AWAITING (line 963). `test_status_transitions_432hz` GREEN |
| 7 | 440Hz path emits Downloading → Awaiting folder (no Retuning step) | VERIFIED | `_download_worker` skips RETUNING block when `hz_mode != 432`. `test_status_transitions_440hz` GREEN |
| 8 | A failed download row shows `Failed — download` and does not block other rows | VERIFIED | `except` block lines 967-974: emits `SongStatus.FAILED_DOWNLOAD.value`. `test_failed_download_isolation` GREEN |
| 9 | Full test suite: 10 Phase 4 tests GREEN + 52 prior tests GREEN = 62 total, 0 failures | VERIFIED | `python -m pytest tests/ -v` output: `62 passed in 1.27s` |

**Score:** 9/9 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `tests/test_download_pipeline.py` | 10-test RED-gate scaffold | VERIFIED | File exists, 214 lines, 10 test functions confirmed by pytest collection |
| `tunebridge.py` — `retune_file` | Pitch-shift 440→432Hz, write MP3 | VERIFIED | Lines 171-232: full implementation with librosa, soundfile, ffmpeg, mutagen ID3 preservation |
| `tunebridge.py` — `download_track_for_row` | yt-dlp subprocess serialized via `_download_lock` | VERIFIED | Lines 235-284: `with _download_lock:` wraps entire `Popen + process.wait()` cycle |
| `tunebridge.py` — `_download_lock` | `threading.Lock()` at module level | VERIFIED | Line 150: `_download_lock = threading.Lock()` |
| `tunebridge.py` — `SongStatus.FAILED_DOWNLOAD` | Enum value `"Failed — download"` | VERIFIED | Line 303: `FAILED_DOWNLOAD = "Failed — download"` |
| `tunebridge.py` — `_STATUS_COLORS["Failed — download"]` | `QColor("#EF4444")` | VERIFIED | Line 551: `"Failed — download": QColor("#EF4444")` |
| `tunebridge.py` — `_btn_440`, `_btn_432`, `_hz_group`, `_btn_start` | Toolbar UI elements | VERIFIED | Lines 794-814: all four attributes created in `__init__` |
| `tunebridge.py` — `_refresh_start_button` | Slot enabling/disabling Start | VERIFIED | Lines 1007-1022: full implementation; connected to `row_status_changed` signal (line 842) and called in `_process_urls` (line 886) |
| `tunebridge.py` — `_download_worker` | Per-row download + retune worker | VERIFIED | Lines 916-974: full implementation with closing guard, Spotify/YouTube routing, 432Hz retune branch, error isolation |
| `tunebridge.py` — `_start_processing` | Full batch launch (not stub) | VERIFIED | Lines 1024-1071: reads hz_mode, locks UI, collects METADATA_READY rows, resets counters, connects `_on_download_row_finished`, submits workers |
| `tunebridge.py` — `_on_download_row_finished` | Batch completion tracker slot | VERIFIED | Lines 976-1005: increments done/failed counters, updates status bar, disconnects self when batch complete |
| `tunebridge.py` — `_row_metadata`, `_session_tmp`, `_temp_paths` | Phase 4 state in `__init__` | VERIFIED | Lines 827-830: all three initialized; `metadata_ready` signal connected to populate `_row_metadata` (line 838-840) |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `_dispatcher.row_status_changed` | `_refresh_start_button` | `connect()` in `__init__` line 842 | WIRED | Signal fires on every status change; `_refresh_start_button` re-evaluates Start button state |
| `_btn_start.clicked` | `_start_processing` | `clicked.connect(self._start_processing)` line 813 | WIRED | Click triggers full batch launch |
| `_start_processing` | `_download_worker` | `self._executor.submit(self._download_worker, ...)` lines 1068-1070 | WIRED | One worker submitted per METADATA_READY row |
| `_download_worker` | `_dispatcher.row_status_changed` | `emit(row_id, SongStatus.DOWNLOADING.value)` line 933 | WIRED | Status transitions emitted at Downloading, Retuning, Awaiting folder |
| `_dispatcher.metadata_ready` | `self._row_metadata[row_id]` | lambda `__setitem__` connected line 838-840 | WIRED | Phase 3 metadata persisted for download worker access |
| `_download_lock` | `download_track_for_row` subprocess | `with _download_lock:` line 255 wraps `Popen + wait()` | WIRED | yt-dlp serialized; Firefox cookie conflict prevented |
| `_dispatcher.row_status_changed` | `_on_download_row_finished` | `connect()` in `_start_processing` line 1063 | WIRED | Batch-scoped connection; disconnects after all rows finish |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `_download_worker` | `search_url` | `metadata.get("artist")` + `metadata.get("track_title")` from `_row_metadata[row_id]` (Phase 3) | Yes — populated by `ItunesClient`/`YoutubeExtractor` via `metadata_ready` signal | FLOWING |
| `download_track_for_row` | `mp3s` | `out_dir.glob("*.mp3")` after yt-dlp subprocess | Yes — real filesystem glob after real download | FLOWING |
| `_start_processing` | `jobs` list | `self.table._rows.get(row_id)` + `self._row_metadata.get(row_id)` | Yes — populated by `_process_urls` and metadata workers | FLOWING |
| `_on_download_row_finished` | status bar message | `_download_done` + `_download_failed` counters | Yes — incremented by real terminal status signals | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All 10 Phase 4 tests pass | `python -m pytest tests/test_download_pipeline.py -v` | `10 passed in 0.66s` | PASS |
| Full suite 62 tests pass | `python -m pytest tests/ -v` | `62 passed in 1.27s` | PASS |
| Module imports cleanly (all Phase 4 names exportable) | Confirmed by pytest collection — `from tunebridge import TuneBridgeApp, SongStatus, _download_lock, download_track_for_row, retune_file` in test file header | No ImportError | PASS |
| `SongStatus.FAILED_DOWNLOAD.value` equals `"Failed — download"` | Verified by code read line 303 + test `test_failed_download_isolation` passing | Correct | PASS |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| DL-01 | 04-01, 04-02, 04-04 | Spotify rows use `ytsearch:{artist} {title} audio` path | SATISFIED | `_download_worker` lines 940-943; tests 1+2 GREEN |
| DL-02 | 04-01, 04-02, 04-04 | YouTube rows use direct URL path | SATISFIED | `_download_worker` lines 944-945; test 3 GREEN |
| DL-03 | 04-01, 04-03 | 440Hz/432Hz toggle UI with default 440Hz; Start button enabled only when all rows METADATA_READY | SATISFIED | `_btn_440`, `_btn_432`, `_hz_group`, `_btn_start`, `_refresh_start_button` all present and wired; tests 5+6+7 GREEN |
| DL-04 | 04-01, 04-04 | Per-row status tracking: Downloading → (Retuning →) Awaiting folder; `retune_file()` called at 432Hz only | SATISFIED | `_download_worker` status transitions; `retune_file` called conditionally; tests 8+9+10 GREEN |

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `tunebridge.py` | 1034 | `_start_processing` stub (`pass`) — Wave 2 placeholder | None | Replaced by full implementation in Wave 3 (lines 1024-1071). No stub remains. |

No actionable anti-patterns. The Wave 2 `pass` stub was correctly replaced by Wave 3. No `TODO`, `FIXME`, placeholder returns, or empty implementations in the final code.

---

### Human Verification Required

The following behaviors require manual testing with real Firefox + yt-dlp installed:

1. **Real Spotify download (DL-01)**
   - **Test:** Paste a Spotify track URL, wait for "Metadata ready", click Start Processing with 440Hz selected
   - **Expected:** Status bar shows "Downloading 0 / 1...", row transitions to "Awaiting folder", MP3 file exists in session temp dir
   - **Why human:** Requires real yt-dlp, real Firefox cookies, real Spotify metadata fetch against live network

2. **Real 432Hz retune pipeline (DL-04)**
   - **Test:** Paste a YouTube URL, wait for "Metadata ready", select 432Hz, click Start Processing
   - **Expected:** Row shows Downloading → Retuning → Awaiting folder in sequence; output file is a valid MP3 pitched down by ~31.77 cents
   - **Why human:** Requires real audio processing (librosa + ffmpeg); cannot verify MP3 pitch shift programmatically without running the full stack

3. **UI lock during batch (DL-03)**
   - **Test:** Start a batch; immediately try to paste new URLs or click the Hz toggle
   - **Expected:** Paste area is read-only; 440Hz and 432Hz buttons are disabled during processing; re-enable when "Done" message appears
   - **Why human:** Requires observing live UI state during async batch run

---

## Gaps Summary

No gaps. All 9 observable truths verified. All artifacts exist, are substantive, and are wired. All 4 requirements satisfied. Full test suite: 62/62 passed.

The only human-verification items are live network/audio smoke tests that cannot be automated without real external dependencies (yt-dlp, Firefox, ffmpeg with an actual audio file).

---

_Verified: 2026-05-16T23:05:00+03:00_
_Verifier: Claude (gsd-verifier)_
