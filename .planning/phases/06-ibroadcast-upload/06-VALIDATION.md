---
phase: 6
slug: ibroadcast-upload
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-19
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | `pytest.ini` or `pyproject.toml [tool.pytest]` |
| **Quick run command** | `python -m pytest tests/ -x -q` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/ -x -q`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | Status |
|---------|------|------|-------------|-----------|-------------------|--------|
| 06-01-01 | 01 | 1 | UPL-01 | unit | `python -m pytest tests/ -k "test_ibroadcast_login" -x -q` | ⬜ pending |
| 06-01-02 | 01 | 1 | UPL-01 | unit | `python -m pytest tests/ -k "test_is_duplicate" -x -q` | ⬜ pending |
| 06-01-03 | 01 | 1 | UPL-01 | unit | `python -m pytest tests/ -k "test_ibroadcast_upload" -x -q` | ⬜ pending |
| 06-01-04 | 01 | 1 | UPL-01 | unit | `python -m pytest tests/ -k "test_song_status" -x -q` | ⬜ pending |
| 06-02-01 | 02 | 2 | UPL-01 | unit | `python -m pytest tests/ -k "test_start_upload_batch" -x -q` | ⬜ pending |
| 06-02-02 | 02 | 2 | UPL-02 | unit | `python -m pytest tests/ -k "test_missing_credentials" -x -q` | ⬜ pending |
| 06-03-01 | 03 | 2 | UPL-01 | unit | `python -m pytest tests/ -k "test_upload_worker" -x -q` | ⬜ pending |
| 06-03-02 | 03 | 2 | UPL-01, UPL-02 | unit | `python -m pytest tests/ -k "test_on_upload_row_finished" -x -q` | ⬜ pending |
| 06-03-03 | 03 | 2 | UPL-01 | unit | `python -m pytest tests/ -k "test_upload_batch_counter" -x -q` | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_phase6_upload.py` — test stubs for UPL-01, UPL-02 covering all scenarios in RESEARCH.md §Validation Architecture
- [ ] Existing `tests/conftest.py` — may need `requests-mock` or `unittest.mock.patch` fixture for HTTP mocking

*Existing pytest infrastructure covers the framework. New test file only.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Status bar shows "iBroadcast credentials not configured — upload will be skipped" at startup | UPL-02 | Requires Qt app startup with missing env vars | Launch app without IBROADCAST_USERNAME set; verify status bar message |
| Already-uploaded row shows muted teal color (`#14B8A6`) | UPL-02 | Qt color rendering requires visual inspection | Run batch with a duplicate track; verify row color is teal, not red or green |
| Upload progress bar updates "Uploading X of N…" during batch | UPL-01 | Requires live network call timing | Observe status bar during a real upload batch |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
