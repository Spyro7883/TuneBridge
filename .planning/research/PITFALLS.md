# TuneBridge — Pitfalls Research (v1.0 New Features)

**Date:** 2026-05-06
**Scope:** Mixed-URL batch pipeline + per-song tkinter dialogs
**Confidence:** HIGH — derived from retune_app.py code analysis + established Python threading/tkinter/yt-dlp behavior

---

## Key Findings

- **threading.Event deadlock is the #1 rewrite risk.** If the folder dialog is closed via the OS X button or crashes, `confirm_event.wait()` blocks forever — consuming a ThreadPoolExecutor slot permanently. With 4 workers all blocked, the batch silently stalls.
- **`_download_lock` must cover info-extraction too.** Firefox's cookies.sqlite uses SQLite write-locks. Any concurrent yt-dlp subprocess sharing Firefox cookies fails with a DB lock error if run outside the lock.
- **yt-dlp info fields are all nullable.** `uploader`, `channel`, `artist`, `album`, `track` are optional and routinely `None`. `info['uploader']` raises `AttributeError`/`KeyError` in production.
- **URL substring matching must be replaced** with `urlparse` hostname comparison — edge cases exist with the current approach in retune_app.py.
- **Dialog stacking is a real concurrent failure mode.** Multiple workers reaching `AWAITING_FOLDER` simultaneously causes overlapping modal windows. The poll handler must enforce one dialog at a time.

---

## URL Detection Pitfalls

### Pitfall 1: Substring matching misclassifies edge cases

Existing code in retune_app.py uses `"spotify.com" in url` string matching. This misclassifies third-party URLs containing "spotify" in path segments.

**Prevention:** Use `urllib.parse.urlparse` hostname comparison:
```python
from urllib.parse import urlparse

def classify_url(url: str) -> str:  # "spotify" | "youtube" | "unknown"
    try:
        host = urlparse(url).netloc.lower().lstrip("www.")
    except Exception:
        return "unknown"
    if host in ("open.spotify.com", "spotify.com"):
        return "spotify"
    if host in ("youtube.com", "youtu.be", "music.youtube.com"):
        return "youtube"
    return "unknown"
```

Reject `"unknown"` at input-parse time with a visible per-row error. Never let unknown URL type reach a worker thread.

### Pitfall 2: youtu.be short-links not normalized

`youtu.be/dQw4w9WgXcQ` passed to `extract_info` without normalization can return a `webpage_url` that differs from the input.

**Prevention:**
```python
import re
def normalize_youtube_url(url: str) -> str:
    m = re.match(r"https?://youtu\.be/([A-Za-z0-9_-]+)", url)
    if m:
        return f"https://www.youtube.com/watch?v={m.group(1)}"
    return url
```

### Pitfall 3: Playlist URL treated as single-video during info extraction

`youtube.com/watch?v=XYZ&list=PLabc` — without `--no-playlist` on the info-extraction call, yt-dlp returns playlist metadata. `info['title']` becomes the playlist title.

**Prevention:** Strip `list=` from query string before info extraction AND pass `--no-playlist` to every yt-dlp invocation independently.

```python
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
def strip_playlist_param(url: str) -> str:
    p = urlparse(url)
    qs = {k: v for k, v in parse_qs(p.query).items() if k != "list"}
    return urlunparse(p._replace(query=urlencode(qs, doseq=True)))
```

### Pitfall 4: Unknown URL type fails deep in pipeline, not at input

Raising `ValueError("unknown URL")` inside a worker thread produces a cryptic log message.

**Prevention:** Validate all URLs synchronously on the main thread before submitting any futures to ThreadPoolExecutor. Set per-row `FAILED` state with "Unrecognized URL" message before any thread starts.

---

## yt-dlp Info Extraction Pitfalls

### Pitfall 5: Nullable fields treated as always-present

| Field | When absent |
|-------|-------------|
| `uploader` | Channel deleted, YouTube Music auto-generated, VEVO channels |
| `channel` | Same as `uploader` |
| `artist` | Only set for YouTube Music tracks with ID3-style metadata |
| `album` / `track` | Same as `artist` |
| `duration` | Live streams, restricted videos |

**Prevention:** Single extraction function with all `.get()` fallbacks:
```python
def extract_track_meta(info: dict, source: str) -> SongMetadata:
    title = (info.get('title') or info.get('track') or '').strip()
    if not title:
        raise ValueError("yt-dlp returned no usable title")
    artist = (info.get('uploader') or info.get('channel') or info.get('artist') or 'Unknown').strip()
    return SongMetadata(title=title, artist=artist, source=source)
```
Never access `info['field']` directly anywhere outside this function.

### Pitfall 6: Private, deleted, and age-restricted video failures

- **Private/deleted:** yt-dlp raises `DownloadError` with "Private video" or "Video unavailable".
- **Age-restricted without cookies:** Info-extraction fails if `--cookies-from-browser firefox` is omitted from the info-extract call but present on the download call — two code paths, inconsistent flags.
- **Rate-limited (HTTP 429):** Parallel info-extraction calls without `_download_lock` trigger YouTube's rate limiter.

**Prevention:** All yt-dlp subprocess calls (info-extract AND download) pass identical flags including `--cookies-from-browser firefox` and are guarded by `_download_lock`. Parse stderr for "Private video", "unavailable", "429" to set specific `FAILED` messages.

### Pitfall 7: Info extraction doubles lock acquisitions — stalls batch

Each song acquires `_download_lock` twice (info-extract + download). With 4 workers × 2 acquisitions × ~10s each = significant serialized time before retuning begins.

**Prevention options (preferred order):**
1. Use `--print title` + `--print uploader` flags in one subprocess call instead of full `--dump-json` — faster, one lock acquisition.
2. Extract title from yt-dlp download output template `%(title)s`.
3. Accept serialization — document it and show "Fetching info..." status so user knows app is working.

### Pitfall 8: ytsearch result metadata describes YouTube channel, not artist

For Spotify-routed songs, yt-dlp's `uploader` field is the YouTube channel ("VEVO", "Topic"), not the artist.

**Prevention:** For Spotify-routed songs, folder proposal uses Spotify API metadata only. yt-dlp info is only used for folder proposal when source is a directly-provided YouTube URL.

---

## Per-Song Dialog Pitfalls (Threading)

### Pitfall 9: threading.Event never set — permanent worker deadlock

If user closes dialog via OS X button and close handler doesn't call `event.set()`, the worker blocks forever. All 4 ThreadPoolExecutor slots get consumed. Batch stalls silently.

**Prevention — three layers:**

**Layer 1:** Timeout:
```python
confirmed = confirm_event.wait(timeout=300)  # 5 minutes
if not confirmed:
    raise RuntimeError("Folder confirmation timed out — song skipped.")
```

**Layer 2:** WM_DELETE_WINDOW always sets event:
```python
def _on_dialog_close():
    result_holder['cancelled'] = True
    confirm_event.set()  # MUST be called in ALL exit paths

dialog.protocol("WM_DELETE_WINDOW", _on_dialog_close)
```

**Layer 3:** try/finally in dialog spawner:
```python
try:
    _show_folder_dialog(song_id, proposed_path, confirm_event, result_holder)
except Exception as e:
    self._log(f"Dialog error: {e}")
    result_holder.setdefault('cancelled', True)
    confirm_event.set()  # unblock worker even on creation failure
```

### Pitfall 10: _poll_queue loop stops — all workers starve

If `_handle_event` raises, `self.after(50, ...)` is never called. Queue accumulates. Workers blocked on `confirm_event.wait()` never get unblocked.

**Prevention — always re-schedule via try/finally:**
```python
def _poll_queue(self):
    try:
        while not self._queue.empty():
            event_type, *args = self._queue.get_nowait()
            try:
                self._handle_event(event_type, *args)
            except Exception as e:
                self._log(f"[internal error in event handler] {e}")
    finally:
        self.after(50, self._poll_queue)  # always re-schedule
```

### Pitfall 11: Dialog stacking — multiple workers at AWAITING_FOLDER simultaneously

Songs finishing download within the same 50ms poll window cause multiple modal windows to open simultaneously.

**Prevention:** One dialog at a time — flag + re-queue deferred events:
```python
if event_type == 'confirm_folder':
    if self._dialog_open:
        self._queue.put((event_type, *args))  # defer
        break
    self._dialog_open = True
    self._show_folder_dialog(*args)
    # _show_folder_dialog sets self._dialog_open = False when closed
```

### Pitfall 12: result_holder shared across songs — wrong path assigned

Using `self._result_holder` (class attribute) for multiple concurrent confirmations causes songs to overwrite each other's confirmed path.

**Prevention:** Fresh `dict` per call in worker thread:
```python
result_holder = {}  # new per call, never self._result_holder
confirm_event = threading.Event()
self._queue.put(('confirm_folder', song_id, proposed_path, confirm_event, result_holder))
```

### Pitfall 13: Dialog invisible behind main window on Windows (z-order)

`tk.Toplevel()` dialog appears behind the main window on Windows when the main window was recently active.

**Prevention — all four calls required:**
```python
dialog = tk.Toplevel(self)
dialog.transient(self)   # associate with parent
dialog.lift()            # raise in z-order
dialog.focus_force()     # force keyboard focus
dialog.grab_set()        # modal — all four are needed on Windows
```

### Pitfall 14: Worker thread calling tkinter directly

Any tkinter call from a worker thread is undefined behavior. Causes `RuntimeError: main thread is not in main loop` or silent Tcl state corruption.

**Prevention:** Workers communicate ONLY via `queue.Queue.put()`. Main thread reads queue in `_poll_queue`. No direct widget access from any worker thread. (retune_app.py already does this correctly — do not regress.)

---

## Prevention Strategies Summary

| Strategy | Mechanism |
|----------|-----------|
| Always-set Event contract | `event.wait(timeout=300)` + WM_DELETE_WINDOW handler + try/finally in spawner |
| URL validation at input boundary | `urlparse` hostname classification before `ThreadPoolExecutor.submit()` |
| yt-dlp field access discipline | Single `extract_track_meta()` function with all `.get()` fallbacks |
| Lock acquisition accounting | Document per-song lock acquisitions; combine info-extract + download into one call if possible |
| Poll loop resilience | `try/finally` guarantees `self.after()` re-schedule regardless of handler exceptions |
| One dialog at a time | Flag + re-queue deferred `confirm_folder` events |
| Fresh result_holder per call | New `dict` in worker thread per confirmation |

---

## Phase Recommendations

| Phase Topic | Likely Pitfall | Required Mitigation |
|-------------|---------------|---------------------|
| URL input parsing | Substring match misroutes; playlist params bleed | `urlparse` hostname; `strip_playlist_param`; validate before any thread |
| YouTube direct URL handling | `youtu.be` short-links not normalized | Normalize to canonical `watch?v=` form |
| yt-dlp info extraction | `None` fields; private/age-restricted; 429 | `.get()` fallbacks; same flags as download; under `_download_lock` |
| Spotify → ytsearch metadata | Wrong artist from YouTube channel name | Use Spotify API metadata for folder proposal only |
| Folder confirmation (threading.Event) | Event never set → deadlock | `wait(timeout=300)`; always-set in all exit paths |
| Multiple parallel songs → dialog | Stacking | One-at-a-time enforcement with re-queue deferral |
| Dialog z-order on Windows | Dialog invisible | `transient` + `lift` + `focus_force` + `grab_set` — all four |
| _poll_queue exception handling | Loop stops → workers starve | `try/finally` for guaranteed re-schedule |
| result_holder state | Wrong path to wrong song | Fresh `dict` per call; never `self._result_holder` |

---

*Pitfalls research: 2026-05-06 — focused on v1.0 new features*
