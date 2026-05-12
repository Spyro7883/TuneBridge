# Phase 2: Input & Detection - Context

**Gathered:** 2026-05-13
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver a working URL paste area that accepts a mixed batch of Spotify and YouTube URLs, classifies each immediately on paste, shows a type badge per row, and flags malformed/unrecognized URLs inline. No metadata fetch, no download — classification only.

**In scope:** paste input widget, URL splitting, Spotify/YouTube regex classification, type badge rendering in the batch table, inline error state for invalid rows.
**Out of scope:** metadata fetching (Phase 3), download (Phase 4), any processing beyond classification.

</domain>

<decisions>
## Implementation Decisions

### A — Input Widget Layout (Claude's discretion)
Replace the Phase 1 "Start Demo" placeholder in `self.input_frame` with a `tk.Text` widget:
- Expand `input_frame` height to ~80px (from 60px, remove `pack_propagate(False)` constraint or increase fixed height)
- Add placeholder hint text rendered in dim color (e.g., `#555555`) — "Paste Spotify or YouTube URLs here (one per line)" — cleared on first focus/paste
- "Start Demo" button removed — it was Phase 1 only

### B — Paste Trigger (user decision: auto on paste)
Rows are added and classified **immediately on paste** — no button required.
- Bind `<<Paste>>` event on the `tk.Text` widget
- After paste fires: read widget contents, split into URLs, classify, populate table rows, then clear the widget
- The input box acts as a transient staging area, not a persistent list

### C — URL Splitting (Claude's discretion)
Split pasted text by newlines. Strip leading/trailing whitespace per line. Skip blank lines. Each non-blank line is treated as one URL candidate.

### D — Classification Logic (Claude's discretion)
Use regex to classify each URL candidate:
- **Spotify**: matches `open\.spotify\.com/(track|album|playlist|artist)/` → type `"Spotify"`
- **YouTube**: matches `(youtube\.com/watch\?.*v=|youtu\.be/)` → type `"YouTube"`
- **Invalid/unrecognized**: anything else → error state

Classification runs synchronously on the main thread immediately after paste (no threading needed — regex is instant).

### E — Type Badge Visual (Claude's discretion)
Render type in the existing `"type"` column of `BatchTable`:
- Text: `"Spotify"` / `"YouTube"` / `"Invalid URL"`
- Row-level Treeview tag colors (extending existing `_TAG_COLORS`):
  - `"spotify"` tag → foreground `#1DB954` (green, matches app brand)
  - `"youtube"` tag → foreground `#EF4444` (red, distinct)
  - `"error"` tag (already exists or add) → foreground `#EF4444`, distinct style
- `update_row_type()` already exists on `BatchTable` — use it directly

### F — Inline Error Display (Claude's discretion)
For malformed/unrecognized URLs:
- Set type column to `"Invalid URL"` with `error` tag (red foreground)
- Set status column to `"Skipped — bad URL"` with `error` tag
- The row remains visible but visually distinct; other rows are unaffected
- No separate error column needed — repurpose existing type + status columns

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` §INPUT — INP-01, INP-02, INP-03 (paste area, type badges, inline errors)
- `.planning/ROADMAP.md` §Phase 2 — success criteria and phase scope

### Existing Implementation
- `tunebridge.py` — full source; `BatchTable` (L1–~80), `TuneBridgeApp._build_layout()` (input_frame placeholder), `_schedule()` / `_poll_updates()` queue pattern

### Prior Phase Context
- `.planning/phases/01-foundation/01-CONTEXT.md` — established patterns (Treeview tags, queue-based UI updates, single-file structure)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `BatchTable.add_row(url, title, url_type) -> str` — add a classified row directly with type pre-set
- `BatchTable.update_row_type(row_id, url_type)` — update type after row exists
- `BatchTable.update_row_status(row_id, status)` — set error status on invalid rows
- `BatchTable.clear()` — reset table if needed
- `TuneBridgeApp._schedule(func, *args)` — queue UI updates from any thread (not needed for Phase 2 since classification is synchronous, but available)
- `self.input_frame` — already packed in `_build_layout()` at correct position (between title and batch table)

### Established Patterns
- `ttk.Treeview` tag-based row coloring via `_TAG_COLORS` dict + `tag_configure()`
- `tk.Tk` subclass with `_build_layout()` method — add Phase 2 widget setup inside `_build_layout()`
- Single file `tunebridge.py` — no module split needed for Phase 2

### Integration Points
- Phase 2 populates `self.input_frame` (currently 60px placeholder) — Phase 3 workers will call `add_row()` result iids returned from Phase 2's classification pass
- Phase 3 reads `url_type` set by Phase 2 to route Spotify vs YouTube paths

</code_context>

<specifics>
## Specific Ideas

No specific visual references provided — follow existing dark theme aesthetics and Spotify green brand color for badges.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 02-input-detection*
*Context gathered: 2026-05-13*
