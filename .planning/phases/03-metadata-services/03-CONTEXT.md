# Phase 3: Metadata Services - Context

**Gathered:** 2026-05-13
**Status:** Ready for planning

<domain>
## Phase Boundary

Given a batch of classified Spotify and YouTube URL rows (populated by Phase 2), fetch full metadata for each row using the appropriate service, update the batch table row with the result, and surface any errors per-row without blocking other rows.

**In scope:** `SpotifyClient` (client credentials OAuth), `YoutubeExtractor` (yt-dlp info extraction), metadata display in batch table, `(guessed)` label convention, `.env`-based credentials, per-row error handling, auto-fetch on paste.

**Out of scope:** actual download/retune pipeline (Phase 4), folder organisation (Phase 5), iBroadcast upload (Phase 6), user-editable metadata fields.

</domain>

<decisions>
## Implementation Decisions

### A — Credentials Storage
- **D-01:** SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET are loaded from a `.env` file using `python-dotenv` (`load_dotenv()` at startup). The `.env` file lives in the project root and is git-ignored.
- **D-02:** If the `.env` file is missing or the Spotify keys are empty at startup, the app warns in the status bar and disables Spotify metadata fetching for those rows. YouTube rows continue to work normally. No crash, no blocking dialog.

### B — Fetch Trigger
- **D-03:** Metadata fetching starts automatically as soon as URLs are classified and added to the batch table (same auto-trigger pattern as Phase 2's paste-and-classify flow). No separate "Fetch Metadata" button.
- **D-04:** While fetching, each row's status column transitions to `"Fetching metadata..."` (matching `SongStatus.FETCHING_METADATA`). This transition happens immediately before the background thread starts.

### C — Row Display
- **D-05:** When metadata arrives, the URL in column 0 is replaced with a human-readable label formatted as `"Artist — Title"`. For Spotify albums: `"Artist — Album [album]"`. The original URL is no longer visible in the table after replacement.
- **D-06:** The `(guessed)` label appears **inline in the cell text** for any field parsed (not confirmed) from a YouTube title. Example: `"The Weeknd (guessed) — Blinding Lights (guessed)"`. Never omit the label for guessed fields — META-03 is non-negotiable.
- **D-07:** On metadata fetch failure (network error, API error, etc.), the row shows its original URL with status `"Failed — metadata"`. Other rows in the batch are unaffected. Per-row error isolation must be enforced.

### D — YouTube Title Parsing
- **D-08:** The YouTube title parser splits on the **first occurrence of ` - ` (space-dash-space)** only. No other separators. Result: `"The Weeknd - Blinding Lights"` → `artist="The Weeknd (guessed)"`, `track_title="Blinding Lights (guessed)"`.
- **D-09:** If no ` - ` separator is found in the title, there is **no artist field** — the raw video title is shown as `"(guessed) — <raw title>"` with no artist. Channel name is stored internally but NOT used as artist guess.

### Claude's Discretion
- Exact HTTP retry strategy for `SpotifyClient._get_token()` (e.g., single attempt is fine for Phase 3)
- Internal token caching TTL within `SpotifyClient` (caching is required by tests; exact TTL is Claude's call)
- Exact `yt_dlp.YoutubeDL` options dict (quiet mode, no-playlist, etc.)
- Threading model for concurrent metadata fetches (use existing `ThreadPoolExecutor` + `_Dispatcher` Signal/Slot pattern from Phase 2)
- `fetch_metadata_for_row()` function signature details (already tested in `tests/test_metadata_services.py`)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` §METADATA — META-01, META-02, META-03 (locked requirements for this phase)
- `.planning/ROADMAP.md` §Phase 3 — Phase goal and success criteria

### Existing Implementation
- `tunebridge.py` — Full source: `_Dispatcher`, `BatchTable`, `TuneBridgeApp`, `SongStatus`, `classify_url`, `_mock_worker`, `_start_demo` — Phase 3 replaces the mock worker with real metadata fetching
- `tests/test_metadata_services.py` — TDD scaffold (RED gate): 21 tests defining the exact interfaces for `SpotifyClient`, `YoutubeExtractor`, `fetch_metadata_for_row`, and `BatchTable.update_row_metadata` — **planner MUST read this before designing tasks**

### Prior Phase Context
- `.planning/phases/02-input-and-detection/02-CONTEXT.md` — Phase 2 decisions (PySide6, Signal/Slot threading pattern, `_Dispatcher` design)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_Dispatcher(QObject)` — emits `Signal(int, str)` for thread-safe row status updates; same pattern needed for metadata result delivery
- `BatchTable.update_row_status(row_id, status)` — already wired to `_Dispatcher`; Phase 3 needs a new `update_row_metadata(row_id, metadata_dict)` method
- `TuneBridgeApp._schedule(func, *args)` — queues callable on Qt main thread from any worker thread
- `ThreadPoolExecutor` with `min(batch_size, 4)` workers — already set up in `_start_demo`; Phase 3 reuses this executor for metadata fetch tasks
- `SongStatus.FETCHING_METADATA` — enum value `"Fetching metadata"` already exists; use it directly
- `TuneBridgeApp._mock_worker(row_id)` — current placeholder; Phase 3 replaces this with a real metadata worker

### Established Patterns
- Thread-safe UI updates: worker threads post results via `_Dispatcher.update.emit(row_id, status)` → Qt queued connection → main thread `_on_update(row_id, status)` — Phase 3 extends this with a metadata-specific signal or a second `_Dispatcher` for metadata dicts
- `SongStatus` enum: all status strings come from the enum — no hardcoded strings in worker threads
- `classify_url(url) -> str | None` returning `"Spotify"` or `"YouTube"` — `fetch_metadata_for_row` uses `url_type` to route to the correct service

### Integration Points
- `TuneBridgeApp._start_demo()` / `_mock_worker()` — the real metadata fetch replaces the mock sleep; same executor, same `_Dispatcher` wiring
- `BatchTable` — needs new `update_row_metadata(row_id, dict)` method (tested in `test_metadata_services.py:test_batch_table_update_row_metadata_*`)
- `.env` load must happen at `TuneBridgeApp.__init__` before `SpotifyClient` is instantiated

</code_context>

<specifics>
## Specific Ideas

- TDD test scaffold already written: `tests/test_metadata_services.py` (21 tests, all RED). Phase 3 implementation must make all 21 tests GREEN without modifying the test assertions.
- `fetch_metadata_for_row(url, url_type, spotify_client, yt_extractor)` is the tested interface — planner must implement this exact signature.
- Token caching in `SpotifyClient` is tested: `test_spotify_token_cached_second_call_no_extra_post` asserts only 1 POST for 2 token calls.
- `(guessed)` label is enforced by tests: `test_youtube_guessed_artist_carries_label` and `test_youtube_guessed_track_title_carries_label` will fail if the label is omitted.

</specifics>

<deferred>
## Deferred Ideas

- Settings dialog / UI for entering Spotify credentials (would be a new capability, Phase 6+ or standalone)
- Manual metadata editing per-row (belongs in a later UX polish phase)
- Retry button per row after failure
- Spotify playlist expansion (fetching all tracks in a playlist URL — Phase 4 scope)

</deferred>

---

*Phase: 03-metadata-services*
*Context gathered: 2026-05-13*
