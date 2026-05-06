# TuneBridge — Research Summary (v1.0 New Features)

**Date:** 2026-05-06
**Synthesized from:** STACK.md, FEATURES.md, ARCHITECTURE.md (§New Feature Integration), PITFALLS.md

---

## Stack Additions

**Zero new pip dependencies.** yt-dlp already supports everything needed:
- `--dump-json --skip-download` for YouTube metadata extraction
- Direct URL download vs ytsearch is one argument change
- `json` (stdlib) to parse `--dump-json` output

Add `requirements.txt` with pinned minimums (`yt-dlp>=2024.1.0`, `librosa`, `soundfile`, etc.) — none exist yet.

---

## Feature Table Stakes

Features that must ship — missing any feels like a bug:

| Feature | Reference |
|---------|-----------|
| Auto-detect URL type per row (Spotify vs YouTube) | spotdl v4, yt-dlp — standard behavior |
| Inline error on bad URL (not modal, not abort) | Universal in batch tools |
| Show proposed folder before confirmation | beets import — user can't validate unseen path |
| Skip individual song without canceling batch | Universal in batch tools |
| Strip YouTube title noise (`(Official Video)`, etc.) | Raw title in filename = amateur output |
| Last-used folder memory within session | Every OS file picker does this |
| "(guessed)" label on inferred artist/title from YouTube | Honest UX — user knows what's inferred |

---

## Architecture Decisions

**URL classification in PipelineController** (not services) — single `_classify_url()` method before any thread starts.

**`SongMetadata` dataclass** (`pipeline/models.py`) — unified across both sources. Optional fields for source-specific data:
- Spotify → fills `album`, `release_type`, `track_number`, `search_query`
- YouTube → fills `youtube_url`, `duration_seconds`; leaves album/release_type `None`

**YouTubeService** splits into 3 methods:
- `extract_info(url)` — `--dump-json` only, no lock needed
- `search_and_download(metadata, out_dir)` — Spotify path, holds `_download_lock`
- `download_direct(url, out_dir)` — YouTube path, holds `_download_lock`

**StorageService** adds session-only `_last_used_folder` — updated on every `save()`, suggested as default for next song. No persistence needed for v1.0.

**SongState enum: no changes.** `FETCHING_METADATA` covers both SpotifyService and YouTubeService.extract_info. Existing states cover the full pipeline for both paths.

---

## Watch Out For

### #1: threading.Event deadlock (batch silently stalls)

Worker blocks on `confirm_event.wait()`. If dialog closes without setting event, that thread slot is gone forever. With 4 workers, 4 bad closes = total stall.

**Required mitigations (all three):**
1. `event.wait(timeout=300)` — timeout unblocks after 5 minutes
2. `WM_DELETE_WINDOW` handler always calls `event.set()` with `cancelled=True`
3. `try/finally` in dialog spawner sets event even on creation exception

### #2: _poll_queue loop stops (all workers starve)

If `_handle_event` raises an exception, `self.after(50, _poll_queue)` is never scheduled. Workers blocked on `confirm_event.wait()` wait forever.

**Required:** Wrap `_poll_queue` body in `try/finally` so `self.after()` always re-schedules.

### #3: URL validation before threading

Unknown URL type failing inside a worker = cryptic error. Validate all URLs synchronously on the main thread before submitting any futures. Per-row error state only.

### #4: yt-dlp fields are all nullable

`uploader`, `channel`, `artist`, `album` can all be `None` or absent. Use a single `extract_track_meta(info)` function with `.get()` fallbacks everywhere. Never `info['field']` directly.

### #5: Dialog stacking

Multiple workers reaching `AWAITING_FOLDER` simultaneously causes overlapping modals. Enforce one dialog at a time: flag + re-queue deferred `confirm_folder` events in `_poll_queue`.

### #6: Spotify path — use Spotify metadata for folder proposal, not yt-dlp

For Spotify-routed songs, yt-dlp `uploader` is the YouTube channel ("VEVO", "Topic"), not the artist. Only use yt-dlp info for folder proposal on direct YouTube URLs.

---

## Build Order Recommendation

1. `pipeline/models.py` — `SongMetadata` dataclass (dependency for all services)
2. `services/youtube_service.py` — `extract_info()` + `download_direct()` + `search_and_download()` refactor
3. `pipeline/controller.py` — `_classify_url()` + dual-path `_process_song()` dispatch
4. `services/storage_service.py` — `_last_used_folder` session state + `propose_folder()` priority
5. `ui/folder_confirm.py` — dialog with all threading.Event safety layers
6. `services/spotify_service.py` — Spotify Web API client credentials (metadata only)
7. `services/ibroadcast_service.py` — auth + duplicate check + upload
8. `app.py` + `ui/batch_panel.py` — main window wiring

---

*Research synthesis: 2026-05-06*
