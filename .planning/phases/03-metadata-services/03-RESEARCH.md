# Phase 3: Metadata Services - Research

**Researched:** 2026-05-13
**Domain:** Spotify Web API (client credentials), yt-dlp info extraction, PySide6 Signal/Slot threading, python-dotenv
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01:** SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET loaded from `.env` via `python-dotenv` `load_dotenv()` at startup. `.env` in project root, git-ignored.

**D-02:** If `.env` is missing or Spotify keys are empty at startup — warn in status bar, disable Spotify metadata fetching for those rows. YouTube rows continue normally. No crash, no blocking dialog.

**D-03:** Metadata fetching starts automatically as soon as URLs are classified and added to the batch table (same auto-trigger as Phase 2 paste-and-classify flow). No separate button.

**D-04:** While fetching, each row's status transitions to `"Fetching metadata..."` matching `SongStatus.FETCHING_METADATA`. Transition happens immediately before background thread starts.

**D-05:** When metadata arrives, URL in column 0 is replaced with `"Artist — Title"` for tracks; `"Artist — Album [album]"` for Spotify albums. Original URL not visible after replacement.

**D-06:** `(guessed)` label appears inline in cell text for any field parsed (not confirmed) from a YouTube title. Example: `"The Weeknd (guessed) — Blinding Lights (guessed)"`. Non-negotiable (META-03).

**D-07:** On fetch failure — row shows original URL, status `"Failed — metadata"`. Per-row error isolation enforced.

**D-08:** YouTube title parser splits on first ` - ` only. `"The Weeknd - Blinding Lights"` -> `artist="The Weeknd (guessed)"`, `track_title="Blinding Lights (guessed)"`.

**D-09:** No ` - ` separator found -> no artist field. Display: `"(guessed) — <raw title>"`. Channel name stored internally but NOT used as artist guess.

### Claude's Discretion

- Exact HTTP retry strategy for `SpotifyClient._get_token()` (single attempt fine for Phase 3)
- Internal token caching TTL within `SpotifyClient` (caching required; exact TTL is Claude's call)
- Exact `yt_dlp.YoutubeDL` options dict
- Threading model for concurrent metadata fetches (use existing `ThreadPoolExecutor` + `_Dispatcher` pattern)
- `fetch_metadata_for_row()` function signature details (already tested)

### Deferred Ideas (OUT OF SCOPE)

- Settings dialog / UI for entering Spotify credentials
- Manual metadata editing per-row
- Retry button per row after failure
- Spotify playlist expansion
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| META-01 | For Spotify URLs, fetch artist, album, title, release_type via Spotify Web API using client credentials (no user login) | Spotify token endpoint + track/album endpoints verified; `requests` library already installed |
| META-02 | For YouTube URLs, extract title and channel name via yt-dlp info extraction (no Spotify lookup) | `yt_dlp.YoutubeDL` context manager API verified; `download=False` flag confirmed |
| META-03 | Metadata fields inferred from YouTube title parsing labeled `(guessed)` — never presented as confirmed | Title split logic verified; test scaffold enforces label via assertions |
</phase_requirements>

---

## Summary

Phase 3 adds two new service classes (`SpotifyClient`, `YoutubeExtractor`) and one orchestrator function (`fetch_metadata_for_row`) to `tunebridge.py`. The TDD scaffold in `tests/test_metadata_services.py` defines the exact interfaces — all 21 tests are currently RED (ImportError). The implementation turns them GREEN without modifying test assertions.

All three external dependencies are already installed: `yt-dlp 2026.3.17`, `requests 2.32.5`, `python-dotenv 1.2.2`. No new packages are required. The threading model is already in place from Phase 2 (`ThreadPoolExecutor` + `_Dispatcher` Signal/Slot). Phase 3 extends `_Dispatcher` with a second signal carrying `(int, object)` to deliver metadata dicts to the main thread, and adds `BatchTable.update_row_metadata()` to apply the result to the table.

The test mocks require module-level imports: `import requests` and `import yt_dlp` (not `from`-style imports), because they patch `tunebridge.requests.post` and `tunebridge.yt_dlp.YoutubeDL` respectively.

**Primary recommendation:** Add `SpotifyClient`, `YoutubeExtractor`, `fetch_metadata_for_row`, `BatchTable.update_row_metadata`, and a `metadata_ready Signal(int, object)` on `_Dispatcher` to `tunebridge.py`. Wire auto-fetch into `_process_urls`. All logic fits in one file — no new modules needed.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Spotify token fetch (OAuth2 client credentials) | Backend service class (`SpotifyClient`) | — | Network I/O; must run in worker thread, not main thread |
| Spotify track/album metadata fetch | Backend service class (`SpotifyClient`) | — | Network I/O; worker thread |
| YouTube info extraction | Backend service class (`YoutubeExtractor`) | — | yt-dlp I/O; worker thread |
| YouTube title parsing + `(guessed)` label | `YoutubeExtractor.extract_metadata()` | — | Happens immediately after yt-dlp returns info |
| Metadata routing (Spotify vs YouTube) | `fetch_metadata_for_row()` | — | Pure function; routes by `url_type` param |
| Thread-safe result delivery to UI | `_Dispatcher.metadata_ready Signal(int, object)` | Qt queued connection | Signals cross thread boundary safely |
| Row display update (col 0 text + status) | `BatchTable.update_row_metadata()` (main thread) | — | Must run on Qt main thread |
| Credential loading | `TuneBridgeApp.__init__` via `load_dotenv()` | — | Must happen before `SpotifyClient` instantiation |
| Auto-fetch trigger | `TuneBridgeApp._process_urls()` | — | Submits worker tasks after adding rows |

---

## Standard Stack

### Core (all already installed — no new packages)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `requests` | 2.32.5 | Spotify API HTTP calls | Already in project; standard HTTP client [VERIFIED: pip show] |
| `yt-dlp` | 2026.3.17 | YouTube info extraction | Already in project; actively maintained yt-dlp fork [VERIFIED: pip show] |
| `python-dotenv` | 1.2.2 | Load `.env` credentials | Already in project; de-facto standard for env file loading [VERIFIED: pip show] |
| `PySide6` | 6.11.1 | Signal(int, object) for metadata delivery | Already in project from Phase 2 [VERIFIED: Phase 2 complete] |

### No New Installations Required

```bash
# Nothing to install — all dependencies already present
# Verify:
pip show requests yt-dlp python-dotenv
```

---

## Architecture Patterns

### System Architecture Diagram

```
User pastes URLs
      |
      v
_process_urls()  [main thread]
  classify_url() per URL
  table.add_row()
  row.status = "Fetching metadata"
  executor.submit(_metadata_worker, row_id, url, url_type)
      |
      v [worker thread, up to 4 concurrent]
_metadata_worker(row_id, url, url_type)
  fetch_metadata_for_row(url, url_type, spotify_client, yt_extractor)
    |-- url_type == "Spotify" --> SpotifyClient.get_track_metadata(id)
    |                        or   SpotifyClient.get_album_metadata(id)
    |                             uses _get_token() [cached within TTL]
    |                             POST accounts.spotify.com/api/token
    |                             GET  api.spotify.com/v1/tracks/{id}
    |                             GET  api.spotify.com/v1/albums/{id}
    |
    +-- url_type == "YouTube" --> YoutubeExtractor.extract_metadata(url)
                                  yt_dlp.YoutubeDL(opts).__enter__()
                                  .extract_info(url, download=False)
                                  title split on first " - "
                                  append "(guessed)" to parsed fields
  returns metadata_dict with "source" key
      |
      v [still worker thread]
_dispatcher.metadata_ready.emit(row_id, metadata_dict)
      |
      v [Qt queued connection -- main thread]
_on_metadata_ready(row_id, metadata_dict)
  table.update_row_metadata(row_id, metadata_dict)
    col 0: "Artist — Title" or "(guessed) — <raw title>"
    col 2: "Metadata ready"
      |
      v [on error in worker]
_dispatcher.row_status_changed.emit(row_id, "Failed — metadata")
  original URL preserved in col 0, status set to failed color
```

### Recommended Project Structure

```
tunebridge.py              # All Phase 3 code added here (no new files)
  imports: requests, yt_dlp, dotenv (load_dotenv)
  SpotifyClient              # new class
  YoutubeExtractor           # new class
  fetch_metadata_for_row()   # new function
  _Dispatcher                # add metadata_ready Signal(int, object)
  BatchTable                 # add update_row_metadata()
  SongStatus                 # add METADATA_READY = "Metadata ready"
  TuneBridgeApp              # add _spotify_client, _yt_extractor attrs
                             # extend _process_urls() for auto-fetch
.env                         # SPOTIFY_CLIENT_ID=... SPOTIFY_CLIENT_SECRET=...
                             # git-ignored, created by user
tests/
  test_metadata_services.py  # 21 RED tests -- make GREEN (no modifications)
  test_tunebridge.py         # 34 existing GREEN tests -- must stay GREEN
```

### Pattern 1: SpotifyClient with Token Caching

**What:** Client credentials OAuth2 — POST for token, cache until expiry minus buffer, use Bearer token for API calls.

**When to use:** Any Spotify API call; `_get_token()` is called before every API request but only POSTs when cache is stale.

```python
# Source: Spotify Web API docs (accounts.spotify.com/api/token) [VERIFIED: endpoint confirmed]
import base64
import time
import requests

class SpotifyClient:
    TOKEN_URL = "https://accounts.spotify.com/api/token"
    API_BASE  = "https://api.spotify.com/v1"
    TTL_BUFFER = 60  # seconds before expiry to refresh

    def __init__(self, client_id: str, client_secret: str):
        self._client_id = client_id
        self._client_secret = client_secret
        self._token: str | None = None
        self._token_expiry: float = 0.0

    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expiry:
            return self._token
        credentials = base64.b64encode(
            f"{self._client_id}:{self._client_secret}".encode()
        ).decode()
        resp = requests.post(
            self.TOKEN_URL,
            headers={"Authorization": f"Basic {credentials}"},
            data={"grant_type": "client_credentials"},
        )
        resp.raise_for_status()
        payload = resp.json()
        self._token = payload["access_token"]
        self._token_expiry = time.time() + payload["expires_in"] - self.TTL_BUFFER
        return self._token

    def get_track_metadata(self, track_id: str) -> dict:
        token = self._get_token()
        resp = requests.get(
            f"{self.API_BASE}/tracks/{track_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "artist":       data["artists"][0]["name"],
            "title":        data["name"],
            "album":        data["album"]["name"],
            "release_type": data["album"]["album_type"],
        }

    def get_album_metadata(self, album_id: str) -> dict:
        token = self._get_token()
        resp = requests.get(
            f"{self.API_BASE}/albums/{album_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "artist":       data["artists"][0]["name"],
            "album":        data["name"],
            "release_type": data["album_type"],
        }
```

**Test mock pattern — CRITICAL:** Tests patch `tunebridge.requests.post` and `tunebridge.requests.get`. This only works if `tunebridge.py` uses `import requests` (module-level), NOT `from requests import post`. [VERIFIED: test file line 73, 109]

### Pattern 2: YoutubeExtractor with Context Manager

**What:** Use `yt_dlp.YoutubeDL` as a context manager, call `extract_info(url, download=False)` to get metadata without downloading. Parse title for `(guessed)` fields.

**When to use:** All YouTube URL rows.

```python
# Source: yt-dlp API [VERIFIED: inspect.signature confirms download=True default]
import yt_dlp

class YoutubeExtractor:
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
        # Title parsing (D-08, D-09)
        raw_title = info.get("title", "")
        if " - " in raw_title:
            artist_part, track_part = raw_title.split(" - ", 1)
            result["artist"]      = f"{artist_part} (guessed)"
            result["track_title"] = f"{track_part} (guessed)"
        else:
            # D-09: no separator — no artist field; raw title as guessed display
            result["track_title"] = f"{raw_title} (guessed)"
        return result
```

**Test mock pattern — CRITICAL:** Tests patch `tunebridge.yt_dlp.YoutubeDL` and call `__enter__` on the return value. This only works if `tunebridge.py` uses `import yt_dlp` (module-level), NOT `from yt_dlp import YoutubeDL`. [VERIFIED: test file lines 162-165]

### Pattern 3: fetch_metadata_for_row Routing

**What:** Pure function that routes to the correct service based on `url_type`, extracts Spotify ID from URL, and appends `source` key.

**When to use:** Called from worker thread for each row.

```python
# Source: derived from test_metadata_services.py interface [VERIFIED: test file lines 235-307]
import re

_SPOTIFY_RESOURCE_RE = re.compile(
    r"open\.spotify\.com/(?:[a-z]{2}/)?(?:intl-[a-z]+/)?(track|album)/([A-Za-z0-9]+)"
)

def fetch_metadata_for_row(
    url: str,
    url_type: str,
    spotify_client: "SpotifyClient",
    yt_extractor: "YoutubeExtractor",
) -> dict:
    if url_type == "Spotify":
        m = _SPOTIFY_RESOURCE_RE.search(url)
        resource_type = m.group(1) if m else "track"
        resource_id   = m.group(2) if m else url.split("/")[-1].split("?")[0]
        if resource_type == "album":
            metadata = spotify_client.get_album_metadata(resource_id)
        else:
            metadata = spotify_client.get_track_metadata(resource_id)
        metadata["source"] = "Spotify"
        return metadata
    else:  # YouTube
        metadata = yt_extractor.extract_metadata(url)
        metadata["source"] = "YouTube"
        return metadata
```

**Regex verified:** Handles locale-prefixed URLs (`/intl-ro/`, `/en/`) correctly. [VERIFIED: python -c test above]

### Pattern 4: Extended _Dispatcher for Metadata Dicts

**What:** Add `metadata_ready = Signal(int, object)` to `_Dispatcher`. `object` type accepts Python dicts across thread boundaries.

**When to use:** Worker thread emits `metadata_ready` after successful `fetch_metadata_for_row`. Signal(int, object) verified working on PySide6 6.11.1. [VERIFIED: python -c test above]

```python
class _Dispatcher(QObject):
    row_status_changed = Signal(int, str)
    metadata_ready     = Signal(int, object)  # row_id, metadata_dict

    def __init__(self, table: "BatchTable"):
        super().__init__()
        self.row_status_changed.connect(table.update_row_status)
        self.metadata_ready.connect(table.update_row_metadata)
```

### Pattern 5: BatchTable.update_row_metadata

**What:** Write human-readable display string to column 0, update status to "Metadata ready".

**When to use:** Called on main thread via queued Signal connection.

```python
# Source: derived from test assertions [VERIFIED: test file lines 315-360]
def update_row_metadata(self, row_id: int, metadata: dict) -> None:
    if row_id >= self._table.rowCount():
        return
    # Build display string (D-05, D-06, D-09)
    source = metadata.get("source", "")
    if source == "Spotify":
        artist = metadata.get("artist", "")
        release_type = metadata.get("release_type", "")
        if release_type == "album":
            label = f"{artist} — {metadata.get('album', '')} [album]"
        else:
            label = f"{artist} — {metadata.get('title', '')}"
    else:  # YouTube
        artist = metadata.get("artist", "")
        track  = metadata.get("track_title", metadata.get("title", ""))
        if artist:
            label = f"{artist} — {track}"
        else:
            label = f"(guessed) — {track}"

    color = self._STATUS_COLORS.get("Metadata ready", QColor("#1DB954"))
    item0 = self._table.item(row_id, 0)
    if item0:
        item0.setText(label)
        item0.setForeground(QBrush(color))

    # Update status column
    self.update_row_status(row_id, "Metadata ready")
```

**Note:** `_STATUS_COLORS` must include `"Metadata ready"` key, and `SongStatus` must include `METADATA_READY = "Metadata ready"`.

### Pattern 6: Auto-fetch Hook in _process_urls

**What:** After adding valid rows, immediately submit metadata fetch tasks to the executor.

**When to use:** Called when user pastes URLs (D-03).

```python
# In TuneBridgeApp._process_urls(), after the for-url loop:
valid_rows = [(row_id, url, url_type)]  # collect during loop
for row_id, url, url_type in valid_rows:
    self._dispatcher.row_status_changed.emit(row_id, SongStatus.FETCHING.value)
    self._executor.submit(self._metadata_worker, row_id, url, url_type)
```

`_executor` must be a persistent `ThreadPoolExecutor` on `TuneBridgeApp` (not created per-batch), so it can receive submissions at any time.

### Pattern 7: Credential Loading in __init__

```python
# In TuneBridgeApp.__init__:
from dotenv import load_dotenv
import os
load_dotenv()
client_id     = os.getenv("SPOTIFY_CLIENT_ID", "")
client_secret = os.getenv("SPOTIFY_CLIENT_SECRET", "")
if client_id and client_secret:
    self._spotify_client = SpotifyClient(client_id, client_secret)
    self._spotify_enabled = True
else:
    self._spotify_client = None
    self._spotify_enabled = False
    self.statusBar().showMessage(
        "Spotify credentials not found — Spotify rows will be skipped. Add .env with SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET."
    )
self._yt_extractor = YoutubeExtractor()
```

**load_dotenv() behavior verified:** Returns `False` (not exception) when `.env` is missing. `os.getenv` returns `""` for missing keys. [VERIFIED: python -c test above]

### Anti-Patterns to Avoid

- **`from requests import post`:** Breaks `patch("tunebridge.requests.post")` mock. Must use `import requests`.
- **`from yt_dlp import YoutubeDL`:** Breaks `patch("tunebridge.yt_dlp.YoutubeDL")` mock. Must use `import yt_dlp`.
- **New ThreadPoolExecutor per paste:** Phase 2's `_start_demo` creates executor per-call. Phase 3 needs a persistent executor on the app instance so `_process_urls` can submit at any time.
- **Hardcoded status strings in workers:** All status strings from `SongStatus` enum only.
- **`SongStatus.FETCHING.value` vs `"Fetching metadata..."`:** CONTEXT.md D-04 says `"Fetching metadata..."` with ellipsis, but the enum value is `"Fetching metadata"` (no ellipsis). Use `SongStatus.FETCHING.value` — the test checks `_STATUS_COLORS` lookup which uses the enum value.
- **Using channel as artist guess:** D-09 explicitly forbids using channel name as artist. Parser must only use title split.
- **Calling both `get_track_metadata` and `get_album_metadata`:** Tests assert `get_album_metadata` is called for album URLs and `get_track_metadata` is NOT called (and vice versa).

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTTP client for Spotify API | Custom urllib code | `requests` (already installed) | Cookie handling, keep-alive, raise_for_status, json() |
| YouTube metadata extraction | YouTube Data API v3 client | `yt_dlp.YoutubeDL(download=False)` | Already installed, handles age-gates, redirects, cookies, short URLs |
| Environment variable loading | `os.environ` direct reads | `python-dotenv load_dotenv()` | Loads from file; `.env` missing = silent no-op, no crash |
| Thread-to-UI communication | `QTimer.singleShot` polling | `Signal(int, object)` Qt queued connection | Thread-safe, no polling, deterministic delivery |
| Base64 auth encoding | Manual string concat | `base64.b64encode(...)` from stdlib | Correct padding; same as what Spotify expects |

**Key insight:** Every hard part of this phase (OAuth token exchange, YouTube page parsing, thread-safe UI updates) is already solved by installed libraries.

---

## Common Pitfalls

### Pitfall 1: Wrong import style breaks test mocks

**What goes wrong:** Using `from requests import post` or `from yt_dlp import YoutubeDL` causes `patch("tunebridge.requests.post")` to fail — the name no longer exists on the `tunebridge` module.

**Why it happens:** `patch` replaces an attribute on the named object. If you've already imported the function directly, patching the module attribute has no effect on the already-bound local name.

**How to avoid:** Always `import requests` and `import yt_dlp` at module level. Confirmed by reading test mock targets. [VERIFIED: test_metadata_services.py lines 73, 162]

**Warning signs:** `mock_post.call_count == 0` when you expected calls; `AssertionError: Expected call not found`.

### Pitfall 2: Token caching test fails if TTL check is missing

**What goes wrong:** `test_spotify_token_cached_second_call_no_extra_post` asserts `mock_post.call_count == 1` after two `_get_token()` calls. If there is no caching check, count is 2.

**Why it happens:** Naive implementation calls POST every time.

**How to avoid:** Check `time.time() < self._token_expiry` before POSTing. Initialize `_token_expiry = 0.0` so first call always fetches. [VERIFIED: TTL pattern tested]

**Warning signs:** `assert mock_post.call_count == 1` failing with `call_count == 2`.

### Pitfall 3: Persistent executor required for auto-fetch

**What goes wrong:** Phase 2's `_start_demo` creates `ThreadPoolExecutor` inside a `run()` closure. If `_process_urls` does the same, the executor is created and immediately awaited — blocking the main thread.

**Why it happens:** `with ThreadPoolExecutor(...) as pool:` waits for all futures at context manager exit.

**How to avoid:** Create executor once in `TuneBridgeApp.__init__`: `self._executor = ThreadPoolExecutor(max_workers=self._MAX_WORKERS)`. Submit tasks from `_process_urls` without blocking. Close executor in `closeEvent`.

**Warning signs:** UI freezes on paste.

### Pitfall 4: yt-dlp extract_info with download=True downloads files

**What goes wrong:** Default `download=True` causes yt-dlp to download the video file when `extract_info` is called.

**Why it happens:** The default was designed for the CLI use case.

**How to avoid:** Always pass `download=False`. Also set `"quiet": True` and `"no_warnings": True` in opts dict to suppress console output. [VERIFIED: signature default confirmed]

**Warning signs:** Files appearing in project directory, long hang on `extract_info` call.

### Pitfall 5: Spotify URL regex must handle locale prefixes

**What goes wrong:** URL like `https://open.spotify.com/intl-ro/track/2374M0fkVJiOF9EtE81NuG` fails ID extraction with naive regex.

**Why it happens:** Spotify injects locale prefixes (`/intl-XX/`, `/en/`) in some URL formats.

**How to avoid:** Use regex `r"open\.spotify\.com/(?:[a-z]{2}/)?(?:intl-[a-z]+/)?(track|album)/([A-Za-z0-9]+"` which handles both prefixes. [VERIFIED: python regex test confirmed all 4 URL formats]

**Warning signs:** `get_track_metadata` called with wrong ID or entire URL as ID.

### Pitfall 6: _STATUS_COLORS missing "Metadata ready" key

**What goes wrong:** `update_row_status("Metadata ready")` falls back to `QColor("#FFFFFF")` (default) instead of the intended accent color. Not a crash, but visual inconsistency.

**How to avoid:** Add `"Metadata ready": QColor("#1DB954")` to `BatchTable._STATUS_COLORS`. Also add `"Failed — metadata": QColor("#EF4444")` for failure state (D-07).

### Pitfall 7: SongStatus enum missing METADATA_READY

**What goes wrong:** `test_batch_table_update_row_metadata_status_transitions_to_done` checks `status_item.text() in ("Metadata ready", "Fetching metadata", "Done")`. If status is set to something else, test fails.

**How to avoid:** Add `METADATA_READY = "Metadata ready"` to `SongStatus`. Use `SongStatus.METADATA_READY.value` in `update_row_metadata`.

---

## Runtime State Inventory

Not applicable — this is a greenfield feature addition, not a rename/refactor/migration phase.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `requests` | SpotifyClient HTTP calls | Yes | 2.32.5 | — |
| `yt-dlp` | YoutubeExtractor | Yes | 2026.3.17 | — |
| `python-dotenv` | Credential loading | Yes | 1.2.2 | — |
| `PySide6` | Signal(int, object), BatchTable | Yes | 6.11.1 | — |
| Internet access | Spotify API + yt-dlp | Assumed | — | Tests use mocks; no internet needed for test suite |

[VERIFIED: pip show requests yt-dlp python-dotenv]

**Missing dependencies with no fallback:** None.

**Note on `.env` file:** Does not exist yet in project. User must create it. D-02 handles the missing file gracefully (status bar warning, no crash). The `.env` file is only needed at runtime for live Spotify calls — all tests use mocks.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (pytest.ini present) |
| Config file | `pytest.ini` — `testpaths = tests`, `addopts = -q` |
| Quick run command | `pytest tests/test_metadata_services.py -q` |
| Full suite command | `pytest -q` |

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| META-01 | SpotifyClient token fetch uses client_credentials grant | unit | `pytest tests/test_metadata_services.py::test_spotify_token_uses_client_credentials_grant -x` | Yes (RED) |
| META-01 | Token caching — second call no extra POST | unit | `pytest tests/test_metadata_services.py::test_spotify_token_cached_second_call_no_extra_post -x` | Yes (RED) |
| META-01 | HTTP 401 on token endpoint raises exception | unit | `pytest tests/test_metadata_services.py::test_spotify_token_http_error_raises -x` | Yes (RED) |
| META-01 | get_track_metadata returns artist/title/album/release_type | unit | `pytest tests/test_metadata_services.py::test_spotify_get_track_metadata_returns_required_keys -x` | Yes (RED) |
| META-01 | Track metadata values correct from API response | unit | `pytest tests/test_metadata_services.py::test_spotify_get_track_metadata_values_correct -x` | Yes (RED) |
| META-01 | get_album_metadata returns artist/album/release_type | unit | `pytest tests/test_metadata_services.py::test_spotify_get_album_metadata_returns_required_keys -x` | Yes (RED) |
| META-01 | HTTP error on track fetch raises | unit | `pytest tests/test_metadata_services.py::test_spotify_get_track_metadata_http_error_raises -x` | Yes (RED) |
| META-02 | YoutubeExtractor returns title | unit | `pytest tests/test_metadata_services.py::test_youtube_extract_returns_title -x` | Yes (RED) |
| META-02 | YoutubeExtractor returns channel | unit | `pytest tests/test_metadata_services.py::test_youtube_extract_returns_channel -x` | Yes (RED) |
| META-02 | extract_metadata passes download=False | unit | `pytest tests/test_metadata_services.py::test_youtube_extract_does_not_download -x` | Yes (RED) |
| META-02 | yt-dlp failure raises exception | unit | `pytest tests/test_metadata_services.py::test_youtube_extract_error_raises -x` | Yes (RED) |
| META-03 | Artist parsed from title contains (guessed) | unit | `pytest tests/test_metadata_services.py::test_youtube_guessed_artist_carries_label -x` | Yes (RED) |
| META-03 | Track title parsed from title contains (guessed) | unit | `pytest tests/test_metadata_services.py::test_youtube_guessed_track_title_carries_label -x` | Yes (RED) |
| META-01+02 | Spotify URL routes to SpotifyClient only | unit | `pytest tests/test_metadata_services.py::test_fetch_metadata_routes_spotify_url_to_spotify_client -x` | Yes (RED) |
| META-01+02 | YouTube URL routes to YoutubeExtractor only | unit | `pytest tests/test_metadata_services.py::test_fetch_metadata_routes_youtube_url_to_yt_extractor -x` | Yes (RED) |
| META-01 | Result includes source=Spotify | unit | `pytest tests/test_metadata_services.py::test_fetch_metadata_result_includes_source_spotify -x` | Yes (RED) |
| META-02 | Result includes source=YouTube | unit | `pytest tests/test_metadata_services.py::test_fetch_metadata_result_includes_source_youtube -x` | Yes (RED) |
| META-01 | Spotify album URL delegates to get_album_metadata | unit | `pytest tests/test_metadata_services.py::test_fetch_metadata_spotify_album_url_delegates_to_get_album_metadata -x` | Yes (RED) |
| META-01+03 | update_row_metadata stores title in col 0 | integration | `pytest tests/test_metadata_services.py::test_batch_table_update_row_metadata_stores_title -x` | Yes (RED) |
| META-01 | Status transitions to Metadata ready after update | integration | `pytest tests/test_metadata_services.py::test_batch_table_update_row_metadata_status_transitions_to_done -x` | Yes (RED) |
| META-03 | (guessed) label preserved in table round-trip | integration | `pytest tests/test_metadata_services.py::test_batch_table_update_row_metadata_guessed_label_preserved -x` | Yes (RED) |

### Regression Guard

| Requirement | Test Suite | Command |
|-------------|-----------|---------|
| All Phase 2 tests still GREEN | 34 existing tests | `pytest tests/test_tunebridge.py -q` |

### Sampling Rate

- **Per task commit:** `pytest tests/test_metadata_services.py -q`
- **Per wave merge:** `pytest -q` (full suite — 34 + 21 = 55 tests expected GREEN)
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

None — existing test infrastructure covers all phase requirements. `tests/test_metadata_services.py` already exists. `pytest.ini` already configured.

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No (client-side only; client credentials never exposed to browser) | — |
| V3 Session Management | No | — |
| V4 Access Control | No | — |
| V5 Input Validation | Yes (URLs before sending to yt-dlp/Spotify) | `classify_url()` already validates URL type; `_SPOTIFY_RESOURCE_RE` regex validates ID extraction |
| V6 Cryptography | No (Basic auth header is base64 encode, not encryption; transport is HTTPS) | `requests` uses HTTPS by default for `accounts.spotify.com` and `api.spotify.com` |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Credential exposure in `.env` committed to git | Information disclosure | `.gitignore` entry for `.env` (user responsibility; plan must include reminder) |
| Malformed Spotify ID injected into API URL | Tampering | `_SPOTIFY_RESOURCE_RE` regex limits ID to `[A-Za-z0-9]+` — no path traversal possible |
| yt-dlp called with attacker-controlled URL | Tampering | `classify_url()` pre-validates URL as YouTube pattern before passing to extractor |
| `expires_in` from Spotify response controls TTL | Spoofing | Low risk: only affects token refresh frequency; `raise_for_status()` rejects invalid responses |

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Spotipy library for Spotify API | Direct `requests` calls | N/A | Spotipy adds OAuth user-flow complexity; direct requests is simpler for client credentials |
| youtube-dl | yt-dlp (fork) | ~2021 | yt-dlp actively maintained; youtube-dl stagnant |
| Polling with `QTimer` for thread results | Qt Signal/Slot queued connection | Phase 2 decision | No polling; deterministic delivery |

**Deprecated/outdated:**
- `youtube-dl`: Superseded by `yt-dlp`. Do not add `youtube-dl` as dependency.
- `Spotipy` library: Would work, but adds dependency for a flow we don't need (user auth). Direct `requests` is sufficient and already installed.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Spotify API response shape (`artists[0]["name"]`, `album["album_type"]`) is stable | Pattern 1 code example | API response fields renamed -> KeyError in production; tests use mocks so won't catch this in CI |
| A2 | `yt_dlp.YoutubeDL` `channel` field is always present in `_YT_INFO` fixture and real responses | Pattern 2 code example | Missing `channel` key -> KeyError; `.get("channel") or .get("uploader", "")` fallback mitigates |
| A3 | Internet connection available for real Spotify/YouTube calls at runtime | Environment Availability | Tests use mocks — no internet needed for CI; runtime requires network access |

**All three are mitigated by the test scaffold using mocks. Runtime failures surface as "Failed — metadata" per D-07.**

---

## Open Questions

1. **Persistent executor shutdown**
   - What we know: `ThreadPoolExecutor` should be shut down when app closes to avoid thread leaks.
   - What's unclear: `TuneBridgeApp` does not currently override `closeEvent`.
   - Recommendation: Add `closeEvent` that calls `self._executor.shutdown(wait=False)`.

2. **`SongStatus.FETCHING` vs `SongStatus.FETCHING_METADATA`**
   - What we know: Current enum has `FETCHING = "Fetching metadata"`. CONTEXT.md references `SongStatus.FETCHING_METADATA`. Test checks status is in `("Metadata ready", "Fetching metadata", "Done")`.
   - What's unclear: Whether to add `FETCHING_METADATA` as a new alias or just use existing `FETCHING`.
   - Recommendation: Use existing `SongStatus.FETCHING` (value `"Fetching metadata"`) — matches the test's allowed values. No new enum member needed.

3. **Spotify rows when `_spotify_enabled = False`**
   - What we know: D-02 says disable Spotify fetching for those rows.
   - What's unclear: What status to show for a Spotify row when no credentials are configured.
   - Recommendation: Show `"Failed — no credentials"` status immediately (skip worker submission). This is consistent with per-row error isolation (D-07).

---

## Sources

### Primary (HIGH confidence)
- `tests/test_metadata_services.py` — exact interface contracts for all 4 classes/functions [VERIFIED: file read]
- `tunebridge.py` — existing `_Dispatcher`, `BatchTable`, `SongStatus`, `_process_urls` patterns [VERIFIED: file read]
- `yt_dlp.YoutubeDL` — `__enter__` support confirmed, `extract_info` signature confirmed [VERIFIED: python inspect]
- `requests` 2.32.5, `yt-dlp` 2026.3.17, `python-dotenv` 1.2.2 — all installed [VERIFIED: pip show]
- `PySide6.QtCore.Signal(int, object)` — accepts dict payload, queued connection works [VERIFIED: python -c test]
- `load_dotenv()` — returns False on missing file, `os.getenv` returns `""` for missing keys [VERIFIED: python -c test]
- Spotify ID regex — handles locale-prefixed URLs including `/intl-ro/` and `/en/` [VERIFIED: python regex test]

### Secondary (MEDIUM confidence)
- Spotify Web API token endpoint `https://accounts.spotify.com/api/token` with `grant_type=client_credentials` and Basic auth header [CITED: developer.spotify.com/documentation/web-api/tutorials/client-credentials-flow — standard OAuth2 client credentials, endpoint and header format consistent with test mock expectations]
- Spotify track endpoint `https://api.spotify.com/v1/tracks/{id}` and album endpoint `https://api.spotify.com/v1/albums/{id}` [CITED: standard Spotify Web API v1 endpoints; response shape matches `_TRACK_RESP` and `_ALBUM_RESP` fixtures in test file]

### Tertiary (LOW confidence)
- None — all claims verified by tool.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all packages verified with pip show
- Architecture: HIGH — patterns derived from test contracts and existing code
- Pitfalls: HIGH — import mock patterns verified by inspecting test file mock targets
- Spotify API response shape: MEDIUM — consistent with test fixtures, but not live-tested

**Research date:** 2026-05-13
**Valid until:** 2026-06-13 (30 days — stable APIs)
