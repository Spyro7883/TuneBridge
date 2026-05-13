---
milestone: v1.0
name: Full Pipeline
status: planning
progress:
  phases_complete: 2
  phases_total: 6
  plans_complete: 4
  plans_total: 4
---

## Current Position

Phase: Phase 3 — Metadata Services (not started)
Plan: —
Status: Phase 2 complete — ready to discuss/plan Phase 3
Last activity: 2026-05-13 — Phase 2 complete: PySide6 + classify_url + PasteTextEdit + StatCard — 31/31 tests GREEN, 10/10 verified

## Decisions

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
