---
milestone: v1.0
name: Full Pipeline
status: planning
progress:
  phases_complete: 1
  phases_total: 6
  plans_complete: 2
  plans_total: 2
---

## Current Position

Phase: Phase 2 — Input & Detection (context gathered)
Plan: —
Status: Context captured; ready for Phase 2 planning
Last activity: 2026-05-13 — Phase 2 context gathered (paste trigger: auto-on-paste; badges: row tags)

## Decisions

- Dual input: Spotify URL and YouTube URL both supported in the same batch
- Per-song folder confirmation with last-used folder as default suggestion
- All 19 v1.0 requirements scoped into single milestone delivery
- YouTube link flow: yt-dlp info extraction for metadata (no Spotify API call)
- Spotify link flow: Spotify Web API (client credentials) → yt-dlp ytsearch → download
- Phase 1 bundles GUI shell + thread infrastructure + status state machine (PROC-01, PROC-02, GUI-01) — these are tightly coupled; no value in splitting
- Organization phase (Phase 5) owns the folder confirmation dialog with all threading.Event safety layers
- iBroadcast upload isolated in Phase 6 — independent of folder logic, can be developed and tested separately

## Blockers

(none)

## Todos

- Run `/gsd-plan-phase 2` to decompose Phase 2: Input & Detection into executable plans
