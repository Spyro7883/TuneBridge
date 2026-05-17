---
phase: 05-organization
verified: 2026-05-17T20:55:21Z
status: human_needed
score: 4/5 must-haves verified
overrides_applied: 0
overrides: []
gaps: []
human_verification:
  - test: "Run the app, process 2+ songs to AWAITING status, observe that only one dialog appears at a time"
    expected: "Second dialog does not appear until user clicks Confirm or Skip on the first"
    why_human: "Threading serialization via _dialog_lock cannot be verified by test introspection alone — requires live concurrent UI interaction"
  - test: "Open dialog with no prior session (fresh app). First-song field should be empty; confirm a folder; reopen for second song — field should pre-fill with first confirmed path"
    expected: "First dialog: empty field. Second dialog: pre-filled with confirmed path from first"
    why_human: "Visual inspection of QLineEdit text and UX flow — tests mock the dialog, can't verify actual pre-fill rendering"
  - test: "In dialog, type a non-existent path; verify Confirm button is disabled and error label is visible; type a real directory path; verify Confirm button enables"
    expected: "Confirm disabled for bad/empty path, enabled for valid existing directory; inline error label appears/disappears live on each keystroke"
    why_human: "Live textChanged signal response and button enable/disable state requires visual UI interaction"
---

# Phase 5: Organization Verification Report

**Phase Goal:** Each downloaded song is confirmed by the user into an existing folder before saving — with a smart default, skip option, and no folder creation
**Verified:** 2026-05-17T20:55:21Z
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths (Roadmap Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| SC-1 | For each song, a folder confirmation dialog appears with a pre-filled proposed path — last confirmed folder as default suggestion | ✓ VERIFIED (partial) | `_show_folder_dialog` passes `self._last_folder` as `proposed`; `FolderConfirmDialog.__init__` pre-fills `QLineEdit` with `str(proposed)` if not None; first song: empty field (None). Metadata-derived path (artist/album) is explicitly **out of scope** per 05-CONTEXT.md D-12 and Deferred section — last-used folder is the v1.0 policy. |
| SC-2 | User can confirm the proposed path, type a different path, or browse via directory picker | ✓ VERIFIED | `FolderConfirmDialog` has `QLineEdit` (type), Browse button → `QFileDialog.getExistingDirectory`, Confirm button. `_browse` wired to `_browse()` method. `test_browse_calls_get_existing_directory` PASS. |
| SC-3 | User can Skip without blocking or canceling other songs | ✓ VERIFIED | Skip button calls `self.reject()` → `_result_path` stays None. `_show_folder_dialog` detects `result is None`, calls `Path(temp).unlink(missing_ok=True)`, emits `SongStatus.SKIPPED`. `test_skip_does_not_block_other_rows` PASS — `_folder_events[row_id].is_set()` after skip. |
| SC-4 | Confirming saves MP3 into that folder; app never creates/renames/deletes folders | ✓ VERIFIED | `_show_folder_dialog` calls `shutil.move(str(temp), str(result))` where `result` is a `Path.is_dir()`-validated existing directory. `FolderConfirmDialog._validate` only enables Confirm for existing directories. No `os.makedirs`, `mkdir`, or folder creation code present. `test_confirm_calls_shutil_move` PASS. |
| SC-5 | Only one dialog shown at a time regardless of concurrent AWAITING songs | ? UNCERTAIN | `_dialog_lock = threading.Lock()` at module level (line 154). `_folder_worker` acquires `with _dialog_lock:` block containing ev creation + `ev.wait()` (lock held until dialog is dismissed). Structurally correct — but live concurrent behavior requires human verification. |

**Score:** 4/5 truths verified (SC-5 routes to human)

---

### SC-1 Note: Metadata-Based Proposal

ROADMAP SC-1 says "proposed path derived from metadata (artist/album/single)". The implementation proposes `_last_folder` (last confirmed path), not a metadata-derived path.

**This is an explicit, documented phase-scoping decision — not a gap:**
- 05-CONTEXT.md Deferred section: "Metadata-derived sub-path proposal (e.g., Artist_432Hz/Album|Singles appended to base) — deferred; last-used folder is the v1.0 policy; metadata path-building risks misfiled songs on bad metadata"
- 05-CONTEXT.md D-12: "Proposed path = self._last_folder (last confirmed folder, Path | None). No metadata-derived sub-path is appended."
- 05-CONTEXT.md scope: "Out of scope: metadata-derived sub-path auto-generation (Artist/Album)"

The ROADMAP SC-1 wording was not updated to reflect this scoping decision. The implementation satisfies the intent (smart default for each song) via last-used folder. No override entry required — the deviation is fully documented in phase context.

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `tests/test_organization.py` | 14 RED-gate tests | ✓ VERIFIED | 14 tests, all PASS (76 total suite) |
| `tunebridge.py` — `_dialog_lock` | Module-level threading.Lock | ✓ VERIFIED | Line 154: `_dialog_lock = threading.Lock()` |
| `tunebridge.py` — `FolderConfirmDialog` | QDialog above TuneBridgeApp | ✓ VERIFIED | Line 762 (TuneBridgeApp at 833) |
| `tunebridge.py` — `SongStatus.SKIPPED` | "Skipped — folder" (em-dash) | ✓ VERIFIED | Line 328; `repr()` confirms `—` |
| `tunebridge.py` — `SongStatus.FAILED_SAVE` | "Failed — save" (em-dash) | ✓ VERIFIED | Line 329; `repr()` confirms `—` |
| `tunebridge.py` — `_STATUS_COLORS` entries | Both new statuses colored | ✓ VERIFIED | Lines 582-583: `#B3B3B3` and `#EF4444` |
| `tunebridge.py` — `_Dispatcher` signals | `folder_requested Signal(int)`, `folder_batch_done Signal()` | ✓ VERIFIED | Lines 360-361; runtime type: `SignalInstance` |
| `tunebridge.py` — `__init__` Phase 5 vars | `_last_folder`, `_folder_events`, `_folder_results`, `_saved_paths`, counters | ✓ VERIFIED | Lines 941-947; runtime: all None/`{}`/0 on fresh instance |
| `tunebridge.py` — `_folder_worker` | Acquires lock, blocks on Event, moves file or skips | ✓ VERIFIED | Line 1095; `with _dialog_lock:` at 1104; `ev.wait()` at 1111 inside lock |
| `tunebridge.py` — `_show_folder_dialog` | Main-thread slot, shows dialog, sets event, performs I/O | ✓ VERIFIED | Line 1143; `dlg.exec()` at 1159; file I/O at 1169-1195 |
| `tunebridge.py` — `_on_folder_row_finished` | Batch counter, `folder_batch_done` emit, status bar | ✓ VERIFIED | Line 1197; `folder_batch_done.emit()` at 1226; status bar at 1227-1230 |
| `tunebridge.py` — `closeEvent` extension | Unblocks all `_folder_events` on close | ✓ VERIFIED | Line 1335: `for ev in list(self._folder_events.values()): ev.set()` |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `_folder_worker` | `_dialog_lock` | `with _dialog_lock:` containing `ev.wait()` | ✓ WIRED | Lock scope includes event creation (line 1104) through `ev.wait()` (line 1111) — Pitfall 3 guard confirmed |
| `_show_folder_dialog` | `FolderConfirmDialog` | `dlg = FolderConfirmDialog(...); dlg.exec()` | ✓ WIRED | Lines 1154-1159 |
| `closeEvent` | `_folder_events` | `for ev in list(self._folder_events.values())` | ✓ WIRED | Line 1335 |
| `_on_download_row_finished` | `_folder_worker` | `self._executor.submit(self._folder_worker, _row_id)` | ✓ WIRED | Line 1244 |
| `_dispatcher.folder_requested` | `_show_folder_dialog` | `connect(self._show_folder_dialog)` | ✓ WIRED | Line 956 in `__init__` |
| `_on_folder_row_finished` | `folder_batch_done` | `self._dispatcher.folder_batch_done.emit()` | ✓ WIRED | Line 1226 |
| `_on_folder_row_finished` | `statusBar` | `f"Saved {self._folder_done}, skipped {self._folder_skipped}, failed {self._folder_failed}"` | ✓ WIRED | Lines 1227-1230 |
| `FolderConfirmDialog._validate` | `Path.is_dir()` | `bool(text.strip()) and Path(text.strip()).is_dir()` | ✓ WIRED | Line 805 — Windows-safe empty-string guard confirmed (Pitfall 1) |
| `_folder_worker` | `shutil.move` | `Path(shutil.move(str(temp), str(result)))` | ✓ WIRED | Line 1132 in `_folder_worker`, also line 1186 in `_show_folder_dialog` — Pitfall 4 guard (str→Path wrap) confirmed |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `FolderConfirmDialog` | `_result_path` | `QLineEdit._path_edit.text()` in `_on_confirm` | Yes — user input via validated text field | ✓ FLOWING |
| `_show_folder_dialog` | `result` | `dlg.result_path()` → `_folder_results[row_id]` | Yes — Path or None from dialog | ✓ FLOWING |
| `_folder_worker` | `result` | `self._folder_results.get(row_id)` after `ev.wait()` | Yes — set by `_show_folder_dialog` before `ev.set()` | ✓ FLOWING |
| `_on_folder_row_finished` | `_folder_done/_folder_skipped/_folder_failed` | Direct int increments from each resolved row | Yes — driven by actual UPLOADING/SKIPPED/FAILED_SAVE status calls | ✓ FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All 14 Phase 5 tests pass | `pytest tests/test_organization.py -q` | `14 passed` | ✓ PASS |
| Full suite (76 tests) passes | `pytest tests/ -q` | `76 passed, 0 failed` | ✓ PASS |
| Symbol imports resolve | `python -c "from tunebridge import FolderConfirmDialog, SongStatus, _dialog_lock"` | OK, no error | ✓ PASS |
| `SongStatus.SKIPPED.value` em-dash | `repr(SongStatus.SKIPPED.value)` | `'Skipped — folder'` | ✓ PASS |
| `TuneBridgeApp.__init__` Phase 5 vars | Runtime instantiation | `_last_folder=None`, all dicts `{}`, all counters `0` | ✓ PASS |
| Dialog before TuneBridgeApp | Line number check | `FolderConfirmDialog` line 762 < `TuneBridgeApp` line 833 | ✓ PASS |
| Lock includes `ev.wait()` | Line position check | `with _dialog_lock:` at 1104, `ev.wait()` at 1111 — inside block | ✓ PASS |
| Concurrent dialog serialization | Requires live UI interaction | Cannot test programmatically | ? SKIP → Human |

---

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| ORG-01 | 05-01, 05-02, 05-03, 05-04 | Folder proposal with last-used default | ✓ SATISFIED | `_last_folder` pre-fills dialog; None on first song; updated after each confirm. Metadata-derived path explicitly deferred per 05-CONTEXT.md. |
| ORG-02 | 05-01, 05-02, 05-03, 05-04 | Confirm/edit/browse dialog per song | ✓ SATISFIED | `FolderConfirmDialog` with QLineEdit, Browse button (QFileDialog), Confirm/Skip buttons. 4 dialog tests PASS. |
| ORG-03 | 05-01, 05-02, 05-03, 05-04 | Per-song skip without blocking batch | ✓ SATISFIED | Skip → `reject()` → `result_path()=None` → `unlink` temp → emit SKIPPED. `_folder_events[row_id].is_set()` after skip. |
| ORG-04 | 05-01, 05-02, 05-03, 05-04 | Save to existing folder, no creation | ✓ SATISFIED | `shutil.move` to `Path.is_dir()`-validated destination only. No `mkdir`/`makedirs` anywhere in Phase 5 code. |

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `tunebridge.py` | 741, 746 | `PLACEHOLDER` string | ℹ️ Info | `QTextEdit.PLACEHOLDER` constant for `setPlaceholderText()` — UI hint text, not a code stub. Not Phase 5 code. No impact. |

No blockers or warnings found in Phase 5 code.

---

### Human Verification Required

#### 1. Concurrent Dialog Serialization (SC-5)

**Test:** Process 3+ songs to "Awaiting folder" status simultaneously. Observe dialog behavior.
**Expected:** Only one FolderConfirmDialog appears. Second dialog does not appear until the first is dismissed (Confirm or Skip). Third appears after second is dismissed.
**Why human:** `_dialog_lock` serialization is structurally correct (lock scope verified, `ev.wait()` inside lock), but live concurrent UI behavior requires actual multi-song batch execution to confirm the UX contract.

#### 2. Smart Default Pre-Fill Behavior (SC-1)

**Test:** Fresh app, process 2 songs. First song dialog should have empty path field. Confirm with a real folder. Second song dialog should pre-fill that folder path.
**Expected:** First: empty `QLineEdit`. After confirm: `_last_folder` = confirmed path. Second: `QLineEdit` pre-filled with that path.
**Why human:** Tests mock `FolderConfirmDialog` — actual pre-fill rendering requires visual inspection of the live dialog.

#### 3. Confirm Button Live Validation (SC-2 / ORG-02)

**Test:** Open dialog. Type a non-existent path → Confirm should be disabled, error label visible. Type an existing directory path → Confirm should enable, error label clears.
**Expected:** Real-time response to each keystroke via `textChanged` signal. `bool(text.strip()) and Path(text.strip()).is_dir()` validation visible in UI.
**Why human:** `_validate` logic is verified by tests 3/4/5, but the live UX (label text, button state feedback speed) requires visual confirmation.

---

### Gaps Summary

No automated gaps. All must-have artifacts exist, are substantive, wired, and data flows through them. 14/14 Phase 5 tests pass. 76/76 full suite passes.

SC-5 (single dialog at a time) routes to human because live concurrent threading behavior cannot be asserted programmatically without running a full batch.

The ROADMAP SC-1 wording ("proposed path derived from metadata") is intentionally unimplemented — deferred to v1.1 per 05-CONTEXT.md. The v1.0 policy (last-used folder) satisfies the intent of ORG-01.

---

_Verified: 2026-05-17T20:55:21Z_
_Verifier: Claude (gsd-verifier)_
