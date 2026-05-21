---
date: "2026-05-05 00:00"
promoted: false
---

**Project vision:** A desktop app that bridges Spotify and a personal music library. The user pastes one or more Spotify (or YouTube) track URLs; the app scrapes track metadata, finds the best audio-only match on YouTube, downloads it via yt-dlp, optionally retunes from 440 Hz to 432 Hz, and saves the file into a user-confirmed folder on disk. After processing, newly downloaded tracks are uploaded to iBroadcast into a configurable playlist — with duplicate detection to avoid re-uploading existing tracks. Thread count for parallel downloads scales dynamically with queue size.
