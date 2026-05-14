---
phase: 03-metadata-services
plan: "02"
subsystem: youtube-extractor
tags: [youtube, yt-dlp, title-parser, guessed-label, META-02, META-03]
dependency_graph:
  requires: [03-01]
  provides: [YoutubeExtractor.extract_metadata, TuneBridgeApp._yt_extractor-live]
  affects: [tunebridge.py]
tech_stack:
  added: []
  patterns: [yt-dlp context manager, first-separator title split (D-08), guessed-label convention (D-06)]
key_files:
  created: []
  modified: [tunebridge.py]
decisions:
  - "YoutubeExtractor already fully implemented in Plan 01 (all 6 tests were GREEN before this plan ran)"
  - "Task 2 is the only change needed: replace self._yt_extractor = None with self._yt_extractor = YoutubeExtractor()"
  - "No TDD RED/GREEN cycle needed for Task 1 — implementation already existed and tests were GREEN"
metrics:
  duration: "~5 minutes"
  completed: "2026-05-14T17:00:00Z"
  tasks_completed: 2
  files_changed: 1
---

# Phase 3 Plan 02: YoutubeExtractor and _yt_extractor Wiring Summary

YoutubeExtractor class verified GREEN for all 6 YouTube tests (already implemented in Plan 01); replaced the `self._yt_extractor = None` Plan 01 placeholder with a live `YoutubeExtractor()` instance in `TuneBridgeApp.__init__`.

## What Was Built

### YoutubeExtractor class (META-02, META-03) — verified as existing

Already present in `tunebridge.py` from Plan 01. Verified against all plan acceptance criteria:

- `_YDL_OPTS`: `{"quiet": True, "no_warnings": True, "extract_flat": False, "noplaylist": True}`
- `extract_metadata(url)`: opens `yt_dlp.YoutubeDL(_YDL_OPTS)` as context manager, calls `ydl.extract_info(url, download=False)`
- Returns `{"title": raw_title, "channel": channel}` always
- D-08: splits on FIRST `" - "` only — `raw_title.split(" - ", 1)` — keeps "(Official Video)" on track side
- D-09: no `" - "` separator → no "artist" key; `track_title = f"{raw_title} (guessed)"`
- Both `artist` and `track_title` carry `(guessed)` suffix when separator found (D-06)
- Channel falls back to `info.get("uploader", "")` when "channel" key absent
- Exceptions from `extract_info` propagate unchanged (no try/except)
- Module-level `import yt_dlp` intact — `patch("tunebridge.yt_dlp.YoutubeDL")` target works

### Task 2: _yt_extractor wiring (META-02)

Changed in `TuneBridgeApp.__init__` (line 616):

```python
# Before (Plan 01 placeholder):
self._yt_extractor = None

# After (Plan 02):
self._yt_extractor = YoutubeExtractor()
```

Instantiated unconditionally — yt-dlp requires no credentials. Spotify credential gating block unchanged.

## Test Outcomes

| Suite | Tests | Result |
|-------|-------|--------|
| Phase 2 regression (test_tunebridge.py) | 31 | GREEN |
| Phase 3 Spotify (test_metadata_services.py) | 7 | GREEN |
| Phase 3 YouTube (test_metadata_services.py) | 6 | GREEN |
| Phase 3 fetch_metadata routing (test_metadata_services.py) | 5 | GREEN |
| Phase 3 BatchTable.update_row_metadata (test_metadata_services.py) | 3 | GREEN |
| **Total** | **52** | **GREEN** |

YouTube tests verified (6/6):
- `test_youtube_extract_returns_title` — raw title from yt-dlp info dict
- `test_youtube_extract_returns_channel` — channel/uploader fallback
- `test_youtube_extract_does_not_download` — `download=False` passed to extract_info
- `test_youtube_guessed_artist_carries_label` — " (guessed)" suffix on artist field
- `test_youtube_guessed_track_title_carries_label` — " (guessed)" suffix on track_title
- `test_youtube_extract_error_raises` — exceptions propagate (no silent None)

## Acceptance Criteria Verification

| Criterion | Result |
|-----------|--------|
| `grep -nE '^class YoutubeExtractor' tunebridge.py` = 1 line | PASS (line 227) |
| `grep -nE 'def extract_metadata\b' tunebridge.py` = 1 line | PASS (line 241) |
| `grep -nE 'download=False' tunebridge.py` = 1 line | PASS (line 243) |
| `grep -nE 'split\(" - ", 1\)' tunebridge.py` = 1 line | PASS (line 250) |
| `grep -c '(guessed)' tunebridge.py` >= 3 | PASS (5 occurrences) |
| `grep -v '^#' ... grep -c 'from yt_dlp import'` = 0 | PASS (0) |
| `grep -c '^import yt_dlp$' tunebridge.py` = 1 | PASS |
| `self._yt_extractor = YoutubeExtractor()` present (1 line) | PASS (line 616) |
| `self._yt_extractor = None` absent (0 lines) | PASS |
| Python harness `isinstance(w._yt_extractor, YoutubeExtractor)` exits 0 | PASS |

## Deviations from Plan

### Task 1 already complete — no TDD cycle needed

**Observation:** Plan 01 implemented the full YoutubeExtractor class (including all D-08/D-09 title parsing and guessed-label logic) because the test file imports all four names at module level. All 6 YouTube tests were GREEN before this plan executed.

**Action:** Verified all acceptance criteria pass. No code changes made for Task 1.

**Task 2 commit:** `1723be5`

## Known Stubs

None — `_yt_extractor` is now a live `YoutubeExtractor()` instance. No placeholder stubs remain for Plans 01-02 scope.

## Threat Flags

None — no new network endpoints or trust boundaries introduced beyond those documented in Plan 01. T-03-06 through T-03-10 remain as documented in the plan's threat model.

## Self-Check: PASSED

Files verified:
- `tunebridge.py` — contains `class YoutubeExtractor` (line 227), `def extract_metadata` (line 241), `self._yt_extractor = YoutubeExtractor()` (line 616)

Commits verified:
- `1723be5` — Task 2: replace _yt_extractor placeholder with live YoutubeExtractor instance

Test results: 52 passed, 0 failed
