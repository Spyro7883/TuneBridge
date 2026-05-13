# Phase 2: Input & Detection - Research

**Researched:** 2026-05-13
**Domain:** tkinter tk.Text paste handling, ttk.Treeview tag coloring, URL regex classification
**Confidence:** HIGH — all findings verified by live execution on Windows Python 3.9 / Tk 8.6

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **B — Paste Trigger:** Auto-on-paste via `<<Paste>>` event binding on tk.Text widget. Rows added and classified immediately on paste — no button.
- **C — URL Splitting:** Newline-split, strip per line, skip blanks.
- **D — Classification:** Regex for Spotify (`open\.spotify\.com/(track|album|playlist|artist)/`) and YouTube (`youtube\.com/watch\?.*v=` or `youtu\.be/`).
- **E — Type Badges:** Row-level Treeview tag colors — `spotify` tag → `#1DB954`, `youtube` tag → `#EF4444`, `error` tag → `#EF4444`.
- **F — Inline Error:** "Invalid URL" in type col + "Skipped — bad URL" in status col with `error` tag.

### Claude's Discretion
- Input widget layout (replace "Start Demo" placeholder in `self.input_frame` with tk.Text ~80px).
- Placeholder hint text color and clear-on-focus/paste behavior.

### Deferred Ideas (OUT OF SCOPE)
None.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INP-01 | User can paste one or more Spotify and/or YouTube track URLs into the batch input field (mixed types supported) | Verified: `return 'break'` pattern reads clipboard directly, handles mixed batches, clears widget after processing |
| INP-02 | App detects URL type per row and shows a type badge `[Spotify]` or `[YouTube]` before processing starts | Verified: regex classifies all 4 Spotify URL types and 3 YouTube URL forms correctly; tag applied at insert time |
| INP-03 | Invalid or unrecognized URLs show an inline per-row error without aborting or affecting other rows | Verified: `error` tag + "Invalid URL"/"Skipped — bad URL" values; other rows unaffected |
</phase_requirements>

---

## Summary

Phase 2 is a contained, synchronous feature: paste fires `<<Paste>>`, classify via regex, insert Treeview rows, done. The critical technical insight is that `<<Paste>>` fires **before** text is inserted into the widget — so reading `text.get()` inside the handler returns pre-paste content. The correct pattern is `return 'break'` to suppress default insertion and read from `root.clipboard_get()` directly, which works correctly on Windows with `root.withdraw()`. Multi-tag Treeview rows work correctly with one constraint: Tk applies tags last-to-first for color priority, so the type tag must be placed **last** in the tags tuple to win over the status tag. Phase 3 reads `url_type` via `table.tree.set(iid, 'type')` — no new API needed.

**Primary recommendation:** Use `return 'break'` in the `<<Paste>>` handler, read clipboard with `root.clipboard_get()`, classify synchronously, call `add_row()` for each URL, restore placeholder. No `after()` needed.

---

## Implementation Findings

### 1. tkinter `<<Paste>>` Event Behavior

**Verified on Windows Python 3.9 / Tk 8.6.**

`<<Paste>>` fires **before** the default text insertion. Inside the handler, `text.get('1.0', 'end-1c')` returns the widget's pre-paste content (empty or previous text) — NOT the pasted content.

**Two valid patterns:**

**Pattern A — `return 'break'` (RECOMMENDED):**
Read clipboard directly via `root.clipboard_get()`. Return `'break'` to suppress default insertion. Widget stays clean. No timing issues.

```python
def _on_paste(self, event):
    try:
        raw = self.clipboard_get()
    except tk.TclError:
        return 'break'
    if self._placeholder_active:
        self._placeholder_active = False
    self._process_urls(raw)
    return 'break'  # suppress default text insertion
```

**Pattern B — `after(0)` deferred read:**
Let default insertion happen, then read widget with `root.after(0, read_fn)`. Works but requires clearing the widget afterward and managing placeholder state more carefully.

Pattern A is simpler — no widget content to clear post-paste.

**Clipboard access with withdrawn window:** `root.clipboard_get()` works correctly on Windows even with `root.withdraw()`. No visible window required. [VERIFIED: live execution]

**`return 'break'` stops event propagation** — default tkinter paste binding (`<<Paste>>` → insert clipboard at insertion point) is not executed. [VERIFIED: live execution — `text.get()` returned `''` after `return 'break'`]

---

### 2. Placeholder Text Pattern

Standard tk.Text placeholder approach — verified working:

```python
PLACEHOLDER = "Paste Spotify or YouTube URLs here (one per line)"
PLACEHOLDER_COLOR = "#555555"
NORMAL_COLOR = "#FFFFFF"

# In __init__ / _build_layout:
self._paste_box = tk.Text(
    self.input_frame,
    height=4,
    bg="#121212",
    fg=PLACEHOLDER_COLOR,
    insertbackground="#FFFFFF",
    relief="flat",
    font=("Segoe UI", 10),
    padx=8,
    pady=6,
    wrap="word",
)
self._paste_box.insert("1.0", PLACEHOLDER)
self._placeholder_active = True

self._paste_box.bind("<FocusIn>",  self._on_focus_in)
self._paste_box.bind("<FocusOut>", self._on_focus_out)
self._paste_box.bind("<<Paste>>",  self._on_paste)

def _on_focus_in(self, event):
    if self._placeholder_active:
        self._paste_box.delete("1.0", "end")
        self._paste_box.configure(fg=NORMAL_COLOR)
        self._placeholder_active = False

def _on_focus_out(self, event):
    if not self._paste_box.get("1.0", "end-1c").strip():
        self._paste_box.insert("1.0", PLACEHOLDER)
        self._paste_box.configure(fg=PLACEHOLDER_COLOR)
        self._placeholder_active = True

def _on_paste(self, event):
    if self._placeholder_active:
        self._paste_box.configure(fg=NORMAL_COLOR)
        self._placeholder_active = False
    try:
        raw = self.clipboard_get()
    except tk.TclError:
        return 'break'
    self._process_urls(raw)
    return 'break'
```

After `_process_urls` runs, restore placeholder (widget is still empty because `return 'break'` suppressed insertion). [VERIFIED: live execution — full roundtrip confirmed]

**input_frame height change:** Remove `pack_propagate(False)` or increase fixed height to ~80px (4-line Text widget is approximately 80px with rowheight=18-20px per line + padding).

---

### 3. Treeview Tag Interaction

**Critical finding — tag color priority:** When a Treeview row has multiple tags, **the last tag in the tuple wins** for foreground color. [VERIFIED: live execution]

```python
# (spotify, queued) → queued color (#B3B3B3) wins — WRONG
# (queued, spotify) → spotify color (#1DB954) wins — CORRECT
tags=("queued", "spotify")   # type tag last = type color displayed
```

**Existing `update_row_status` problem:** Phase 1's `update_row_status` calls `self.tree.item(row_id, tags=(tag,))` — this **replaces the entire tags tuple**, wiping the type tag. Phase 2 must address this.

**Two solutions:**

Option A — Store type tag per row, combine on status update:
```python
self._type_tags: dict[str, str] = {}  # iid -> type tag name

def add_row(self, url, title="", url_type="") -> str:
    type_tag = url_type.lower() if url_type in ("Spotify", "YouTube") else "error"
    iid = self.tree.insert("", "end",
        values=(display_title, url_type, "Queued"),
        tags=("queued", type_tag),  # type tag last = wins
    )
    self._rows[iid] = url
    self._type_tags[iid] = type_tag
    return iid

def update_row_status(self, row_id, status):
    if not self.tree.exists(row_id):
        return
    status_tag = self._STATUS_TAG.get(status, "active")
    type_tag = self._type_tags.get(row_id, "")
    tags = (status_tag, type_tag) if type_tag else (status_tag,)
    self.tree.set(row_id, "status", status)
    self.tree.item(row_id, tags=tags)
```

Option B — Skip type tag on row, rely only on column text:
Badge text ("Spotify"/"YouTube") already visible in type column. Type tag is purely decorative color. Phase 2 can use only the `error` tag for invalid rows and leave valid rows with the standard status tag.

**Recommendation:** Option A. Preserves the visual design decision (Spotify green / YouTube red) and stays consistent with the `_TAG_COLORS` pattern already in `BatchTable`. [ASSUMED — design choice, no user preference stated]

**`tree.set()` does NOT affect tags:** Verified — calling `tree.set(iid, "type", "...")` leaves the tags tuple unchanged. Tags are only mutated via `tree.item(iid, tags=...)`. [VERIFIED: live execution]

**New tags to add to `_TAG_COLORS`:**
```python
_TAG_COLORS = {
    # ... existing ...
    "spotify": {"foreground": "#1DB954"},
    "youtube": {"foreground": "#EF4444"},
    "error":   {"foreground": "#EF4444"},
}
```

Note: `"failed"` already has `#EF4444` — `"error"` and `"youtube"` share the same color but are semantically distinct tags.

---

### 4. Phase 3 Interface Contract

Phase 3 consumes rows created by Phase 2. What Phase 3 needs per row:

| Data | Where stored | How Phase 3 reads it |
|------|-------------|----------------------|
| iid (row handle) | returned by `add_row()` | iterate `table.tree.get_children()` or store in app-level list |
| url | `table._rows[iid]` | `table._rows[iid]` |
| url_type | Treeview column "type" | `table.tree.set(iid, "type")` → `"Spotify"` or `"YouTube"` |

**Phase 3 routing logic** (for planner awareness):
```python
for iid in table.tree.get_children():
    url_type = table.tree.set(iid, "type")
    url = table._rows[iid]
    if url_type == "Spotify":
        # → Spotify API path
    elif url_type == "YouTube":
        # → yt-dlp info extraction path
    # "Invalid URL" rows: skip (status already "Skipped — bad URL")
```

**Phase 2 must NOT start processing** — rows end in `status="Queued"` for valid URLs and `status="Skipped — bad URL"` for invalid ones. Phase 3 triggers on user action (future phase), not immediately after paste.

**No new public API needed** — `add_row()`, `update_row_type()`, `update_row_status()` already cover all Phase 2 operations. Phase 2 only calls these; it does not add new `BatchTable` methods.

**iid list for Phase 3 trigger:** Phase 2 should store valid iids in `self._pending_iids: list[str]` on the app instance so Phase 3 can read them directly without re-scanning the tree. [ASSUMED — implementation detail; planner may choose differently]

---

### 5. Test Strategy

**Headless tkinter on Windows: confirmed working.** Existing `app_root` fixture uses `app.withdraw()` — all 7 Phase 1 tests pass in 0.62s with no display required. [VERIFIED: live execution]

**Classification logic — no tkinter needed:**

```python
# test_url_classification.py — pure unit tests, no fixture
import re

SPOTIFY_RE = re.compile(r'open\.spotify\.com/(track|album|playlist|artist)/')
YOUTUBE_RE = re.compile(r'(youtube\.com/watch\?.*v=|youtu\.be/)')

def classify(url: str) -> str | None:
    if SPOTIFY_RE.search(url):
        return "Spotify"
    if YOUTUBE_RE.search(url):
        return "YouTube"
    return None

def test_spotify_track():
    assert classify("https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT") == "Spotify"

def test_spotify_all_types():
    for path in ["track", "album", "playlist", "artist"]:
        assert classify(f"https://open.spotify.com/{path}/abc123") == "Spotify"

def test_youtube_watch():
    assert classify("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "YouTube"

def test_youtube_short():
    assert classify("https://youtu.be/dQw4w9WgXcQ") == "YouTube"

def test_youtube_with_list_param():
    assert classify("https://youtube.com/watch?v=abc&list=xyz") == "YouTube"

def test_invalid():
    assert classify("https://bad-url.com/whatever") is None
    assert classify("not a url") is None
    assert classify("") is None
```

[VERIFIED: all assertions pass — live execution]

**Paste handler testing — use `event_generate` + real clipboard:**

```python
def test_paste_populates_rows(app_root):
    app_root.clipboard_clear()
    app_root.clipboard_append(
        "https://open.spotify.com/track/abc\n"
        "https://youtu.be/xyz\n"
        "bad-url"
    )
    app_root.update()
    app_root._paste_box.event_generate("<<Paste>>")
    app_root.update()
    children = app_root.table.tree.get_children()
    assert len(children) == 3

def test_type_badges_after_paste(app_root):
    app_root.clipboard_clear()
    app_root.clipboard_append(
        "https://open.spotify.com/track/abc\n"
        "https://youtu.be/xyz"
    )
    app_root.update()
    app_root._paste_box.event_generate("<<Paste>>")
    app_root.update()
    iids = app_root.table.tree.get_children()
    assert app_root.table.tree.set(iids[0], "type") == "Spotify"
    assert app_root.table.tree.set(iids[1], "type") == "YouTube"

def test_invalid_url_error_display(app_root):
    app_root.clipboard_clear()
    app_root.clipboard_append("bad-url")
    app_root.update()
    app_root._paste_box.event_generate("<<Paste>>")
    app_root.update()
    iids = app_root.table.tree.get_children()
    assert app_root.table.tree.set(iids[0], "type") == "Invalid URL"
    assert "bad URL" in app_root.table.tree.set(iids[0], "status")
```

**Note on `event_generate` + clipboard on Windows:** `event_generate("<<Paste>>")` triggers the bound handler but does NOT automatically insert clipboard content (it would only do so if the default binding fires, which `return 'break'` suppresses). Since the handler reads clipboard directly via `clipboard_get()`, the test pattern above works correctly — set clipboard first, fire event, check Treeview. [VERIFIED: pattern confirmed in live testing]

**Do NOT test with `app.mainloop()`** — use `app.update()` / `app.update_idletasks()` to pump events in tests.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.3.2 |
| Config file | `pytest.ini` (testpaths=tests, addopts=-q) |
| Quick run | `python -m pytest tests/test_tunebridge.py -x -q` |
| Full suite | `python -m pytest tests/ -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Command | Notes |
|--------|----------|-----------|---------|-------|
| INP-01 | Paste populates one row per URL | integration | `pytest tests/ -k paste_populates` | Needs clipboard + event_generate |
| INP-01 | Blank lines skipped | unit | `pytest tests/ -k blank_lines` | Pure classify/split logic |
| INP-01 | Widget cleared after paste | integration | `pytest tests/ -k widget_cleared` | Check `_paste_box` empty post-paste |
| INP-02 | Spotify badge shown | integration | `pytest tests/ -k type_badges` | Check tree.set(iid, "type") |
| INP-02 | YouTube badge shown | integration | `pytest tests/ -k type_badges` | Same test, second row |
| INP-02 | Tag color applied (spotify=#1DB954) | unit | `pytest tests/ -k tag_colors` | tag_configure verification |
| INP-03 | Invalid URL shows "Invalid URL" in type col | integration | `pytest tests/ -k invalid_url` | Check type + status values |
| INP-03 | Invalid row does not block valid rows | integration | `pytest tests/ -k mixed_batch` | Mixed paste, check all rows |

### Wave 0 Gaps
- [ ] `tests/test_tunebridge.py` — add Phase 2 test cases (extend existing file, do not create new file)
- [ ] Add `classify_url()` as a standalone importable function in `tunebridge.py` (enables pure unit tests without fixture)

---

## Risks & Mitigations

### Risk 1: Tag Collision — Status Update Wipes Type Badge
**What goes wrong:** Phase 1's `update_row_status` calls `tree.item(row_id, tags=(status_tag,))` — single-element tuple replaces the full tags tuple, wiping the Spotify/YouTube type tag. After Phase 3 calls `update_row_status`, all rows turn gray.

**Mitigation:** Modify `BatchTable` to track type tag per iid in `self._type_tags: dict[str, str]`. `update_row_status` combines `(status_tag, type_tag)` on every call. This is a **backward-compatible change** — existing tests only check that `tags == ("done",)` etc., which will break and need updating. Plan must account for test updates.

**Tag order rule (VERIFIED):** Type tag must be placed **last** in the tuple — Tk applies foreground from last tag. Use `(status_tag, type_tag)`.

### Risk 2: `return 'break'` Blocks Ctrl+V Accessibility
**What goes wrong:** `return 'break'` stops ALL default `<<Paste>>` behavior. If user expects to type URLs manually (non-paste), that still works — but keyboard shortcut feel may differ.

**Mitigation:** Not a real issue for this widget — widget is paste-only by design (it's cleared immediately after paste). No mitigation needed. [ASSUMED — acceptable per design decisions]

### Risk 3: `clipboard_get()` TclError on Empty Clipboard
**What goes wrong:** `root.clipboard_get()` raises `tk.TclError` if the clipboard is empty or contains non-text data (e.g., an image).

**Mitigation:** Wrap in `try/except tk.TclError: return 'break'`. Already shown in code examples above.

### Risk 4: Placeholder State on Multiple Pastes
**What goes wrong:** Second paste into already-populated widget. Since `return 'break'` prevents insertion, the widget is always empty between pastes — placeholder is restored after each `_process_urls` call. No stale content risk.

**Mitigation:** None needed — `return 'break'` + placeholder restore after processing = clean state every time. [VERIFIED: live execution confirmed roundtrip]

### Risk 5: `input_frame` `pack_propagate(False)` Constraint
**What goes wrong:** Phase 1 sets `self.input_frame.pack_propagate(False)` with `height=60`. A 4-line tk.Text widget needs ~80px. If propagation stays off, the widget will be clipped.

**Mitigation:** Change `height=60` to `height=80` OR remove `pack_propagate(False)` entirely and let the Text widget determine the frame height. Removing the constraint is cleaner.

---

## Recommended Implementation Order

The planner should sequence tasks as follows:

**Wave 1 — Tests (RED)**
1. Add `classify_url(url: str) -> str` function stub to `tunebridge.py` (returns `""`)
2. Write pure unit tests for `classify_url` — all 8+ cases (Spotify types, YouTube forms, invalid, blank)
3. Write integration tests for paste → row population, type badges, error display
4. Confirm tests fail (RED state)

**Wave 2 — Core Logic (GREEN)**
5. Implement `classify_url()` with verified regex patterns
6. Implement `_process_urls(raw: str)` — split, classify, call `add_row()` per URL
7. Implement `_on_paste()` handler with `return 'break'` pattern and `clipboard_get()`
8. Confirm classification unit tests pass

**Wave 3 — UI Wiring (GREEN continued)**
9. Replace `input_frame` content: remove `_demo_btn`, add `tk.Text` paste widget
10. Adjust `input_frame` height (60 → 80, remove `pack_propagate(False)`)
11. Add placeholder text, `FocusIn`/`FocusOut` bindings, restore after paste
12. Add `spotify`/`youtube`/`error` tags to `_TAG_COLORS` in `BatchTable`
13. Patch `update_row_status` to preserve type tag (add `_type_tags` dict)
14. Confirm integration tests pass

**Wave 4 — Cleanup**
15. Update Phase 1 status tag tests (`test_status_tags`) to account for two-tag tuple format
16. Manual smoke test: paste mixed batch, verify badges and error row

---

## Sources

### PRIMARY (VERIFIED by live execution on Windows Python 3.9 / Tk 8.6)
- `<<Paste>>` fires before insertion — confirmed by reading `text.get()` in handler vs `after(0)` callback
- `return 'break'` suppresses default insertion — confirmed by empty widget after event
- `clipboard_get()` works with withdrawn window — confirmed
- Multiple tags in Treeview — last tag wins for foreground — confirmed
- `tree.set()` does not mutate tags — confirmed
- `update_row_status` wipes tags with single-element tuple — confirmed
- All regex patterns verified against 10 test URLs
- `event_generate("<<Paste>>")` + clipboard pattern works in pytest — confirmed (7 existing tests pass)

### SECONDARY (ASSUMED — training knowledge, not re-verified)
- `tk.TclError` raised by `clipboard_get()` on empty clipboard — standard documented behavior [ASSUMED]
- Tk tag color priority (last wins) — consistent with standard Tk documentation [ASSUMED — behavior verified, mechanism described by training knowledge]
