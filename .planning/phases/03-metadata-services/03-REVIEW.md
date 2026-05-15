---
phase: 03-metadata-services
reviewed: 2026-05-15T00:00:00Z
depth: standard
files_reviewed: 2
files_reviewed_list:
  - tunebridge.py
  - tests/test_metadata_services.py
findings:
  critical: 3
  warning: 5
  info: 2
  total: 10
status: issues_found
---

# Phase 03: Code Review Report

**Reviewed:** 2026-05-15T00:00:00Z
**Depth:** standard
**Files Reviewed:** 2
**Status:** issues_found

## Summary

Two files reviewed: the main application module (`tunebridge.py`) and the Phase 3 test suite (`tests/test_metadata_services.py`). The core metadata-routing logic is structurally sound and the Signal-based cross-thread dispatch is correct in principle. However, three blockers were found: a race condition in `SpotifyClient` token refresh that causes data corruption under concurrent load, a `None`-dereference crash when `spotify_client=None` is passed to `fetch_metadata_for_row`, and credential values being retained in memory as plain strings with no zeroing. Five warnings cover incomplete error handling, a leaky `ThreadPoolExecutor` in the demo path, a silent fallback that loses the real Spotify resource ID, and two test reliability gaps.

---

## Critical Issues

### CR-01: Race condition in `SpotifyClient._get_token` — token corruption under concurrent fetch

**File:** `tunebridge.py:177-192`

**Issue:** `_get_token` reads `self._token` and `self._token_expiry`, decides a refresh is needed, then writes back the new token — all without any lock. When `_MAX_WORKERS=4` workers call this concurrently during the first batch (token is `None`), all four threads pass the `if self._token and …` guard, all four POST to the token endpoint, and the last write wins. In practice this means three redundant token fetches and a window where `self._token_expiry` is from one response while `self._token` is from another, producing an immediately-invalid cached token that causes every subsequent call to re-POST, hammering the Spotify rate limit.

**Fix:**
```python
import threading

class SpotifyClient:
    def __init__(self, client_id: str, client_secret: str):
        self._client_id     = client_id
        self._client_secret = client_secret
        self._token:        str | None = None
        self._token_expiry: float      = 0.0
        self._token_lock   = threading.Lock()   # add this

    def _get_token(self) -> str:
        with self._token_lock:                  # guard entire check+refresh
            if self._token and time.time() < self._token_expiry:
                return self._token
            credentials = base64.b64encode(
                f"{self._client_id}:{self._client_secret}".encode()
            ).decode()
            resp = requests.post(
                self.TOKEN_URL,
                headers={"Authorization": f"Basic {credentials}"},
                data={"grant_type": "client_credentials"},
            )
            resp.raise_for_status()
            payload = resp.json()
            self._token        = payload["access_token"]
            self._token_expiry = time.time() + payload["expires_in"] - self.TTL_BUFFER
            return self._token
```

---

### CR-02: `None`-dereference crash in `fetch_metadata_for_row` when `spotify_client=None`

**File:** `tunebridge.py:287`

**Issue:** When `_spotify_enabled` is `False`, `TuneBridgeApp._process_urls` correctly short-circuits Spotify rows with `"Failed — metadata"` before calling `_executor.submit`. However, `fetch_metadata_for_row` is a public function whose signature accepts `spotify_client: SpotifyClient | None`, and its body at line 287 calls `spotify_client.get_album_metadata(resource_id)` and at line 289 calls `spotify_client.get_track_metadata(resource_id)` without any None guard. Any direct caller (including future phases or tests that construct the function call themselves) will get an `AttributeError: 'NoneType' object has no attribute 'get_album_metadata'` crash. The guard in `_process_urls` is not sufficient because it is a separate callsite, not a contract enforced in the function itself.

**Fix:**
```python
def fetch_metadata_for_row(
    url: str,
    url_type: str,
    spotify_client: "SpotifyClient | None",
    yt_extractor: "YoutubeExtractor",
) -> dict:
    if url_type == "Spotify":
        if spotify_client is None:
            raise ValueError("spotify_client is required for Spotify URLs")
        m = _SPOTIFY_RESOURCE_RE.search(url)
        ...
```

---

### CR-03: Spotify client credentials retained in memory as plain strings

**File:** `tunebridge.py:613-616`

**Issue:** `client_id` and `client_secret` are stored on `self._spotify_client` as `self._client_id` and `self._client_secret` (plain `str` attributes, lines 173-174) and are never zeroed. Because Python strings are immutable and interned, there is no way for the GC to collect them promptly, and a heap dump or memory inspection reveals the raw credentials in cleartext for the application's entire lifetime. Additionally, `_get_token` constructs the Base64-encoded `credentials` string (line 181) and leaves it on the stack — it is not zeroed either. While this is a common limitation in Python, the issue is that `_client_secret` is kept permanently when it only needs to be available during token refresh.

**Fix:** Store the pre-encoded Authorization header instead of the raw secret, so the secret itself is referenced only during `__init__` and then discarded:
```python
def __init__(self, client_id: str, client_secret: str):
    # encode once; do not store raw secret beyond this scope
    self._auth_header = "Basic " + base64.b64encode(
        f"{client_id}:{client_secret}".encode()
    ).decode()
    self._token:        str | None = None
    self._token_expiry: float      = 0.0

def _get_token(self) -> str:
    with self._token_lock:
        if self._token and time.time() < self._token_expiry:
            return self._token
        resp = requests.post(
            self.TOKEN_URL,
            headers={"Authorization": self._auth_header},
            data={"grant_type": "client_credentials"},
        )
        ...
```

---

## Warnings

### WR-01: Silent fallback loses real Spotify resource ID when URL does not match regex

**File:** `tunebridge.py:283-285`

**Issue:** When `_SPOTIFY_RESOURCE_RE` fails to match (line 283), the code silently falls back to `url.split("/")[-1].split("?")[0]` as `resource_id` and hard-codes `resource_type = "track"`. If a valid Spotify URL has an unexpected locale prefix or path structure that the regex does not cover, this fallback sends an incorrect ID to the API, returning a 404 that is swallowed by `_metadata_worker`'s broad `except Exception` and displayed as `"Failed — metadata"` with no diagnostic information. The user sees failure with no actionable message.

**Fix:** Either assert the regex must match (and surface a descriptive error), or log the fallback path so failures are diagnosable:
```python
m = _SPOTIFY_RESOURCE_RE.search(url)
if not m:
    raise ValueError(f"Cannot parse Spotify resource from URL: {url!r}")
resource_type = m.group(1)
resource_id   = m.group(2)
```

---

### WR-02: `_start_demo` creates a second `ThreadPoolExecutor` that is never shut down

**File:** `tunebridge.py:696-709`

**Issue:** `_start_demo` (line 696) creates a new `ThreadPoolExecutor` inside a `with` block on a daemon thread. When the daemon thread finishes, the pool is shut down by the context manager — that part is correct. However, the outer `threading.Thread(target=run, daemon=True)` is a daemon thread. If the main window closes while the daemon thread is blocked waiting inside `as_completed`, Python's shutdown sequence kills the daemon thread without running the `with` block's `__exit__`, leaving the pool's internal resources (e.g., `_work_queue`, worker threads) in an inconsistent state. More importantly, `_start_demo` is documented as "kept for Phase 1 backward-compat" but is dead code — it is never called from any UI element. Dead production code that creates threads should be removed.

**Fix:** Remove `_start_demo` and `_mock_worker` if they are not reachable from the UI. If kept for testing, gate them with `if __debug__:` or move them to a test helper.

---

### WR-03: `closeEvent` shuts down executor with `wait=False` — in-flight workers may crash after Qt teardown

**File:** `tunebridge.py:742-745`

**Issue:** `self._executor.shutdown(wait=False)` returns immediately while workers may still be running. Workers call `self._dispatcher.metadata_ready.emit(...)` and `self._dispatcher.row_status_changed.emit(...)` after the window (and its Qt objects) have been destroyed. In PySide6, emitting a signal to a deleted QObject causes a `RuntimeError: Internal C++ object ... already deleted`. `wait=False` is appropriate for responsiveness, but the workers need a cancellation flag checked before emitting.

**Fix:**
```python
def __init__(self):
    ...
    self._closing = threading.Event()

def _metadata_worker(self, row_id: int, url: str, url_type: str) -> None:
    try:
        if self._closing.is_set():
            return
        metadata = fetch_metadata_for_row(...)
        if not self._closing.is_set():
            self._dispatcher.metadata_ready.emit(row_id, metadata)
    except Exception:
        if not self._closing.is_set():
            self._dispatcher.row_status_changed.emit(row_id, "Failed — metadata")

def closeEvent(self, event) -> None:
    self._closing.set()
    self._executor.shutdown(wait=False)
    super().closeEvent(event)
```

---

### WR-04: `_metadata_worker` swallows all exceptions silently — no logging

**File:** `tunebridge.py:739-740`

**Issue:** `except Exception: pass` (bare except with only an emit) discards the exception entirely. When a worker fails, the status shows `"Failed — metadata"` but there is no record of what went wrong. This makes debugging network errors, API rate-limit responses, and malformed URLs impossible without a debugger attached.

**Fix:**
```python
except Exception as exc:
    import logging
    logging.getLogger(__name__).warning(
        "Metadata fetch failed for row %d (%s): %s", row_id, url, exc
    )
    if not self._closing.is_set():
        self._dispatcher.row_status_changed.emit(row_id, "Failed — metadata")
```

---

### WR-05: `remove_selected_rows` rebuilds `_rows` dict with an assumption about contiguous ordering that breaks after prior deletions

**File:** `tunebridge.py:496-510`

**Issue:** After removing rows, `_rows` is rebuilt (lines 504-509) by iterating `sorted(self._rows)` and re-enumerating to produce new keys `0, 1, 2, …`. However, `QTableWidget.removeRow(row)` shifts all rows below the deleted one upward. After multiple delete operations the `_rows` dict key (which represents the logical row index used by `_dispatcher` signals) drifts from the actual `QTableWidget` row index. If a worker emits `metadata_ready` with a stale `row_id` while the user is deleting rows concurrently, `update_row_metadata` will update the wrong row.

The root issue is that `row_id` is used both as the `_rows` dict key and as the `QTableWidget` row index, but the latter changes on delete while the former is rebuilt by re-enumeration. These two uses need to be decoupled (e.g., use a stable UUID or per-session incrementing ID stored alongside the row).

**Fix:** Use a separate monotonically-increasing ID for worker tracking, independent of the display row index. Store a mapping `{stable_id: qt_row_index}` and update it on delete.

---

## Info

### IN-01: `_on_clear` typed as `callable | None` — should be `Callable[[], None] | None`

**File:** `tunebridge.py:419`

**Issue:** `self._on_clear: "callable | None" = None` uses the built-in `callable` (lowercase) as a type annotation, which is not a valid type hint. The correct annotation is `Callable[[], None] | None` from `collections.abc` or `typing`. At runtime this is ignored (it's in a string), but it will confuse type checkers and readers.

**Fix:**
```python
from collections.abc import Callable
...
self._on_clear: Callable[[], None] | None = None
```

---

### IN-02: Test `test_batch_table_update_row_metadata_status_transitions_to_done` has an overly-loose assertion

**File:** `tests/test_metadata_services.py:343`

**Issue:** The test asserts `status_item.text() in ("Metadata ready", "Fetching metadata", "Done")`. Accepting `"Fetching metadata"` means the test passes even if `update_row_metadata` never updates the status at all (the row starts as `"Queued"` after `add_row`, transitions to `"Fetching metadata"` only if `_process_urls` is called, but here `add_row` is called directly so the initial status is `"Queued"` — not `"Fetching metadata"`). In practice this means the test accepts any of three states and would not catch a regression where `update_row_metadata` fails to transition the status. The test should assert the exact expected value `"Metadata ready"`.

**Fix:**
```python
assert status_item.text() == "Metadata ready"
```

---

_Reviewed: 2026-05-15T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
