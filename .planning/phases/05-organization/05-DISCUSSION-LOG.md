# Phase 5: Organization - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in 05-CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-17
**Phase:** 05-organization
**Areas discussed:** Dialog queue architecture, Skip status & cleanup, Phase 5→6 handoff terminal state, Folder proposal format

---

## Dialog Queue Architecture

| Option | Description | Selected |
|--------|-------------|----------|
| threading.Event per row | Each worker waits on its own Event; main thread sets it after dialog closes | ✓ |
| Queue drain on main thread | Workers post row_id to queue.Queue; main thread dequeues and shows dialog; no thread blocking | |

**User's choice:** threading.Event per row

---

| Option | Description | Selected |
|--------|-------------|----------|
| Shared dict + signal | Worker stores Event in _folder_events[row_id], emits folder_requested(row_id); main thread retrieves, shows dialog, stores result, sets event | ✓ |
| Pass Event via Signal | Emit Signal(int, object) with the threading.Event itself; main thread receives and sets | |

**User's choice:** Shared dict + signal

---

| Option | Description | Selected |
|--------|-------------|----------|
| _dialog_lock = threading.Lock() | Module-level lock acquired by each worker before triggering dialog; mirrors _download_lock pattern | ✓ |
| threading.Semaphore(1) | Same effect as Lock; named differently for semantic clarity | |
| You decide | Leave serialization mechanism to implementer | |

**User's choice:** _dialog_lock = threading.Lock() (module-level)

---

| Option | Description | Selected |
|--------|-------------|----------|
| Module-level | _dialog_lock at module level, mirroring _download_lock | ✓ |
| Instance-level on TuneBridgeApp | self._dialog_lock in __init__ | |

**User's choice:** Module-level

---

| Option | Description | Selected |
|--------|-------------|----------|
| Set all pending Events on closeEvent | closeEvent iterates _folder_events and sets each with skip sentinel | ✓ |
| You decide | Leave close-while-dialog-open handling to implementer | |

**User's choice:** Set all pending Events on closeEvent (with None sentinel)

---

## Skip Status & Cleanup

| Option | Description | Selected |
|--------|-------------|----------|
| New SongStatus.SKIPPED = 'Skipped — folder' | New enum value; gray #B3B3B3; distinct from Failed and Done | ✓ |
| Reuse SongStatus.DONE | Simpler (no new value) but loses distinction | |
| Reuse SongStatus.FAILED | Misleading — skip is intentional, not an error | |

**User's choice:** New SongStatus.SKIPPED = "Skipped — folder"

---

| Option | Description | Selected |
|--------|-------------|----------|
| Delete immediately | Path.unlink(missing_ok=True) on skip; no orphan temp files | ✓ |
| Leave for session-end cleanup | atexit/closeEvent handles cleanup; simpler code | |

**User's choice:** Delete immediately

---

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — skip means no upload | Skipped rows excluded from Phase 6; only UPLOADING rows upload | ✓ |
| Ask again at upload time | Phase 6 shows skipped rows with option to re-confirm | |

**User's choice:** Yes — skip means no upload (UPLOADING-only filter for Phase 6)

---

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — include skipped in summary | Status bar: "Saved X, skipped Y, failed Z" | ✓ |
| You decide | Leave exact message format to implementer | |

**User's choice:** Yes — status bar summary includes skipped count

---

## Phase 5→6 Handoff Terminal State

| Option | Description | Selected |
|--------|-------------|----------|
| UPLOADING = 'Uploading' after save | Phase 6 intercepts at UPLOADING; _saved_paths dict stores final path | ✓ |
| DONE = 'Done' | Row goes straight to Done; Phase 6 needs another mechanism | |

**User's choice:** UPLOADING after shutil.move succeeds

---

| Option | Description | Selected |
|--------|-------------|----------|
| self._saved_paths: dict[int, Path] | Mirrors _temp_paths (Phase 4→5 handoff) pattern | ✓ |
| You decide | Leave storage mechanism to implementer | |

**User's choice:** self._saved_paths: dict[int, Path]

---

| Option | Description | Selected |
|--------|-------------|----------|
| FAILED = 'Failed — save' | OSError → "Failed — save" status; excluded from Phase 6; error isolated | ✓ |
| Re-show folder dialog | On save failure, re-present dialog for different folder selection | |

**User's choice:** "Failed — save" on OSError (no retry in Phase 5)

---

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — emit folder_batch_done signal | _dispatcher.folder_batch_done() when last dialog resolves; Phase 6 connects to this | ✓ |
| No signal — Phase 6 monitors row statuses | Phase 6 watches row_status_changed for UPLOADING rows | |

**User's choice:** Yes — folder_batch_done signal

---

## Folder Proposal Format

| Option | Description | Selected |
|--------|-------------|----------|
| Last-used folder as root (no sub-path) | Proposed path = last confirmed folder; no artist/album appended | ✓ |
| Last-used root + metadata sub-path | Proposed = last_root / Artist_432Hz / Album\|Singles | |
| Empty field (user types from scratch) | No proposal; user types full path every time | |

**User's choice:** Last-used folder as root (no metadata-derived sub-path)

---

| Option | Description | Selected |
|--------|-------------|----------|
| Empty (user types or browses) | First dialog: empty text field; no wrong guess to correct | ✓ |
| Home directory or hardcoded default | Pre-fill with Path.home() or ~/Music | |

**User's choice:** Empty for first song

---

| Option | Description | Selected |
|--------|-------------|----------|
| In-session only | _last_folder reset on app restart; cross-session deferred to v1.1 | ✓ |
| Cross-session persistence | Save to ~/.tunebridge_state.json; out of scope per REQUIREMENTS.md | |

**User's choice:** In-session only

---

| Option | Description | Selected |
|--------|-------------|----------|
| QDialog: title + path field + Browse + Confirm + Skip | Modal QDialog; song title at top; text field + Browse + Confirm + Skip | ✓ |
| You decide | Leave dialog layout to implementer | |

**User's choice:** Modal QDialog with song title label + QLineEdit + Browse + Confirm + Skip

---

| Option | Description | Selected |
|--------|-------------|----------|
| Show inline error, block Confirm | Confirm disabled if Path.is_dir() is False; inline error label | ✓ |
| Silently fail and show FAILED status | Allow Confirm, catch OSError, mark Failed | |

**User's choice:** Inline error + block Confirm for non-existent paths

---

| Option | Description | Selected |
|--------|-------------|----------|
| Last confirmed folder (or home if none) | Browse opens at _last_folder or Path.home() | ✓ |
| Always home directory | Browse always opens from Path.home() | |

**User's choice:** Last confirmed folder (or home if none)

---

## Claude's Discretion

- Exact signal names in _Dispatcher (suggested: folder_requested = Signal(int), folder_batch_done = Signal())
- Skip sentinel value in _folder_results (suggested: None — unambiguous vs Path objects)
- Dialog styling consistent with existing Liquid Glass QSS theme
- _folder_events/_folder_results dict locking strategy
- Whether _folder_worker is submitted to existing ThreadPoolExecutor or chains directly in _download_worker
- Exact SongStatus enum value for "Failed — save" (new enum member or reuse FAILED with distinct string)

## Deferred Ideas

- Cross-session folder persistence (~/.tunebridge_state.json) — REQUIREMENTS.md deferred to v1.1
- Metadata-derived sub-path proposal (Artist_432Hz/Album|Singles) — deferred; last-used folder sufficient for v1.0
- Per-row retry for failed saves — Phase 5+ enhancement
- Stop/pause mid-batch during folder dialogs — complex threading; not scoped for Phase 5
