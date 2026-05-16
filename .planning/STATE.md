---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
last_updated: "2026-05-16T00:00:00.000Z"
last_activity: 2026-05-16 -- Phase 04 executing (2/4 plans done); Wave 1 core infra complete — retune_file, download_track_for_row, _download_lock, _row_metadata gap fix
progress:
  total_phases: 6
  completed_phases: 3
  total_plans: 16
  completed_plans: 11
  percent: 50
---

## Current Position

Phase: Phase 4 — Download Pipeline (executing)
Plan: 04-03 (Wave 2 — Toolbar UI)
Status: Executing — 2/4 plans done
Last activity: 2026-05-16 -- 04-02 complete: retune_file, download_track_for_row, _download_lock, SongStatus.FAILED_DOWNLOAD, _row_metadata gap fix, _session_tmp lifecycle all added; 52/52 prior tests GREEN

## Decisions

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

## Blockers

(none)

## Todos

(none)
