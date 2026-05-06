# TuneBridge — Architecture Research

**Date:** 2026-05-05
**Confidence:** HIGH — based on direct code analysis of retune_app.py + established Python stdlib patterns

---

## Key Findings

- **Keep retune_app.py untouched.** Copy `retune_file()`, `download_track()`, `semitones_for_ratio()` verbatim into service modules. Do not import or monkey-patch.
- **Threading pattern:** Worker threads NEVER touch tkinter widgets. All UI updates go through a `queue.Queue`; main thread polls with `self.after(50, self._poll_queue)`. This is the only universally safe pattern.
- **Folder confirmation (mid-pipeline blocking):** Use `threading.Event` handshake — worker puts event on queue with an Event object, blocks on `event.wait()`, UI shows dialog, sets event when user confirms. Other workers continue unblocked.
- **Sequential stages per song, parallel songs** — the existing ThreadPoolExecutor pattern is correct; don't invert to a global stage queue.
- **SongState enum** (`QUEUED → FETCHING_METADATA → DOWNLOADING → RETUNING → AWAITING_FOLDER → SAVING → UPLOADING → DONE / FAILED`) drives per-row UI updates in the batch table.
- **5 services:** `SpotifyService`, `YouTubeService`, `RetuneService`, `StorageService`, `iBroadcastService` — each a class holding auth/config state, injected from a single `AppConfig` dataclass.

---

## Proposed File Layout

```
tunebridge/
├── app.py                    # TuneBridgeApp (tk.Tk) — entry point
├── pipeline/
│   ├── controller.py         # PipelineController
│   └── song_state.py         # SongState, Status enum
├── services/
│   ├── spotify_service.py
│   ├── youtube_service.py    # wraps download_track() logic
│   ├── retune_service.py     # wraps retune_file() logic
│   ├── storage_service.py
│   └── ibroadcast_service.py
├── ui/
│   ├── batch_panel.py        # per-song status rows
│   ├── folder_confirm.py     # mid-pipeline dialog
│   └── styles.py             # ttk styles from RetuneApp
├── config.py
└── retune_app.py             # UNTOUCHED
```

---

## Pipeline Flow

```
SpotifyURL(s)
    └─► SpotifyService.get_metadata()
            └─► YouTubeService.search_and_download()
                    └─► [if 432Hz] RetuneService.retune()
                            └─► StorageService.propose_folder() ← user confirms
                                    └─► iBroadcastService.upload()
```

Each song runs this full sequence in its own thread. Parallel songs = parallel threads (ThreadPoolExecutor).

---

## Threading Architecture

### UI-safe update pattern
```python
# Worker thread — NEVER touch widgets directly
self._queue.put(('status', song_id, Status.DOWNLOADING))

# Main thread — polls queue every 50ms
def _poll_queue(self):
    while not self._queue.empty():
        event_type, *args = self._queue.get_nowait()
        self._handle_event(event_type, *args)
    self.after(50, self._poll_queue)
```

### Folder confirmation handshake
```python
# Worker thread — blocks waiting for user input
confirm_event = threading.Event()
self._queue.put(('confirm_folder', song_id, proposed_path, confirm_event, result_holder))
confirm_event.wait()  # other songs continue running
final_path = result_holder['path']
```

---

## SongState Enum

```python
class Status(Enum):
    QUEUED = "Queued"
    FETCHING_METADATA = "Fetching metadata..."
    DOWNLOADING = "Downloading..."
    RETUNING = "Retuning to 432Hz..."
    AWAITING_FOLDER = "Waiting for folder confirmation"
    SAVING = "Saving..."
    UPLOADING = "Uploading to iBroadcast..."
    DONE = "Done ✓"
    FAILED = "Failed ✗"
```

---

## Service Layer

| Service | Responsibility |
|---------|---------------|
| `SpotifyService` | Auth (client credentials), metadata lookup from track URL |
| `YouTubeService` | yt-dlp search + audio-only download |
| `RetuneService` | librosa pitch shift (wraps retune_file() logic) |
| `StorageService` | Propose folder path from metadata, validate path exists, save file |
| `iBroadcastService` | Auth, duplicate check, upload, playlist assignment |

All services receive `AppConfig` at init — no global state.

---

## Critical Anti-Patterns

1. Calling tkinter widget methods from worker threads — use queue instead
2. Monolithic `process_one()` spanning all stages — blocks granular status + dialog insertion
3. Blocking main loop for folder confirmation — use `threading.Event` handshake
4. Re-importing/monkey-patching retune_app.py — copy pure functions verbatim
5. Hardcoding thread count — use `min(batch_size, 4)` (yt-dlp is I/O bound, no benefit past 4)

---

## Roadmap Implications

- Phase 1: Scaffold services + PipelineController using existing download/retune logic
- Folder confirmation dialog is the trickiest UI interaction — needs its own task
- iBroadcast duplicate-check logic lives in `iBroadcastService.upload()`, not the controller
- Thread count: `min(batch_size, 4)` — cap at 4 for yt-dlp I/O-bound workload

---

## New Feature Integration (v1.0 additions)

**Added:** 2026-05-06
**Covers:** YouTube direct URL input, unified SongMetadata, dual-source routing, last-used folder memory

### 1. URL Type Detection — Where It Happens

Detection belongs in `PipelineController`, not in any service. The controller receives raw URL strings from the UI and decides which pipeline path to execute before dispatching.

```python
# pipeline/controller.py
def _classify_url(self, url: str) -> Literal["spotify", "youtube"]:
    if "youtube.com/watch" in url or "youtu.be/" in url or "youtube.com/shorts/" in url:
        return "youtube"
    if "spotify.com/track" in url or "spotify:track:" in url:
        return "spotify"
    raise ValueError(f"Unrecognized URL format: {url[:80]}")
```

Pipeline branches:
```
Spotify URL → SpotifyService.get_metadata()  → YouTubeService.search_and_download() → shared tail
YouTube URL → YouTubeService.extract_info()  → YouTubeService.download_direct()     → shared tail
```

Shared tail (retune → folder confirm → save → upload) is identical for both paths.

### 2. Unified SongMetadata Dataclass

```python
# pipeline/models.py
from dataclasses import dataclass, field
from typing import Literal, Optional

@dataclass
class SongMetadata:
    source: Literal["spotify", "youtube"]
    title: str
    artist: str                           # channel name for YouTube-source

    # Spotify-source only (None for YouTube)
    album: Optional[str] = None
    release_type: Optional[Literal["album", "single", "ep"]] = None
    track_number: Optional[int] = None

    # YouTube-source only (None for Spotify)
    youtube_url: Optional[str] = None
    duration_seconds: Optional[int] = None

    # Derived: "artist title audio" for Spotify path; empty for YouTube path
    search_query: str = ""

    def proposed_filename(self) -> str:
        name = f"{self.artist} - {self.title}" if self.artist else self.title
        return _sanitize(name)

    def proposed_folder_hint(self) -> str:
        if self.release_type == "single" or self.album is None:
            return f"{self.artist} / Singles"
        return f"{self.artist} / {self.album}"
```

**Population responsibility:**
- `SpotifyService.get_metadata(url)` → fills title, artist, album, release_type, search_query
- `YouTubeService.extract_info(url)` → fills title, artist (uploader), youtube_url, duration_seconds; leaves album/release_type None

### 3. YouTubeService Changes

Three distinct public methods replace the existing single function:

| Method | When called | Lock? |
|--------|-------------|-------|
| `extract_info(url)` | YouTube path, before folder confirm | No — read-only, concurrent-safe |
| `search_and_download(metadata, out_dir, on_log)` | Spotify path, post-metadata | Yes — `_download_lock` |
| `download_direct(url, out_dir, on_log)` | YouTube path, post-extract_info | Yes — `_download_lock` |

Both download methods share a `_run_download(target, out_dir, on_log)` private method (existing `download_track()` body).

### 4. StorageService — Last-Used Folder (Session State)

Session-only in-memory state; auto-updated after every confirmed save:

```python
class StorageService:
    def __init__(self, config: AppConfig):
        self._last_used_folder: Optional[Path] = None  # session-only, GIL-safe

    def propose_folder(self, metadata: SongMetadata) -> Path:
        if self._last_used_folder is not None:
            return self._last_used_folder          # last-used takes priority
        return self._derive_from_metadata(metadata) # metadata-based fallback

    def save(self, src: Path, folder: Path, metadata: SongMetadata) -> Path:
        dest = folder / (metadata.proposed_filename() + ".mp3")
        shutil.move(str(src), dest)
        self._last_used_folder = folder  # auto-update on every confirmed save
        return dest

    def _derive_from_metadata(self, metadata: SongMetadata) -> Path:
        base = self._config.base_music_dir
        if metadata.release_type == "single" or metadata.album is None:
            return base / _sanitize(metadata.artist) / "Singles"
        return base / _sanitize(metadata.artist) / _sanitize(metadata.album)
```

### 5. SongState Enum — No Changes Required

Existing states cover both paths:

| State | Spotify path | YouTube path |
|-------|-------------|-------------|
| `FETCHING_METADATA` | SpotifyService.get_metadata() | YouTubeService.extract_info() |
| `DOWNLOADING` | YouTubeService.search_and_download() | YouTubeService.download_direct() |
| `RETUNING → AWAITING_FOLDER → SAVING → UPLOADING` | shared | shared |

### 6. PipelineController — Dual-Path Dispatch

```python
def _process_song(self, song_id: str, url: str) -> None:
    kind = self._classify_url(url)

    self._set_status(song_id, Status.FETCHING_METADATA)
    metadata = (self._spotify.get_metadata(url) if kind == "spotify"
                else self._youtube.extract_info(url))

    self._set_status(song_id, Status.DOWNLOADING)
    raw_dir = self._tmp_dir / song_id
    downloaded = (self._youtube.search_and_download(metadata, raw_dir, on_log=...)
                  if kind == "spotify"
                  else self._youtube.download_direct(metadata.youtube_url, raw_dir, on_log=...))

    # Shared tail — identical for both sources
    if self._config.retune_to_432:
        self._set_status(song_id, Status.RETUNING)
        downloaded = self._retune.retune(downloaded, raw_dir)

    self._set_status(song_id, Status.AWAITING_FOLDER)
    proposed = self._storage.propose_folder(metadata)
    confirmed = self._request_folder_confirm(song_id, proposed)

    self._set_status(song_id, Status.SAVING)
    final = self._storage.save(downloaded, confirmed, metadata)

    self._set_status(song_id, Status.UPLOADING)
    self._ibroadcast.upload(final, metadata)
    self._set_status(song_id, Status.DONE)
```

**Services changed by this milestone:**
- `YouTubeService` — add `extract_info()`, `download_direct()`, refactor into `search_and_download()` + `_run_download()`
- `StorageService` — add `_last_used_folder`, update `propose_folder()` priority
- `PipelineController` — add `_classify_url()`, branch dispatch in `_process_song()`
- `pipeline/models.py` — new file: `SongMetadata` dataclass

**Services unchanged:** `SpotifyService`, `RetuneService`, `iBroadcastService`
