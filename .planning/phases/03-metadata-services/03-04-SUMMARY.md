---
phase: 03-metadata-services
plan: 04
subsystem: auto-fetch-executor
tags: [batch-table, auto-fetch, executor, signal-slot, ui-integration, thread-pool]
dependency_graph:
  requires: [03-01, 03-02, 03-03]
  provides: [persistent-executor, _metadata_worker, auto-fetch-wiring, closeEvent-shutdown]
  affects: [tunebridge.TuneBridgeApp.__init__, tunebridge.TuneBridgeApp._process_urls, tunebridge.TuneBridgeApp._metadata_worker, tunebridge.TuneBridgeApp.closeEvent]
tech_stack:
  added: []
  patterns: [persistent-ThreadPoolExecutor, per-row-error-isolation, D-02-fail-fast, D-03-auto-fetch, D-04-fetching-status, Qt-queued-signal]
key_files:
  created: []
  modified:
    - tunebridge.py
decisions:
  - "Executor created once in __init__ (not inside _process_urls) — avoids main-thread blocking (Research Pitfall 3)"
  - "D-02 fail-fast: Spotify rows emit 'Failed — metadata' immediately when _spotify_enabled is False — consistent with D-07 per-row error isolation, no worker submission"
  - "closeEvent calls shutdown(wait=False) — non-blocking teardown; in-flight workers complete independently"
  - "Task 1 (update_row_metadata full impl) was pre-delivered by wave 3 plan 03-03 — no code change required; deviation documented"
  - "_metadata_worker catches ALL exceptions and emits only the literal 'Failed — metadata' string — T-03-16 mitigation (no traceback/token data surfaces to UI)"
metrics:
  duration: "~15 min"
  completed: "2026-05-15"
  tasks_completed: 2
  files_changed: 1
---

# Phase 03 Plan 04: Auto-Fetch Executor and _metadata_worker Summary

One-liner: Added persistent `ThreadPoolExecutor` + `_metadata_worker` + D-02 fail-fast + auto-fetch wiring in `_process_urls` + `closeEvent` shutdown — end-to-end paste→fetch→display pipeline complete.

## What Was Built

### Task 1: BatchTable.update_row_metadata (D-05/D-06/D-09 display logic)

Pre-delivered by wave 3 plan 03-03. The full implementation was already present in `tunebridge.py` at plan start:

- Spotify track: `"Artist — Title"` (uses `"title"` key presence to distinguish track vs album)
- Spotify album: `"Artist — Album [album]"` (no `"title"` key, uses `"album"` key)
- YouTube with separator: `"Artist (guessed) — Track (guessed)"`
- YouTube without separator: `"(guessed) — <raw title (guessed)>"`
- Column 0 foreground updated to `#1DB954` (METADATA_READY color)
- Status transitions to `"Metadata ready"` via `update_row_status`

All 3 target tests (`stores_title`, `status_transitions_to_done`, `guessed_label_preserved`) were GREEN at plan start.

### Task 2: Persistent ThreadPoolExecutor, _metadata_worker, auto-fetch wiring, closeEvent

**Edit A — Persistent executor in `__init__`** (line 610):
```python
self._executor = ThreadPoolExecutor(max_workers=self._MAX_WORKERS)
```
Created once after `_Dispatcher`, before Spotify credential gating. Single instance for the app lifetime.

**Edit B — `_process_urls` auto-fetch wiring** (lines 639-661):
- `add_row` now captures the returned `row_id`
- D-02 + D-07: Spotify rows with `_spotify_enabled = False` → emit `"Failed — metadata"` immediately, no worker submitted
- D-03 + D-04: valid rows → emit `SongStatus.FETCHING.value` → `self._executor.submit(self._metadata_worker, row_id, url, url_type)`

**Edit C — `_metadata_worker` + `closeEvent`** (lines 725-746):
```python
def _metadata_worker(self, row_id, url, url_type):
    try:
        metadata = fetch_metadata_for_row(url, url_type, self._spotify_client, self._yt_extractor)
        self._dispatcher.metadata_ready.emit(row_id, metadata)
    except Exception:
        self._dispatcher.row_status_changed.emit(row_id, "Failed — metadata")

def closeEvent(self, event):
    self._executor.shutdown(wait=False)
    super().closeEvent(event)
```

Per T-03-16 mitigation: exception details are never surfaced to UI — only the literal string `"Failed — metadata"`.

## Deviations from Plan

### Pre-delivered Implementation

**1. [Context] Task 1 update_row_metadata pre-delivered by wave 3 plan 03-03**
- **Found during:** Initial file read — `update_row_metadata` was already full implementation, not the Plan 02 stub
- **Impact:** All 3 update_row_metadata tests were already GREEN at plan start; no code change required for Task 1
- **Action:** Documented as deviation; proceeded directly to Task 2 implementation

## Test Outcomes

| Suite | Count | Status |
|-------|-------|--------|
| Phase 2 (test_tunebridge.py) | 31 | GREEN |
| Phase 3 (test_metadata_services.py) | 21 | GREEN |
| **Total** | **52** | **GREEN** |

## Integration Harness Results

| Harness | Output | Status |
|---------|--------|--------|
| `OK executor + worker present` | `hasattr(w, '_executor')` and `hasattr(w, '_metadata_worker')` | PASS |
| `OK D-02 fail-fast` | Spotify row status == `'Failed — metadata'` with no credentials | PASS |
| `OK end-to-end auto-fetch` | Spotify row transitions to `'Metadata ready'` with mocked client | PASS |

## Phase 3 Success Criteria — Final Status

| Criterion | Status |
|-----------|--------|
| Pasting Spotify URL (with creds) → Fetching → Metadata ready with artist/title | SATISFIED |
| Pasting YouTube URL → Fetching → Metadata ready with title/channel; no Spotify call | SATISFIED |
| YouTube artist + track_title display `(guessed)` label inline | SATISFIED (META-03) |
| Failed fetches mark row `"Failed — metadata"` without affecting other rows (D-07) | SATISFIED |
| Spotify rows fail immediately when credentials missing (D-02) | SATISFIED |
| ThreadPoolExecutor created once, shut down on close (Pitfall 3) | SATISFIED |

## Known Stubs

None — all display paths implemented, all workers wired, executor shutdown handled.

## Threat Flags

None — no new network endpoints or trust boundaries. `_metadata_worker` catches all exceptions and emits only a literal string (T-03-16 mitigation applied).

## Self-Check: PASSED

- [x] `tunebridge.py` contains `self._executor = ThreadPoolExecutor(max_workers=self._MAX_WORKERS)` (1 occurrence)
- [x] `def _metadata_worker` exists (1 occurrence)
- [x] `def closeEvent` exists (1 occurrence)
- [x] `self._executor.submit(self._metadata_worker` wired in `_process_urls`
- [x] `self._executor.shutdown(wait=False)` in `closeEvent`
- [x] `"Failed — metadata"` appears 3 times (D-02 branch + D-07 except + _STATUS_COLORS key)
- [x] `SongStatus.FETCHING.value` emitted before submit (D-04)
- [x] 52/52 combined tests GREEN
- [x] Commit ac2c6ef exists
- [x] No STATE.md or ROADMAP.md modified
