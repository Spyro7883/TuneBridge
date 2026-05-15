# Phase 4: Download Pipeline - Context

**Gathered:** 2026-05-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Given a batch of rows with confirmed metadata ("Metadata ready"), download each URL as an audio-only MP3 via yt-dlp (Spotify rows → ytsearch, YouTube rows → direct), optionally pitch-shift to 432Hz via librosa, and hand the resulting MP3 file path to Phase 5 for folder confirmation.

**In scope:** "Start Processing" button + state machine, 440Hz/432Hz segmented control, yt-dlp subprocess integration, `_download_lock` serialization, `retune_file()` reuse from `retune_app.py`, per-row status transitions (Downloading → Retuning → Awaiting folder), system temp dir management, overall batch progress in status bar.

**Out of scope:** folder confirmation dialog (Phase 5), iBroadcast upload (Phase 6), per-row retry UI, configurable audio quality, output path picker.

</domain>

<decisions>
## Implementation Decisions

### A — Download Trigger
- **D-01:** Downloads start **manually** — user clicks "Start Processing" after verifying metadata and setting the 432Hz toggle. No auto-trigger after metadata resolves.
- **D-02:** "Start Processing" button is **enabled only when ALL rows have status "Metadata ready"**. Rows with "Failed — metadata", "Skipped — bad URL", or any in-progress status keep the button disabled.
- **D-03:** Once Start is clicked, the **batch is locked** — paste area and table modifications are disabled. No appending or editing during an active download run.

### B — 432Hz Toggle UI
- **D-04:** A **toolbar row** sits between the stat cards and the batch table. It contains two elements: the segmented control and the Start Processing button.
- **D-05:** The Hz choice is a **segmented control with two buttons**: `440Hz` (original) | `432Hz` (retune). One button is always active/highlighted. Default: `440Hz` selected.
- **D-06:** The toggle applies to the **entire batch** — not per-row. Users set it once before clicking Start.

### C — Download Concurrency
- **D-07:** yt-dlp calls are **serialized via a global `_download_lock`** (same as `retune_app.py`) to avoid Firefox cookie DB conflicts. Only one yt-dlp subprocess runs at a time.
- **D-08:** `retune_file()` (librosa pitch shift) runs **in parallel** via the existing `ThreadPoolExecutor` — retune is the slow step and has no cookie conflict risk. Workers download serially, retune concurrently.
- **D-09:** Use **`--cookies-from-browser firefox`** in all yt-dlp calls — same as `retune_app.py`. Required for age-restricted content and avoiding rate-limiting.

### D — Temp File Handling
- **D-10:** Downloaded MP3s land in a **system temp directory** (`tempfile.mkdtemp()` or a per-session subfolder). The temp path is never shown to the user in the UI.
- **D-11:** Phase 5 receives the temp file path and moves the file to the confirmed folder. Phase 4 does not clean up until Phase 5 confirms the move (or the file fails).
- **D-12:** On app close, any leftover temp files are deleted via `closeEvent`.

### E — Failure Handling
- **D-13:** If a row's download fails, its status becomes **"Failed — download"**. The error is isolated — other rows continue normally.
- **D-14:** Failed rows are **excluded from Phase 5** (folder confirmation). They do not generate a dialog and do not block the pipeline.
- **D-15:** No per-row retry in Phase 4. Retry is a Phase 4+ enhancement.

### F — Status Feedback
- **D-16:** Status bar shows **overall batch progress**: `"Downloading 2 / 5…"` while active, `"Done — 4 downloaded, 1 failed"` when complete.
- **D-17:** Per-row status column transitions: `Metadata ready` → `Downloading` → `Retuning` (if 432Hz) → `Awaiting folder` (handed to Phase 5) or `Failed — download`.

### Claude's Discretion
- Exact ytsearch query format for Spotify rows (e.g., `f"ytsearch:{artist} {title} audio"` — use artist + title from Phase 3 metadata, avoid "lyrics" keyword bias)
- yt-dlp options dict (quiet flags, `--no-playlist`, `--audio-quality 192K`, etc.)
- Per-row temp subfolder naming (e.g., `uuid4().hex[:8]` prefix as in `retune_app.py`)
- `_download_lock` scope (module-level singleton, same as `retune_app.py`)
- Exact status bar message strings beyond the patterns in D-16

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` §DOWNLOAD — DL-01, DL-02, DL-03, DL-04 (locked requirements for this phase)
- `.planning/ROADMAP.md` §Phase 4 — Phase goal and success criteria

### Existing Implementation (reuse targets)
- `retune_app.py` — **MUST read entire file**: `retune_file()`, `download_track()`, `_download_lock`, `process_one()`, `_DOWNLOAD_LOCK` serialization pattern, yt-dlp subprocess + timeout/kill pattern
- `tunebridge.py` — Full source: `_Dispatcher`, `BatchTable`, `TuneBridgeApp`, `SongStatus`, `ThreadPoolExecutor` wiring, `_metadata_worker` pattern (Phase 4 `_download_worker` mirrors this)

### Prior Phase Context
- `.planning/phases/03-metadata-services/03-CONTEXT.md` — Phase 3 decisions (Signal/Slot threading, auto-fetch wiring, per-row error isolation pattern)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `retune_file(in_path, out_path)` in `retune_app.py:43` — full librosa pitch shift + ffmpeg MP3 encode; copy verbatim into `tunebridge.py`
- `download_track(url, out_dir, on_log)` in `retune_app.py:116` — yt-dlp subprocess with `_download_lock`, timeout/kill guard, Spotify ytsearch routing; adapt search query to use Phase 3 metadata
- `_download_lock = threading.Lock()` in `retune_app.py:113` — module-level lock; replicate in `tunebridge.py`
- `_metadata_worker(row_id, url, url_type)` in `tunebridge.py` — exact pattern for `_download_worker`: submit to executor, emit signal on result, emit "Failed" on exception
- `_Dispatcher` with `row_status_changed` and `metadata_ready` signals — Phase 4 adds no new signals; reuses `row_status_changed.emit(row_id, "Downloading")` etc.
- `ThreadPoolExecutor` (persistent, `min(batch_size, 4)`) — already set up; Phase 4 submits download tasks to the same executor

### Established Patterns
- **Thread-safe UI:** worker thread → `_dispatcher.row_status_changed.emit(row_id, status)` → Qt queued connection → `BatchTable.update_row_status()` on main thread — same for all Phase 4 status updates
- **Per-row error isolation:** `try/except Exception` in worker, emit "Failed — download" on any exception, log warning — same as `_metadata_worker`
- **`SongStatus` enum:** all status strings must use enum values or match `_STATUS_COLORS` keys — no hardcoded strings in workers

### Integration Points
- `TuneBridgeApp.__init__` — add toolbar row (segmented control + Start button) between stat cards and `BatchTable`
- `BatchTable` — needs no new methods for Phase 4; reuses `update_row_status()` for all download transitions
- `SongStatus` enum — add `DOWNLOADING = "Downloading"`, `RETUNING = "Retuning"`, `AWAITING_FOLDER = "Awaiting folder"`, `FAILED_DOWNLOAD = "Failed — download"` if not already present
- `closeEvent` — extend to clean up temp files and cancel in-progress downloads (set `_closing` flag, kill any yt-dlp subprocess)

</code_context>

<specifics>
## Specific Ideas

- The segmented control (440Hz | 432Hz) should visually match the Liquid Glass aesthetic — two adjacent buttons, one highlighted with `#1DB954` accent when active
- Start Processing button: prominent, same row as the segmented control, disabled (grayed) until all rows are "Metadata ready"
- The `_download_lock` from `retune_app.py` is the critical insight — without it, concurrent Firefox cookie access causes SQLite lock errors
- ytsearch query should use both `artist` and `track_title` from Phase 3 metadata: `f"ytsearch:{artist} {title} audio"` — avoids the "lyrics" bias from `retune_app.py` and produces better audio matches

</specifics>

<deferred>
## Deferred Ideas

- Per-row retry button for failed downloads — Phase 4+ enhancement
- Configurable audio quality (192K hardcoded for now) — REQUIREMENTS.md deferred
- Stop/pause mid-batch — complex threading; not scoped for Phase 4
- Progress bar widget (determinate bar showing N/M) — status bar count is sufficient for Phase 4

</deferred>

---

*Phase: 04-download-pipeline*
*Context gathered: 2026-05-16*
