# Phase 4: Download Pipeline - Research

**Researched:** 2026-05-16
**Domain:** yt-dlp subprocess, librosa pitch shift, PySide6 toolbar UI, threading serialization
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Downloads start manually — user clicks "Start Processing" after verifying metadata and setting the 432Hz toggle. No auto-trigger.
- **D-02:** "Start Processing" enabled only when ALL rows have status "Metadata ready". Any row with "Failed — metadata", "Skipped — bad URL", or in-progress status keeps button disabled.
- **D-03:** Once Start is clicked, batch is locked — paste area and table modifications disabled. No appending or editing during active download run.
- **D-04:** A toolbar row sits between stat cards and batch table, containing segmented control + Start button.
- **D-05:** Hz choice is a segmented control with two buttons: `440Hz` (original) | `432Hz` (retune). One always active. Default: `440Hz`.
- **D-06:** Toggle applies to entire batch — not per-row.
- **D-07:** yt-dlp calls serialized via global `_download_lock` (same as retune_app.py) to avoid Firefox cookie DB conflicts.
- **D-08:** `retune_file()` runs in parallel via existing ThreadPoolExecutor — retune has no cookie conflict risk.
- **D-09:** Use `--cookies-from-browser firefox` in all yt-dlp calls.
- **D-10:** Downloaded MP3s land in system temp directory (`tempfile.mkdtemp()`). Temp path never shown in UI.
- **D-11:** Phase 5 receives temp file path and moves it. Phase 4 does not clean up until Phase 5 confirms.
- **D-12:** On app close, leftover temp files deleted via `closeEvent`.
- **D-13:** Failed row status becomes "Failed — download". Error isolated — other rows continue.
- **D-14:** Failed rows excluded from Phase 5. No dialog, no blocking.
- **D-15:** No per-row retry in Phase 4.
- **D-16:** Status bar: `"Downloading 2 / 5..."` while active, `"Done — 4 downloaded, 1 failed"` when complete.
- **D-17:** Per-row status transitions: `Metadata ready` → `Downloading` → `Retuning` (if 432Hz) → `Awaiting folder` or `Failed — download`.

### Claude's Discretion

- Exact ytsearch query format (use artist + title from Phase 3 metadata, avoid "lyrics" keyword bias)
- yt-dlp options dict (quiet flags, `--no-playlist`, `--audio-quality 192K`, etc.)
- Per-row temp subfolder naming (e.g., `uuid4().hex[:8]` prefix)
- `_download_lock` scope (module-level singleton)
- Exact status bar message strings beyond D-16 patterns

### Deferred Ideas (OUT OF SCOPE)

- Per-row retry button for failed downloads
- Configurable audio quality (192K hardcoded)
- Stop/pause mid-batch
- Progress bar widget (determinate bar)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DL-01 | Spotify URLs: search YouTube via yt-dlp ytsearch, download best audio-only match as MP3 | `download_track()` in retune_app.py:116 — adapt search query to use Phase 3 metadata (artist + title) instead of oEmbed title |
| DL-02 | YouTube URLs: download directly from provided URL as audio-only MP3 | Same `download_track()` — `else` branch already uses URL directly |
| DL-03 | User selects 440Hz or 432Hz per batch before processing starts — toggle visible and choice persists | Segmented control via two checkable QPushButton in QButtonGroup; state read at Start click |
| DL-04 | When 432Hz selected, downloaded file retuned via librosa pitch shift; row shows "Retuning" during step | `retune_file()` in retune_app.py:43 — copy verbatim; call after download completes in worker |
</phase_requirements>

---

## Summary

Phase 4 adds the download pipeline to TuneBridge. The codebase already contains all complex logic needed: `retune_app.py` provides a production-proven `retune_file()`, `download_track()`, and `_download_lock` pattern. `tunebridge.py` provides the `_metadata_worker` template that `_download_worker` mirrors exactly.

The primary engineering work is: (1) porting `download_track()` from retune_app.py into tunebridge.py, adapting the Spotify ytsearch query to use Phase 3 metadata (artist + title) rather than oEmbed lookup; (2) adding a toolbar row with two QPushButton segmented control and a Start Processing button; (3) implementing `_download_worker` as a mirror of `_metadata_worker`; (4) wiring button enable/disable logic driven by per-row status; (5) temp dir lifecycle management.

The critical serialization insight is preserved from retune_app.py: `_download_lock` must wrap the entire Popen + wait cycle to prevent concurrent Firefox SQLite access. Retune (librosa) has no such constraint and runs concurrently in the thread pool.

**Primary recommendation:** Copy `retune_file()` and the `_download_lock` pattern verbatim from retune_app.py. Write `_download_worker` as a structural mirror of `_metadata_worker`. The only net-new logic is the toolbar UI and the batch enable/disable state machine.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Download (yt-dlp subprocess) | Worker thread (executor) | — | Blocking I/O; must not run on Qt main thread |
| _download_lock serialization | Worker thread | — | Lock wraps Popen+wait in worker; never on main thread |
| Retune (librosa) | Worker thread (executor) | — | CPU-intensive; must not block UI; no cookie conflict |
| Per-row status updates | Qt main thread (via Signal) | Worker thread emits | All QTableWidget writes on main thread via queued signal |
| Temp file lifecycle | Worker thread (create) | closeEvent (delete) | Worker creates per-row tempdir; closeEvent cleans up |
| Start button enable/disable | Qt main thread | — | Reads row statuses — must be on main thread |
| Toolbar row / segmented control | Qt main thread (init) | — | Pure UI; instantiated in __init__ |
| Status bar progress | Qt main thread (via Signal) | Worker thread emits count | Same dispatcher pattern as metadata |

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| yt-dlp | 2026.03.17 | Audio download + ytsearch | VERIFIED: installed; same as retune_app.py |
| librosa | 0.11.0 | Pitch shift for 432Hz retune | VERIFIED: installed; proven in retune_app.py |
| soundfile | 0.13.1 | WAV intermediate write for librosa→ffmpeg | VERIFIED: installed; required by retune_file() |
| ffmpeg | 8.0.1 | MP3 encode from WAV after pitch shift | VERIFIED: in PATH; retune_file() requires it |
| mutagen | 1.47.0 | ID3 tag preservation after retune | VERIFIED: installed; used in retune_file() |
| PySide6 | 6.11.1 | UI — toolbar row, segmented control, signals | VERIFIED: installed; project standard |
| numpy | 2.3.5 | Array ops in retune_file() | VERIFIED: installed |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| tempfile (stdlib) | — | mkdtemp() for per-session temp dir | Used at Start Processing click |
| threading (stdlib) | — | Lock for _download_lock, Event for _closing | Already in tunebridge.py |
| uuid (stdlib) | — | Per-row temp subfolder prefix | uuid4().hex[:8] pattern from retune_app.py |
| shutil (stdlib) | — | which("yt-dlp"), which("ffmpeg") | Already in retune_app.py |

**No new pip installs required.** All dependencies already present. [VERIFIED: pip list confirmed above]

---

## Architecture Patterns

### System Architecture Diagram

```
[Start Processing click]
        |
        v
[_start_processing()] -- reads hz_mode from segmented control
        |
        +-- locks paste area + table (D-03)
        |
        +-- for each row with METADATA_READY status:
               |
               v
        [executor.submit(_download_worker, row_id, url, url_type, metadata, hz_mode)]
               |
               v (worker thread)
        [emit row_status_changed("Downloading")]
               |
               v
        [_download_lock acquired] --> [yt-dlp subprocess] --> [_download_lock released]
               |           (serialized: one at a time)
               |
        if hz_mode == 432:
               v
        [emit row_status_changed("Retuning")]
               |
               v
        [retune_file(temp_in, temp_out)]  <-- parallel, no lock needed
               |
        else:
               v
        [temp_path = downloaded file]
               |
               v
        [emit row_status_changed("Awaiting folder")]
        [store temp_path in row metadata]
        [increment downloaded counter]
               |
               v (on exception anywhere above)
        [emit row_status_changed("Failed — download")]
        [increment failed counter]
               |
               v (after all workers complete)
        [status bar: "Done — N downloaded, M failed"]
        [unlock paste area + table]
```

### Recommended Project Structure

No structural changes to directory layout. All new code goes into `tunebridge.py`:

```
tunebridge.py additions:
  - _download_lock = threading.Lock()          # module-level, after imports
  - _SESSION_TEMP_DIR: Path | None = None      # per-session temp root
  - retune_file(in_path, out_path)             # copied verbatim from retune_app.py
  - download_track_for_row(...)                # adapted from retune_app.py download_track()
  - TuneBridgeApp._toolbar_row()               # QHBoxLayout: segmented control + Start btn
  - TuneBridgeApp._start_processing()          # Start button handler
  - TuneBridgeApp._download_worker(...)        # mirrors _metadata_worker
  - TuneBridgeApp._check_all_metadata_ready()  # enable/disable Start button
  - SongStatus additions: DOWNLOADING, RETUNING, AWAITING_FOLDER, FAILED_DOWNLOAD
  - BatchTable._STATUS_COLORS additions for new statuses
  - closeEvent extension: temp dir cleanup
```

### Pattern 1: _download_worker mirrors _metadata_worker exactly

```python
# Source: tunebridge.py _metadata_worker (existing pattern)
def _download_worker(self, row_id: int, url: str, url_type: str,
                     metadata: dict, hz_mode: int) -> None:
    """Worker thread: download + optional retune. Per-row error isolation."""
    if self._closing.is_set():
        return
    try:
        self._dispatcher.row_status_changed.emit(row_id, SongStatus.DOWNLOADING.value)

        # Build per-row temp dir
        row_tmp = self._session_tmp / uuid.uuid4().hex[:8]
        row_tmp.mkdir(parents=True, exist_ok=True)

        # Route: Spotify (ytsearch) vs YouTube (direct)
        if url_type == "Spotify":
            artist = metadata.get("artist", "")
            title  = metadata.get("track_title", "")
            search_url = f"ytsearch:{artist} {title} audio"
        else:
            search_url = url

        downloaded = download_track_for_row(search_url, row_tmp)
        if not downloaded:
            raise RuntimeError("No audio file found after download.")

        if hz_mode == 432:
            self._dispatcher.row_status_changed.emit(row_id, SongStatus.RETUNING.value)
            out_path = row_tmp / (downloaded.stem + "_432hz.mp3")
            retune_file(downloaded, out_path)
            downloaded.unlink(missing_ok=True)
            downloaded = out_path

        if not self._closing.is_set():
            self._dispatcher.row_status_changed.emit(row_id, SongStatus.AWAITING.value)
            # Store temp path for Phase 5 retrieval
            self._temp_paths[row_id] = downloaded

    except Exception as exc:
        logging.getLogger(__name__).warning(
            "Download failed for row %d (%s): %s", row_id, url, exc
        )
        if not self._closing.is_set():
            self._dispatcher.row_status_changed.emit(row_id, "Failed — download")
```

### Pattern 2: _download_lock wraps entire Popen+wait cycle

```python
# Source: retune_app.py:144 — CRITICAL: do not narrow the lock scope
_download_lock = threading.Lock()   # module-level

def download_track_for_row(search_url: str, out_dir: Path) -> Path | None:
    ytdlp = shutil.which("yt-dlp")
    if not ytdlp:
        raise RuntimeError("yt-dlp not found.")

    cmd = [
        ytdlp, "--no-playlist",
        "--cookies-from-browser", "firefox",
        "-x", "--audio-format", "mp3", "--audio-quality", "192K",
        "-o", str(out_dir / "%(title)s.%(ext)s"),
        search_url,
    ]

    with _download_lock:
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace"
        )
        timer = threading.Timer(600, lambda: process.kill() if process.poll() is None else None)
        timer.start()
        try:
            process.stdout.read()  # drain
            process.wait()
        finally:
            timer.cancel()

        if process.returncode != 0:
            raise RuntimeError("yt-dlp download failed or timed out.")

    mp3s = sorted(out_dir.glob("*.mp3"), key=lambda p: p.stat().st_mtime, reverse=True)
    return mp3s[0] if mp3s else None
```

Note: retune_app.py uses `--js-runtimes node --remote-components ejs:github` flags. These are yt-dlp extractor-helper flags for certain sites. For audio-only MP3 extraction from YouTube they are not required and should be **omitted** to reduce subprocess complexity. [ASSUMED — verify if yt-dlp raises without them on current YouTube]

### Pattern 3: Segmented control via QButtonGroup

```python
# Source: PySide6 QButtonGroup + checkable QPushButton pattern [ASSUMED from PySide6 docs]
from PySide6.QtWidgets import QPushButton, QButtonGroup, QHBoxLayout

hz_group = QButtonGroup(self)
hz_group.setExclusive(True)

btn_440 = QPushButton("440 Hz")
btn_432 = QPushButton("432 Hz")
btn_440.setCheckable(True)
btn_432.setCheckable(True)
btn_440.setChecked(True)  # default: 440Hz selected

hz_group.addButton(btn_440, 440)
hz_group.addButton(btn_432, 432)

# Read active choice at Start click:
hz_mode = hz_group.checkedId()  # returns 440 or 432
```

QSS for active/inactive segmented button state:
```css
QPushButton[hz_btn="true"] {
    background-color: rgba(255,255,255,10);
    border: 1px solid rgba(255,255,255,20);
    border-radius: 6px;
    color: #B3B3B3;
    padding: 4px 16px;
    font-size: 10pt;
}
QPushButton[hz_btn="true"]:checked {
    background-color: rgba(29, 185, 84, 40);
    border: 1px solid #1DB954;
    color: #1DB954;
    font-weight: bold;
}
```

### Pattern 4: Start button enable/disable state machine

```python
# Called after every row_status_changed signal — on main thread
def _refresh_start_button(self) -> None:
    row_count = self._table._table.rowCount()
    if row_count == 0:
        self._btn_start.setEnabled(False)
        return
    all_ready = all(
        self._table._table.item(r, 2) is not None
        and self._table._table.item(r, 2).text() == SongStatus.METADATA_READY.value
        for r in range(row_count)
    )
    self._btn_start.setEnabled(all_ready)
```

This must be connected to `_dispatcher.row_status_changed` as an additional slot, and also called after `_process_urls` adds rows.

### Pattern 5: Temp dir lifecycle

```python
# In TuneBridgeApp.__init__:
import tempfile
self._session_tmp = Path(tempfile.mkdtemp(prefix="tunebridge_"))
self._temp_paths: dict[int, Path] = {}   # row_id -> temp MP3 path for Phase 5

# In closeEvent:
def closeEvent(self, event) -> None:
    self._closing.set()
    self._executor.shutdown(wait=False)
    # Clean up leftover temp files (D-12)
    try:
        import shutil as _shutil
        _shutil.rmtree(self._session_tmp, ignore_errors=True)
    except Exception:
        pass
    super().closeEvent(event)
```

### Anti-Patterns to Avoid

- **Narrowing `_download_lock` scope:** Never move the lock to wrap only `Popen()` — the lock must cover `Popen` + `process.wait()`. Firefox SQLite is locked for the duration of yt-dlp execution, not just startup.
- **UI updates from worker thread:** Never call `self._table.update_row_status()` directly from a worker. Always go through `self._dispatcher.row_status_changed.emit()` — Qt queued connection handles thread crossing.
- **Polling row statuses from worker thread:** `_refresh_start_button()` reads QTableWidget items — must only be called on main thread. Connect it as a slot to the dispatcher signal.
- **Using "lyrics" in ytsearch query:** retune_app.py uses `ytsearch:{title} lyrics` — this biases toward lyric videos which are lower audio quality. Phase 4 uses `ytsearch:{artist} {title} audio` (D-17 discretion).
- **Calling retune_file() inside _download_lock:** retune is pure CPU (librosa+ffmpeg), no cookie access. Running it inside the lock serializes what should be parallel, destroying throughput.
- **Not stripping locale prefix for Spotify URLs in ytsearch:** Phase 3 metadata already has `artist` and `track_title` resolved — use those fields directly instead of parsing the URL again.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Audio pitch shift | Custom FFT/resampling | `librosa.effects.pitch_shift` | Semitone math, edge cases (mono/stereo), anti-aliasing already handled |
| MP3 encode | Raw audio write | ffmpeg via subprocess (in retune_file) | Codec licensing, quality settings, metadata embedding complexity |
| YouTube search + download | Custom HTTP scraper | yt-dlp ytsearch | Bot detection, rate limiting, format selection, cookie handling |
| ID3 tag preservation | Custom ID3 parser | mutagen (in retune_file) | Encoding edge cases, ID3v2 version quirks |
| Thread-safe UI updates | Shared queue + polling | PySide6 Signal/queued connection | Already wired in _Dispatcher; adding polling would be redundant and racy |

---

## Runtime State Inventory

Not applicable — Phase 4 is a feature addition (greenfield within existing codebase), not a rename/refactor/migration phase.

---

## Common Pitfalls

### Pitfall 1: Firefox cookie DB SQLite lock error
**What goes wrong:** Two concurrent yt-dlp subprocesses both try to read `~/.mozilla/firefox/*/cookies.sqlite` simultaneously; SQLite raises "database is locked".
**Why it happens:** Firefox keeps cookies.sqlite open with WAL mode but yt-dlp opens it read-only — concurrent readers can fail with SQLITE_BUSY under certain WAL checkpoint states.
**How to avoid:** `_download_lock` wraps the entire `Popen` + `process.wait()` cycle. Never submit more than one yt-dlp subprocess at a time.
**Warning signs:** yt-dlp stderr contains "unable to open database file" or "database is locked".

### Pitfall 2: ytsearch returns no results or wrong track
**What goes wrong:** `ytsearch:` query matches a cover, karaoke, or remix rather than the studio track.
**Why it happens:** Generic queries return popularity-sorted results; uncommon artists may have poor matches.
**How to avoid:** Use `f"ytsearch:{artist} {title} audio"` — "audio" keyword biases toward audio-focused uploads. Don't include "lyrics" (biases to lyric videos). This is best-effort; Phase 4 does not validate match accuracy.
**Warning signs:** Downloaded file is much shorter or longer than expected track duration.

### Pitfall 3: retune_file() path handling on Windows
**What goes wrong:** `subprocess.run` with a Path containing spaces fails if not quoted, or ffmpeg not found.
**Why it happens:** retune_app.py uses `shutil.which("ffmpeg")` — if ffmpeg is not in PATH on the target machine, raises RuntimeError.
**How to avoid:** ffmpeg 8.0.1 is verified in PATH on this machine. [VERIFIED: ffmpeg -version returned 8.0.1] The `shutil.which` guard in retune_file() will raise a clear RuntimeError rather than failing silently.
**Warning signs:** `RuntimeError: ffmpeg not found in PATH.`

### Pitfall 4: Temp MP3 glob finds wrong file
**What goes wrong:** `sorted(out_dir.glob("*.mp3"), key=mtime, reverse=True)[0]` returns a stale file if a previous download partially wrote to the same dir.
**Why it happens:** Using shared output dir across rows.
**How to avoid:** Use per-row temp subdirs (`uuid4().hex[:8]` prefix) — each row's download lands in its own clean directory. Already the pattern in retune_app.py `process_one()`.
**Warning signs:** Downloaded track plays a different song than expected.

### Pitfall 5: Start button checking non-METADATA_READY rows during batch run
**What goes wrong:** While downloads are running, rows have status "Downloading" — `_refresh_start_button` sees non-METADATA_READY rows and correctly disables Start. But if batch completes and some rows are "Awaiting folder", Start remains disabled (correct — can't re-run).
**Why it happens:** D-02 is intentionally strict — only ALL rows METADATA_READY enables Start.
**How to avoid:** This is correct behavior per D-02. Document clearly in code that Start is one-shot per batch. Batch lock (D-03) prevents adding new rows mid-run.

### Pitfall 6: librosa loading stereo audio
**What goes wrong:** `librosa.load()` with `mono=False` returns shape `(channels, samples)`. `pitch_shift` expects 1D array.
**Why it happens:** retune_file() already handles this with the channel loop — copy verbatim, don't simplify.
**How to avoid:** Copy `retune_file()` exactly as-is. The `if y.ndim == 1: y = y[np.newaxis, :]` guard + channel loop handles mono and stereo.

---

## Code Examples

### retune_file() — copy verbatim from retune_app.py:43

The full function (lines 43–98) is production-ready. Copy it into tunebridge.py unchanged. It handles:
- librosa stereo/mono loading
- per-channel pitch_shift
- soundfile WAV intermediate
- ffmpeg MP3 encode at 192K
- mutagen ID3 tag preservation with UTF-8 forced encoding

### SongStatus additions needed

```python
# Source: tunebridge.py SongStatus enum (existing)
# Phase 4 additions — check first: DOWNLOADING, RETUNING, AWAITING already exist in enum
class SongStatus(Enum):
    QUEUED          = "Queued"
    FETCHING        = "Fetching metadata"
    DOWNLOADING     = "Downloading"       # already present
    RETUNING        = "Retuning"          # already present
    AWAITING        = "Awaiting folder"   # already present
    SAVING          = "Saving"
    UPLOADING       = "Uploading"
    DONE            = "Done"
    FAILED          = "Failed"
    METADATA_READY  = "Metadata ready"
    # NEEDED: no FAILED_DOWNLOAD — currently only "Failed" exists
    # D-17 requires "Failed — download" as distinct status string
```

`_STATUS_COLORS` in BatchTable is missing `"Failed — download"` and `"Downloading"` color entries. Currently `"Downloading"` maps to `QColor("#FFFFFF")` (white) and `"Retuning"` is also white — these exist. `"Failed — download"` needs to be added with `QColor("#EF4444")`.

### Toolbar row layout

```python
# In TuneBridgeApp.__init__, after cards_row, before BatchTable:
toolbar_row = QHBoxLayout()
toolbar_row.setSpacing(8)

# Segmented control
self._hz_group = QButtonGroup(self)
self._hz_group.setExclusive(True)
self._btn_440 = QPushButton("440 Hz")
self._btn_432 = QPushButton("432 Hz")
for btn in (self._btn_440, self._btn_432):
    btn.setCheckable(True)
    btn.setProperty("hz_btn", True)
self._btn_440.setChecked(True)
self._hz_group.addButton(self._btn_440, 440)
self._hz_group.addButton(self._btn_432, 432)

toolbar_row.addWidget(self._btn_440)
toolbar_row.addWidget(self._btn_432)
toolbar_row.addStretch()

# Start Processing button
self._btn_start = QPushButton("Start Processing")
self._btn_start.setEnabled(False)   # disabled until all rows METADATA_READY
self._btn_start.clicked.connect(self._start_processing)
toolbar_row.addWidget(self._btn_start)

layout.addLayout(toolbar_row)   # after cards_row, before BatchTable
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Spotify oEmbed for search query (retune_app.py) | Phase 3 metadata (artist + track_title already fetched) | Phase 3 complete | No extra HTTP call at download time; use metadata dict directly |
| `ytsearch:{title} lyrics` (retune_app.py:129) | `ytsearch:{artist} {title} audio` | Phase 4 design | Better audio match, avoids lyric video bias |
| Per-session output dir (retune_app.py) | System temp dir, per-row subdir | Phase 4 design | Temp files cleaned up on close; never in user-visible location |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `--js-runtimes node --remote-components ejs:github` flags in retune_app.py are not required for standard YouTube audio download | Pattern 2 (download_track_for_row) | yt-dlp may fail on current YouTube without them; add back if downloads fail |
| A2 | QButtonGroup with two checkable QPushButton and setExclusive(True) provides correct mutual exclusion without extra wiring | Pattern 3 (segmented control) | May need manual toggling if Qt version behaves differently; low risk on PySide6 6.11.1 |
| A3 | Per-row `_refresh_start_button()` check (iterating all rows) is fast enough for batches up to ~50 rows | Pattern 4 (Start button) | At 50 rows this is a tight loop over QTableWidget items — acceptable; would need optimization for 500+ rows |

---

## Open Questions

1. **`--js-runtimes node` / `--remote-components ejs:github` flags**
   - What we know: These appear in retune_app.py's download_track(); they are yt-dlp plugin/extractor-helper options.
   - What's unclear: Whether current yt-dlp 2026.03.17 requires them for YouTube audio extraction, or if they were added for a specific site.
   - Recommendation: Omit in initial implementation. If downloads fail with "Sign in to confirm your age" or similar, add them back.

2. **Batch completion signal — who fires "Done — N downloaded, M failed"?**
   - What we know: Workers emit per-row signals; there is no "all done" signal in _Dispatcher.
   - What's unclear: Whether to add a new `batch_complete` signal or track completion via a counter in TuneBridgeApp.
   - Recommendation: Use an atomic counter (`threading.Lock` + int) in TuneBridgeApp. When counter reaches total_submitted, emit status bar update from the last completing worker's signal handler on main thread.

3. **`_temp_paths` dict for Phase 5 handoff**
   - What we know: Phase 4 must hand off temp file path to Phase 5. Phase 5 does not exist yet.
   - What's unclear: Exact interface Phase 5 expects.
   - Recommendation: Store `self._temp_paths: dict[int, Path] = {}` in TuneBridgeApp. Phase 5 reads it. This is the minimal contract — document as the Phase 4/5 boundary.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| yt-dlp | DL-01, DL-02 | Yes | 2026.03.17 | None — blocking |
| ffmpeg | DL-04 (retune_file) | Yes | 8.0.1 | None — blocking for 432Hz path; 440Hz path unaffected |
| librosa | DL-04 | Yes | 0.11.0 | None — 432Hz path fails |
| soundfile | DL-04 | Yes | 0.13.1 | None — retune_file() writes WAV via soundfile |
| mutagen | DL-04 | Yes | 1.47.0 | Graceful degradation — retune_file() wraps tag ops in try/except |
| Firefox | DL-01, DL-02 | Assumed present | Unknown | If absent: yt-dlp `--cookies-from-browser firefox` fails; add fallback `--no-cookies` for testing |

**Missing dependencies with no fallback:** None for the 440Hz path. For 432Hz path, ffmpeg + librosa + soundfile all required — all verified present.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.3.2 (inferred from existing tests) |
| Config file | `pytest.ini` (testpaths = tests, addopts = -q) |
| Quick run command | `python -m pytest tests/test_tunebridge.py -q` |
| Full suite command | `python -m pytest -q` |

**Existing test count:** 52 total (18 in test_metadata_services.py + 34 in test_tunebridge.py)

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DL-01 | Spotify row builds ytsearch query using artist+title from metadata | unit | `python -m pytest tests/test_download_pipeline.py::test_spotify_search_query -xvs` | No — Wave 0 |
| DL-01 | Spotify row calls yt-dlp with ytsearch URL (mocked subprocess) | unit | `python -m pytest tests/test_download_pipeline.py::test_download_worker_spotify_path -xvs` | No — Wave 0 |
| DL-02 | YouTube row uses direct URL in yt-dlp call (no ytsearch prefix) | unit | `python -m pytest tests/test_download_pipeline.py::test_download_worker_youtube_path -xvs` | No — Wave 0 |
| DL-03 | 440Hz button is checked by default; QButtonGroup mutually exclusive | unit | `python -m pytest tests/test_download_pipeline.py::test_hz_toggle_default_440 -xvs` | No — Wave 0 |
| DL-03 | Start button disabled when rows have non-METADATA_READY status | unit | `python -m pytest tests/test_download_pipeline.py::test_start_button_disabled_on_mixed_status -xvs` | No — Wave 0 |
| DL-03 | Start button enabled when all rows have METADATA_READY | unit | `python -m pytest tests/test_download_pipeline.py::test_start_button_enabled_all_ready -xvs` | No — Wave 0 |
| DL-04 | retune_file() called when hz_mode=432; not called when hz_mode=440 | unit | `python -m pytest tests/test_download_pipeline.py::test_retune_called_on_432 -xvs` | No — Wave 0 |
| DL-04 | row status transitions: Downloading → Retuning → Awaiting folder | unit | `python -m pytest tests/test_download_pipeline.py::test_status_transitions_432hz -xvs` | No — Wave 0 |
| DL-01/02 | Failed download sets row to "Failed — download"; does not affect other rows | unit | `python -m pytest tests/test_download_pipeline.py::test_failed_download_isolation -xvs` | No — Wave 0 |
| DL-02 | Status transitions 440Hz: Downloading → Awaiting folder (no Retuning) | unit | `python -m pytest tests/test_download_pipeline.py::test_status_transitions_440hz -xvs` | No — Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_download_pipeline.py -q`
- **Per wave merge:** `python -m pytest -q` (full 52+ test suite)
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_download_pipeline.py` — covers DL-01 through DL-04 (10 new tests)
- [ ] Mocking strategy: `unittest.mock.patch("tunebridge.subprocess.Popen")` for yt-dlp calls; `unittest.mock.patch("tunebridge.retune_file")` for librosa calls; `unittest.mock.patch("tunebridge.shutil.which", return_value="/usr/bin/yt-dlp")` for path checks
- [ ] `tempfile.mkdtemp` patch needed in tests that exercise temp dir creation

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | — |
| V3 Session Management | No | — |
| V4 Access Control | No | — |
| V5 Input Validation | Yes | URL validated by classify_url() before reaching download worker; ytsearch query built from Phase 3 metadata (not raw user input after classification) |
| V6 Cryptography | No | — |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Subprocess injection via crafted URL | Tampering | `search_url` is either a validated YouTube URL (passed through classify_url) or a constructed `ytsearch:` string from metadata fields — not raw user input. yt-dlp receives it as a positional arg in a list (never shell=True). |
| Temp file path traversal | Elevation of Privilege | `tempfile.mkdtemp()` creates a system-managed temp dir with restricted permissions; per-row subdirs use uuid4 hex prefix |
| yt-dlp timeout bypass | Denial of Service | 600s timer kills subprocess if stuck; `_closing` event checked at worker start |

**`shell=False` (default for subprocess.Popen with list args) is mandatory** — retune_app.py already follows this pattern. Copy as-is.

---

## Sources

### Primary (HIGH confidence)
- `retune_app.py` — full source read; `download_track()`, `retune_file()`, `_download_lock` pattern verified in codebase
- `tunebridge.py` — full source read; `_metadata_worker`, `_Dispatcher`, `ThreadPoolExecutor`, `SongStatus` enum verified
- `pip list` output — all package versions verified against installed environment

### Secondary (MEDIUM confidence)
- PySide6 QButtonGroup exclusive mode — standard documented behavior; pattern consistent with Qt5/Qt6 docs [ASSUMED for exact PySide6 6.11.1 API]

### Tertiary (LOW confidence)
- A1: `--js-runtimes`/`--remote-components` flags being optional — not verified against current yt-dlp 2026.03.17 changelog

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all packages verified installed with exact versions
- Architecture: HIGH — directly derived from existing proven patterns in codebase
- Pitfalls: HIGH — Firefox lock issue documented in retune_app.py comments; temp file and stereo handling verified in code
- Test strategy: HIGH — mirrors existing test_tunebridge.py patterns

**Research date:** 2026-05-16
**Valid until:** 2026-06-16 (yt-dlp updates frequently; re-check if download failures occur)
