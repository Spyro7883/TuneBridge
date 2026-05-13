# Phase 3: Metadata Services - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-13
**Phase:** 03-metadata-services
**Areas discussed:** Credentials storage, Fetch trigger, Row display, YouTube title parsing

---

## Credentials Storage

| Option | Description | Selected |
|--------|-------------|----------|
| .env file + python-dotenv | Standard pattern. `pip install python-dotenv`, read with `load_dotenv()`. User creates .env in project root. Easy to keep out of git. | ✓ |
| Environment variables only | No .env file — user must set env vars before running. Simpler code, less convenient for desktop app. | |
| Simple config.json in app dir | JSON file with keys. Easy to edit, but plain-text and easy to accidentally commit. | |

**User's choice:** `.env file + python-dotenv`
**Notes:** Missing keys → warn in status bar, disable Spotify fetch for those rows. App starts fine.

---

## Fetch Trigger

| Option | Description | Selected |
|--------|-------------|----------|
| Automatically after paste | As soon as URLs are classified and added to the table, fetch starts immediately. Same UX as Phase 2's auto-paste. | ✓ |
| On a 'Fetch Metadata' button click | User pastes, sees classified rows, then clicks a button to trigger fetching. | |
| When the main 'Start' pipeline runs | Metadata fetch is the first step of the full pipeline. No separate trigger. | |

**User's choice:** Automatically after paste

| Option | Description | Selected |
|--------|-------------|----------|
| Show 'Fetching metadata...' in status column | Row status transitions from 'Queued' to 'Fetching metadata...'. SongStatus enum already has this value. | ✓ |
| Show a spinner animation | Animated indicator while fetching. Requires QTimer or QMovie. | |
| You decide | Leave to Claude. | |

**User's choice:** Status column shows `"Fetching metadata..."` (SongStatus.FETCHING_METADATA)

---

## Row Display

| Option | Description | Selected |
|--------|-------------|----------|
| Artist — Title | URL cell replaced with human-readable label. Albums: 'Artist — Album [album]'. | ✓ |
| Title only | Just the track/video title. Simpler, loses artist context. | |
| Keep URL, add Title in new column | Original URL visible, title in column 3. Schema change required. | |

**User's choice:** Artist — Title (URL replaced)

| Option | Description | Selected |
|--------|-------------|----------|
| Inline in the cell text | Cell shows: 'The Weeknd (guessed) — Blinding Lights (guessed)'. META-03 compliant. | ✓ |
| Tooltip on hover | Cell shows clean text, tooltip shows '(guessed)'. Easy to miss. | |
| Different text color | Guessed values in muted gray. Requires tag-based coloring. | |

**User's choice:** `(guessed)` inline in cell text — never omit

| Option | Description | Selected |
|--------|-------------|----------|
| Status: 'Failed — metadata' + keep URL visible | Row shows original URL + status. Other rows unaffected. | ✓ |
| Status: 'Failed' + red row highlight | Clear red visual indicator. | |
| You decide | Leave to Claude. | |

**User's choice:** `"Failed — metadata"` status, URL preserved, per-row isolation

---

## YouTube Title Parsing

| Option | Description | Selected |
|--------|-------------|----------|
| Split on first ' - ' only | Simple and predictable. 'The Weeknd - Blinding Lights' → artist + track. | ✓ |
| Try multiple separators: ' - ', ' – ', ' \| ' | Broader match, more false positives. | |
| You decide | Leave parsing details to Claude. | |

**User's choice:** Split on first ` - ` (space-dash-space) only

| Option | Description | Selected |
|--------|-------------|----------|
| Show raw title as '(guessed)' with no artist | Cell: '(guessed) — <raw title>'. Honest. | ✓ |
| Use channel name as artist guess | Sometimes right, often wrong for VEVO channels. | |
| Mark row as needing manual metadata | Blocks automatic processing. | |

**User's choice:** No ` - ` match → raw title shown as `(guessed)`, no artist field, channel name stored internally only

---

## Claude's Discretion

- HTTP retry strategy for token endpoint (single attempt is fine for Phase 3)
- Token caching TTL in `SpotifyClient`
- Exact `yt_dlp.YoutubeDL` options dict
- Threading model for concurrent metadata fetches (use existing `_Dispatcher` pattern)
- `fetch_metadata_for_row()` signature implementation details

## Deferred Ideas

- Settings dialog / UI for entering Spotify credentials — new capability, not Phase 3
- Manual metadata editing per-row — later UX polish phase
- Retry button per row after metadata failure
- Spotify playlist expansion (fetching all tracks) — Phase 4 scope
