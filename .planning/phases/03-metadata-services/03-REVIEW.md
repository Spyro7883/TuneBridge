---
phase: 03-metadata-services
reviewed: 2026-05-15T17:02:00Z
depth: standard
files_reviewed: 3
files_reviewed_list:
  - tunebridge.py
  - tests/test_metadata_services.py
  - tests/test_tunebridge.py
findings:
  critical: 4
  warning: 6
  info: 3
  total: 13
status: issues_found
---

# Phase 03: Code Review Report

**Reviewed:** 2026-05-15T17:02:00Z
**Depth:** standard
**Files Reviewed:** 3
**Status:** issues_found

## Summary

Three files reviewed: `tunebridge.py`, `tests/test_metadata_services.py`, and `tests/test_tunebridge.py`. The Signal-based cross-thread dispatch is structurally correct. The metadata routing and YouTube title parsing are sound. Four blockers were found: a stat card undercount when Spotify rows fail fast due to missing credentials (the `_on_row_failed` callback fires before `_card_valid` is ever incremented, decrementing from zero), a race condition in `SpotifyClient._get_token` under concurrent workers, a `None`-dereference crash path in `fetch_metadata_for_row`, and a regex structural mismatch between `_SPOTIFY_RE` and `_SPOTIFY_RESOURCE_RE` that can route a classified URL into the silent fallback. Six warnings cover the silent resource-ID fallback, thread shutdown safety, exception swallowing, executor lifecycle, a weak test assertion, and a missing test for the credential-gating stat card path.

---

## Critical Issues

### CR-01: Stat card undercount — `_on_row_failed` fires before `_card_valid` is incremented for Spotify-no-credentials rows

**File:** `tunebridge.py:670-688`

**Issue:** In `_process_urls`, when a Spotify URL arrives but `_spotify_enabled` is `False`, the code emits `row_status_changed("Failed — metadata")` at line 672 **inside the loop**, before the loop ends. The signal connection uses `AutoConnection`, and because this runs on the main thread, the slot fires **synchronously**. The slot calls `update_row_status`, which calls `_on_row_failed`, which executes:

```python
self._card_valid.set_count(max(0, self._card_valid.count() - 1))
self._card_invalid.set_count(self._card_invalid.count() + 1)
```

At this point `_card_valid` has **not yet been incremented** for this batch (the `set_count(count() + valid_count)` at line 687 runs after the loop). So `_card_valid` is decremented from its pre-batch value — potentially below the true count, or clamped to 0 (hiding the underflow). `_card_invalid` is incremented once by `_on_row_failed`, but the Spotify-no-credentials row is also not added to `invalid_count` (the `else` branch at line 684 only runs for truly unclassified URLs). So this row is counted in neither `valid_count` nor `invalid_count`. The final `set_count` calls at lines 687-688 do not correct for it. Net result: one Spotify-no-credentials row causes `_card_valid` to go from X to `max(0, X-1)` and `_card_invalid` to go from Y to `Y+1`, even when X was already 0 — the counts are permanently wrong for the session.

**Fix:** Do not call `_on_row_failed` during the loop. Instead, track failed-credential rows separately and apply all card adjustments in a single post-loop update:

```python
valid_count   = 0
invalid_count = 0
cred_fail_count = 0   # Spotify rows rejected due to missing credentials

for url in candidates:
    url_type = classify_url(url)
    if url_type is not None:
        row_id = self.table.add_row(url=url, url_type=url_type)
        if url_type == "Spotify" and not self._spotify_enabled:
            # Emit the status update (UI only), but defer card accounting
            self._dispatcher.row_status_changed.emit(row_id, "Failed — metadata")
            cred_fail_count += 1
        else:
            valid_count += 1
            self._dispatcher.row_status_changed.emit(row_id, SongStatus.FETCHING.value)
            self._executor.submit(self._metadata_worker, row_id, url, url_type)
    else:
        self.table.add_row(url=url, url_type="Invalid URL")
        invalid_count += 1

# Apply all card adjustments once, after the loop
self._card_valid.set_count(self._card_valid.count() + valid_count)
self._card_invalid.set_count(self._card_invalid.count() + invalid_count + cred_fail_count)
```

Note: `_metadata_worker` can still call `_on_row_failed` for async failures (network errors) because by then the initial card increment has already run. You may want to rename the callback to clarify it is for async failures only.

---

### CR-02: Race condition in `SpotifyClient._get_token` — token corruption under concurrent fetch

**File:** `tunebridge.py:177-192`

**Issue:** `_get_token` reads `self._token` and `self._token_expiry`, decides a refresh is needed, then writes the new token — all without any lock. When `_MAX_WORKERS=4` workers call this concurrently during the first batch (token is `None`), all four threads pass the `if self._token and …` guard simultaneously, all four POST to the token endpoint, and the last write wins. This creates a window where `self._token_expiry` is from one response while `self._token` is from another — producing an immediately-invalid cached token that causes every subsequent call to re-POST, hammering the Spotify rate limit.

**Fix:**
```python
import threading

class SpotifyClient:
    def __init__(self, client_id: str, client_secret: str):
        self._client_id     = client_id
        self._client_secret = client_secret
        self._token:        str | None = None
        self._token_expiry: float      = 0.0
        self._token_lock    = threading.Lock()   # add this

    def _get_token(self) -> str:
        with self._token_lock:
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

### CR-03: `_SPOTIFY_RE` and `_SPOTIFY_RESOURCE_RE` have different locale-prefix structures — classified URLs can fall into the broken fallback

**File:** `tunebridge.py:125` and `tunebridge.py:266-268`

**Issue:** The two regexes use structurally different patterns for locale prefixes:

- `_SPOTIFY_RE` (line 125): `(?:[a-z]{2}/|intl-[a-z]+/)?` — one optional group, two **alternatives** (either a 2-letter prefix OR an intl prefix, not both)
- `_SPOTIFY_RESOURCE_RE` (line 266): `(?:[a-z]{2}/)?(?:intl-[a-z]+/)?` — two **separate** optional groups (2-letter prefix AND/OR intl prefix, independently)

For a URL like `open.spotify.com/intl-ro/track/abc`, both match. But their behaviour differs for edge cases. More critically: any URL that `_SPOTIFY_RE` accepts as "Spotify" must also be parseable by `_SPOTIFY_RESOURCE_RE`. If the structures diverge (e.g., a new Spotify URL format satisfies one but not the other), `fetch_metadata_for_row` at line 283 falls into the silent fallback (`resource_id = url.split("/")[-1]`, `resource_type = "track"`), sending a wrong ID to the API and silently failing as `"Failed — metadata"`.

Both regexes should use the identical locale-prefix pattern. The `_SPOTIFY_RESOURCE_RE` two-group form is strictly more permissive and should be used in both places:

```python
_LOCALE_PREFIX = r"(?:[a-z]{2}/)?(?:intl-[a-z]+/)?"

_SPOTIFY_RE = re.compile(
    r"open\.spotify\.com/" + _LOCALE_PREFIX + r"(track|album|playlist|artist)/"
)
_SPOTIFY_RESOURCE_RE = re.compile(
    r"open\.spotify\.com/" + _LOCALE_PREFIX + r"(track|album)/([A-Za-z0-9]+)"
)
```

---

### CR-04: `None`-dereference crash in `fetch_metadata_for_row` when `spotify_client=None`

**File:** `tunebridge.py:286-288`

**Issue:** The function signature declares `spotify_client: "SpotifyClient | None"` but the body calls `spotify_client.get_album_metadata(...)` and `spotify_client.get_track_metadata(...)` without a `None` guard. The protection exists only in `_process_urls`, a single callsite. Any future callsite (test, CLI, Phase 4 orchestrator) that passes `None` with `url_type="Spotify"` crashes with `AttributeError: 'NoneType' object has no attribute 'get_album_metadata'`. The type signature promises safety but the implementation does not enforce it.

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

## Warnings

### WR-01: Silent fallback in `fetch_metadata_for_row` loses the real resource ID

**File:** `tunebridge.py:283-285`

**Issue:** When `_SPOTIFY_RESOURCE_RE` fails to match, the code silently uses `url.split("/")[-1].split("?")[0]` as `resource_id` and hard-codes `resource_type = "track"`. If the regex fails (e.g., due to the structural mismatch in CR-03, or a new Spotify URL format), the function sends a wrong ID to the API, gets a 404, which `_metadata_worker` swallows as `"Failed — metadata"` with no diagnostic information.

**Fix:** Raise on regex failure rather than guessing:
```python
m = _SPOTIFY_RESOURCE_RE.search(url)
if not m:
    raise ValueError(f"Cannot parse Spotify resource from URL: {url!r}")
resource_type = m.group(1)
resource_id   = m.group(2)
```

---

### WR-02: `closeEvent` with `wait=False` — in-flight workers may emit signals to deleted Qt objects

**File:** `tunebridge.py:765-768`

**Issue:** `self._executor.shutdown(wait=False)` returns immediately while workers may still be running. Workers call `self._dispatcher.metadata_ready.emit(...)` or `self._dispatcher.row_status_changed.emit(...)` after the window and its Qt objects are destroyed. In PySide6 this causes `RuntimeError: Internal C++ object ... already deleted`.

**Fix:** Add a cancellation flag checked before any emit:
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
    except Exception as exc:
        if not self._closing.is_set():
            self._dispatcher.row_status_changed.emit(row_id, "Failed — metadata")

def closeEvent(self, event) -> None:
    self._closing.set()
    self._executor.shutdown(wait=False)
    super().closeEvent(event)
```

---

### WR-03: `_metadata_worker` discards exception information — failures are undiagnosable

**File:** `tunebridge.py:762-763`

**Issue:** `except Exception:` with no logging discards the actual error. When a row shows `"Failed — metadata"`, there is no way to determine whether the failure was a network timeout, an API 429, a malformed URL, or a code bug without attaching a debugger.

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

### WR-04: `_start_demo` creates a second `ThreadPoolExecutor` inside a daemon thread with no shutdown safety

**File:** `tunebridge.py:706-732`

**Issue:** `_start_demo` spawns a daemon thread that creates a `ThreadPoolExecutor` via a `with` block. If the main window closes while this daemon thread is blocked in `as_completed`, Python kills the daemon without running `__exit__`, leaving the pool's worker threads and queue in an inconsistent state. More importantly, `_start_demo` is dead code — it is never connected to any UI element. Dead threaded code creates maintenance and crash risk.

**Fix:** Remove `_start_demo` and `_mock_worker` if they are unreachable from the UI. If retained for manual testing, move them out of production code (test helper module or `if __debug__:` block).

---

### WR-05: `remove_selected_rows` row-index drift when workers emit stale `row_id` after deletion

**File:** `tunebridge.py:499-521`

**Issue:** `row_id` is used as both the `QTableWidget` row index and the worker tracking key. `QTableWidget.removeRow(row)` shifts all subsequent rows up. After deletion, `_rows` is rebuilt with re-enumerated keys (0, 1, 2, …), but any in-flight worker holds the original `row_id`. If that worker emits `metadata_ready` or `row_status_changed` with the old `row_id`, `update_row_metadata` or `update_row_status` will update the **wrong row** (or a completely different song's row).

**Fix:** Decouple the stable worker ID from the display row index. Use a monotonically-increasing session counter as the worker ID and maintain a `{stable_id: qt_row_index}` mapping that is updated on deletion.

---

### WR-06: Test `test_batch_table_update_row_metadata_status_transitions_to_done` assertion accepts states that prove nothing

**File:** `tests/test_metadata_services.py:343`

**Issue:** `assert status_item.text() in ("Metadata ready", "Fetching metadata", "Done")`. The initial status after `add_row` is `"Queued"`, not `"Fetching metadata"`, so `"Fetching metadata"` in the allowed set is unreachable. Accepting `"Done"` (which `update_row_metadata` never sets) also weakens the assertion. The test passes even if `update_row_metadata` fails to change the status, as long as the text happens to be one of the three strings.

**Fix:**
```python
assert status_item.text() == "Metadata ready"
```

---

## Info

### IN-01: Credential secrets retained in memory as plain strings for application lifetime

**File:** `tunebridge.py:173-174`

**Issue:** `self._client_id` and `self._client_secret` are stored as plain `str` attributes and are never zeroed. A heap dump or memory inspection exposes raw credentials for the entire process lifetime. While Python's GC cannot guarantee prompt collection of immutable strings, storing the pre-encoded Authorization header instead of the raw secret reduces the window during which the secret is addressable.

**Fix:** Encode once in `__init__` and store only the header value; do not retain the raw secret:
```python
def __init__(self, client_id: str, client_secret: str):
    self._auth_header = "Basic " + base64.b64encode(
        f"{client_id}:{client_secret}".encode()
    ).decode()
    self._token:        str | None = None
    self._token_expiry: float      = 0.0
```

---

### IN-02: `_on_clear`, `_on_rows_removed`, `_on_row_failed` typed as `"callable | None"` — invalid type hint

**File:** `tunebridge.py:418-420`

**Issue:** `callable` (lowercase) is a built-in function, not a valid generic type hint. The string-form annotation silences the type checker at runtime, but static analysers (mypy, pyright) will reject it. The correct annotation is `Callable[..., None] | None` from `collections.abc`.

**Fix:**
```python
from collections.abc import Callable
self._on_clear:        Callable[[], None] | None = None
self._on_rows_removed: Callable[[int, int], None] | None = None
self._on_row_failed:   Callable[[], None] | None = None
```

---

### IN-03: `test_batch_table_update_row_metadata_youtube_label_round_trip` never asserts label content

**File:** `tests/test_metadata_services.py:346-359`

**Issue:** The test adds a YouTube row, calls `update_row_metadata` with `artist="Artist"` and `track_title="Song"`, then asserts only `url_item is not None`. It never checks what text was written to the cell. The test name implies a "round trip" verification but would pass even if `update_row_metadata` wrote an empty string or the wrong value.

**Fix:** Add a content assertion:
```python
url_item = window.table._table.item(row_id, 0)
assert url_item is not None
assert "Artist" in url_item.text()
assert "Song" in url_item.text()
```

---

_Reviewed: 2026-05-15T17:02:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
