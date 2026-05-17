# Phase 5: Organization - Context

**Gathered:** 2026-05-17
**Status:** Ready for planning

<domain>
## Phase Boundary

For each downloaded song that reaches "Awaiting folder" status, present a modal folder confirmation dialog (one at a time, serialized via `_dialog_lock`) showing the last confirmed folder as the default. User can confirm, type a different path, browse to a folder, or skip. On confirm: move the temp MP3 to the selected folder, update status to `UPLOADING`, store the final path for Phase 6. On skip: delete temp file, mark row `SKIPPED`. On app close while dialogs are pending: unblock all waiting workers with a skip sentinel.

**In scope:** `FolderConfirmDialog` QDialog, `_dialog_lock` (module-level), `folder_requested` + `folder_batch_done` signals in `_Dispatcher`, `_folder_worker` that blocks on `threading.Event`, `_last_folder` session state, `SongStatus.SKIPPED`, `"Failed — save"` status, `_saved_paths` dict, batch completion counter + status bar summary, `closeEvent` extension.

**Out of scope:** Folder creation, renaming, or deletion; metadata-derived sub-path auto-generation (Artist/Album); cross-session folder persistence; per-row retry for failed saves; iBroadcast upload (Phase 6).

</domain>

<decisions>
## Implementation Decisions

### A — Dialog Queue Architecture
- **D-01:** `_dialog_lock = threading.Lock()` at **module level** — mirrors `_download_lock` pattern. Serializes dialog access so exactly one folder confirmation dialog is visible at a time, regardless of how many workers reach `AWAITING` concurrently.
- **D-02:** Each `_folder_worker` acquires `_dialog_lock`, then stores its `threading.Event` in `self._folder_events[row_id]`, then emits `_dispatcher.folder_requested(row_id)`. The worker then blocks on `event.wait()` until the main thread sets it.
- **D-03:** Main thread slot connected to `folder_requested(row_id)` retrieves the event from `_folder_events[row_id]`, shows `FolderConfirmDialog`, stores the result (confirmed `Path` or skip sentinel) in `self._folder_results[row_id]`, then calls `event.set()`. Worker unblocks, reads result, acts on it, releases `_dialog_lock`.
- **D-04:** `closeEvent` iterates `self._folder_events` and calls `event.set()` with a skip sentinel (`None`) for any unresolved events — ensures no worker threads hang when the app closes.

### B — Skip Behavior
- **D-05:** New `SongStatus.SKIPPED = "Skipped — folder"` added to the `SongStatus` enum. Add `"Skipped — folder": QColor("#B3B3B3")` to `_STATUS_COLORS`. Clearly distinct from `Failed` (unintentional) and `Done` (saved successfully).
- **D-06:** On skip, the temp MP3 is deleted immediately via `Path(temp_path).unlink(missing_ok=True)`. No orphan temp files left during long sessions with many skips.
- **D-07:** Skipped rows are excluded from Phase 6 (iBroadcast upload). Phase 6 only processes rows in `UPLOADING` status.
- **D-08:** When all folder dialogs resolve, status bar shows `"Saved X, skipped Y, failed Z"` — mirrors Phase 4's `"Done — X downloaded, Y failed"` summary pattern.

### C — Phase 5→6 Handoff
- **D-09:** After `shutil.move(temp_path, dest_folder)` succeeds: row transitions `SAVING → UPLOADING`. Final saved path stored in `self._saved_paths[row_id] = final_path`. Phase 6 reads `_saved_paths` for each `UPLOADING` row.
- **D-10:** On `OSError` during `shutil.move`: row transitions to `"Failed — save"` (use `SongStatus.FAILED` with label `"Failed — save"`; add color `QColor("#EF4444")` matching other failure states). Error is isolated per row — other dialogs continue.
- **D-11:** When the last folder dialog resolves (saved + skipped + failed == total rows that reached `AWAITING`), emit `_dispatcher.folder_batch_done()`. Phase 6 connects to this signal to start upload processing.

### D — Folder Proposal
- **D-12:** Proposed path = `self._last_folder` (last confirmed folder, `Path | None`). No metadata-derived sub-path is appended — user confirmed a full folder path last time, so it's the best default for the next song.
- **D-13:** First song in batch (no `_last_folder` yet): dialog text field starts **empty**. User must type or use Browse. No wrong guess to correct.
- **D-14:** `self._last_folder` is **in-session only** — not persisted to disk on exit. Cross-session persistence deferred to v1.1 per REQUIREMENTS.md.
- **D-15:** `FolderConfirmDialog` is a **modal `QDialog`** parented to `TuneBridgeApp` (centers on main window). Layout: song title label at top → path `QLineEdit` (pre-filled or empty) → Browse `QPushButton` → row of Confirm `QPushButton` + Skip `QPushButton`.
- **D-16:** **Confirm button is disabled** (`setEnabled(False)`) if `Path(line_edit.text()).is_dir()` is `False`. Inline error label: `"Folder not found — select an existing folder."` Updates live as user types (connect `textChanged` signal).
- **D-17:** Browse button calls `QFileDialog.getExistingDirectory(self, "Select folder", str(self._last_folder or Path.home()))` — opens at the last confirmed folder (or home directory if none).

### Claude's Discretion
- Exact signal name in `_Dispatcher` (suggested: `folder_requested = Signal(int)`, `folder_batch_done = Signal()`)
- Skip sentinel value in `_folder_results` (suggested: `None` — unambiguous since valid results are `Path` objects)
- Dialog styling (button colors, spacing, fonts) consistent with existing Liquid Glass QSS theme
- `_folder_events: dict[int, threading.Event]` and `_folder_results: dict[int, Path | None]` — initialization in `__init__`, locking on writes (mirror `_temp_paths_lock` pattern if needed)
- Whether `_folder_worker` is submitted to the existing `ThreadPoolExecutor` (after `_download_worker` completes) or runs in the same worker continuation
- Exact `"Failed — save"` label in `SongStatus` enum (may reuse `FAILED` with a distinct string value)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` §ORGANIZATION — ORG-01, ORG-02, ORG-03, ORG-04 (4 locked requirements for this phase)
- `.planning/ROADMAP.md` §Phase 5 — Phase goal and 5 success criteria

### Existing Implementation (primary read targets)
- `tunebridge.py` — **MUST read entire file**: `SongStatus` enum (lines 312–323), `_Dispatcher` class (signals), `TuneBridgeApp.__init__` (instance vars to extend), `_download_worker` (pattern for `_folder_worker`), `_on_download_row_finished` (pattern for `_on_folder_row_finished`), `closeEvent` (lines 1100+, extend to set pending Events), `_temp_paths`/`_temp_paths_lock` (Phase 5 reads these), `_STATUS_COLORS` dict (add new status colors)
- `retune_app.py` — `_download_lock = threading.Lock()` module-level lock pattern (lines 113–114); mirror exactly for `_dialog_lock`

### Prior Phase Context
- `.planning/phases/04-download-pipeline/04-CONTEXT.md` — Phase 4 decisions: D-11 (`_temp_paths` handoff), `_download_lock` pattern, `AWAITING` status wiring, `_on_download_row_finished` batch tracker

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `self._temp_paths: dict[int, Path]` (`tunebridge.py:851`) — Phase 4 populates this; Phase 5 reads `_temp_paths[row_id]` to get the temp MP3 for each AWAITING row
- `self._temp_paths_lock = threading.Lock()` (`tunebridge.py:857`) — pattern for any new per-row dict that gets written from worker threads
- `_download_lock = threading.Lock()` at module level (`retune_app.py:113`) — copy this pattern exactly for `_dialog_lock`
- `_metadata_worker` / `_download_worker` in `tunebridge.py` — exact pattern for `_folder_worker`: acquire lock, emit signal, wait on Event, read result, update status
- `_on_download_row_finished` slot (`tunebridge.py:1003`) — batch completion counter pattern; mirror for `_on_folder_row_finished`
- `shutil` already imported at `tunebridge.py:9` — `shutil.move` available immediately

### Established Patterns
- **Thread-safe UI:** worker thread → `_dispatcher.row_status_changed.emit(row_id, status)` → Qt queued connection → `BatchTable.update_row_status()` on main thread. All Phase 5 status updates use this same path.
- **Per-row error isolation:** `try/except Exception` in worker body, emit failure status on any exception, log warning
- **Module-level lock:** `_download_lock = threading.Lock()` — replicate for `_dialog_lock`

### Integration Points
- `_Dispatcher` class — add `folder_requested = Signal(int)` and `folder_batch_done = Signal()`
- `SongStatus` enum — add `SKIPPED = "Skipped — folder"` (and a `FAILED_SAVE` or string variant for save failures)
- `_STATUS_COLORS` dict — add entries for `"Skipped — folder"` (gray `#B3B3B3`) and `"Failed — save"` (red `#EF4444`)
- `TuneBridgeApp.__init__` — add: `_last_folder: Path | None = None`, `_folder_events: dict[int, threading.Event] = {}`, `_folder_results: dict[int, Path | None] = {}`, `_saved_paths: dict[int, Path] = {}`, `_folder_done = 0`, `_folder_skipped = 0`, `_folder_failed = 0`
- Connect `_dispatcher.folder_requested` → `_show_folder_dialog` slot (runs on main thread via Qt queued connection)
- `closeEvent` (`tunebridge.py:1105`) — extend: after existing temp cleanup, iterate `_folder_events` and call `event.set()` with `None` sentinel for unresolved events
- `_on_download_row_finished` — when a row reaches `AWAITING`, submit `_folder_worker(row_id)` to the executor (or chain directly in `_download_worker` after status emit)

</code_context>

<specifics>
## Specific Ideas

- `_dialog_lock` at module level is the critical architectural decision — without it, concurrent workers could each trigger a dialog simultaneously, violating Success Criteria 5
- The `threading.Event` pattern (worker blocks, main thread shows dialog, sets event) is simpler than a queue-drain approach and matches the ROADMAP's "threading.Event safety" language exactly
- `FolderConfirmDialog.Confirm` button validation: wire `QLineEdit.textChanged` to re-evaluate `Path(text).is_dir()` live — user gets immediate feedback as they type
- Browse button start directory: `str(self._last_folder or Path.home())` — opens near the likely target after the first song is confirmed

</specifics>

<deferred>
## Deferred Ideas

- **Cross-session folder persistence** (`~/.tunebridge_state.json`) — already deferred to v1.1 in REQUIREMENTS.md; `_last_folder` is in-session only for Phase 5
- **Metadata-derived sub-path proposal** (e.g., `Artist_432Hz/Album|Singles` appended to base) — deferred; last-used folder is the v1.0 policy; metadata path-building risks misfiled songs on bad metadata
- **Per-row retry for failed saves** — Phase 5+ enhancement; not scoped for Phase 5
- **Stop/pause mid-batch during folder dialogs** — complex threading; not scoped for Phase 5

</deferred>

---

*Phase: 05-organization*
*Context gathered: 2026-05-17*
