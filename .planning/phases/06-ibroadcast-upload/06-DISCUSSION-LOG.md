# Phase 6: iBroadcast Upload - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-19
**Phase:** 06-ibroadcast-upload
**Areas discussed:** Credential Handling, Duplicate Detection, Upload Trigger Timing, Upload Failure Behavior

---

## Credential Handling

| Option | Description | Selected |
|--------|-------------|----------|
| .env file | IBROADCAST_USERNAME + IBROADCAST_PASSWORD in .env, mirrors Spotify pattern | ✓ |
| Runtime prompt dialog | QInputDialog at first launch, memory-only for session | |

**User's choice:** .env file

---

| Option | Description | Selected |
|--------|-------------|----------|
| Upload silently disabled | App starts normally, rows skip to Done, one-time notice | |
| Warning in status bar only | Status bar shows warning, upload skipped for all UPLOADING rows | ✓ |
| Startup error dialog | App refuses to start without credentials | |

**User's choice:** Warning in status bar only

---

| Option | Description | Selected |
|--------|-------------|----------|
| Continue — mark all UPLOADING rows as Failed—upload | Auth failure is isolated, batch continues | ✓ |
| Stop batch — show auth error dialog | Blocks all upload rows with a modal dialog | |

**User's choice:** Continue — mark all UPLOADING rows as Failed—upload

---

| Option | Description | Selected |
|--------|-------------|----------|
| Once per batch (Recommended) | Login when folder_batch_done fires, token held in memory for batch | ✓ |
| Once per app session | Login at startup, cache token across multiple batches | |

**User's choice:** Once per batch

---

## Duplicate Detection

| Option | Description | Selected |
|--------|-------------|----------|
| Title + artist match (Recommended) | Case-insensitive, catches re-downloads with different filenames | ✓ |
| Filename match | Fast but misses renamed re-downloads | |
| You decide | Leave to Claude | |

**User's choice:** Title + artist match

---

| Option | Description | Selected |
|--------|-------------|----------|
| Exact match, case-insensitive (Recommended) | Both fields must match exactly ignoring case | ✓ |
| Fuzzy / normalized match | Strip punctuation and tags before comparing | |

**User's choice:** Exact match, case-insensitive

---

| Option | Description | Selected |
|--------|-------------|----------|
| Done ✓ (same as successful upload) | Treat already-uploaded as success | |
| Already uploaded (distinct label) | New SongStatus value with distinct color | ✓ |

**User's choice:** Already uploaded (distinct label)

---

| Option | Description | Selected |
|--------|-------------|----------|
| Upload anyway (Recommended) | Library check failure → proceed with upload | ✓ |
| Skip with 'Failed — upload' | Library check failure → treat row as failed | |

**User's choice:** Upload anyway

---

| Option | Description | Selected |
|--------|-------------|----------|
| Use guessed artist for YouTube rows too | Consistent behavior across all row types | ✓ |
| Title-only check for YouTube rows | Fall back to title-only when artist is guessed/empty | |

**User's choice:** Use guessed artist for YouTube rows too

---

## Upload Trigger Timing

| Option | Description | Selected |
|--------|-------------|----------|
| After folder_batch_done — batch upload (Recommended) | Login once, library fetch once, upload all UPLOADING rows | ✓ |
| Per-row as soon as each saves | Upload starts immediately per row, requires N auth calls or token caching | |

**User's choice:** After folder_batch_done — batch upload

---

| Option | Description | Selected |
|--------|-------------|----------|
| Parallel — submit all to ThreadPoolExecutor (Recommended) | Each upload row gets a worker thread | ✓ |
| Serial — one upload at a time | One by one, simpler but slower | |

**User's choice:** Parallel

---

| Option | Description | Selected |
|--------|-------------|----------|
| Status bar summary only (Recommended) | "Uploading X of N..." + final "Done — X uploaded, Y already existed, Z failed" | ✓ |
| Per-row progress percentage | Requires iBroadcast API progress callbacks | |

**User's choice:** Status bar summary only

---

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — unlock UI after upload batch completes | Same _unlock_ui pattern as Phase 4/5 | ✓ |
| UI stays locked until user manually clears | Stays visible; user must clear before new batch | |

**User's choice:** Yes — unlock UI after upload batch completes

---

| Option | Description | Selected |
|--------|-------------|----------|
| Skip upload phase entirely (Recommended) | _saved_paths empty → skip auth + upload, call _unlock_ui immediately | ✓ |
| Run anyway (no-op) | Run upload phase even with no uploadable rows | |

**User's choice:** Skip upload phase entirely

---

## Upload Failure Behavior

| Option | Description | Selected |
|--------|-------------|----------|
| "Failed — upload" (new label, same FAILED color) | Distinct label consistent with Failed—save and Failed—download | ✓ |
| Reuse existing FAILED status | Simpler but no distinction between failure types | |

**User's choice:** "Failed — upload" new label

---

| Option | Description | Selected |
|--------|-------------|----------|
| Permanent terminal state — no retry (Recommended) | Consistent with prior phases | ✓ |
| One automatic retry | Wait 2s and retry once before marking Failed | |

**User's choice:** Permanent terminal state — no retry

---

| Option | Description | Selected |
|--------|-------------|----------|
| No — fully isolated per row (Recommended) | Each upload worker handles its own failure | ✓ |
| Yes — abort remaining uploads on first failure | Cancel all pending uploads on any failure | |

**User's choice:** Fully isolated per row

---

| Option | Description | Selected |
|--------|-------------|----------|
| "Done — X uploaded, Y already existed, Z failed" | Explicit breakdown across all terminal states | ✓ |
| "Done" only | Minimal, no breakdown | |

**User's choice:** "Done — X uploaded, Y already existed, Z failed"

---

| Option | Description | Selected |
|--------|-------------|----------|
| Python logging only (Recommended) | logging.getLogger(__name__).warning() — same as save/download workers | ✓ |
| Row tooltip with error detail | Hover shows error message; more debuggable | |

**User's choice:** Python logging only

---

## Claude's Discretion

- Exact color for "Already uploaded" status (muted teal `#14B8A6` suggested)
- HTTP library for iBroadcast API calls (`requests` with `verify=False` vs `urllib`)
- iBroadcast API endpoint details (auth URL, library list URL, upload URL)
- Signal name for upload batch completion
- Upload counter variable names
- Status transition for UPLOADING rows when credentials missing at startup
- Lock strategy for reading `_saved_paths` and `_row_metadata` in upload workers

## Deferred Ideas

- iBroadcast playlist assignment — v1.1 feature
- Retry UI for failed uploads — post-batch retry button, not scoped for v1.0
- Per-row upload progress percentage — requires API progress callback support
- Cross-session upload history — deferred
