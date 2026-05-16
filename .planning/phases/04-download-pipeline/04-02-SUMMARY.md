---
phase: 4
plan: "04-02"
subsystem: download-infrastructure
tags: [yt-dlp, librosa, threading, retune, download, enum, tempfile]
dependency_graph:
  requires: ["04-01"]
  provides: ["retune_file", "download_track_for_row", "_download_lock", "SongStatus.FAILED_DOWNLOAD", "_row_metadata", "_session_tmp"]
  affects: ["tunebridge.py", "tests/test_tunebridge.py"]
tech_stack:
  added: [librosa, numpy, soundfile, mutagen (optional tag preservation)]
  patterns: [module-level threading.Lock singleton, subprocess.Popen with 600s timer, tempfile.mkdtemp lifecycle, Qt signal lambda setitem]
key_files:
  created: []
  modified:
    - tunebridge.py
    - tests/test_tunebridge.py
decisions:
  - "retune_file copied verbatim from retune_app.py — no adaptation needed"
  - "_download_lock placed at module level (not class level) — shared singleton across all worker threads"
  - "_row_metadata populated via lambda connected to metadata_ready signal — simpler than new slot method"
  - "test_status_enum_values updated to include FAILED_DOWNLOAD (Rule 1 deviation — test tracks production enum)"
metrics:
  duration_seconds: 335
  completed_date: "2026-05-16"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 2
---

# Phase 4 Plan 02: Core Download Infrastructure Summary

Port retune_file() verbatim from retune_app.py, add download_track_for_row() with _download_lock serialization, SongStatus.FAILED_DOWNLOAD enum value, and _row_metadata gap fix so Phase 3 metadata is accessible to the download worker.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add imports, _download_lock, retune constants, retune_file, download_track_for_row, SongStatus.FAILED_DOWNLOAD | b459c4c | tunebridge.py |
| 2 | Fix _row_metadata gap + TuneBridgeApp.__init__ Phase 4 state + extend closeEvent | 6662eb8 | tunebridge.py, tests/test_tunebridge.py |

## Verification

- `from tunebridge import retune_file, download_track_for_row, _download_lock, SongStatus` — PASSED
- `SongStatus.FAILED_DOWNLOAD.value == "Failed — download"` — PASSED
- `TuneBridgeApp.__init__` sets `_row_metadata`, `_session_tmp`, `_temp_paths` — PASSED
- `metadata_ready` signal populates `_row_metadata` via lambda — PASSED (functional test confirmed)
- 52 prior tests GREEN — PASSED
- 10 download pipeline tests still FAIL (correct: `_download_worker`/`_btn_440` not yet added — Wave 2/3)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] test_status_enum_values expected list missing FAILED_DOWNLOAD**
- **Found during:** Task 2 regression check
- **Issue:** `test_status_enum_values` in `tests/test_tunebridge.py` had a hardcoded expected list of 10 enum values that did not include `FAILED_DOWNLOAD`. Adding the new enum member caused the assertion to fail.
- **Fix:** Added `"Failed — download"` to the expected list with a Phase 4 comment
- **Files modified:** `tests/test_tunebridge.py`
- **Commit:** 6662eb8

## Known Stubs

None — no UI wiring or stub data paths in this wave. Functions are complete and testable.

## Threat Flags

None — no new network endpoints or trust boundaries introduced. All subprocess calls use list args (shell=False). `tempfile.mkdtemp()` uses OS-restricted temp dir. `_download_lock` serializes yt-dlp correctly.

## Self-Check: PASSED

- `tunebridge.py` exists and contains all required additions
- Commits b459c4c and 6662eb8 verified in git log
- 52/52 prior tests GREEN, 10/10 download pipeline tests failing for correct reasons (not ImportError)
