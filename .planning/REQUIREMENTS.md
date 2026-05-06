# TuneBridge — Requirements v1.0

**Milestone:** v1.0 Full Pipeline
**Date:** 2026-05-06
**Status:** Approved

---

## Milestone Requirements

### INPUT

- [ ] **INP-01**: User can paste one or more Spotify and/or YouTube track URLs into the batch input field (mixed types supported in the same batch)
- [ ] **INP-02**: App detects URL type per row and shows a type badge `[Spotify]` or `[YouTube]` before processing starts
- [ ] **INP-03**: Invalid or unrecognized URLs show an inline per-row error without aborting or affecting other rows in the batch

### METADATA

- [ ] **META-01**: For Spotify URLs, app fetches artist, album, title, and release type via Spotify Web API using client credentials flow (no user login)
- [ ] **META-02**: For YouTube URLs, app extracts title and channel name via yt-dlp info extraction (no Spotify lookup performed)
- [ ] **META-03**: Metadata fields inferred from YouTube title parsing (artist, title) are labeled "(guessed)" in the UI — never presented as confirmed

### DOWNLOAD

- [ ] **DL-01**: For Spotify URLs, app searches YouTube using yt-dlp ytsearch and downloads the best audio-only match as MP3
- [ ] **DL-02**: For YouTube URLs, app downloads directly from the provided URL as audio-only MP3
- [ ] **DL-03**: User selects 440Hz (keep original) or 432Hz (retune) per batch before processing starts
- [ ] **DL-04**: When 432Hz is selected, downloaded audio is retuned via librosa pitch shift before saving

### ORGANIZATION

- [ ] **ORG-01**: App proposes a destination folder per song based on metadata (artist/album/single classification); last confirmed folder is suggested as the default for the next song in the batch
- [ ] **ORG-02**: User can confirm the proposed folder, edit it via a text field, or browse to a different folder using a directory picker — per song, before saving
- [ ] **ORG-03**: User can skip an individual song from the folder confirmation dialog without canceling or affecting the rest of the batch
- [ ] **ORG-04**: App saves the processed MP3 into the confirmed existing folder; app never creates, renames, or deletes folders

### UPLOAD

- [ ] **UPL-01**: App uploads each saved file to iBroadcast after saving using username/password authentication
- [ ] **UPL-02**: App checks for duplicate tracks on iBroadcast before uploading and skips upload if the track already exists

### PROCESSING

- [ ] **PROC-01**: Batch processing runs in parallel threads with thread count = `min(batch_size, 4)` (dynamic, not hardcoded)
- [ ] **PROC-02**: Each song displays real-time status in the batch table: Queued → Fetching metadata → Downloading → Retuning → Awaiting folder → Saving → Uploading → Done ✓ / Failed ✗

### GUI

- [ ] **GUI-01**: Desktop GUI built with tkinter using a dark minimal design: background `#121212`, accent `#1DB954` (green), text `#FFFFFF`/`#B3B3B3`; batch table with per-row progress indicator and `[Spotify]`/`[YouTube]` type badges; visually distinct from retune_app.py

---

## Future Requirements

- Cross-session folder memory persistence (`~/.tunebridge_state.json`) — deferred from v1.0 (session-only is sufficient)
- iBroadcast playlist assignment (assign to specific playlist after upload) — deferred to v1.1
- Configurable yt-dlp audio quality (currently hardcoded 192K MP3) — deferred to v1.1

## Out of Scope

- Spotify user account login / OAuth — client credentials only (metadata lookup, no playback)
- Support for sources other than Spotify and YouTube — Apple Music, SoundCloud, etc. deferred
- Creating or renaming folders on disk — read-only to existing folder structure
- Streaming or playback within the app — download and organize only
- Automatic background polling — user triggers sync manually via UI
- AcoustID fingerprint for metadata recovery — overkill for this stack

---

## Traceability

| REQ-ID | Phase | Notes |
|--------|-------|-------|
| PROC-01 | Phase 1 | Foundation — thread pool infrastructure |
| PROC-02 | Phase 1 | Foundation — status state machine + batch table |
| GUI-01 | Phase 1 | Foundation — dark theme base window and table scaffold |
| INP-01 | Phase 2 | Input & Detection — paste area |
| INP-02 | Phase 2 | Input & Detection — URL type badges |
| INP-03 | Phase 2 | Input & Detection — inline per-row errors |
| META-01 | Phase 3 | Metadata Services — Spotify Web API |
| META-02 | Phase 3 | Metadata Services — yt-dlp info extraction |
| META-03 | Phase 3 | Metadata Services — "(guessed)" label convention |
| DL-01 | Phase 4 | Download Pipeline — Spotify path (ytsearch) |
| DL-02 | Phase 4 | Download Pipeline — YouTube path (direct) |
| DL-03 | Phase 4 | Download Pipeline — 432Hz toggle |
| DL-04 | Phase 4 | Download Pipeline — librosa retune step |
| ORG-01 | Phase 5 | Organization — folder proposal + last-used default |
| ORG-02 | Phase 5 | Organization — confirm/edit/browse dialog |
| ORG-03 | Phase 5 | Organization — per-song skip |
| ORG-04 | Phase 5 | Organization — file save (no folder creation) |
| UPL-01 | Phase 6 | iBroadcast Upload — auth + upload |
| UPL-02 | Phase 6 | iBroadcast Upload — duplicate check |

---

*Last updated: 2026-05-06*
