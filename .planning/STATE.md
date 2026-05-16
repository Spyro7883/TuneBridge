---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
last_updated: "2026-05-16T00:00:00.000Z"
last_activity: 2026-05-16 -- Phase 04 executing (3/4 plans done); Wave 2 toolbar UI complete — toolbar_row, _btn_440/_btn_432/_hz_group/_btn_start, _refresh_start_button, 55 GREEN
progress:
  total_phases: 6
  completed_phases: 3
  total_plans: 16
  completed_plans: 12
  percent: 56
---

## Current Position

Phase: Phase 4 — Download Pipeline (executing)
Plan: 04-04 (Wave 3 — Download Worker)
Status: Executing — 3/4 plans done
Last activity: 2026-05-16 -- 04-03 complete: toolbar_row UI, QButtonGroup Hz toggle (440 default), _btn_start gate, _refresh_start_button wired to row_status_changed; 55 GREEN (3 DL-03 + 52 prior)

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
- Toolbar row inserted after BatchTable wiring — ensures _on_clear/_on_rows_removed are set before Start button evaluates
- _start_processing stub added as pass body at Wave 2; Wave 3 replaces it with download dispatch logic
- _refresh_start_button uses self.table._table (QTableWidget inner widget) — BatchTable exposes _table as private attribute

## Blockers

(none)

## Todos

(none)
