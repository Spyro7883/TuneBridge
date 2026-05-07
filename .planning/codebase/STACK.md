# Technology Stack

**Analysis Date:** 2026-05-05

## Languages

**Primary:**
- Python 3.10+ - Entire application (`retune_app.py`)
  - Uses `Path | None` union type hint syntax (requires Python 3.10+)
  - Uses `match`-compatible structural patterns via `pathlib.Path`

## Runtime

**Environment:**
- CPython 3.10+ (minimum — union type hint `Path | None` on line 116)

**Package Manager:**
- pip (no lockfile detected — only inline install comment in docstring)
- Lockfile: missing (`requirements.txt` not present)

## Frameworks

**Core:**
- `tkinter` (stdlib) - Desktop GUI framework; main window, widgets, dialogs
- `tkinter.ttk` (stdlib) - Themed widget set; buttons, labels, progress bar, spinbox

**Testing:**
- Not detected

**Build/Dev:**
- No build tool detected (single-file script, run directly via `python retune_app.py`)

## Key Dependencies

**Critical:**
- `librosa` (version unpinned) - Audio loading (`librosa.load`) and pitch shifting (`librosa.effects.pitch_shift`) at 440→432 Hz
- `soundfile` (version unpinned) - Writing intermediate WAV before ffmpeg encode (`sf.write`)
- `numpy` (version unpinned) - Audio array manipulation, channel stacking, clipping (`np.clip`, `np.stack`, `np.newaxis`)
- `yt-dlp` (CLI tool, version unpinned) - YouTube/search audio download; invoked via `subprocess`
- `ffmpeg` (system binary, version unpinned) - MP3 encoding from WAV; must be on PATH
- `mutagen` (optional, version unpinned) - ID3 tag read/rewrite on MP3 files (`mutagen.mp3.MP3`, `mutagen.id3.ID3`); imported lazily inside `retune_file`, failures silently ignored

**Infrastructure:**
- `concurrent.futures.ThreadPoolExecutor` (stdlib) - Parallel track processing (1–6 workers, user-configurable)
- `threading.Lock` (stdlib) - Serializes yt-dlp subprocess calls to avoid Firefox cookie DB conflicts
- `threading.Timer` (stdlib) - 10-minute safety timeout per yt-dlp process

## Configuration

**Environment:**
- No environment variables — all configuration is runtime/UI-driven
- Output folder defaults to `~/Music/432hz` (line 238)
- Parallel worker count: 1–6, default 2 (line 247)

**Build:**
- No build config files

**Audio processing constants** (hardcoded in `retune_app.py`, lines 34–36):
- `SRC_A4 = 440.0`
- `DST_A4 = 432.0`
- `RATIO = DST_A4 / SRC_A4` → pitch shift in semitones via `12 * log2(ratio)`

**ffmpeg encode settings** (hardcoded, line 74–78):
- Codec: `libmp3lame`
- Bitrate: `192k`
- Video stripped: `-vn`

## Platform Requirements

**Development:**
- Python 3.10+
- `pip install yt-dlp librosa soundfile numpy mutagen`
- `ffmpeg` binary on system PATH
- Firefox browser (for `--cookies-from-browser firefox` in yt-dlp; required for authenticated YouTube downloads)
- Node.js (`node`) on PATH (for `--js-runtimes node` yt-dlp flag)

**Production:**
- Single-file desktop application; no server or deployment target
- Runs on any OS with the above dependencies (Windows/macOS/Linux)
- Default output path uses `Path.home()` — platform-portable

---

*Stack analysis: 2026-05-05*
