---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
last_updated: "2026-05-17T20:36:00.000Z"
last_activity: 2026-05-17 -- Phase 05 Plan 02 complete — FolderConfirmDialog + static symbols committed (c476678); 62 existing tests passing
progress:
  total_phases: 6
  completed_phases: 4
  total_plans: 20
  completed_plans: 15
  percent: 75
---

## Current Position

Phase: Phase 5 — Organization
Plan: 3 of 4 — Ready to execute
Status: executing — Plan 02 complete (Wave 1 static symbols + FolderConfirmDialog)
Last activity: 2026-05-17 -- Plan 05-02 complete: FolderConfirmDialog + _dialog_lock + SongStatus/colors/signals committed; Wave 2 (threading wiring) next

## Decisions

- Wave 0 RED-gate: 14 tests import FolderConfirmDialog/_dialog_lock — intentional ImportError until Wave 1
- Option B (dialog in isolation) for button-state tests 3/4/5; Option A (patch + window) for integration tests 7-13
- _download_lock at module level (not class level) — shared singleton across all executor threads
- _row_metadata populated via lambda connected to metadata_ready signal — no new slot method needed
- retune_file copied verbatim from retune_app.py — zero adaptation, identical behavior
- Dual input: Spotify URL and YouTube URL both supported in the same batch
- Per-song folder confirmation with last-used folder as default suggestion
- All 19 v1.0 requirements scoped into single milestone delivery
- YouTube link flow: yt-dlp info extraction for metadata (no Spotify API call)
- Spotify link flow: Spotify Web API (client credentials) → yt-dlp ytsearch → download
- Phase 1 bundles GUI shell + thread infrastructure + status state machine (PROC-01, PROC-02, GUI-01) — these are tightly coupled; no value in splitting
- Organization phase (Phase 5) owns the folder confirmation dialog with all threading.Event safety layers
- iBroadcast upload isolated in Phase 6 — independent of folder logic, can be developed and tested separately
- Phase 2 migrated from tkinter to PySide6 (Liquid Glass QSS) — framework decision locked
- StatCard Bento Grid widgets added (Valid/Invalid URL counters) — design from mockup.txt
- Toolbar row inserted after BatchTable wiring — ensures _on_clear/_on_rows_removed are set before Start button evaluates
- _start_processing stub added as pass body at Wave 2; Wave 3 replaces it with download dispatch logic
- _refresh_start_button uses self.table._table (QTableWidget inner widget) — BatchTable exposes _table as private attribute
- _on_download_row_finished connected batch-scoped in _start_processing (not __init__) — avoids spurious fires from prior status changes
- Spotify search URL built as 'ytsearch:{artist} {title} audio' inside _download_worker using _row_metadata from Phase 3
- _download_lock acquired inside download_track_for_row, never in _download_worker — worker body stays clean

## Blockers

(none)

## Todos

(none)
