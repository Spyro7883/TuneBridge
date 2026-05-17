---
status: partial
phase: 05-organization
source: [05-VERIFICATION.md]
started: 2026-05-17T21:00:00Z
updated: 2026-05-17T21:00:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Concurrent Dialog Serialization (SC-5)

expected: Only one FolderConfirmDialog appears at a time. Second dialog does not appear until user clicks Confirm or Skip on the first. Third appears after second is dismissed.
result: [pending]

**How to test:** Run the app, paste 3+ Spotify/YouTube URLs, click Start Processing. Wait for rows to reach "Awaiting folder" status concurrently. Observe that dialogs appear one at a time.

### 2. Smart Default Pre-Fill Behavior (SC-1)

expected: First dialog has empty path field. After confirming a folder, second dialog pre-fills with that confirmed path.
result: [pending]

**How to test:** Fresh app, process 2 songs. First dialog: QLineEdit should be empty. Confirm with a real folder path. Second dialog: QLineEdit should be pre-filled with the previously confirmed path.

### 3. Confirm Button Live Validation (SC-2 / ORG-02)

expected: Confirm button disabled for empty/non-existent path with error label visible; Confirm enabled and error label clears when a valid existing directory is typed.
result: [pending]

**How to test:** Open dialog (or trigger song to AWAITING). Type a non-existent path → Confirm should be disabled, error label visible. Type a real existing directory path → Confirm should enable, error label disappears. Test on each keystroke.

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps
