---
status: partial
phase: 04-download-pipeline
source: [04-VERIFICATION.md]
started: 2026-05-16T20:00:00Z
updated: 2026-05-16T20:00:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Real Spotify download via ytsearch
expected: Paste a Spotify track URL, wait for metadata fetch, click Start Processing — song downloads as MP3 in a temp folder, status transitions through Downloading → Awaiting folder
result: [pending]

### 2. 432Hz retune pipeline end-to-end
expected: With 432Hz selected, Spotify row transitions Downloading → Retuning → Awaiting folder; output MP3 plays at 432Hz pitch
result: [pending]

### 3. UI lock during active batch
expected: While batch is downloading, paste box is read-only, 440Hz/432Hz buttons are disabled, Start button is disabled; all re-enable when batch completes (Done — N downloaded, M failed)
result: [pending]

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps
