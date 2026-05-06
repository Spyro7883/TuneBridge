# TuneBridge

## What This Is

TuneBridge is a desktop GUI application (tkinter) that takes Spotify track links, finds the exact audio match on YouTube, downloads it via yt-dlp, optionally retunes from 440Hz to 432Hz, organizes the file into an existing folder structure, and uploads it to iBroadcast — all in one automated pipeline. Built for personal music collection management.

## Core Value

Given a batch of Spotify links, TuneBridge delivers the downloaded (and optionally retuned) audio files into the right folders and uploads them to iBroadcast without manual intervention at each step.

## Current Milestone: v1.0 Full Pipeline

**Goal:** Deliver the complete TuneBridge application — end-to-end pipeline from link input to iBroadcast upload.

**Target features:**
- Dual input: Spotify URL (metadata → YouTube search → download) and YouTube URL (direct download)
- Batch processing with dynamic thread count
- Optional 440Hz → 432Hz retune per batch
- Per-song folder confirmation with last-used folder suggestion
- iBroadcast upload with duplicate check
- tkinter GUI consistent with retune_app.py

## Requirements

### Validated

- ✓ Audio retune 440Hz → 432Hz via librosa pitch shift — existing (`retune_app.py`)
- ✓ YouTube audio download via yt-dlp — existing (`retune_app.py`)
- ✓ Threaded parallel downloads — existing (`retune_app.py`)

### Active

- [ ] Accept batch Spotify AND/OR YouTube track links (paste multiple at once; each link can be either type)
- [ ] For Spotify links: extract track metadata (artist, album, title, release type) via Spotify Web API
- [ ] For YouTube links: extract title and channel name via yt-dlp info extraction (no Spotify lookup needed)
- [ ] For Spotify links: search YouTube for audio match using yt-dlp ytsearch
- [ ] For YouTube links: download directly from the provided URL
- [ ] Download audio-only (no video) via yt-dlp
- [ ] User chooses 440Hz (original) or 432Hz per batch before processing
- [ ] Retune downloaded audio to 432Hz when selected
- [ ] Propose folder destination per-song based on metadata (artist/album/single classification)
- [ ] User confirms or adjusts folder per-song before saving (each song in batch gets its own folder dialog; last-used folder suggested as default)
- [ ] Save to existing folder structure (e.g. BoqueronPlaylist/432hz/Artist_432Hz/Album|Singles)
- [ ] Upload processed files to iBroadcast via official API
- [ ] Dynamic thread count based on number of songs in current batch
- [ ] Desktop GUI (tkinter) consistent with retune_app.py aesthetic

### Out of Scope

- Spotify account login / OAuth — only Spotify Web API for metadata (client credentials flow)
- Automatic background polling — user triggers sync manually via UI
- Creating new folder structure — folders already exist on disk, app only saves into them
- Streaming / playback within the app — download and organize only
- Support for sources other than Spotify and YouTube links — Apple Music, SoundCloud, etc. deferred

## Context

- **Existing codebase**: `retune_app.py` — functional 440→432Hz desktop retune app with tkinter GUI, yt-dlp download, librosa pitch shift, threaded parallel processing. Core retune + download logic will be reused directly.
- **Folder structure**: Already established on disk by the user (e.g. `BoqueronPlaylist/432hz/Artist_432Hz/AlbumName/` or `.../Singles/`). App must respect and navigate this structure.
- **iBroadcast**: Personal cloud music service with official API. Auth via username/password. Target playlist: "Boquerón Playlist" (configurable).
- **Spotify API**: Client credentials flow (no user login) — sufficient for track metadata lookup from a track URL.
- **YouTube search strategy**: yt-dlp `ytsearch` — no API key required, searches by artist + title + "audio" to find best audio-only match.

## Constraints

- **Tech stack**: Python 3 + tkinter — must stay consistent with retune_app.py
- **Dependencies**: yt-dlp, librosa, soundfile, numpy, ffmpeg already in use — extend, don't replace
- **Folders**: Must not create or rename existing folders — read-only to folder structure
- **Threading**: Reuse ThreadPoolExecutor pattern from retune_app.py; thread count dynamic (not hardcoded)
- **iBroadcast API**: Must not upload duplicates — check before uploading

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Desktop GUI (tkinter) | Consistent with existing retune_app.py; user familiar with this UI style | — Pending |
| Spotify client credentials (no OAuth) | Simpler setup; metadata-only access is sufficient for track lookup | — Pending |
| yt-dlp search (no YouTube Data API key) | No API key management; yt-dlp already a dependency | — Pending |
| User confirms folder before saving | Metadata-based classification can be wrong; user validation prevents misfiled songs | — Pending |
| 432Hz choice per batch (not per song) | Reduces confirmation fatigue; user typically processes a batch with same intent | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-05-05 after initialization*
