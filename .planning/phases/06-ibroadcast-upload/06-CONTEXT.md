# Phase 6: iBroadcast Upload - Context

**Gathered:** 2026-05-19
**Status:** Ready for planning

<domain>
## Phase Boundary

After each song is saved to disk (reaching `SongStatus.UPLOADING`), automatically upload it to iBroadcast using stored username/password credentials. Before uploading, check the user's iBroadcast library for the track — skip upload if already present. Rows that upload successfully transition to `Done`; duplicates show `Already uploaded`; failures show `Failed — upload`. Upload starts in batch after `folder_batch_done` fires. UI unlocks when all uploads complete.

**In scope:** iBroadcast auth (token per batch), library duplicate check (title+artist), parallel upload workers, `SongStatus.ALREADY_UPLOADED` and `SongStatus.FAILED_UPLOAD` states, status bar summary, `_start_upload_batch` slot, `upload_batch_done` signal, `.env.example` additions, `_unlock_ui` trigger migration.

**Out of scope:** Playlist assignment on iBroadcast (v1.1), retry UI for failed uploads, per-row upload progress percentage, any upload for rows in `SKIPPED` or `FAILED_SAVE` or `FAILED_DOWNLOAD` status, iBroadcast tag editing after upload.

</domain>

<decisions>
## Implementation Decisions

### A — Credential Handling
- **D-01:** Credentials stored in `.env` file as `IBROADCAST_USERNAME` and `IBROADCAST_PASSWORD`. Both keys added to `.env.example`. Loaded at startup via `python-dotenv` — mirrors existing Spotify credential pattern.
- **D-02:** Missing credentials at startup → show one-time status bar warning: `"iBroadcast credentials not configured — upload will be skipped"`. Upload workers skip HTTP calls; each `UPLOADING` row transitions directly to `Done` (file is saved; upload step is a no-op). No startup error dialog.
- **D-03:** Auth failure during batch (wrong password, network error) → do NOT block or show a modal dialog. Mark every `UPLOADING` row as `"Failed — upload"`. Other pipeline operations are unaffected.
- **D-04:** Auth token obtained **once per batch** — login when `folder_batch_done` fires and before any upload workers are submitted. Token held in memory for that batch only; discarded after batch completes.

### B — Duplicate Detection
- **D-05:** Duplicate check: compare track title **and** artist against the user's iBroadcast library, **case-insensitive exact match** (both fields must match). Performed before each upload attempt.
- **D-06:** If the iBroadcast library fetch fails (network error, timeout, API error) → proceed with the upload anyway. Worst case is a duplicate on iBroadcast, which iBroadcast handles gracefully.
- **D-07:** Track already exists on iBroadcast → row transitions to new `SongStatus.ALREADY_UPLOADED = "Already uploaded"`. Distinct status color (not red, not the same green as Done — Claude's discretion for exact color; muted teal suggested).
- **D-08:** Artist source for duplicate check: use whatever artist is in `_row_metadata[row_id]` including `"(guessed)"` artist from YouTube rows. No special fallback — consistent across Spotify and YouTube rows.

### C — Upload Trigger and Timing
- **D-09:** `_dispatcher.folder_batch_done` connects to new `_start_upload_batch` slot — **replaces** the Phase 5 direct `_dispatcher.folder_batch_done.connect(self._unlock_ui)` wire (tunebridge.py line 1153). Phase 6 calls `_unlock_ui` after upload batch completes instead.
- **D-10:** Parallel uploads: each `UPLOADING` row is submitted to the existing `ThreadPoolExecutor` as a `_upload_worker(row_id, token, library)` call. Mirrors `_download_worker` and `_folder_worker` patterns.
- **D-11:** Status bar during upload shows `"Uploading X of N…"` (updated as each row completes). On batch complete: `"Done — {uploaded} uploaded, {existed} already existed, {failed} failed"`.
- **D-12:** UI unlocked (paste area, Hz buttons re-enabled) by `_unlock_ui()` call at the end of `_on_upload_row_finished` when the batch counter reaches total. Mirrors Phase 5's `_unlock_ui` trigger migration from folder → upload.
- **D-13:** Empty batch guard: if `_saved_paths` is empty when `folder_batch_done` fires (all rows were skipped or failed before saving), skip auth and upload entirely — call `_unlock_ui()` immediately.

### D — Upload Failure Behavior
- **D-14:** Upload failure → `SongStatus.FAILED_UPLOAD = "Failed — upload"`. Add `"Failed — upload": QColor("#EF4444")` to `_STATUS_COLORS`. Same red as `FAILED_SAVE` — consistent failure palette.
- **D-15:** No automatic retry. Upload failure is a **permanent terminal state** for the row. Consistent with `FAILED_DOWNLOAD` and `FAILED_SAVE` behavior from prior phases.
- **D-16:** Per-row isolation: one upload failure does not affect other rows' upload workers. Each `_upload_worker` handles its own exception independently.
- **D-17:** Python `logging.getLogger(__name__).warning(...)` for upload errors — same as save and download workers. No UI tooltip or modal dialog for individual upload failures.

### Claude's Discretion
- Exact color for `"Already uploaded"` status (muted teal `#14B8A6` suggested as distinct from Done's green and Failed's red)
- HTTP library for iBroadcast API calls: `requests` with `verify=False` (required for SSL proxy on this machine) or `urllib` — whichever matches the iBroadcast API's auth/upload flow better
- iBroadcast API endpoint details: token auth URL, library list URL, upload URL (reverse-engineer from pyibroadcast or ibroadcast-uploader package if it exists, or raw API)
- Signal name for upload batch completion (suggested: `upload_batch_done = Signal()` in `_Dispatcher`)
- Counter vars for upload tracking (suggested: `_upload_total`, `_upload_done`, `_upload_existed`, `_upload_failed` on `TuneBridgeApp`)
- Status transition for `UPLOADING` rows when credentials are missing at startup (suggested: emit `Done` via the standard `row_status_changed` signal)
- Lock strategy for reading `_saved_paths` and `_row_metadata` in upload workers (likely safe — upload phase starts after folder phase fully completes, but review if needed)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` §UPLOAD — UPL-01, UPL-02 (2 locked requirements for this phase)
- `.planning/ROADMAP.md` §Phase 6 — Phase goal and 3 success criteria

### Existing Implementation (primary read targets)
- `tunebridge.py` — **MUST read entire file before planning**:
  - `SongStatus` enum (lines 426–437) — add `ALREADY_UPLOADED` and `FAILED_UPLOAD` values
  - `_Dispatcher` class (lines 462–475) — add `upload_batch_done = Signal()`
  - `_STATUS_COLORS` dict — add entries for new statuses
  - `TuneBridgeApp.__init__` (lines 1100+) — add upload counter vars, reconnect `folder_batch_done` to `_start_upload_batch`
  - Line 1153: `self._dispatcher.folder_batch_done.connect(self._unlock_ui)` — **Phase 6 replaces this** with `_start_upload_batch`
  - `_folder_worker` pattern (lines 1340–1380) — exact template for `_upload_worker` structure
  - `_on_folder_row_finished` (lines 1383–1415) — exact template for `_on_upload_row_finished` batch counter
  - `_saved_paths: dict[int, Path]` (line 1137) — Phase 6 reads this for file paths
  - `_row_metadata: dict` — Phase 6 reads title + artist for duplicate check
  - `_unlock_ui` (lines 1454–1459) — called by Phase 6's upload batch completion

### Phase 5 Handoff
- `.planning/phases/05-organization/05-CONTEXT.md` — D-07: only `UPLOADING` rows upload; D-09: `_saved_paths[row_id]` is the file path; D-11: `folder_batch_done` is the trigger

### Platform Constraints
- `.planning/.continue-here.md` §BLOCKING CONSTRAINTS — Windows SSL proxy requires `verify=False` (or `--no-check-certificate` for subprocesses); `PYTHONUTF8=1` for subprocess encoding. **iBroadcast HTTP calls via `requests` must pass `verify=False`.**

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `self._saved_paths: dict[int, Path]` (tunebridge.py:1137) — Phase 5 populates this; Phase 6 reads `_saved_paths[row_id]` to get the final MP3 path for each `UPLOADING` row
- `self._row_metadata: dict[int, dict]` — contains `artist`, `title` fields (from Spotify or "(guessed)" from YouTube); Phase 6 reads these for duplicate check
- `_folder_worker` / `_on_folder_row_finished` — exact pattern to replicate for `_upload_worker` / `_on_upload_row_finished`
- `_download_lock = threading.Lock()` and `_dialog_lock = threading.Lock()` module-level lock patterns — follow same for any shared upload state if needed
- `ThreadPoolExecutor` already instantiated on `TuneBridgeApp` — reuse for upload workers (same as Phase 4 download workers and Phase 5 folder workers)
- `_unlock_ui` slot (line 1454) — call at end of upload batch completion

### Established Patterns
- **Thread-safe status updates:** worker → `_dispatcher.row_status_changed.emit(row_id, status.value)` → Qt queued → `BatchTable.update_row_status()` on main thread. All Phase 6 status transitions use this path.
- **Batch counter pattern:** `_upload_total` set at `_start_upload_batch`; `_upload_done / _existed / _failed` incremented in `_on_upload_row_finished`; when total reached → emit signal + update status bar + `_unlock_ui()`
- **Per-row error isolation:** `try/except Exception` in worker body, emit failure status on any exception, log warning
- **`.env` loading:** `python-dotenv` already used for Spotify credentials — same pattern for iBroadcast

### Integration Points
- Line 1153: `folder_batch_done.connect(self._unlock_ui)` → **replace** with `folder_batch_done.connect(self._start_upload_batch)`
- `_Dispatcher` class: add `upload_batch_done = Signal()`
- `SongStatus` enum: add `ALREADY_UPLOADED = "Already uploaded"`, `FAILED_UPLOAD = "Failed — upload"`
- `_STATUS_COLORS`: add entries for both new statuses
- `TuneBridgeApp.__init__`: add upload counter vars + connect `upload_batch_done → _unlock_ui`
- `.env.example`: add `IBROADCAST_USERNAME=` and `IBROADCAST_PASSWORD=`

</code_context>

<specifics>
## Specific Ideas

- `IBROADCAST_USERNAME` and `IBROADCAST_PASSWORD` as the exact env var names — consistent with `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET` naming convention
- Status bar warning at startup (credentials missing): `"iBroadcast credentials not configured — upload will be skipped"` — one-time message, shown after app initializes
- Status bar during upload: `"Uploading X of N…"` → `"Done — X uploaded, Y already existed, Z failed"` — mirrors Phase 4's `"Downloaded X, failed Y"` pattern exactly
- `_upload_worker(row_id, token, library)` receives the auth token and fetched library as arguments (passed from `_start_upload_batch` before submitting workers) — avoids each worker doing its own auth call

</specifics>

<deferred>
## Deferred Ideas

- **iBroadcast playlist assignment** — assign uploaded track to a specific playlist after upload. Deferred to v1.1 per REQUIREMENTS.md §Future Requirements.
- **Retry UI for failed uploads** — a "Retry Failed" button post-batch. Not scoped for v1.0; user re-runs batch if needed.
- **Per-row upload progress percentage** — requires iBroadcast API progress callback support; not guaranteed. Deferred.
- **Cross-session upload history** — remembering which tracks were uploaded in past sessions to skip redundant duplicate checks. Deferred.

</deferred>

---

*Phase: 06-ibroadcast-upload*
*Context gathered: 2026-05-19*
