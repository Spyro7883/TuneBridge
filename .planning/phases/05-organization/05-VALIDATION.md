---
phase: 5
slug: organization
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-17
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing — 62 tests passing) |
| **Config file** | `pytest.ini` (`testpaths = tests`, `addopts = -q`) |
| **Quick run command** | `python -m pytest tests/test_organization.py -q --tb=short -p no:warnings` |
| **Full suite command** | `python -m pytest tests/ -q --tb=short -p no:warnings` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_organization.py -q --tb=short -p no:warnings`
- **After every plan wave:** Run `python -m pytest tests/ -q --tb=short -p no:warnings`
- **Before `/gsd-verify-work`:** Full suite must be green (62 + Phase 5 tests)
- **Max feedback latency:** ~15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 5-01-01 | 01 | 0 | ORG-01 | — | N/A | unit | `pytest tests/test_organization.py::test_last_folder_empty_on_first -x` | ❌ W0 | ⬜ pending |
| 5-01-02 | 01 | 0 | ORG-01 | — | N/A | unit | `pytest tests/test_organization.py::test_last_folder_updates_after_confirm -x` | ❌ W0 | ⬜ pending |
| 5-01-03 | 01 | 0 | ORG-02 | V5 | Confirm disabled when text empty | unit | `pytest tests/test_organization.py::test_confirm_disabled_empty_text -x` | ❌ W0 | ⬜ pending |
| 5-01-04 | 01 | 0 | ORG-02 | V5 | Confirm disabled on non-existent path | unit | `pytest tests/test_organization.py::test_confirm_disabled_nonexistent_path -x` | ❌ W0 | ⬜ pending |
| 5-01-05 | 01 | 0 | ORG-02 | V5 | Confirm enabled on valid existing dir | unit | `pytest tests/test_organization.py::test_confirm_enabled_valid_dir -x` | ❌ W0 | ⬜ pending |
| 5-01-06 | 01 | 0 | ORG-02 | — | N/A | unit | `pytest tests/test_organization.py::test_browse_calls_get_existing_directory -x` | ❌ W0 | ⬜ pending |
| 5-01-07 | 01 | 0 | ORG-03 | — | N/A | unit | `pytest tests/test_organization.py::test_skip_deletes_temp_and_emits_skipped -x` | ❌ W0 | ⬜ pending |
| 5-01-08 | 01 | 0 | ORG-03 | — | N/A | unit | `pytest tests/test_organization.py::test_skip_does_not_block_other_rows -x` | ❌ W0 | ⬜ pending |
| 5-01-09 | 01 | 0 | ORG-04 | — | N/A | unit | `pytest tests/test_organization.py::test_confirm_calls_shutil_move -x` | ❌ W0 | ⬜ pending |
| 5-01-10 | 01 | 0 | ORG-04 | — | N/A | unit | `pytest tests/test_organization.py::test_saved_paths_populated_after_move -x` | ❌ W0 | ⬜ pending |
| 5-01-11 | 01 | 0 | ORG-04 | — | N/A | unit | `pytest tests/test_organization.py::test_oserror_emits_failed_save -x` | ❌ W0 | ⬜ pending |
| 5-01-12 | 01 | 0 | D-11 | — | N/A | unit | `pytest tests/test_organization.py::test_folder_batch_done_emitted -x` | ❌ W0 | ⬜ pending |
| 5-01-13 | 01 | 0 | D-08 | — | N/A | unit | `pytest tests/test_organization.py::test_status_bar_summary -x` | ❌ W0 | ⬜ pending |
| 5-01-14 | 01 | 0 | D-04 | — | N/A | unit | `pytest tests/test_organization.py::test_close_event_unblocks_pending_workers -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_organization.py` — 14 RED-gate tests covering ORG-01 through ORG-04, D-04, D-08, D-11
- [ ] No new framework install needed — pytest + PySide6 + unittest.mock already present

*Existing infrastructure covers all phase requirements except test_organization.py file.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Dialog appears centered on main window | D-15 | Requires visual inspection; Qt parent centering cannot be headlessly asserted | Launch app, add a Spotify URL, start processing, observe FolderConfirmDialog appears modal and centered |
| Only one dialog shown at a time with concurrent AWAITING rows | SC-5 | Requires concurrent thread execution with timing | Add 3+ URLs, trigger processing simultaneously, verify dialogs appear one-by-one not simultaneously |
| Browse opens at _last_folder after first confirm | D-17 | Requires visual inspection of QFileDialog start path | Confirm a folder for song 1, click Browse on song 2's dialog, verify the file picker opens at song 1's confirmed folder |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
