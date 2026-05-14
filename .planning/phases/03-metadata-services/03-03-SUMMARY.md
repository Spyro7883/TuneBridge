---
phase: 03-metadata-services
plan: 03
subsystem: dispatcher-signal
tags: [routing, dispatcher, signal, thread-safety, spotify, youtube]
dependency_graph:
  requires: [03-01, 03-02]
  provides: [metadata_ready-signal, fetch_metadata_for_row, _SPOTIFY_RESOURCE_RE]
  affects: [tunebridge._Dispatcher, tunebridge.BatchTable, tunebridge.fetch_metadata_for_row]
tech_stack:
  added: []
  patterns: [Qt-Signal-cross-thread, client-credentials-routing, locale-aware-regex]
key_files:
  created:
    - tests/test_metadata_services.py
  modified:
    - tunebridge.py
    - tests/test_tunebridge.py
decisions:
  - "_Dispatcher.metadata_ready uses Signal(int, object) — object type allows dict payload across thread boundary without custom signal type"
  - "update_row_metadata full implementation (not stub) carried forward from master Plans 01+02 — stores artist/title label in col 0, transitions status to METADATA_READY"
  - "test_status_enum_values updated (Rule 1 auto-fix) — Phase 2 test was stale after METADATA_READY added in Plan 01"
metrics:
  duration: "~10 min"
  completed: "2026-05-15"
  tasks_completed: 2
  files_changed: 3
---

# Phase 03 Plan 03: Metadata Services Dispatcher Signal Summary

One-liner: Added `metadata_ready = Signal(int, object)` to `_Dispatcher` and synced Phase 3 Plans 01+02 code into the Plan 03 worktree, achieving 52/52 tests GREEN.

## What Was Built

### Task 1: fetch_metadata_for_row routing + _SPOTIFY_RESOURCE_RE

The worktree's `tunebridge.py` was at Phase 2 state (no SpotifyClient, YoutubeExtractor, or routing function). The complete Phase 3 code from master (Plans 01+02 already merged) was synced to the worktree:

- `SpotifyClient` — OAuth2 client credentials, token caching, `get_track_metadata`, `get_album_metadata`
- `YoutubeExtractor` — yt-dlp wrapper, `(guessed)` labeling for parsed artist/track_title
- `_SPOTIFY_RESOURCE_RE` — locale-aware regex: handles `/intl-ro/`, `/en/`, plain `/track/`, `/album/`
- `fetch_metadata_for_row(url, url_type, spotify_client, yt_extractor)` — routes by url_type, adds `source` key
- `SongStatus.METADATA_READY = "Metadata ready"` — new status enum value
- `BatchTable.update_row_metadata` — full implementation: writes artist/title label to col 0, updates status

### Task 2: _Dispatcher.metadata_ready Signal

Added the missing `metadata_ready = Signal(int, object)` to `_Dispatcher` and wired the connection:

```python
class _Dispatcher(QObject):
    row_status_changed = Signal(int, str)
    metadata_ready     = Signal(int, object)   # (row_id, metadata_dict) — crosses thread boundary

    def __init__(self, table: "BatchTable"):
        super().__init__()
        self.row_status_changed.connect(table.update_row_status)
        self.metadata_ready.connect(table.update_row_metadata)
```

The `Signal(int, object)` type allows dicts to cross thread boundaries via Qt's queued connection mechanism. Plan 04 will emit this signal from worker threads.

### Test file

`tests/test_metadata_services.py` (21 tests) was copied from master. All 21 pass:
- 3 SpotifyClient token tests
- 4 SpotifyClient metadata tests  
- 6 YoutubeExtractor tests
- 5 fetch_metadata_for_row routing tests
- 3 BatchTable.update_row_metadata tests

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated test_status_enum_values for METADATA_READY**
- **Found during:** Running tests after sync
- **Issue:** `test_tunebridge.py::test_status_enum_values` expected 9 enum values; `METADATA_READY` was added in Plan 01 making it 10
- **Fix:** Added `"Metadata ready"` to expected list with comment `# added Phase 3 — META-01` (matches master)
- **Files modified:** `tests/test_tunebridge.py`
- **Commit:** e2a8a52

**2. [Rule 3 - Blocking] Worktree behind master by 2 plans**
- **Found during:** Initial file read — worktree `tunebridge.py` was Phase 2 version
- **Issue:** Plans 01+02 were merged to master but not present in the worktree; the test file referenced `SpotifyClient`, `YoutubeExtractor`, `fetch_metadata_for_row` which didn't exist in the worktree
- **Fix:** Synced master's `tunebridge.py` (Plans 01+02) to worktree, then applied Plan 03 addition (metadata_ready Signal)
- **Files modified:** `tunebridge.py`
- **Commit:** e2a8a52

## Test Outcomes

| Suite | Count | Status |
|-------|-------|--------|
| Phase 2 (test_tunebridge.py) | 31 | GREEN |
| Phase 3 (test_metadata_services.py) | 21 | GREEN |
| **Total** | **52** | **GREEN** |

All 3 `update_row_metadata` tests pass (including `stores_title` and `guessed_label_preserved`) because the full implementation from Plan 01 was already on master — not a stub.

## Known Stubs

None — `update_row_metadata` has full implementation (label construction + status transition).

## Threat Flags

None — no new network endpoints, auth paths, or trust boundaries introduced. The `metadata_ready` Signal carries dicts internally within the process; no external surface added.

## Self-Check: PASSED

- [x] `tunebridge.py` exists and contains `metadata_ready = Signal(int, object)`
- [x] `tests/test_metadata_services.py` exists (21 tests)
- [x] Commit e2a8a52 exists
- [x] 52/52 tests GREEN
- [x] `_Dispatcher.metadata_ready.connect(table.update_row_metadata)` wired in `__init__`
- [x] `_SPOTIFY_RESOURCE_RE` handles locale prefixes (`intl-[a-z]+`)
- [x] No STATE.md or ROADMAP.md modified
