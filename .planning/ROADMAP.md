# TuneBridge — Roadmap v1.0

**Milestone:** v1.0 Full Pipeline
**Granularity:** Standard
**Requirements mapped:** 19/19

---

## Phases

- [x] **Phase 1: Foundation** — Dark GUI shell, batch table scaffold, threaded pipeline infrastructure, status state machine
- [ ] **Phase 2: Input & Detection** — Paste area, URL type classification, type badges, inline per-row error display
- [ ] **Phase 3: Metadata Services** — Spotify Web API client, yt-dlp info extraction, "(guessed)" label convention
- [ ] **Phase 4: Download Pipeline** — Dual-path download (ytsearch vs direct), 432Hz retune toggle, audio-only MP3 output
- [ ] **Phase 5: Organization** — Folder proposal logic, per-song folder confirmation dialog with threading.Event safety, skip support, file save
- [ ] **Phase 6: iBroadcast Upload** — Auth, duplicate check, upload to iBroadcast after file save

---

## Phase Details

### Phase 1: Foundation
**Goal**: A running dark-themed GUI window with a functional batch table and parallel thread pipeline that tracks per-song status through all states
**Depends on**: Nothing
**Requirements**: PROC-01, PROC-02, GUI-01
**Success Criteria** (what must be TRUE):
  1. App launches with background `#121212`, accent `#1DB954`, white/gray text — visually distinct from retune_app.py
  2. Batch table renders one row per song with a status column that cycles through: Queued → Fetching metadata → Downloading → Retuning → Awaiting folder → Saving → Uploading → Done / Failed
  3. Parallel processing uses `min(batch_size, 4)` threads — verified by running 5+ songs and observing max 4 concurrent workers
  4. `[Spotify]` and `[YouTube]` type badge columns exist as placeholders in the table (not yet populated)
**Plans**: 2 plans
**UI hint**: yes

Plans:
- [x] 01-01-PLAN.md — Test scaffold: pytest config + 7 test cases for SongStatus, BatchTable API, dark theme colors
- [x] 01-02-PLAN.md — Core implementation: tunebridge.py with TuneBridgeApp, BatchTable, SongStatus, mock pipeline

### Phase 2: Input & Detection
**Goal**: Users can paste a mixed batch of Spotify and YouTube URLs and see each row classified or flagged before any processing begins
**Depends on**: Phase 1
**Requirements**: INP-01, INP-02, INP-03
**Success Criteria** (what must be TRUE):
  1. User pastes multiple URLs (mixed Spotify and YouTube) into a single input area and each URL becomes a separate row
  2. Each row shows a `[Spotify]` or `[YouTube]` badge immediately after paste, before any download or metadata fetch
  3. An unrecognized or malformed URL shows a red inline error on that row only — other valid rows are unaffected and remain processable
**Plans**: TBD

### Phase 3: Metadata Services
**Goal**: App can resolve full metadata for any URL in the batch — confirmed fields from Spotify API or extracted fields (labeled as guessed) from YouTube
**Depends on**: Phase 2
**Requirements**: META-01, META-02, META-03
**Success Criteria** (what must be TRUE):
  1. A Spotify URL row transitions to "Fetching metadata" and populates artist, album, title, and release type using Spotify client credentials (no user login required)
  2. A YouTube URL row transitions to "Fetching metadata" and populates title and channel name via yt-dlp info extraction without calling Spotify
  3. Fields inferred by parsing a YouTube title (artist, track title) are visibly labeled "(guessed)" in the batch row — never shown without the label
**Plans**: TBD

### Phase 4: Download Pipeline
**Goal**: Every song in the batch downloads as an audio-only MP3, with optional 432Hz retune applied, using the correct path for its URL type
**Depends on**: Phase 3
**Requirements**: DL-01, DL-02, DL-03, DL-04
**Success Criteria** (what must be TRUE):
  1. A Spotify-sourced song searches YouTube via yt-dlp ytsearch (artist + title + "audio") and downloads the best audio-only match as MP3
  2. A YouTube-sourced song downloads directly from its provided URL as audio-only MP3 — no search step
  3. User can select "440Hz (original)" or "432Hz (retune)" for the batch before processing starts — the toggle is visible and the choice persists for all songs in that batch
  4. When 432Hz is selected, the downloaded file is retuned via librosa pitch shift before being passed to the organization step; row status shows "Retuning" during this step
**Plans**: TBD

### Phase 5: Organization
**Goal**: Each downloaded song is confirmed by the user into an existing folder before saving — with a smart default, skip option, and no folder creation
**Depends on**: Phase 4
**Requirements**: ORG-01, ORG-02, ORG-03, ORG-04
**Success Criteria** (what must be TRUE):
  1. For each song, a folder confirmation dialog appears with a pre-filled proposed path derived from metadata (artist/album/single) and the last confirmed folder as the default suggestion
  2. User can confirm the proposed path, type a different path in a text field, or browse via a directory picker — all within the dialog
  3. User can click Skip in the dialog to skip saving that song without blocking or canceling any other song in the batch
  4. Confirming a folder saves the processed MP3 into that folder — app never creates, renames, or deletes any folder; only writes the file
  5. Only one folder confirmation dialog is shown at a time regardless of how many songs reach "Awaiting folder" concurrently
**Plans**: TBD
**UI hint**: yes

### Phase 6: iBroadcast Upload
**Goal**: Every saved song is automatically uploaded to iBroadcast, with duplicate protection preventing re-upload of already-present tracks
**Depends on**: Phase 5
**Requirements**: UPL-01, UPL-02
**Success Criteria** (what must be TRUE):
  1. App authenticates to iBroadcast using stored username/password credentials — no manual login step during batch processing
  2. Before uploading, app checks iBroadcast for the track; if it already exists, the upload is skipped and the row is marked accordingly (not as Failed)
  3. A new track is uploaded successfully and the row transitions to "Done" after upload completes
**Plans**: TBD

---

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 2/2 | Complete | 2026-05-12 |
| 2. Input & Detection | 0/? | Not started | - |
| 3. Metadata Services | 0/? | Not started | - |
| 4. Download Pipeline | 0/? | Not started | - |
| 5. Organization | 0/? | Not started | - |
| 6. iBroadcast Upload | 0/? | Not started | - |

---

*Last updated: 2026-05-12*
