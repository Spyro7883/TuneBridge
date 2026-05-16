---
phase: 4
plan: "04-04"
subsystem: download-pipeline
tags: [download, worker, executor, batch, hz-mode, retune, status-bar]
dependency_graph:
  requires:
    - "04-03"   # toolbar UI, _start_processing stub, _refresh_start_button
    - "04-02"   # _session_tmp, _temp_paths, _row_metadata, batch counters, executor
    - "04-01"   # RED gate, SongStatus.FAILED_DOWNLOAD, download_track_for_row, _download_lock
  provides:
    - "_download_worker: full Spotify/YouTube routing + 432Hz retune"
    - "_on_download_row_finished: batch counter + status bar + UI unlock"
    - "_start_processing: full batch launch (replaces stub)"
  affects:
    - "Phase 5 — folder confirmation reads _temp_paths populated here"
tech_stack:
  added: []
  patterns:
    - "_download_worker mirrors _metadata_worker exactly (closing guard → try/except → emit)"
    - "Spotify rows: ytsearch:{artist} {title} audio built from _row_metadata"
    - "YouTube rows: direct URL passthrough"
    - "432Hz branch: RETUNING emit + retune_file() + path swap"
    - "batch-scoped slot: connected in _start_processing, disconnected on completion"
    - "ThreadPoolExecutor.submit per row (serialized inside download_track_for_row via _download_lock)"
key_files:
  created: []
  modified:
    - path: "tunebridge.py"
      change: "Added _download_worker, _on_download_row_finished; replaced _start_processing stub"
decisions:
  - "_on_download_row_finished connected in _start_processing (batch-scoped), not __init__ — avoids spurious fires from prior status changes"
  - "Spotify search URL constructed as 'ytsearch:{artist} {title} audio' inside _download_worker using _row_metadata set in Wave 1"
  - "_download_lock acquired inside download_track_for_row, never in _download_worker — keeps worker body clean"
  - "retune_file called synchronously inside worker thread — no extra thread needed (retune is CPU-bound, executor handles concurrency)"
  - "_on_download_row_finished self-disconnects via try/disconnect on batch completion — no dangling connection"
metrics:
  duration: "~10 minutes"
  completed: "2026-05-16"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 1
  tests_added: 0
  tests_passing: 62
---

# Phase 4 Plan 04: Download Worker GREEN Wave Summary

One-liner: Full batch download pipeline — Spotify ytsearch + YouTube direct URL + 432Hz retune + batch counter slot — all 62 tests GREEN.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | _download_worker + _on_download_row_finished | db3196f | tunebridge.py |
| 2 | _start_processing full implementation (stub replaced) | 39fc14f | tunebridge.py |

## What Was Built

**Task 1 — _download_worker:**
- Entry closing guard (mirrors _metadata_worker)
- Emits `SongStatus.DOWNLOADING` at worker start
- Per-row uuid4 subdir under `_session_tmp` (path traversal isolation)
- Spotify routing: `ytsearch:{artist} {title} audio` from `_row_metadata`
- YouTube routing: direct URL passthrough
- Calls `download_track_for_row(search_url, row_tmp)`
- 432Hz branch: emits `RETUNING`, calls `retune_file()`, swaps downloaded path
- Success path: emits `AWAITING`, stores path in `_temp_paths[row_id]`
- Except: logs warning, emits `FAILED_DOWNLOAD` — other rows unaffected

**Task 1 — _on_download_row_finished:**
- Ignores non-terminal statuses (only reacts to AWAITING + FAILED_DOWNLOAD)
- Increments `_download_done` or `_download_failed` under `_download_lock_counter`
- Updates status bar with `Downloading {n} / {total}…` on partial progress
- On completion: shows `Done — N downloaded, M failed` + self-disconnects

**Task 2 — _start_processing:**
- Reads `hz_mode` from `_hz_group.checkedId()` before any locks
- Collects all METADATA_READY rows (url, url_type, metadata) on main thread
- Guards against empty batch (no-op return)
- Locks paste_box + all 3 toolbar buttons
- Resets batch counters, connects `_on_download_row_finished`
- Shows `Downloading 0 / N…` before submitting
- Submits one `_download_worker` per row via `_executor.submit`

## Deviations from Plan

None — plan executed exactly as written.

## Test Results

| Suite | Before | After |
|-------|--------|-------|
| test_download_pipeline.py | 3/10 (7 failing) | 10/10 GREEN |
| Full suite | 55/62 | 62/62 GREEN |

## Known Stubs

None — `_start_processing` stub fully replaced.

## Threat Surface Scan

No new network endpoints, auth paths, or file access patterns beyond those declared in the plan's `<threat_model>`. All T-4-0x mitigations implemented as specified:
- T-4-01: search_url built from classify_url-validated or structured metadata — no raw shell input
- T-4-02: uuid4 subdir under mkdtemp — no user-controlled path segments
- T-4-03: threading.Timer 600s + _closing guard in worker entry
- T-4-06: _temp_paths in-memory only, cleaned by closeEvent shutil.rmtree

## Self-Check: PASSED

- `tunebridge.py` exists and modified: FOUND
- commit db3196f: Task 1 — FOUND
- commit 39fc14f: Task 2 — FOUND
- 62 tests GREEN: CONFIRMED (62 passed in 1.36s)
- `grep -n "def _download_worker" tunebridge.py`: 1 match FOUND
- `grep -n "ytsearch:" tunebridge.py`: match inside _download_worker FOUND
- `grep -n "def _on_download_row_finished" tunebridge.py`: 1 match FOUND
- `grep -n "def _start_processing" tunebridge.py`: 1 match, no `pass` stub FOUND
