# Phase 1: Foundation - Context

**Gathered:** 2026-05-08
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver a running dark-themed tkinter window with a functional batch table scaffold and parallel thread pipeline that tracks per-song status through all states. No real processing yet — this is infrastructure + UI skeleton.

**In scope:** dark GUI window, batch table with status/type columns, ThreadPoolExecutor with `min(batch_size, 4)` workers, status state machine, thread-safe UI updates.
**Out of scope:** URL parsing, metadata fetching, actual download/retune/upload logic — those belong in Phases 2–6.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation decisions delegated to Claude — user had no specific preferences. Apply best judgment consistent with `retune_app.py` patterns and the requirements below.

**Guidance for planner:**
- Batch table widget: use `ttk.Treeview` — standard tkinter tabular widget; acceptable styling limitations for Phase 1 placeholder badges
- Module structure: single file `tunebridge.py` for Phase 1; split into modules only if planner determines it significantly eases Phase 2+ integration
- Thread→UI update: follow `retune_app.py` pattern — `self.after(0, callback)` for all cross-thread GUI mutations
- Window layout: title header + batch table (dominant area) + status bar at bottom; input area and controls are Phase 2+ responsibility; add minimal placeholders if natural

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Existing Implementation
- `retune_app.py` — reference implementation; reuse `ThreadPoolExecutor` pattern, `self.after(0, ...)` thread-safety pattern, ttk style setup

### Requirements
- `.planning/REQUIREMENTS.md` — REQ-IDs PROC-01, PROC-02, GUI-01 (Phase 1 scope)
- `.planning/ROADMAP.md` — Phase 1 success criteria (colors, state machine states, thread count formula)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `ThreadPoolExecutor` + `as_completed` pattern (retune_app.py:323–341) — reuse directly for parallel worker pool
- `self.after(0, callback)` pattern (retune_app.py:338–342) — only safe way to update tkinter from worker threads
- `ttk.Style` setup (retune_app.py:211–218) — replicate structure, replace colors with `#121212`/`#1DB954`

### Established Patterns
- `tk.Tk` subclass as app entry point — TuneBridge class follows same structure as `RetuneApp`
- `threading.Lock` for serializing subprocess calls — carry forward if needed in later phases
- `daemon=True` on background threads — keeps app from hanging on close

### Integration Points
- Phase 2 will add the URL paste area above the batch table — leave layout space or a clear placeholder frame
- Phase 3+ workers will call `update_row_status(row_id, status)` — design that method signature now

</code_context>

<specifics>
## Specific Ideas

- Colors locked by GUI-01: `background="#121212"`, accent `#1DB954`, text `#FFFFFF`/`#B3B3B3`
- Status sequence locked by PROC-02: Queued → Fetching metadata → Downloading → Retuning → Awaiting folder → Saving → Uploading → Done ✓ / Failed ✗
- Thread count formula locked by PROC-01: `min(batch_size, 4)` — not hardcoded, recalculated per batch
- `[Spotify]` and `[YouTube]` type badge columns exist as placeholders in the table (not yet populated)

</specifics>

<deferred>
## Deferred Ideas

None — no scope creep during discussion.

</deferred>

---

*Phase: 1-Foundation*
*Context gathered: 2026-05-08*
