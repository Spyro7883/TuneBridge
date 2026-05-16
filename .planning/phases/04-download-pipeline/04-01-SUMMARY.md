---
phase: 4
plan: "04-01"
subsystem: download-pipeline
tags: [tdd, red-gate, tests, wave-0]
dependency_graph:
  requires: []
  provides: [tests/test_download_pipeline.py]
  affects: []
tech_stack:
  added: []
  patterns: [pytest, unittest.mock, PySide6 QApplication fixture]
key_files:
  created:
    - tests/test_download_pipeline.py
  modified: []
decisions:
  - RED gate confirmed: ImportError on _download_lock / download_track_for_row / retune_file causes all 10 tests to fail at collection
  - Test fixture pattern matches test_tunebridge.py (scope=session qapp + window fixtures)
  - All patches use tunebridge.* namespace (not defining module namespace)
metrics:
  duration: "8 minutes"
  completed: "2026-05-16"
  tasks_completed: 1
  tasks_total: 1
  files_changed: 1
---

# Phase 4 Plan 01: RED-Gate Test Scaffold Summary

Wave 0 RED-gate scaffold: 10 failing unit tests covering DL-01 through DL-04, all failing at collection via ImportError on names not yet defined in tunebridge.py.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Write 10 RED-gate tests for Phase 4 download pipeline | 6503fac | tests/test_download_pipeline.py |

## What Was Built

`tests/test_download_pipeline.py` — 222 lines, 10 test functions:

| Test | Requirement | What it verifies |
|------|-------------|-----------------|
| test_spotify_search_query_uses_artist_and_title | DL-01 | ytsearch:{artist} {title} audio format from metadata |
| test_download_worker_spotify_path_calls_ytsearch | DL-01 | Spotify path emits ytsearch URL to download_track_for_row |
| test_download_worker_youtube_path_uses_direct_url | DL-02 | YouTube path passes raw URL, no ytsearch prefix |
| test_failed_download_isolation | DL-01/02 | Failed row gets "Failed — download"; other rows unaffected |
| test_hz_toggle_default_440 | DL-03 | _btn_440 checked, _btn_432 unchecked, _hz_group.checkedId()==440 |
| test_start_button_disabled_on_mixed_status | DL-03 | _btn_start disabled when any row not METADATA_READY |
| test_start_button_enabled_all_ready | DL-03 | _btn_start enabled when all rows METADATA_READY |
| test_retune_called_on_432 | DL-04 | retune_file() called at 432Hz, not called at 440Hz |
| test_status_transitions_432hz | DL-04 | Downloading → Retuning → Awaiting folder order enforced |
| test_status_transitions_440hz | DL-02 | Downloading → Awaiting folder (no Retuning) at 440Hz |

## RED Gate Verification

```
ERROR collecting tests/test_download_pipeline.py
ImportError: cannot import name '_download_lock' from 'tunebridge'
```

Exit code: non-zero. Zero tests pass. RED gate confirmed.

Missing names that cause RED:
- `_download_lock` — not in tunebridge.py
- `download_track_for_row` — not in tunebridge.py
- `retune_file` — not in tunebridge.py
- `SongStatus.FAILED_DOWNLOAD` — not in SongStatus enum
- `TuneBridgeApp._btn_440`, `._btn_432`, `._hz_group`, `._btn_start` — not in __init__
- `TuneBridgeApp._refresh_start_button`, `._download_worker` — not defined

## Deviations from Plan

None — plan executed exactly as written.

## TDD Gate Compliance

- RED gate: CONFIRMED (test(04-01) commit 6503fac)
- GREEN gate: pending (Wave 1-3 plans)
- REFACTOR gate: pending

## Known Stubs

None — this plan produces only test code; no production stubs introduced.

## Threat Flags

None — test-only file, no new network endpoints or production surface.

## Self-Check: PASSED

- tests/test_download_pipeline.py exists: FOUND
- Commit 6503fac exists: FOUND
- 10 test function names present: CONFIRMED
- pytest exits non-zero: CONFIRMED
