---
status: partial
phase: 03-metadata-services
source: [03-VERIFICATION.md]
started: 2026-05-15
updated: 2026-05-15
---

## Current Test

[awaiting human testing]

## Tests

### 1. End-to-end Spotify fetch
expected: Paste a real Spotify track URL → row transitions "Fetching metadata" → column 0 updates to "Artist — Title", status column shows "Metadata ready"
result: [pending]

### 2. End-to-end YouTube fetch
expected: Paste a real YouTube URL → row transitions "Fetching metadata" → column 0 shows "(guessed)" label in artist or track fields
result: [pending]

### 3. D-02 fail-fast UI (no .env credentials)
expected: Without SPOTIFY_CLIENT_ID/.env, paste a Spotify URL → row immediately shows "Failed — metadata" (red), no hanging or crash
result: [pending]

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps
