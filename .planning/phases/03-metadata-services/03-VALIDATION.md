---
phase: 3
slug: metadata-services
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-14
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (pytest.ini present) |
| **Config file** | `pytest.ini` — `testpaths = tests`, `addopts = -q` |
| **Quick run command** | `pytest tests/test_metadata_services.py -q` |
| **Full suite command** | `pytest -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_metadata_services.py -q`
- **After every plan wave:** Run `pytest -q` (full suite — 34 Phase 2 + 21 Phase 3 = 55 tests)
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 1 | META-01 | unit | `pytest tests/test_metadata_services.py::test_spotify_token_uses_client_credentials_grant -x` | ✅ RED | ⬜ pending |
| 03-01-02 | 01 | 1 | META-01 | unit | `pytest tests/test_metadata_services.py::test_spotify_token_cached_second_call_no_extra_post -x` | ✅ RED | ⬜ pending |
| 03-01-03 | 01 | 1 | META-01 | unit | `pytest tests/test_metadata_services.py::test_spotify_token_http_error_raises -x` | ✅ RED | ⬜ pending |
| 03-01-04 | 01 | 1 | META-01 | unit | `pytest tests/test_metadata_services.py::test_spotify_get_track_metadata_returns_required_keys -x` | ✅ RED | ⬜ pending |
| 03-01-05 | 01 | 1 | META-01 | unit | `pytest tests/test_metadata_services.py::test_spotify_get_track_metadata_values_correct -x` | ✅ RED | ⬜ pending |
| 03-01-06 | 01 | 1 | META-01 | unit | `pytest tests/test_metadata_services.py::test_spotify_get_album_metadata_returns_required_keys -x` | ✅ RED | ⬜ pending |
| 03-01-07 | 01 | 1 | META-01 | unit | `pytest tests/test_metadata_services.py::test_spotify_get_track_metadata_http_error_raises -x` | ✅ RED | ⬜ pending |
| 03-02-01 | 02 | 1 | META-02 | unit | `pytest tests/test_metadata_services.py::test_youtube_extract_returns_title -x` | ✅ RED | ⬜ pending |
| 03-02-02 | 02 | 1 | META-02 | unit | `pytest tests/test_metadata_services.py::test_youtube_extract_returns_channel -x` | ✅ RED | ⬜ pending |
| 03-02-03 | 02 | 1 | META-02 | unit | `pytest tests/test_metadata_services.py::test_youtube_extract_does_not_download -x` | ✅ RED | ⬜ pending |
| 03-02-04 | 02 | 1 | META-02 | unit | `pytest tests/test_metadata_services.py::test_youtube_extract_error_raises -x` | ✅ RED | ⬜ pending |
| 03-02-05 | 02 | 1 | META-03 | unit | `pytest tests/test_metadata_services.py::test_youtube_guessed_artist_carries_label -x` | ✅ RED | ⬜ pending |
| 03-02-06 | 02 | 1 | META-03 | unit | `pytest tests/test_metadata_services.py::test_youtube_guessed_track_title_carries_label -x` | ✅ RED | ⬜ pending |
| 03-03-01 | 03 | 2 | META-01+02 | unit | `pytest tests/test_metadata_services.py::test_fetch_metadata_routes_spotify_url_to_spotify_client -x` | ✅ RED | ⬜ pending |
| 03-03-02 | 03 | 2 | META-01+02 | unit | `pytest tests/test_metadata_services.py::test_fetch_metadata_routes_youtube_url_to_yt_extractor -x` | ✅ RED | ⬜ pending |
| 03-03-03 | 03 | 2 | META-01 | unit | `pytest tests/test_metadata_services.py::test_fetch_metadata_result_includes_source_spotify -x` | ✅ RED | ⬜ pending |
| 03-03-04 | 03 | 2 | META-02 | unit | `pytest tests/test_metadata_services.py::test_fetch_metadata_result_includes_source_youtube -x` | ✅ RED | ⬜ pending |
| 03-03-05 | 03 | 2 | META-01 | unit | `pytest tests/test_metadata_services.py::test_fetch_metadata_spotify_album_url_delegates_to_get_album_metadata -x` | ✅ RED | ⬜ pending |
| 03-04-01 | 04 | 2 | META-01+03 | integration | `pytest tests/test_metadata_services.py::test_batch_table_update_row_metadata_stores_title -x` | ✅ RED | ⬜ pending |
| 03-04-02 | 04 | 2 | META-01 | integration | `pytest tests/test_metadata_services.py::test_batch_table_update_row_metadata_status_transitions_to_done -x` | ✅ RED | ⬜ pending |
| 03-04-03 | 04 | 2 | META-03 | integration | `pytest tests/test_metadata_services.py::test_batch_table_update_row_metadata_guessed_label_preserved -x` | ✅ RED | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements. `tests/test_metadata_services.py` (21 tests) is already written and RED. No Wave 0 stub work needed.

---

## Regression Guard

| Suite | Tests | Command |
|-------|-------|---------|
| Phase 2 (full) | 34 | `pytest tests/test_tunebridge.py -q` |
| Phase 3 (new) | 21 | `pytest tests/test_metadata_services.py -q` |
| Combined gate | 55 | `pytest -q` |

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Status bar warning when .env missing | META-01 (D-02) | Requires live app launch without .env | Delete .env, run app, confirm status bar message |
| Rows transition visually in UI | META-01+02 | Qt rendering requires visual check | Paste valid URLs, watch status column update in real time |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
