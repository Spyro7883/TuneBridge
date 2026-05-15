---
phase: 03-metadata-services
verified: 2026-05-15T11:43:00+03:00
status: human_needed
score: 18/18 must-haves verified
overrides_applied: 0
gaps: []
human_verification:
  - test: "Paste a Spotify URL with valid .env credentials and observe the row cycle from Queued → Fetching metadata → Metadata ready with 'Artist — Title' in column 0"
    expected: "Status column shows 'Metadata ready'; Title column shows the formatted artist/title string in green (#1DB954); no crash"
    why_human: "Requires real Spotify credentials, live network call, and visual Qt UI inspection — not automatable without side effects"
  - test: "Paste a YouTube URL and observe row cycle to Metadata ready with '(guessed)' label in title column"
    expected: "Status column shows 'Metadata ready'; Title column contains '(guessed)' suffix on artist and/or track title; no Spotify call made"
    why_human: "Requires live yt-dlp network extraction and visual UI inspection"
  - test: "Launch app with no .env file and paste a Spotify URL"
    expected: "Status bar shows 'Spotify credentials not found...' warning; pasted Spotify row immediately shows 'Failed — metadata'; no crash or dialog"
    why_human: "D-02 fail-fast path — requires manual env setup (delete/rename .env) and visual inspection of status bar + row"
---

# Phase 3: Metadata Services Verification Report

**Phase Goal:** App can resolve full metadata for any URL in the batch — confirmed fields from Spotify API or extracted fields (labeled as guessed) from YouTube
**Verified:** 2026-05-15T11:43:00+03:00
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | SpotifyClient._get_token() POSTs with grant_type=client_credentials and returns access_token | VERIFIED | Lines 183-192 tunebridge.py: `requests.post(TOKEN_URL, ..., data={"grant_type": "client_credentials"})` + `payload["access_token"]`; test `test_spotify_token_uses_client_credentials_grant` GREEN |
| 2 | Second _get_token() call within TTL reuses cached token (no extra POST) | VERIFIED | Line 178: `if self._token and time.time() < self._token_expiry: return self._token`; test `test_spotify_token_cached_second_call_no_extra_post` asserts `call_count == 1` GREEN |
| 3 | get_track_metadata returns dict with keys: artist, title, album, release_type | VERIFIED | Lines 202-207: returns exact 4-key dict from Spotify tracks endpoint; test `test_spotify_get_track_metadata_returns_required_keys` GREEN |
| 4 | get_album_metadata returns dict with keys: artist, album, release_type | VERIFIED | Lines 217-221: returns 3-key dict from albums endpoint; test `test_spotify_get_album_metadata_returns_required_keys` GREEN |
| 5 | HTTP errors from Spotify API propagate as exceptions (no silent empty dict) | VERIFIED | `resp.raise_for_status()` called on every response at lines 188, 200, 213; tests `test_spotify_token_http_error_raises` and `test_spotify_get_track_metadata_http_error_raises` GREEN |
| 6 | App loads .env via load_dotenv() before SpotifyClient instantiation | VERIFIED | Line 559: `load_dotenv()` immediately after `super().__init__()`, before credential gating at lines 613-620 |
| 7 | Missing/empty Spotify credentials warn in status bar without crashing | VERIFIED | Lines 629-632: status bar message "Spotify credentials not found — Spotify rows will be skipped..." when `_spotify_enabled is False`; no exception path |
| 8 | YoutubeExtractor.extract_metadata(url) returns dict with title + channel populated from yt-dlp info | VERIFIED | Lines 246-248: `result = {"title": info.get("title",""), "channel": info.get("channel") or info.get("uploader","")}` ; tests `test_youtube_extract_returns_title` and `test_youtube_extract_returns_channel` GREEN |
| 9 | extract_info is called with download=False (no actual file download) | VERIFIED | Line 245: `ydl.extract_info(url, download=False)`; test `test_youtube_extract_does_not_download` GREEN |
| 10 | Parsed artist field from title split contains '(guessed)' label | VERIFIED | Line 253: `result["artist"] = f"{artist_part} (guessed)"`; test `test_youtube_guessed_artist_carries_label` GREEN |
| 11 | Parsed track_title field from title split contains '(guessed)' label | VERIFIED | Lines 254, 257: both separator and no-separator paths append `(guessed)` to track_title; test `test_youtube_guessed_track_title_carries_label` GREEN |
| 12 | yt-dlp failures propagate as exceptions (no silent None) | VERIFIED | No try/except in `extract_metadata`; test `test_youtube_extract_error_raises` GREEN |
| 13 | TuneBridgeApp._yt_extractor is a real YoutubeExtractor instance (not None) after init | VERIFIED | Line 623: `self._yt_extractor = YoutubeExtractor()` — unconditional, no credential gating |
| 14 | Spotify URL routes to SpotifyClient.get_track_metadata or get_album_metadata, never to YoutubeExtractor | VERIFIED | Lines 282-291: `if url_type == "Spotify"` branch calls `get_track_metadata` or `get_album_metadata` only; test `test_fetch_metadata_routes_spotify_url_to_spotify_client` asserts `mock_yt.extract_metadata.assert_not_called()` GREEN |
| 15 | YouTube URL routes to YoutubeExtractor.extract_metadata, never to SpotifyClient | VERIFIED | Lines 292-295: `else` branch calls `yt_extractor.extract_metadata(url)` only; test `test_fetch_metadata_routes_youtube_url_to_yt_extractor` asserts `mock_sp.get_track_metadata.assert_not_called()` GREEN |
| 16 | fetch_metadata_for_row result dict contains source='Spotify' for Spotify URLs | VERIFIED | Line 290: `metadata["source"] = "Spotify"`; test `test_fetch_metadata_result_includes_source_spotify` GREEN |
| 17 | fetch_metadata_for_row result dict contains source='YouTube' for YouTube URLs | VERIFIED | Line 294: `metadata["source"] = "YouTube"`; test `test_fetch_metadata_result_includes_source_youtube` GREEN |
| 18 | Spotify album URL routes to get_album_metadata, NOT get_track_metadata | VERIFIED | Lines 286-288: regex group(1)=="album" branch calls `get_album_metadata`; test `test_fetch_metadata_spotify_album_url_delegates_to_get_album_metadata` GREEN |

**Score:** 18/18 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `tunebridge.py` — `import requests` (module-level) | Mock patch target | VERIFIED | Line 14: `import requests` — grep count: 1 |
| `tunebridge.py` — `import yt_dlp` (module-level) | Mock patch target | VERIFIED | Line 15: `import yt_dlp` — grep count: 1 |
| `tunebridge.py` — `from dotenv import load_dotenv` | Credential loading | VERIFIED | Line 16 — grep count: 1 |
| `tunebridge.py` — `class SpotifyClient` | OAuth2 client | VERIFIED | Lines 160-221 — full implementation, not stub |
| `tunebridge.py` — `class YoutubeExtractor` | yt-dlp wrapper | VERIFIED | Lines 229-258 — full implementation with D-08/D-09 |
| `tunebridge.py` — `def fetch_metadata_for_row` | Routing function | VERIFIED | Lines 272-295 — routes by url_type, adds source key |
| `tunebridge.py` — `_SPOTIFY_RESOURCE_RE` | Locale-aware regex | VERIFIED | Lines 267-269 — handles `/intl-[a-z]+/` and `/[a-z]{2}/` prefixes |
| `tunebridge.py` — `_Dispatcher.metadata_ready = Signal(int, object)` | Cross-thread signal | VERIFIED | Line 147 — wired to `table.update_row_metadata` at line 152 |
| `tunebridge.py` — `def update_row_metadata` | D-05/D-06/D-09 display | VERIFIED | Lines 463-494 — full implementation: Spotify track, Spotify album, YouTube with/without separator |
| `tunebridge.py` — `SongStatus.METADATA_READY = "Metadata ready"` | Status enum entry | VERIFIED | Line 118 |
| `tunebridge.py` — `_STATUS_COLORS["Metadata ready"]` + `["Failed — metadata"]` | Color entries | VERIFIED | Lines 383-384 |
| `tunebridge.py` — `self._executor = ThreadPoolExecutor(...)` | Persistent executor | VERIFIED | Line 610 — in `__init__`, not inside `_process_urls` |
| `tunebridge.py` — `def _metadata_worker` | Worker with D-07 isolation | VERIFIED | Lines 725-740 — try/except emits only literal "Failed — metadata" |
| `tunebridge.py` — `def closeEvent` | Executor shutdown | VERIFIED | Lines 742-745 — `self._executor.shutdown(wait=False)` |
| `.env.example` | Credential template | VERIFIED | Exists at project root; contains `SPOTIFY_CLIENT_ID=` and `SPOTIFY_CLIENT_SECRET=` |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `SpotifyClient._get_token` | `requests.post` | module-level `import requests` | WIRED | Line 183: `requests.post(self.TOKEN_URL, ...)` |
| `SpotifyClient.get_track_metadata` | `requests.get` | module-level `import requests` | WIRED | Line 196: `requests.get(f"{self.API_BASE}/tracks/{track_id}", ...)` |
| `TuneBridgeApp.__init__` | `dotenv.load_dotenv` | startup credential loading | WIRED | Line 559: `load_dotenv()` |
| `YoutubeExtractor.extract_metadata` | `yt_dlp.YoutubeDL` | module-level `import yt_dlp` | WIRED | Line 244: `with yt_dlp.YoutubeDL(self._YDL_OPTS) as ydl:` |
| `fetch_metadata_for_row(Spotify track)` | `spotify_client.get_track_metadata` | `_SPOTIFY_RESOURCE_RE` group(1) != "album" | WIRED | Lines 283-290 |
| `fetch_metadata_for_row(Spotify album)` | `spotify_client.get_album_metadata` | `_SPOTIFY_RESOURCE_RE` group(1) == "album" | WIRED | Lines 286-288 |
| `fetch_metadata_for_row(YouTube)` | `yt_extractor.extract_metadata` | else branch | WIRED | Lines 292-295 |
| `_Dispatcher.metadata_ready` | `BatchTable.update_row_metadata` | `Signal(int, object)` queued connection | WIRED | Line 152: `self.metadata_ready.connect(table.update_row_metadata)` |
| `TuneBridgeApp._process_urls` | `self._executor.submit(self._metadata_worker, ...)` | D-03 auto-fetch trigger | WIRED | Lines 657-659 |
| `_metadata_worker` success | `self._dispatcher.metadata_ready.emit(row_id, metadata)` | Qt queued signal | WIRED | Line 738 |
| `_metadata_worker` exception | `self._dispatcher.row_status_changed.emit(row_id, "Failed — metadata")` | D-07 per-row isolation | WIRED | Line 740 |
| `TuneBridgeApp.closeEvent` | `self._executor.shutdown(wait=False)` | resource cleanup | WIRED | Line 744 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `BatchTable.update_row_metadata` | `metadata` dict (row_id, metadata) | `_metadata_worker` → `fetch_metadata_for_row` → Spotify API / yt-dlp | Yes — live API/yt-dlp, mocked in tests | FLOWING |
| `_process_urls` D-02 path | `"Failed — metadata"` literal | `_spotify_enabled is False` gate | Hardcoded string (correct — this is the failure sentinel) | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| 52 combined tests GREEN | `pytest tests/test_metadata_services.py tests/test_tunebridge.py -q` | `52 passed in 0.82s` | PASS |
| Module-level `import requests` | grep count | 1 | PASS |
| Module-level `import yt_dlp` | grep count | 1 | PASS |
| No `from requests import ...` style | grep count non-comment lines | 0 | PASS |
| No `from yt_dlp import ...` style | grep count non-comment lines | 0 | PASS |
| `_SPOTIFY_RESOURCE_RE` handles locale prefix | regex: `intl-[a-z]+` in pattern | present (line 268) | PASS |
| executor created in `__init__`, not in `_process_urls` | grep `self._executor = ThreadPoolExecutor` count | 1 (line 610) | PASS |
| `Failed — metadata` appears 3 times | grep count | 3 (line 384 _STATUS_COLORS, line 650 D-02 branch, line 740 worker except) | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| META-01 | 03-01, 03-03, 03-04 | Spotify Web API client credentials flow — artist, album, title, release_type | SATISFIED | `SpotifyClient` class with token caching, `get_track_metadata`, `get_album_metadata`; 7 SpotifyClient tests GREEN |
| META-02 | 03-02, 03-03, 03-04 | YouTube yt-dlp info extraction — title + channel, no Spotify lookup | SATISFIED | `YoutubeExtractor.extract_metadata` with `download=False`; routing isolation verified; 6 YouTube tests GREEN |
| META-03 | 03-02, 03-04 | "(guessed)" label on inferred YouTube fields — never presented as confirmed | SATISFIED | Lines 253-257: `(guessed)` suffix on both artist and track_title paths; `test_batch_table_update_row_metadata_guessed_label_preserved` GREEN |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `tunebridge.py` | 696 | `with ThreadPoolExecutor(...)` inside `_start_demo` (demo method) | Info | Demo/backward-compat path only — not in `_process_urls`; no user impact. Plan 04 explicitly preserves `_start_demo` for Phase 1 compat tests. |

No TODO/FIXME/placeholder comments found in Phase 3 code paths. No stub implementations remain — `update_row_metadata` is full D-05/D-06/D-09 implementation. `_yt_extractor` is a live `YoutubeExtractor()` instance.

### Human Verification Required

#### 1. End-to-end Spotify fetch with real credentials

**Test:** Create `.env` with valid `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET`, launch app, paste a Spotify track URL (e.g. `https://open.spotify.com/track/2374M0fkVJiOF9EtE81NuG`)
**Expected:** Row cycles Queued → Fetching metadata → Metadata ready; column 0 shows "The Weeknd — Blinding Lights" in green; no crash
**Why human:** Requires live Spotify API credentials and network call; visual Qt UI inspection needed

#### 2. End-to-end YouTube fetch

**Test:** Launch app, paste a YouTube URL (e.g. `https://www.youtube.com/watch?v=4NRXx6U8ABQ`)
**Expected:** Row cycles to Metadata ready; column 0 shows parsed title with "(guessed)" suffix; no Spotify network call
**Why human:** Requires live yt-dlp network extraction and visual UI inspection

#### 3. Missing-credentials fail-fast (D-02)

**Test:** Launch app without `.env` file (or with empty credentials), paste a Spotify URL
**Expected:** Status bar shows "Spotify credentials not found..." warning; row immediately shows "Failed — metadata" in red; no blocking dialog, no crash
**Why human:** Requires manual env setup (rename/delete .env) and visual inspection of status bar + row color

### Gaps Summary

No gaps found. All 18 observable truths are VERIFIED by direct code inspection. The 52-test suite (21 Phase 3 + 31 Phase 2) passes with no failures.

---

_Verified: 2026-05-15T11:43:00+03:00_
_Verifier: Claude (gsd-verifier)_
