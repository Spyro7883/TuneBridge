# Phase 2: Input & Detection - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-13
**Phase:** 02-input-detection
**Areas discussed:** B — Paste trigger

---

## B — Paste Trigger

| Option | Description | Selected |
|--------|-------------|----------|
| Auto on paste | Rows appear instantly on Ctrl+V / paste event. No button needed. | ✓ |
| Button-triggered | User pastes into text area, reviews, then clicks "Add to Queue". | |
| Auto + manual re-add | Auto-adds on paste AND a "Clear / re-paste" button to start over. | |

**User's choice:** Auto on paste
**Notes:** Classification fires immediately on `<<Paste>>` event. Input box clears after processing.

---

## Claude's Discretion

- **A — Input widget layout**: `tk.Text` widget in `input_frame`, height ~80px, placeholder hint text, "Start Demo" button removed (Phase 1 placeholder only)
- **C — Type badge visual**: Row-level Treeview tag colors — `spotify` tag (#1DB954), `youtube` tag (#EF4444); text "Spotify"/"YouTube" in Type column
- **D — URL splitting**: Newline-split, strip, skip blank lines
- **E — Classification logic**: Regex for `open.spotify.com/...` and `youtube.com/watch` / `youtu.be/`
- **F — Inline error display**: `"Invalid URL"` in type column + `"Skipped — bad URL"` in status column, both with error tag

## Deferred Ideas

None.
