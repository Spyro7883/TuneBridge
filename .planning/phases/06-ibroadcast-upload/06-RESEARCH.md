# Phase 6: iBroadcast Upload — Research

**Phase:** 06 — iBroadcast Upload
**Date:** 2026-05-19
**Status:** Complete

---

## 1. iBroadcast API — Authentication

### Endpoint & Flow
iBroadcast uses a JSON POST login to obtain a session token:

```
POST https://api.ibroadcast.com/s/JSON/
Content-Type: application/json

{
  "mode": "status",
  "email_address": "<email>",
  "password": "<password>",
  "version": "0.0",
  "client": "tunebridge",
  "supported_types": 1
}
```

On success, the response contains:
```json
{
  "result": true,
  "user": {
    "token": "<session_token>",
    "id": <user_id>
  },
  "library": {
    "tracks": { "<track_id>": { "title": "...", "artist": "..." } }
  }
}
```

**Key insight:** The single `status` call returns BOTH the auth token AND the full library in one round-trip. This is exactly how `ibroadcastaio` and `deseven/ibroadcast-uploader` work — no separate library-fetch call needed.

**Error cases:**
- `result: false` + `message` field → wrong credentials (D-03: mark all UPLOADING rows as FAILED_UPLOAD)
- Network timeout → treat as auth failure

### Credential Names (D-01)
Match `.env.example` naming convention (`SPOTIFY_CLIENT_ID` → `IBROADCAST_USERNAME`, `IBROADCAST_PASSWORD`):

```python
username = os.environ.get("IBROADCAST_USERNAME", "")
password = os.environ.get("IBROADCAST_PASSWORD", "")
```

---

## 2. Library Fetch & Duplicate Detection

### What the API returns
The `status` call response includes `library.tracks` — a dict keyed by track ID:

```json
{
  "tracks": {
    "12345": {
      "title": "Bohemian Rhapsody",
      "artist": "Queen",
      "length": 354,
      "created": "2024-01-15"
    }
  }
}
```

### D-05: Title+Artist vs MD5 — Critical Clarification

**Server-side deduplication:** iBroadcast deduplicates uploaded files by **MD5 hash** server-side when receiving the upload request. If you upload the same file twice, iBroadcast silently ignores the second upload.

**Client-side pre-check (our approach, D-05):** We perform a title+artist comparison against the fetched library BEFORE uploading, to avoid the network cost of uploading a file that's already there. These are two different things:

| Layer | Method | Purpose |
|-------|--------|---------|
| Server (iBroadcast) | MD5 hash | Prevents duplicate file storage |
| Client (TuneBridge) | title+artist exact match | Skip upload bandwidth cost |

**Decision D-05 stands:** title+artist pre-check is correct for our use case. The user's library may contain tracks uploaded from different sources (different file encoding = different MD5 but same song). Title+artist match is the right semantic duplicate check.

**Implementation:**
```python
def _is_duplicate(title: str, artist: str, library: dict) -> bool:
    t = title.strip().casefold()
    a = artist.strip().casefold()
    for track in library.values():
        if (track.get("title", "").strip().casefold() == t and
                track.get("artist", "").strip().casefold() == a):
            return True
    return False
```

---

## 3. Upload Endpoint & Multipart Fields

### Endpoint
```
POST https://upload.ibroadcast.com/
```

### Required multipart/form-data fields
From `deseven/ibroadcast-uploader` and `ibroadcastaio` source:

| Field | Value |
|-------|-------|
| `file` | binary MP3 file content |
| `user_id` | user ID from login response |
| `token` | session token from login response |
| `file_path` | filename (e.g. `"Bohemian Rhapsody.mp3"`) |
| `method` | `"api"` |
| `client` | `"tunebridge"` |
| `supported_types` | `1` |

### Example with `requests`
```python
import requests

def upload_file(file_path: Path, user_id: int, token: str) -> bool:
    with open(file_path, "rb") as f:
        resp = requests.post(
            "https://upload.ibroadcast.com/",
            data={
                "user_id": user_id,
                "token": token,
                "file_path": file_path.name,
                "method": "api",
                "client": "tunebridge",
                "supported_types": 1,
            },
            files={"file": (file_path.name, f, "audio/mpeg")},
            verify=False,   # Windows SSL proxy constraint
            timeout=120,    # large files may take time
        )
    return resp.ok and resp.json().get("result", False)
```

### Response
```json
{"result": true, "message": "File uploaded"}
```
or
```json
{"result": false, "message": "Error description"}
```

---

## 4. Python Library Evaluation

| Library | Auth | Upload | Verdict |
|---------|------|--------|---------|
| `ibroadcast` 2.0.1 (current PyPI) | OAuth 2 only | Yes | **REJECT** — no email/password |
| `ibroadcastaio` 0.6.0 | email/password ✓ | Yes (async) | **REJECT** — async (`aiohttp`) incompatible with synchronous `ThreadPoolExecutor` workers |
| `ibroadcast` 1.1.2 (older PyPI) | email/password ✓ | Yes | **POSSIBLE** but pins to old version |
| **Raw `requests`** | email/password ✓ | Yes | **RECOMMENDED** — already imported, synchronous, matches worker pattern |

**Decision: Use raw `requests`** — already in `tunebridge.py` imports (line 28), synchronous (matches `_folder_worker` / `_download_worker` pattern), no new dependency, `verify=False` trivially supported.

---

## 5. Integration into Existing Codebase

### Key line to change (D-09)
```python
# tunebridge.py:1252 — CURRENT (Phase 5)
self._dispatcher.folder_batch_done.connect(self._unlock_ui)

# PHASE 6 REPLACEMENT
self._dispatcher.folder_batch_done.connect(self._start_upload_batch)
# _start_upload_batch calls _unlock_ui at the end instead
```

### New `_Dispatcher` signal
```python
# In _Dispatcher class (after line 529)
upload_batch_done = Signal()
```
Connect in `__init__`:
```python
self._dispatcher.upload_batch_done.connect(self._unlock_ui)
```

### New `SongStatus` values
```python
ALREADY_UPLOADED = "Already uploaded"
FAILED_UPLOAD    = "Failed — upload"
```

### New `_STATUS_COLORS` entries
```python
"Already uploaded": QColor("#14B8A6"),  # muted teal — distinct from Done green
"Failed — upload":  QColor("#EF4444"),  # same red as FAILED_SAVE (D-14)
```

### New counter vars in `__init__`
```python
# Phase 6: upload batch tracking
self._upload_total   = 0
self._upload_done    = 0
self._upload_existed = 0
self._upload_failed  = 0
```

### `_start_upload_batch` logic (D-04, D-09, D-13)
```python
def _start_upload_batch(self) -> None:
    uploading_rows = [
        row_id for row_id, path in self._saved_paths.items()
        # only rows that reached UPLOADING status
    ]

    # D-13: empty batch guard
    if not uploading_rows:
        self._unlock_ui()
        return

    # Check credentials (D-02)
    username = os.environ.get("IBROADCAST_USERNAME", "").strip()
    password = os.environ.get("IBROADCAST_PASSWORD", "").strip()
    if not username or not password:
        # Skip upload — treat all UPLOADING rows as Done (D-02)
        for row_id in uploading_rows:
            self._dispatcher.row_status_changed.emit(row_id, SongStatus.DONE.value)
        self._unlock_ui()
        return

    # Authenticate once (D-04)
    token, user_id, library = _ibroadcast_login(username, password)
    if token is None:
        # Auth failure — mark all as FAILED_UPLOAD (D-03)
        for row_id in uploading_rows:
            self._dispatcher.row_status_changed.emit(row_id, SongStatus.FAILED_UPLOAD.value)
        self._unlock_ui()
        return

    # Submit parallel workers (D-10)
    self._upload_total = len(uploading_rows)
    for row_id in uploading_rows:
        self._executor.submit(self._upload_worker, row_id, token, user_id, library)
```

### `_upload_worker` signature (D-10, D-16)
```python
def _upload_worker(self, row_id: int, token: str, user_id: int, library: dict) -> None:
    """Worker thread: duplicate check then upload. Per-row isolated (D-16)."""
    try:
        meta = self._row_metadata.get(row_id, {})
        title  = meta.get("title", "")
        artist = meta.get("artist", "")
        file_path = self._saved_paths[row_id]

        if _is_duplicate(title, artist, library):
            self._dispatcher.row_status_changed.emit(row_id, SongStatus.ALREADY_UPLOADED.value)
            self._on_upload_row_finished(row_id, SongStatus.ALREADY_UPLOADED.value)
            return

        success = _ibroadcast_upload(file_path, user_id, token)
        status = SongStatus.DONE if success else SongStatus.FAILED_UPLOAD
        self._dispatcher.row_status_changed.emit(row_id, status.value)
        self._on_upload_row_finished(row_id, status.value)
    except Exception as exc:
        logging.getLogger(__name__).warning("Upload failed row %d: %s", row_id, exc)
        self._dispatcher.row_status_changed.emit(row_id, SongStatus.FAILED_UPLOAD.value)
        self._on_upload_row_finished(row_id, SongStatus.FAILED_UPLOAD.value)
```

### `_on_upload_row_finished` pattern (mirrors `_on_folder_row_finished`)
```python
def _on_upload_row_finished(self, _row_id: int, status: str) -> None:
    terminal = (SongStatus.DONE.value, SongStatus.ALREADY_UPLOADED.value, SongStatus.FAILED_UPLOAD.value)
    if status not in terminal:
        return

    if status == SongStatus.DONE.value:
        self._upload_done += 1
    elif status == SongStatus.ALREADY_UPLOADED.value:
        self._upload_existed += 1
    else:
        self._upload_failed += 1

    finished = self._upload_done + self._upload_existed + self._upload_failed
    if finished < self._upload_total:
        self.statusBar().showMessage(f"Uploading {finished} of {self._upload_total}…")
        return

    self._dispatcher.upload_batch_done.emit()
    self.statusBar().showMessage(
        f"Done — {self._upload_done} uploaded, {self._upload_existed} already existed, "
        f"self._upload_failed} failed"
    )
```

**Note:** `_on_upload_row_finished` is called from worker threads via `row_status_changed` signal (Qt queued connection → main thread), OR directly from `_start_upload_batch` (main thread). Both paths are safe.

---

## 6. Thread Safety Analysis

| Shared resource | Access pattern | Safe? |
|-----------------|---------------|-------|
| `_saved_paths` | Read-only in upload workers; written only in Phase 5 (completed before `folder_batch_done` fires) | ✓ Safe — no concurrent writers |
| `_row_metadata` | Read-only in upload workers; written before batch starts | ✓ Safe — same reasoning |
| `_upload_done/existed/failed` | Written only in `_on_upload_row_finished` via Qt queued → main thread | ✓ Safe — single-threaded access |
| `_upload_total` | Written once in `_start_upload_batch`, read in `_on_upload_row_finished` | ✓ Safe — written before workers start |

No new locks needed for Phase 6.

---

## 7. Module-level Helper Functions

Keep HTTP calls out of the class — pure functions, easy to test:

```python
# --- iBroadcast API helpers (module level) ---

def _ibroadcast_login(
    username: str, password: str
) -> tuple[str | None, int | None, dict]:
    """Authenticate; return (token, user_id, library) or (None, None, {})."""
    try:
        resp = requests.post(
            "https://api.ibroadcast.com/s/JSON/",
            json={
                "mode": "status",
                "email_address": username,
                "password": password,
                "version": "0.0",
                "client": "tunebridge",
                "supported_types": 1,
            },
            verify=False,
            timeout=15,
        )
        data = resp.json()
        if not data.get("result"):
            return None, None, {}
        token   = data["user"]["token"]
        user_id = data["user"]["id"]
        library = data.get("library", {}).get("tracks", {})
        return token, user_id, library
    except Exception as exc:
        logging.getLogger(__name__).warning("iBroadcast login failed: %s", exc)
        return None, None, {}


def _is_duplicate(title: str, artist: str, library: dict) -> bool:
    """Case-insensitive title+artist exact match against fetched library (D-05)."""
    t = title.strip().casefold()
    a = artist.strip().casefold()
    return any(
        track.get("title", "").strip().casefold() == t and
        track.get("artist", "").strip().casefold() == a
        for track in library.values()
    )


def _ibroadcast_upload(file_path: Path, user_id: int, token: str) -> bool:
    """Upload a single MP3 to iBroadcast. Returns True on success."""
    try:
        with open(file_path, "rb") as f:
            resp = requests.post(
                "https://upload.ibroadcast.com/",
                data={
                    "user_id": user_id,
                    "token": token,
                    "file_path": file_path.name,
                    "method": "api",
                    "client": "tunebridge",
                    "supported_types": 1,
                },
                files={"file": (file_path.name, f, "audio/mpeg")},
                verify=False,
                timeout=120,
            )
        return resp.ok and resp.json().get("result", False)
    except Exception as exc:
        logging.getLogger(__name__).warning("Upload failed %s: %s", file_path.name, exc)
        return False
```

---

## 8. `.env.example` Changes

```
# iBroadcast credentials
# Get your login from https://ibroadcast.com
IBROADCAST_USERNAME=
IBROADCAST_PASSWORD=
```

---

## 9. Startup Credential Check (D-02)

Check at app startup (end of `TuneBridgeApp.__init__`) — not blocking:

```python
# Phase 6: warn if iBroadcast credentials missing (D-02)
if not os.environ.get("IBROADCAST_USERNAME") or not os.environ.get("IBROADCAST_PASSWORD"):
    self.statusBar().showMessage(
        "iBroadcast credentials not configured — upload will be skipped"
    )
```

The status bar is overwritten by "Ready — add songs to begin" if credentials are present (existing line:1258), or shows the warning if not.

**Correction:** Show the warning AFTER "Ready" — the last `showMessage` wins. So place credential check AFTER line 1258, or combine:

```python
cred_ok = bool(os.environ.get("IBROADCAST_USERNAME") and os.environ.get("IBROADCAST_PASSWORD"))
self.statusBar().showMessage(
    "Ready — add songs to begin" if cred_ok
    else "iBroadcast credentials not configured — upload will be skipped"
)
```

---

## 10. Plan Decomposition Recommendation

| Plan | Wave | Content |
|------|------|---------|
| 06-01 | 1 | Module-level helpers (`_ibroadcast_login`, `_is_duplicate`, `_ibroadcast_upload`), new `SongStatus` values, `_STATUS_COLORS` entries, `.env.example` update |
| 06-02 | 2 | `_Dispatcher.upload_batch_done` signal, counter vars in `__init__`, startup credential check, reconnect `folder_batch_done → _start_upload_batch`, `_start_upload_batch` slot |
| 06-03 | 2 | `_upload_worker`, `_on_upload_row_finished`, `upload_batch_done → _unlock_ui` wire |

Wave 1 (Plan 01) has no dependencies. Wave 2 (Plans 02 & 03) can run in parallel once Plan 01 is done — 02 sets up the dispatcher/init wiring, 03 adds the worker/slot bodies.

---

## Validation Architecture

### Unit tests (pytest, no Qt required)

| Scenario | Test | Expected |
|----------|------|----------|
| Login success | Mock `requests.post` with `{"result": true, "user": {"token": "abc", "id": 1}, "library": {"tracks": {}}}` | Returns `("abc", 1, {})` |
| Login failure (wrong pw) | Mock with `{"result": false}` | Returns `(None, None, {})` |
| Login network error | Mock raises `requests.ConnectionError` | Returns `(None, None, {})` |
| Duplicate detected | Library has matching title+artist (case variations) | `_is_duplicate` returns `True` |
| No duplicate | Library has different artist | `_is_duplicate` returns `False` |
| Duplicate case-insensitive | "Queen" vs "queen", "BOHEMIAN RHAPSODY" vs "bohemian rhapsody" | Returns `True` |
| Upload success | Mock `requests.post` returns `{"result": true}` | Returns `True` |
| Upload failure (server) | Mock returns `{"result": false}` | Returns `False` |
| Upload network error | Mock raises `requests.Timeout` | Returns `False` |

### Integration tests (requires Qt + mock API)

| Scenario | Test |
|----------|------|
| Empty batch guard (D-13) | `_saved_paths = {}` → `_start_upload_batch` calls `_unlock_ui` immediately |
| Missing credentials (D-02) | No env vars → all UPLOADING rows transition to Done |
| Auth failure (D-03) | Login returns `None` → all UPLOADING rows → FAILED_UPLOAD |
| Already uploaded (D-07) | Duplicate found → row → ALREADY_UPLOADED, not uploaded |
| Successful upload (UPL-01) | Real file, mocked API → row → Done |
| Per-row isolation (D-16) | One worker raises → other rows unaffected |
| Status bar progression | `_upload_total=3` → "Uploading 1 of 3…" → "Done — 2 uploaded, 0 already existed, 1 failed" |
| UI unlock timing | `_unlock_ui` called only after all rows finish, not before |

### Key acceptance criteria to verify
1. `SongStatus.ALREADY_UPLOADED` and `SongStatus.FAILED_UPLOAD` appear in enum
2. `_STATUS_COLORS` has entries for both new statuses
3. `folder_batch_done` connects to `_start_upload_batch` (not `_unlock_ui`) in `__init__`
4. `upload_batch_done` connects to `_unlock_ui`
5. `IBROADCAST_USERNAME` and `IBROADCAST_PASSWORD` present in `.env.example`
6. All requests calls use `verify=False`

---

## RESEARCH COMPLETE
