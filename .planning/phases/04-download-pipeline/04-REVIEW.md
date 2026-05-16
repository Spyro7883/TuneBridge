---
phase: 04-download-pipeline
reviewed: 2026-05-16T15:30:00Z
depth: standard
files_reviewed: 2
files_reviewed_list:
  - tunebridge.py
  - tests/test_download_pipeline.py
findings:
  critical: 0
  warning: 0
  info: 3
  total: 3
status: fixed
fixed: 2026-05-16T20:00:00Z
---

# Phase 4: Code Review Report

**Reviewed:** 2026-05-16T15:30:00Z
**Depth:** standard
**Files Reviewed:** 2
**Status:** issues_found

## Summary

Reviewed the Phase 4 download pipeline implementation in `tunebridge.py` and its test suite `tests/test_download_pipeline.py`. The core pipeline logic (worker routing, retune, lock serialisation) is structurally sound. However, four blockers exist: a race condition in `_start_processing` that dispatches workers before the batch-completion slot is connected, a subprocess injection vector through unsanitised search query strings, a resource leak when the `_closing` flag fires after `row_tmp` is created but before `_temp_paths` is populated, and a test that constructs `TuneBridgeApp` via `__new__` while skipping `__init__`, leaving the real `_session_tmp` tempdir to leak. Six warnings cover unhandled `Path` non-existence assumptions, silent swallowed exceptions in `retune_file`, incomplete `update_row_status` failure routing, a thread-safety issue with `_temp_paths`, a missing UI-unlock path when `_start_processing` finds no jobs, and duplicate `MP3`/`ID3` imports inside `retune_file`. Three info items cover magic literals, a bare-except inside `_kill_if_stuck`, and a minor test-isolation concern.

---

## Critical Issues

### CR-01: Race — workers submitted before `_on_download_row_finished` slot is connected

**File:** `tunebridge.py:1045-1053`
**Issue:** `_start_processing` calls `self._dispatcher.row_status_changed.connect(self._on_download_row_finished)` at line 1045, then immediately submits all workers in the loop starting at line 1050. On any OS with ≥2 CPUs the first worker can finish and emit `row_status_changed` before the connect at line 1045 has had time to propagate through Qt's internal signal bookkeeping — or, more concretely, the worker runs on a thread-pool thread and emits the signal synchronously while the main thread is still in the `for` loop below the connect call. Because Qt queued connections are safe across threads, the signal is *queued* and processed after the `for` loop returns, so the connect itself is fine — **but the batch counters (`_download_total`, `_download_done`, `_download_failed`) are reset to zero at lines 1040-1042, which happens AFTER the connect at line 1045**. Any signal that fires after connect but before the reset will read a stale `_download_total` of 0, causing `finished < self._download_total` (line 976) to evaluate as `0 < 0` → False, immediately printing "Done — 0 downloaded, 0 failed" and disconnecting the slot before the real batch completes.

**Fix:** Reset counters and connect the slot in the correct order — reset first, connect second, submit workers last:
```python
# Reset batch counters FIRST
self._download_total   = len(jobs)
self._download_done    = 0
self._download_failed  = 0

# Connect slot SECOND (slot now sees correct _download_total)
self._dispatcher.row_status_changed.connect(self._on_download_row_finished)

self.statusBar().showMessage(f"Downloading 0 / {self._download_total}…")

# Submit workers LAST
for row_id, url, url_type, metadata in jobs:
    self._executor.submit(
        self._download_worker, row_id, url, url_type, metadata, hz_mode
    )
```

---

### CR-02: Command injection via unsanitised `ytsearch:` query string

**File:** `tunebridge.py:925-927`
**Issue:** The Spotify search query is built as:
```python
search_url = f"ytsearch:{artist} {title} audio"
```
`artist` and `title` come from `metadata`, which is populated from Spotify OG tags (scraped HTML). A malicious or malformed Spotify page can inject arbitrary text. While `subprocess.Popen` with a list argument (not `shell=True`) prevents *shell* injection, yt-dlp itself parses `ytsearch:` strings and passes them to the YouTube search API. A crafted value like `artist = '; rm -rf ~; echo '` would not cause shell execution here, but values containing yt-dlp option-like prefixes (e.g. a title starting with `--cookies-from-browser firefox; ...`) could be misinterpreted by yt-dlp's own argument parsing if it ever receives the query as a single CLI token. More concretely: if `artist` or `title` contain newlines (possible from HTML injection), the `ytsearch:` string is passed as a single list element to Popen and is safe from the shell, but yt-dlp may split on newlines internally. The real risk is that there is **zero validation or sanitisation** of external HTML content before embedding it in a subprocess argument.

**Fix:** Strip or replace any characters that are not safe in a search query before building the string:
```python
import re as _re

def _sanitise_search_term(s: str) -> str:
    """Strip control characters and leading dashes from metadata fields."""
    s = _re.sub(r"[\x00-\x1f\x7f]", " ", s)   # remove control chars incl. newlines
    s = s.strip().lstrip("-")                    # prevent yt-dlp flag misparse
    return s[:100]                               # cap length

artist = _sanitise_search_term(metadata.get("artist", ""))
title  = _sanitise_search_term(metadata.get("track_title", ""))
search_url = f"ytsearch:{artist} {title} audio"
```

---

### CR-03: Temp directory leak when `_closing` fires mid-worker

**File:** `tunebridge.py:919-948`
**Issue:** `_download_worker` creates `row_tmp` at line 921 unconditionally, before the `_closing` check at line 946. If `_closing` is set between `row_tmp.mkdir()` and the `if not self._closing.is_set()` guard at line 946, the directory is created but never stored in `_temp_paths` and never cleaned up — `closeEvent` calls `shutil.rmtree(self._session_tmp)` which would remove the parent, but only if `row_tmp` is a *subdirectory* of `_session_tmp`. Because `row_tmp = self._session_tmp / uuid.uuid4().hex[:8]` this is true, so the parent rmtree would catch it. **However**, if `retune_file` is running at close time, it creates its own `tempfile.TemporaryDirectory()` internally (line 192); that `TemporaryDirectory` is managed by its context manager and is cleaned up. The actual leak is that `row_tmp` itself (and any already-downloaded MP3 inside it) is orphaned in the filesystem if `_session_tmp` rmtree fails (e.g. Windows file-lock on the MP3 that yt-dlp still has open). The `ignore_errors=True` on line 1060 silently skips these locked files.

**Fix:** On Windows, add a finaliser that retries cleanup after the executor is drained, or use `atexit`:
```python
import atexit

# In __init__, after self._session_tmp is set:
atexit.register(shutil.rmtree, self._session_tmp, True)
```
This ensures cleanup even if `closeEvent` is bypassed (e.g. process kill) and provides a retry path after all threads have exited.

---

### CR-04: Test `test_spotify_search_query_uses_artist_and_title` bypasses `__init__`, leaks real tempdir

**File:** `tests/test_download_pipeline.py:57-70`
**Issue:** The test constructs `TuneBridgeApp` via `TuneBridgeApp.__new__(TuneBridgeApp)` (line 57), then manually sets a subset of instance attributes. It does **not** call `__init__`, so `self._session_tmp` is set to `Path("/tmp/tb_test")` (line 60) — a hard-coded path that may not exist on Windows (the CI/dev platform identified as `win32`). More critically, `tempfile.mkdtemp` is patched with `patch("tunebridge.tempfile.mkdtemp", return_value="/tmp/tb_test")` (line 53), but this patch is on `tunebridge.tempfile.mkdtemp`, while `__new__` never calls `__init__`, so `mkdtemp` is never invoked — the patch has no effect. The test also leaves `app._executor`, `app._row_metadata`, `app._download_lock_counter`, `app._itunes_client`, and `app._yt_extractor` unset; if `_download_worker` touches any of these (e.g. the except branch logs via `logging.getLogger(__name__).warning`), it will raise `AttributeError`, masking the real assertion. On Windows `/tmp/tb_test` does not exist as a directory, so `row_tmp.mkdir(parents=True, exist_ok=True)` will attempt to create `C:\tmp\tb_test\<uuid>` which may succeed and create a real filesystem artifact that is never cleaned.

**Fix:** Use the `window` fixture (which calls `__init__` properly) instead of `__new__`, and patch `Path.mkdir` to prevent real FS writes:
```python
def test_spotify_search_query_uses_artist_and_title(window):
    """DL-01: Spotify path builds ytsearch:{artist} {title} audio."""
    metadata = {"artist": "Portishead", "track_title": "Glory Box", "source": "Spotify"}
    with patch("tunebridge.download_track_for_row") as mock_dl, \
         patch("pathlib.Path.mkdir"):
        mock_dl.return_value = Path("/fake/track.mp3")
        with patch("tunebridge.uuid.uuid4") as mock_uuid:
            mock_uuid.return_value.hex = "abcdef1234567890"
            window._download_worker(0, "https://open.spotify.com/track/abc", "Spotify", metadata, 440)
        called_url = mock_dl.call_args[0][0]
        assert called_url == "ytsearch:Portishead Glory Box audio"
```

---

## Warnings

### WR-01: `_on_download_row_finished` runs on main thread but acquires a `threading.Lock`

**File:** `tunebridge.py:969-974`
**Issue:** The docstring at line 963 states "Runs on main thread via Qt queued connection" and then adds "lock is extra safety". Acquiring a `threading.Lock` on the main thread is not harmful in isolation, but if any other code path on a worker thread also acquires `_download_lock_counter` (e.g. future code), it introduces a potential deadlock where the main thread holds `_download_lock_counter` while the worker thread is blocked waiting on it, and the main thread is blocked on a modal dialog or event loop drain. The counter is only ever touched from `_on_download_row_finished` which is indeed main-thread-only, making the lock redundant and a maintenance footgun.

**Fix:** Remove `_download_lock_counter` entirely; use plain `int` increments since all writes happen on the main thread:
```python
# Remove: with self._download_lock_counter:
self._download_done   += 1   # or self._download_failed += 1
finished = self._download_done + self._download_failed
```

---

### WR-02: `_temp_paths` dict mutated from worker threads without synchronisation

**File:** `tunebridge.py:948`
**Issue:** `self._temp_paths[row_id] = downloaded` is executed inside `_download_worker` on a ThreadPoolExecutor thread (line 948). `_temp_paths` is a plain `dict`. Python's GIL makes individual `dict.__setitem__` calls atomic, but if Phase 5 reads `_temp_paths` from the main thread while a worker is writing, there is no happens-before guarantee that the write is visible to the reader (the GIL protects individual bytecode ops, not ordering between threads). On CPython this is practically safe, but it is an undocumented reliance on implementation detail. Additionally, two workers could both finish at exactly the same time and both call `dict.__setitem__` concurrently — CPython's GIL makes this safe for `dict`, but the code pattern is fragile and will break if moved to PyPy or a free-threaded CPython build.

**Fix:** Protect writes with `_download_lock_counter` (or a dedicated `threading.Lock`), or switch to `threading.local` / signal-based handoff:
```python
with self._download_lock_counter:
    self._temp_paths[row_id] = downloaded
```

---

### WR-03: Silent `except Exception: pass` in `retune_file` tag-writing block hides MP3 corruption

**File:** `tunebridge.py:216-217`
**Issue:** The ID3 tag restoration block (lines 204-217) catches all exceptions silently. If `mutagen` raises during `audio.save()` — e.g. because the output MP3 is still being written or the file is locked — the exception is swallowed and the file is returned to the caller as if tags were written. The caller (`_download_worker`) then moves forward to `SongStatus.AWAITING`, presenting the file as ready. The user receives an MP3 with no metadata tags, with no indication that tag writing failed.

**Fix:** Log the failure at WARNING level instead of passing silently:
```python
except Exception as exc:
    logging.getLogger(__name__).warning(
        "ID3 tag restoration failed for %s: %s", out_path, exc
    )
```

---

### WR-04: `update_row_status` only calls `_on_row_failed` for `"Failed — metadata"`, not `"Failed — download"`

**File:** `tunebridge.py:616-617`
**Issue:** The stat card sync callback `_on_row_failed` (which decrements `_card_valid` and increments `_card_invalid`) is triggered only when status equals `"Failed — metadata"` (line 616). When `_download_worker` emits `"Failed — download"` (line 957), `update_row_status` is called but `_on_row_failed` is NOT invoked. This means a download failure does not move the row from "valid" to "invalid" in the stat cards — the "Valide" count stays inflated.

**Fix:** Extend the condition to include both failure statuses:
```python
FAILURE_STATUSES = {"Failed — metadata", "Failed — download"}
if status in FAILURE_STATUSES and self._on_row_failed:
    self._on_row_failed()
```

---

### WR-05: `_start_processing` does not re-enable UI when `jobs` list is empty

**File:** `tunebridge.py:1030-1031`
**Issue:** If `jobs` is empty (line 1030), `_start_processing` returns early without re-enabling `_paste_box`, `_btn_440`, `_btn_432`, or `_btn_start`. The UI-lock (lines 1034-1037) has not yet been applied at this point — the early return is before the lock — so this is technically safe today. However, the UI-disable block and the jobs-collection loop are interleaved in a way that is fragile: `_refresh_start_button` must have correctly gated the button (all rows METADATA_READY), and if it incorrectly enabled the button with zero ready rows, the early return at line 1031 leaves the button enabled but in a broken state. There is no assertion or log when this guard fires.

**Fix:** Add a warning log so silent no-ops are visible during debugging:
```python
if not jobs:
    logging.getLogger(__name__).warning("_start_processing called with no METADATA_READY rows")
    return
```

---

### WR-06: `retune_file` imports `mutagen.mp3.MP3` and `mutagen.id3.ID3` twice

**File:** `tunebridge.py:184-186` and `tunebridge.py:206-207`
**Issue:** `from mutagen.mp3 import MP3` and `from mutagen.id3 import ID3` appear inside two separate `try` blocks within the same function call. The first (lines 184-186) reads the original tags; the second (lines 206-207) writes them to the output file. Each function call to `retune_file` performs two redundant dynamic imports. While Python caches module imports in `sys.modules` making this cheap, it is a code smell that suggests copy-paste from the original and increases the risk that one block is changed while the other is not.

**Fix:** Move both imports to the top of the file alongside the other imports, or at minimum hoist them to the top of `retune_file`:
```python
def retune_file(in_path: Path, out_path: Path) -> None:
    try:
        from mutagen.mp3 import MP3
        from mutagen.id3 import ID3
    except ImportError:
        MP3 = ID3 = None
    ...
```

---

## Info

### IN-01: Magic number `600` (timeout seconds) is an unexplained literal

**File:** `tunebridge.py:257`
**Issue:** `threading.Timer(600, _kill_if_stuck)` — 600 seconds (10 minutes) is a reasonable yt-dlp timeout, but the value is a bare magic number with no named constant or comment explaining the rationale.

**Fix:**
```python
_YTDLP_TIMEOUT_SECONDS = 600   # 10 min — generous for slow networks and large files

timer = threading.Timer(_YTDLP_TIMEOUT_SECONDS, _kill_if_stuck)
```

---

### IN-02: Bare `except Exception: pass` in `_kill_if_stuck` swallows unexpected errors silently

**File:** `tunebridge.py:253-255`
**Issue:** The `_kill_if_stuck` nested function has a bare `except Exception: pass`. While process-kill errors (e.g. `ProcessLookupError`) are expected and safe to ignore, swallowing all exceptions prevents visibility into unexpected errors (e.g. `PermissionError` on Windows where process kill may be denied).

**Fix:** Log at DEBUG level:
```python
except Exception as exc:
    logging.getLogger(__name__).debug("_kill_if_stuck: %s", exc)
```

---

### IN-03: `test_spotify_search_query_uses_artist_and_title` patches `tunebridge.tempfile.mkdtemp` but the patch has no effect

**File:** `tests/test_download_pipeline.py:53`
**Issue:** The patch `patch("tunebridge.tempfile.mkdtemp", return_value="/tmp/tb_test")` is applied, but since `__new__` is used instead of a full `__init__`, `mkdtemp` is never called. The patch is dead code in this test. This is a subset of CR-04 but worth noting independently: future readers may believe the patch is providing isolation when it is not.

**Fix:** Remove the `tempfile.mkdtemp` patch from this test once the test is refactored per CR-04 fix (using the `window` fixture). If keeping the `__new__` approach, remove the dead patch and replace with `patch("pathlib.Path.mkdir")`.

---

_Reviewed: 2026-05-16T15:30:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
