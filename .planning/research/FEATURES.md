# TuneBridge — Features Research (v1.0 New Features)

**Date:** 2026-05-06
**Scope:** YouTube URL direct input + per-song folder selection UX patterns
**Confidence:** MEDIUM-HIGH (reference tools: spotdl v4, beets, MusicBrainz Picard, youtube-dl GUIs)

---

## Key Findings

- **Mixed URL batch input is table stakes.** spotdl v4, yt-dlp, and every youtube-dl GUI accept heterogeneous URL lists silently — detection by URL pattern, no user declaration. Rejecting a YouTube URL in "Spotify mode" feels like a bug.
- **Per-song folder dialog mid-pipeline is a differentiator.** No GUI downloader does this. beets does it in CLI. The threading.Event handshake already in ARCHITECTURE.md is the correct implementation.
- **Last-used folder must persist cross-session.** OS file dialogs remember within-session always. Cross-session persistence (`~/.tunebridge_state.json`) is expected by power users — genuine differentiator vs beets and spotdl.
- **YouTube title parse must be heuristic + shown to user.** "Artist - Title (Official Video)" is the dominant pattern. Strip noise tokens. Always label guessed fields with "(guessed)" — never present inferred data as confirmed.
- **Skip-without-cancel is non-negotiable.** Every batch tool allows per-item skip. Missing this forces users to cancel the whole batch.

---

## Mixed-Source Input UX

**Detection logic (per URL, silent):**
```
"open.spotify.com/track" → SpotifyPath
"youtube.com/watch" or "youtu.be/"  → YouTubePath
else → inline error on that row (not modal), batch continues
```

**UX rules:**
- Each URL gets its own batch row immediately on paste.
- Row shows type badge: `[Spotify]` or `[YouTube]` — user sees detection result before hitting Start.
- Invalid URLs: inline error state on that row only. No modal. Rest of batch unaffected.
- Mixed batches run in parallel — no ordering constraint between Spotify and YouTube rows.

**What NOT to do:**
- No "source mode" toggle — it breaks mixed batches.
- No Spotify lookup for YouTube URLs (PROJECT.md is explicit).
- No silent skip of unrecognized URLs — always surface the error on the row.

---

## Per-Song Folder Selection Patterns

**beets interactive import (`beet import -t`):**
- Shows: proposed destination path + metadata + match confidence BEFORE asking.
- User choices: Apply / More candidates / Skip / Use as-is / Enter path manually / Quit.
- Critical: user sees the full proposed path before confirming. TuneBridge must do the same.
- beets does NOT persist last-used folder — derives from library root + metadata. TuneBridge's last-used memory is a differentiator even vs beets.

**MusicBrainz Picard:** Global scripting rule, no per-file folder confirmation. Lesson: global rules are fast but wrong for edge cases — the per-item dialog is the safety valve.

**youtube-dl GUIs:** Output folder set once globally. Per-item override universally absent. TuneBridge's implementation is novel in this space.

**Dialog design:**
```
Song: "Bohemian Rhapsody"
Artist: Queen  (or "Queen (guessed)" for YouTube path)
Detected type: Album track / Single
Proposed folder: BoqueronPlaylist/432hz/Queen_432Hz/A Night at the Opera/
[Editable path field]                              [Browse...]
[ OK ]  [ Skip this song ]
```

**Key rules:**
1. Show song identity at top — user must know which song when dialogs queue.
2. Editable text field for path — advanced users paste faster than navigating.
3. Browse opens `tkinter.filedialog.askdirectory(initialdir=last_confirmed_folder)`.
4. `last_confirmed_folder` updates on every OK. Persist to `~/.tunebridge_state.json`.
5. "Skip this song" required — no cancel-all from this dialog.
6. X button on dialog = Skip (not cancel-batch).
7. Dialogs appear as songs complete download/retune — not all at once.
8. If two songs finish simultaneously: queue dialogs, show one at a time. Never stack two folder dialogs.

---

## Metadata Fallback Strategies

**YouTube extracts:** `title`, `channel`, `duration`, `view_count`. No guaranteed `artist`/`album`/`track_number`.

**Title parse heuristic (apply in order):**
```python
# Pattern 1: "Artist - Title"
m = re.match(r'^(.+?)\s*[-–—]\s*(.+)$', yt_title)
if m: artist_guess, title_guess = m.group(1), m.group(2)

# Pattern 2: channel as artist fallback
elif channel: artist_guess, title_guess = channel_name, yt_title

# Pattern 3: total unknown
else: artist_guess, title_guess = "Unknown", yt_title
```

**Noise strip after parse:**
Remove from `title_guess`: `(Official Video)`, `(Official Audio)`, `(Lyrics)`, `(HQ)`, `[HD]`, `(ft. ...)`, year patterns `(YYYY)`.

**Folder proposal from YouTube metadata:**
- No album info → always classify as "Singles" (safe default).
- Proposed path: `<root>/<ArtistGuess>_432Hz/Singles/`
- If artist_guess == "Unknown" → `_Unsorted/` bucket.

**Show guesses explicitly:**
```
Artist (guessed): Queen
Title (guessed): Bohemian Rhapsody
Folder type: Singles (YouTube — no album data)
```
Never present a guessed value without the "(guessed)" label.

**Filename:**
- Spotify path: `Artist - Title.mp3` (clean metadata)
- YouTube path: `{artist_guess} - {title_guess}.mp3`
- Ultimate fallback: sanitized raw yt_title

---

## Table Stakes vs Differentiators

**Table Stakes (missing = feels broken):**

| Feature | Why Expected |
|---------|--------------|
| Auto-detect URL type per row | Every batch downloader does this |
| Inline error on bad URL (not modal) | Modal for one bad URL in 20-song batch is unacceptable |
| Last-used folder within session | Every OS file dialog does this |
| Skip individual song without canceling batch | Universal in batch tools |
| Show proposed folder before confirmation | User cannot validate what they cannot see |
| Strip YouTube title noise | Raw `(Official Video)` in filename = amateur output |
| Proposed filename shown in dialog | User must know what file will be named |

**Differentiators (not expected, valued — TuneBridge's advantage):**

| Feature | Value | Effort |
|---------|-------|--------|
| Per-song folder dialog mid-pipeline | No GUI downloader has this | Medium (architecture already designed) |
| Last-used folder cross-session persistence | beets/spotdl don't do this | Low (JSON file) |
| "(guessed)" label on inferred fields | Honest UX; user knows what's confirmed | Low (display only) |
| `_Unsorted/` bucket for unknown metadata | Safe fallback, no data loss | Low (one path constant) |
| Type badge `[Spotify]`/`[YouTube]` on row | Immediate detection feedback | Low (label widget) |

**Anti-Features (do not build):**

| Anti-Feature | Instead |
|--------------|---------|
| Global "source mode" toggle | Auto-detect per URL |
| Spotify lookup for YouTube URLs | Direct download + title parse |
| AcoustID fingerprint for metadata recovery | Title heuristic + user confirmation |
| Per-song 432Hz choice | Batch-level toggle (PROJECT.md) |
| All folder dialogs shown at batch start | Show only after that song's download completes |
| Silent metadata fallback | Always surface the guess with label |

---

## Feature Dependencies

```
URL type detection (per row)
    → Spotify URL → SpotifyService → YouTubeService.search → download
    → YouTube URL → YouTubeService.direct_download → title_parse → metadata_guess

metadata_guess (YouTube path)
    → folder_proposal (Singles default / Unsorted if artist unknown)
    → folder_dialog (shows guess with label)

folder_dialog
    → last_used_folder update → persisted to ~/.tunebridge_state.json
    → "Skip" → song marked SKIPPED → not uploaded to iBroadcast
```

---

## MVP for This Milestone

**Must ship:**
1. URL auto-detection per row
2. Per-song folder dialog with proposed path visible and editable
3. Last-used folder memory (session + JSON persistence)
4. YouTube title heuristic parse + noise strip
5. "(guessed)" label on inferred fields
6. Skip per song without canceling batch
7. Type badge `[Spotify]`/`[YouTube]` on batch row

**Defer:**
- AcoustID fallback — wrong dependency for this stack
- Spotify lookup for YouTube URLs — out of scope (PROJECT.md)
- Multi-level undo for folder choices — not justified for v1

---

*Features research: 2026-05-06 — focused on v1.0 new features only*
