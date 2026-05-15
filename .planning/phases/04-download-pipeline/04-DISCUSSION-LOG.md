# Phase 4: Download Pipeline - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-16
**Phase:** 04-download-pipeline
**Areas discussed:** Download trigger, 432Hz toggle UI, Temp file location, yt-dlp browser cookies, Start button state machine, Partial failure handling, Download concurrency, Status bar & progress feedback

---

## Download Trigger

| Option | Description | Selected |
|--------|-------------|----------|
| Manual — Start button | User verifies metadata + sets 432Hz, then clicks Start | ✓ |
| Auto — after metadata ready | Download starts automatically once metadata resolves | |
| Per-row Start | Each row has its own Download button | |

**User's choice:** Manual — Start button
**Notes:** Existing metadata auto-trigger was fine because metadata is fast. Download is heavy — user needs a checkpoint.

---

## 432Hz Toggle UI Placement

| Option | Description | Selected |
|--------|-------------|----------|
| Toolbar row above table | Dedicated row with segmented control + Start button | ✓ |
| Inside bento stat-card grid | Third bento card acting as a toggle | |
| Bottom bar / status bar | Toggle in the status bar area | |

**User's choice:** Toolbar row above the table

---

## 432Hz Toggle Widget Style

| Option | Description | Selected |
|--------|-------------|----------|
| Segmented control — 440Hz \| 432Hz | Two adjacent buttons, one highlighted | ✓ |
| Radio buttons | ○ 440Hz / ○ 432Hz labels | |
| Single checkbox — "Retune to 432Hz" | Minimal, unchecked = 440Hz | |

**User's choice:** Segmented control (two buttons)

---

## Temp File Location

| Option | Description | Selected |
|--------|-------------|----------|
| System temp dir — auto-cleaned | OS temp, Phase 5 moves the file | ✓ |
| User-configured output folder | Folder picker in UI | |
| Project-local folder | Fixed ~/TuneBridge/downloads/ | |

**User's choice:** System temp dir

---

## yt-dlp Browser Cookies

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — keep Firefox cookies | Same as retune_app.py, handles age-restricted | ✓ |
| No — remove dependency | Simpler but may fail on restricted content | |
| Make it configurable | Try without, fallback to Firefox | |

**User's choice:** Keep `--cookies-from-browser firefox`

---

## Start Button State Machine

| Option | Description | Selected |
|--------|-------------|----------|
| Only when ALL rows = "Metadata ready" | Cleanest state; all metadata confirmed before download | ✓ |
| At least 1 row ready | Faster but mixed state complexity | |
| Always enabled after paste | User can start before metadata | |

**User's choice:** Enabled only when ALL rows = "Metadata ready"

---

## Batch Modification Mid-Download

| Option | Description | Selected |
|--------|-------------|----------|
| No — lock the batch | Paste area + table disabled during download | ✓ |
| Yes — allow appending | New URLs join the queue while downloading | |
| Pause-and-resume | Stop, edit, resume | |

**User's choice:** Lock the batch

---

## Partial Failure Handling

| Option | Description | Selected |
|--------|-------------|----------|
| Skip it — failed rows excluded from Phase 5 | "Failed — download" stays, no dialog | ✓ |
| Block Phase 5 until acknowledged | Dialog per failure before Phase 5 | |
| Per-row retry from table | Right-click or button to retry | |

**User's choice:** Skip — failed rows don't reach Phase 5

---

## Download Concurrency

| Option | Description | Selected |
|--------|-------------|----------|
| Serial yt-dlp, parallel retune (same as retune_app.py) | _download_lock serializes yt-dlp; librosa runs concurrently | ✓ |
| Fully parallel downloads | All yt-dlp calls parallel, no lock | |
| Fully serial | One song at a time, download + retune | |

**User's choice:** Serial yt-dlp via `_download_lock`, parallel retune

---

## Status Bar Progress

| Option | Description | Selected |
|--------|-------------|----------|
| Overall count — "Downloading 2 / 5..." | Batch-level progress, per-row handles individual | ✓ |
| Nothing extra — per-row is enough | Status bar silent during download | |
| Per-song filename as it downloads | Status bar shows current song name | |

**User's choice:** "Downloading N / M..." overall count

---

## Claude's Discretion

- ytsearch query format for Spotify: use `artist` + `track_title` from Phase 3 metadata (`f"ytsearch:{artist} {title} audio"`)
- yt-dlp options dict (quiet, `--no-playlist`, `--audio-quality 192K`)
- Temp subfolder naming (uuid prefix per song)
- Exact status bar message strings beyond "Downloading N / M..." pattern
- `_download_lock` scope (module-level singleton)

## Deferred Ideas

- Per-row retry button — Phase 4+ enhancement
- Configurable audio quality — deferred in REQUIREMENTS.md
- Stop/pause mid-batch — complex threading, not Phase 4
- Determinate progress bar widget — status bar count sufficient for now
