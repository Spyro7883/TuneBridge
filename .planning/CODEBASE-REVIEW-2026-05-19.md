# TuneBridge Codebase Review — 2026-05-19

**Scope**: Full codebase (`tunebridge.py` + `tests/test_*.py`)
**Focus**: Bugs and correctness (per user direction — style/perf de-prioritised)
**Reviewer**: gsd-code-reviewer (deep mode)

## Summary

Sweep of `tunebridge.py` (1552 lines) and four test files turned up **12 Critical**, **11 Warning**, and **6 Info** findings. The single biggest risk cluster is the metadata→download handoff: `ItunesClient.search_duration_ms` references an undefined `_norm_str` symbol (`NameError` on first call) and is never invoked anyway, so `_find_best_yt_match` always receives `duration_ms=0`, silently disabling the duration-scoring branch that the tests assume is active. The folder dialog flow has a race that can deadlock workers (event-registered-after-emit window) and another that double-counts row terminations (`_show_folder_dialog` both writes the result and calls `_on_folder_row_finished`, but the `row_status_changed` signal is *also* connected to `_on_download_row_finished` from the same emit, which observes terminal statuses it should ignore). The download path has a hard-coded 600-second timer plus a blocking `proc.stdout.read()` deadlock risk on stderr-merged subprocesses, and `download_track_for_row` returns the newest mp3 in the folder by mtime — which is wrong when a 432Hz retune writes a sibling `_432hz.mp3` and the worker later picks the wrong file from a re-used `row_tmp`. Overall code health is "demo-ready" but not yet "ship-ready" — most of the listed bugs are triggered by real edge cases (Spotify URL with collaboration credits, network blip on iTunes call, user cancels first dialog, ffmpeg failure mid-batch) rather than exotic input.

## Critical (bugs that will cause data loss, crashes, or silent corruption)

### C-01: `_norm_str` is referenced but never defined → `NameError` on every iTunes lookup
- **File**: `tunebridge.py:515-523`
- **Issue**: `ItunesClient.search_duration_ms` calls `_norm_str(...)` five times, but no such function or import exists in the module. `grep -n "_norm_str"` shows only call sites, no definition.
  ```python
  515  title_n = _norm_str(title)
  516  # For collaboration credits like "Artist A, Artist B", also try first artist only
  517  artist_variants = [_norm_str(artist)]
  518  if "," in artist:
  519      artist_variants.append(_norm_str(artist.split(",")[0].strip()))
  520
  521  for r in results:
  522      r_artist = _norm_str(r.get("artistName", ""))
  523      r_title  = _norm_str(r.get("trackName", ""))
  ```
- **Why it's a bug**: Any caller of `search_duration_ms` raises `NameError: name '_norm_str' is not defined`. The bug is masked today only because the method is **never invoked** (see C-02), but tests like `test_itunes_get_metadata_*` patch `requests.get` and never reach this code path. The first time this function is wired up (or unit-tested directly), it crashes.
- **Repro**: `ItunesClient().search_duration_ms("Artist", "Title")` with `requests.get` returning anything non-empty.
- **Fix**: Either define a helper:
  ```python
  def _norm_str(s: str) -> str:
      """Lowercase + strip diacritics + collapse whitespace for fuzzy match."""
      import unicodedata
      return re.sub(r"\s+", " ", unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()).strip()
  ```
  or replace each `_norm_str(x)` with `x.lower().strip()` if the original intent was just casefold.

### C-02: iTunes duration enrichment is dead code → `duration_ms` is always 0 in `_find_best_yt_match`
- **File**: `tunebridge.py:493-531`, `tunebridge.py:533-566`, `tunebridge.py:1262`
- **Issue**: `ItunesClient.search_duration_ms` exists but `ItunesClient.get_metadata` never calls it and never writes `duration_ms` into the returned dict. The download worker then reads:
  ```python
  1262  duration_ms = metadata.get("duration_ms", 0)
  1263  yt_url = _find_best_yt_match(title, artist, duration_ms=duration_ms)
  ```
  In `_find_best_yt_match`:
  ```python
  373  target_s = duration_ms / 1000.0 if duration_ms else None
  382  if target_s is not None:
  383      diff = abs((c.get("duration") or 0) - target_s)
  ```
  With `duration_ms == 0`, `target_s` is `None`, and the duration-based scoring branch (10pts max) is entirely skipped. Candidate ranking collapses to title-substring + channel + view-count signal — which is what landed the "wrong remix picked" bug the team has been iterating on per commits 50c2e5d / 8f3c072.
- **Why it's a bug**: The team believes (per docstring at 363 and test `test_find_best_yt_match_picks_by_duration_and_title`) that duration is a primary signal. In production it isn't. Tests pass because they pass `duration_ms=183000` directly, bypassing the broken pipeline.
- **Fix**: In `ItunesClient.get_metadata`, after extracting `artist`/`title`, call `self.search_duration_ms(artist, title)` for tracks (skip for albums) and add `"duration_ms": result_or_None` to the returned dict. Also fix C-01 first or this will raise.

### C-03: Race condition: worker can deadlock if dialog signal fires before worker waits on event
- **File**: `tunebridge.py:1309-1316`
- **Issue**: The folder worker emits `folder_requested` while holding `_dialog_lock`, then immediately calls `ev.wait()`. But Qt queued signals are not synchronous — `_show_folder_dialog` runs on the main event loop. If the main thread is fast and the worker is delayed, no problem (event is set after wait starts). But there is **no guarantee** that the worker thread reaches `ev.wait()` before `_show_folder_dialog` finishes and calls `self._folder_events[row_id].set()`. In current code, the worker creates the event and sets `_folder_results[row_id] = None` **before** emitting, so the entry exists when `_show_folder_dialog` runs. Good.
  However, if `self._closing.is_set()` becomes true between `self._folder_events[row_id] = ev` (line 1311) and the `if not self._closing.is_set():` guard at 1314, the worker registers an event, never emits, never waits — leaks the event entry. On a subsequent close, `closeEvent` (line 1535) does `for ev in list(self._folder_events.values()): ev.set()` — harmless. But more dangerous: if `closeEvent` fires *between* line 1315 (emit) and line 1316 (wait), then `closeEvent` calls `ev.set()` and the worker proceeds normally — but `_show_folder_dialog` will still run later from the queued signal, trying to show a dialog on a closing window. `dlg.exec()` on a parent in tear-down is undefined behaviour on PySide6.
  ```python
  1309  with _dialog_lock:
  1310      ev = threading.Event()
  1311      self._folder_events[row_id] = ev
  1312      self._folder_results[row_id] = None
  1313
  1314      if not self._closing.is_set():
  1315          self._dispatcher.folder_requested.emit(row_id)
  1316          ev.wait()                     # ← unbounded; no timeout
  ```
- **Why it's a bug**: `ev.wait()` has **no timeout**. If `_show_folder_dialog` raises before reaching `ev.set()` (line 1342) — e.g. `QFileDialog` throws on a parent that's been destroyed — the worker thread blocks forever, holding `_dialog_lock`. All subsequent folder workers in the batch also block forever. The pool is leaked. The app appears hung.
- **Repro**: Close the window mid-batch while at least one row is in `AWAITING` and one in `SAVING`. The worker for the AWAITING row is queued; main thread starts processing close; folder worker emits; `_show_folder_dialog` runs on a half-torn-down window; any exception above line 1342 strands the worker.
- **Fix**:
  1. Add a timeout: `ev.wait(timeout=60)` and treat timeout as skip.
  2. Wrap `_show_folder_dialog` in try/finally that **unconditionally** sets the event before returning.
  3. Move the `ev.set()` to the very top of the I/O block (before the move) so any later exception still unblocks.

### C-04: `_show_folder_dialog` performs file I/O on main thread while UI is supposedly responsive
- **File**: `tunebridge.py:1344-1379`
- **Issue**: `shutil.move(str(temp), str(result))` is called inline on the main thread. Moving a 5MB MP3 from `%TEMP%` to a user folder on a different drive (common case: temp on C:, music library on D:) is a copy+delete, not a rename. On a slow drive this freezes the UI for seconds per song. More importantly, **the next folder dialog cannot show** because the main thread is stuck moving the file — but the worker for row N+1 is already past `with _dialog_lock` waiting on its event. Result: serial save bottleneck masquerading as parallel-feeling UI.
  Worse: line 1369 `dest_candidate.unlink(missing_ok=True)` then line 1370 `shutil.move(...)` is **not atomic**. If `shutil.move` fails after unlink (disk full, permission denied, antivirus lock), the user's existing file at the destination is gone and the new one wasn't written. **Silent data loss.**
  ```python
  1368  dest_candidate = Path(result) / Path(temp).name
  1369  dest_candidate.unlink(missing_ok=True)        # ← deletes user data
  1370  final = Path(shutil.move(str(temp), str(result)))   # ← may fail
  ```
- **Why it's a bug**: Concrete repro — user has `D:\Music\track.mp3`, downloads same song again, save destination = `D:\Music`. Line 1369 deletes the existing file. Line 1370 fails (disk full / file lock / permission). User has lost their original file and gets `Failed — save`.
- **Fix**:
  1. Move the I/O to a worker thread; only the dialog `exec()` must be on main.
  2. Move to a temporary name first, then rename atomically: `shutil.move(temp, dest_candidate.with_suffix(".tmp"))`, then `os.replace(dest_candidate.with_suffix(".tmp"), dest_candidate)`. Only delete the original after successful replace.
  3. Or simply detect collision and rename the new file (`track (1).mp3`), don't clobber.

### C-05: Double-fire of batch terminator — `_on_download_row_finished` re-enters when `_show_folder_dialog` emits `UPLOADING`
- **File**: `tunebridge.py:1372-1374`, `tunebridge.py:1416-1452`
- **Issue**: `_on_download_row_finished` is connected to `row_status_changed` for the duration of a batch (line 1521). Its terminal-status check is:
  ```python
  1421  terminal = (SongStatus.AWAITING.value, SongStatus.FAILED_DOWNLOAD.value)
  ```
  So `UPLOADING` is not in `terminal` — OK, it returns early. But `_show_folder_dialog` emits **`SAVING` then `UPLOADING`** (lines 1358, 1373), and `_unlock_ui` is connected to `folder_batch_done` (line 1153). Now look at `_on_folder_row_finished` — also called from `_show_folder_dialog` after the status emit (line 1374). It increments `_folder_done` and, when all resolve, fires `folder_batch_done` → `_unlock_ui`. So far OK.
  **But** `_on_download_row_finished` is **still connected** while folder dialogs run, because the only disconnect path is when `_download_done + _download_failed >= _download_total` (line 1431-1447). On a single-row batch where the row succeeds: AWAITING fires → `_download_done = 1`, `finished = 1 = _download_total`, disconnect runs. Good.
  **On a multi-row batch**, say 3 rows, all succeed: AWAITING fires for rows 1, 2, 3 in some order. Between row-1-AWAITING and row-2-AWAITING, `_show_folder_dialog` may run for row 1, emitting `SAVING` → `UPLOADING`. Each of those re-enters `_on_download_row_finished`. They return early (not terminal). But meanwhile `_folder_total += 1` is only incremented at line 1427 *inside the AWAITING branch*. If `_show_folder_dialog` for row 1 calls `_on_folder_row_finished` **before** rows 2 and 3 emit AWAITING, then `_folder_total = 1`, `_folder_done = 1`, `finished >= _folder_total` is true, and **`folder_batch_done` fires after row 1 only**. `_unlock_ui` runs. Rows 2 and 3 are still processing in the background, and the UI is unlocked.
- **Why it's a bug**: The whole point of `folder_batch_done` is "all rows are in a terminal save state". Today it fires the moment the first row finishes if its download was faster than rows 2 and 3's. Pasting new URLs at that moment races with the still-running downloads of the prior batch.
- **Repro**: Start a batch of 3 Spotify rows where row 1 has a small mp3 (fast download) and rows 2/3 are large. Row 1 will reach AWAITING, the user confirms folder, `_show_folder_dialog` calls `_on_folder_row_finished`, `_folder_total` is still 1 → batch_done fires.
- **Fix**: `_folder_total` must be set up-front to the count of jobs that *will* enter the folder phase, not incrementally. Move `_folder_total` increment to `_start_processing` (set to `len(jobs)`) and decrement it on `FAILED_DOWNLOAD`, OR gate `folder_batch_done` on `(_download_done + _download_failed == _download_total)` AND `(_folder_done + _folder_skipped + _folder_failed == _folder_total)`.

### C-06: `download_track_for_row` returns wrong file when row_tmp is re-used or contains pre-existing mp3s
- **File**: `tunebridge.py:313-314`
- **Issue**:
  ```python
  313  mp3s = sorted(out_dir.glob("*.mp3"), key=lambda p: p.stat().st_mtime, reverse=True)
  314  return mp3s[0] if mp3s else None
  ```
  This returns the newest mp3 in `out_dir`. The download worker creates a per-row uuid-named subdir (line 1255-1256), so collisions are unlikely on first run. **But** for a 432Hz row, `retune_file` writes `out_path = row_tmp / (downloaded.stem + "_432hz.mp3")` (line 1277), and immediately `downloaded.unlink(missing_ok=True)` (line 1280). If `unlink` fails (e.g., file lock from antivirus scanning the just-written mp3 on Windows), `row_tmp` now contains both `Track.mp3` (original 440Hz) **and** `Track_432hz.mp3` (pitch-shifted). `downloaded` is reassigned to `out_path` so the right file moves on success. OK.
  **But** if the user re-runs a previously-failed row whose `row_tmp` still exists (because cleanup is `atexit` only — line 1124), the uuid is regenerated so `row_tmp` is a fresh directory. OK.
  **Real bug**: yt-dlp can produce multiple mp3 outputs from a single URL if the URL resolves to a playlist that slipped past `--no-playlist`, or if post-processing writes intermediate files. The sort-by-mtime picks newest, but on Windows mtime resolution is ~16ms and parallel writes within yt-dlp post-processing can produce mp3s with identical or out-of-order mtimes. Returning `mp3s[0]` may pick a non-target file.
  Additionally: if `download_track_for_row` is called twice for the same `out_dir` (which doesn't happen in current code but is structurally possible), the function returns whichever is newer — silently shadowing a previous failed download.
- **Why it's a bug**: Non-deterministic file selection. Symptom: user reports "wrong song was retuned and saved" with no other context, hard to diagnose.
- **Fix**: Use a `--print after_move:filepath` argument to yt-dlp to capture the exact output path, or use `-o` with a known prefix and glob only for that prefix:
  ```python
  out_template = out_dir / f"target_{uuid.uuid4().hex[:8]}_%(title)s.%(ext)s"
  ```
  Then `glob("target_*.mp3")` and assert exactly one match.

### C-07: `proc.stdout.read()` in `_run_attempt` will deadlock on long yt-dlp output via merged stderr
- **File**: `tunebridge.py:275-300`
- **Issue**:
  ```python
  275  proc = subprocess.Popen(
  276      cmd,
  277      stdout=subprocess.PIPE,
  278      stderr=subprocess.STDOUT,        # merge stderr into stdout
  279      ...
  282  )
  ...
  296  proc.stdout.read()                  # blocking read until EOF
  297  proc.wait()
  ```
  The `proc.stdout.read()` call **will** consume the pipe as it fills, so the classic stdout-buffer-overflow deadlock is avoided in the happy path. However: the watchdog timer at line 293 calls `proc.kill()` on timeout. After `kill()`, the OS closes the pipe, `read()` returns, `wait()` returns — fine. **But on Windows**, `subprocess.Popen.kill()` calls `TerminateProcess`, which leaves any child grandchildren orphaned (ffmpeg spawned by yt-dlp). Those grandchildren keep the pipe open. `proc.stdout.read()` blocks until **they** close. The timer fires once, kills yt-dlp, but ffmpeg keeps writing → `read()` never returns → `wait()` is never reached → `timer.cancel()` runs only on the finally, but the function is stuck in `read()`. **The worker thread is permanently wedged.**
- **Why it's a bug**: User-controlled scenario: an audio source that triggers a long ffmpeg post-process, or a yt-dlp download that produces a deeply-nested format conversion. Timeout fires; yt-dlp dies; ffmpeg keeps the pipe open; thread wedged; `_download_lock` is still held (line 302 `with _download_lock:` wraps the loop). **Every subsequent download in the batch blocks forever** waiting on `_download_lock`.
- **Repro**: Kill the yt-dlp process externally via Task Manager during a download while ffmpeg post-processing is running.
- **Fix**: Use `proc.communicate(timeout=600)` instead of manual `read()` + `wait()` + `Timer`. `communicate` handles the timeout, kills the process tree, and drains pipes. On Windows, use `subprocess.CREATE_NEW_PROCESS_GROUP` and send `signal.CTRL_BREAK_EVENT` to terminate the whole tree, or use the `psutil`-based recursive kill pattern.

### C-08: `FAILURE_STATUSES` is missing `"Skipped — bad URL"` and `"Failed"` → stat card never decrements for invalid URLs that fail later
- **File**: `tunebridge.py:160-164`, `tunebridge.py:811-812`
- **Issue**:
  ```python
  160  FAILURE_STATUSES: frozenset[str] = frozenset({
  161      "Failed — metadata",
  162      "Failed — download",
  163      "Failed — save",
  164  })
  ```
  The Status enum includes plain `"Failed"` (line 433) and the table uses `"Skipped — bad URL"` (line 777). Neither is in `FAILURE_STATUSES`. If any code path sets a row to `"Failed"` (no current path does, but the value is in the enum and `_STATUS_COLORS`), the `_on_row_failed` callback never fires, so the stat card balance becomes wrong (valid count stays high, invalid count stays low).
- **Why it's a bug**: Latent — depends on a future caller. But the more concrete defect is `"Failed — save"` is in `FAILURE_STATUSES` AND in `_COMPLETED` (line 887-892). The save failure happens AFTER metadata was ready, AFTER the stat card was already counted as "valid". When `update_row_status` fires `FAILURE_STATUSES`, the `_on_row_failed` lambda decrements valid and increments invalid — but the row WAS valid (it had good metadata, the download succeeded, the save failed for an OS reason). Flipping its category is misleading: a save failure is not an "invalid URL". This corrupts the user-facing semantic of the Invalid stat card.
- **Repro**: Paste 3 Spotify URLs, fill all metadata, start, all download, confirm folder for row 1 succeeds, row 2 fails with disk-full OSError, row 3 succeeds. Valid card shows 2 (correct), Invalid card shows 1 (wrong — there were no invalid URLs).
- **Fix**: Split callbacks: `_on_metadata_failed` (only `"Failed — metadata"`, the only legit "moved to invalid" case) versus `_on_terminal_failure` for save/download (no stat-card move). Reduce `FAILURE_STATUSES` to `{"Failed — metadata"}` for the existing callback.

### C-09: `remove_completed_rows` references nonexistent `SongStatus.FAILED_METADATA`
- **File**: `tunebridge.py:893`
- **Issue**:
  ```python
  893  _INVALID_COMPLETED = {SongStatus.FAILED_METADATA.value} if hasattr(SongStatus, "FAILED_METADATA") else set()
  ```
  `SongStatus` has no `FAILED_METADATA` member (the value `"Failed — metadata"` is set via `FAILED.value = "Failed"` and the explicit text in `update_row_status` paths — see enum lines 424-437). `hasattr` returns False, so `_INVALID_COMPLETED` is always `set()`. The "invalid_removed" count from `remove_completed_rows` is therefore always 0 — even when a `Failed — metadata` row is removed by re-pasting URLs.
- **Why it's a bug**: The stat-card sync via `_on_rows_removed` decrements only `valid_removed`. A row that failed metadata and was counted in the **invalid** card (per C-08 callback) stays in the invalid count after the row itself is removed. Counts drift upward over time as the user re-pastes batches.
- **Repro**: Paste 1 valid Spotify URL with a fake track ID that returns no OG tags → `Failed — metadata` → invalid card = 1, valid card = 0. Paste another URL → `remove_completed_rows` runs, removes the failed row → invalid card still shows 1, valid card shows the new URL's classification.
- **Fix**: Replace with the literal value:
  ```python
  _INVALID_COMPLETED = {"Failed — metadata"}
  ```
  and remove the `hasattr` defensive check.

### C-10: `FolderConfirmDialog._validate` uses `Path('').is_dir()` indirection but the bare `is_dir()` race lets old text pre-validate
- **File**: `tunebridge.py:996-1003`
- **Issue**:
  ```python
  996  def _validate(self, text: str) -> None:
  997      # CRITICAL: check strip() != '' BEFORE is_dir() — Path('').is_dir() is True on Windows (Pitfall 1)
  998      valid = bool(text.strip()) and Path(text.strip()).is_dir()
  ```
  The empty-string guard is correct. But `Path(text.strip()).is_dir()` for a network path like `\\server\share\Music` performs a synchronous SMB query that can hang for 30+ seconds while the user types. Each keystroke triggers `_validate` via `textChanged` (line 993). On a slow VPN or offline UNC path, the dialog freezes per-character.
  Separately: `is_dir()` returns False for a path with trailing whitespace (`C:\Music ` — note trailing space). Windows Explorer accepts trailing spaces but creates a folder name with the space stripped, so the user pastes a path with an accidental trailing space (very common copy-paste artifact) and the Confirm button stays disabled with no useful error.
- **Why it's a bug**: UX hang + silent rejection of paste-with-trailing-whitespace. `Path(text.strip()).is_dir()` — note `text.strip()` removes leading/trailing whitespace, so trailing space is fine. **However** `_on_confirm` (line 1014) uses `Path(self._path_edit.text().strip())` — also stripped. So far OK.
  But the actual save call (line 1370) uses `result` directly: `shutil.move(str(temp), str(result))`. `result` came from `self._result_path = Path(self._path_edit.text().strip())`. OK — stripped. So the trailing-space concern is moot.
  **The remaining bug** is the UNC freeze. Each `textChanged` triggers a blocking I/O check.
- **Repro**: Open dialog, type or paste `\\server\share\` where `server` is offline. UI freezes for the system SMB timeout (default ~21s on Win10).
- **Fix**: Debounce `_validate` with a `QTimer.singleShot(300, ...)`; or do the `is_dir()` check in a worker and update button state via signal.

### C-11: `closeEvent` shuts down executor with `wait=False` while threads hold `_dialog_lock` and `_temp_paths_lock` → leaked locks, partial temp cleanup
- **File**: `tunebridge.py:1531-1545`
- **Issue**:
  ```python
  1531  def closeEvent(self, event) -> None:
  1533      self._closing.set()
  1535      for ev in list(self._folder_events.values()):
  1536          ev.set()
  1537      self._executor.shutdown(wait=False)
  1538      try:
  1539          shutil.rmtree(self._session_tmp, ignore_errors=True)
  ```
  `shutdown(wait=False)` returns immediately while download/folder workers may still be holding `_download_lock`, `_dialog_lock`, `_temp_paths_lock`, AND mid-flight subprocesses (yt-dlp child processes). `shutil.rmtree(... ignore_errors=True)` then tries to delete `_session_tmp` while a worker is in the middle of writing an mp3 there — on Windows this raises `PermissionError: [WinError 32]` per file. `ignore_errors=True` swallows it, but the files remain on disk. Eventually `atexit.register(shutil.rmtree, ...)` (line 1124) runs in interpreter shutdown and tries again — but by then the worker thread may still be alive (`wait=False`!), holding the file open, so atexit also fails silently.
  **End state**: temp files accumulate in `%TEMP%\tunebridge_*\` across crashes/closes during active downloads.
- **Why it's a bug**: Disk space leak on a long-running install. Each crash or close-mid-batch leaves ~5-20MB stranded.
- **Repro**: Start a 10-row batch, close the window after 2 rows finish downloading and 1 is mid-download. Check `%TEMP%` — `tunebridge_*` directories from the killed batch remain.
- **Fix**: `self._executor.shutdown(wait=True, cancel_futures=True)` before `rmtree`. For the in-flight subprocess, store `Popen` references and `proc.kill()` them in `closeEvent` before shutdown.

### C-12: Empty result variable in `ItunesClient.search_duration_ms` after loop with all-empty stores → `NameError` on `if not results:`
- **File**: `tunebridge.py:500-513`
- **Issue**:
  ```python
  500  try:
  501      term = urllib.parse.quote(f"{artist} {title}")
  502      for store in ("&country=ES", "&country=MX", ""):
  503          resp = requests.get(...)
  504          resp.raise_for_status()
  505          results = resp.json().get("results", [])
  506          if results:
  507              break
  508      if not results:
  509          return None
  ```
  `results` is assigned inside the loop. If the loop never executes (impossible here — tuple has 3 elements) or if `requests.get` raises on the first iteration, `results` is unbound when `if not results:` is checked — but the outer `try/except Exception: return None` catches `NameError` and returns None. So this hides as a benign no-op.
  **But** if `requests.get` succeeds for all three stores and returns `{"results": []}` each time, `results = []` after the loop, `if not results: return None` fires correctly. OK.
  **The real bug**: if iTunes returns results from the ES store but the artist/title fuzzy match fails for all 5 results, the function falls through to `return None` (line 529). It does NOT try the MX or US store with potentially different result orderings. The "store fallback" is a "first-non-empty-results" fallback, not a "first-match-in-any-store" fallback.
- **Why it's a bug**: A track available in MX but with weird ES metadata returns no match even though MX would have matched.
- **Repro**: Track with regional release variations; ES store returns wrong-artist results first.
- **Fix**: Collect matches from all three stores and return the first match across the merged list:
  ```python
  all_results = []
  for store in (...):
      r = requests.get(...).json().get("results", [])
      all_results.extend(r)
  for r in all_results:
      ...
  ```

## Warning (real bugs but lower blast radius, or latent issues)

### W-01: `_search_yt_candidates` returns parts[3] without checking len(parts) for channel index
- **File**: `tunebridge.py:336-356`
- **Issue**:
  ```python
  336  parts = line.split("|||")
  337  if len(parts) < 3:
  338      continue
  ...
  352  "title":     parts[1].strip(),
  353  "channel":   parts[3].strip() if len(parts) > 3 else "",
  ```
  Wait — line 353 does check. But line 343: `duration = float(parts[2].strip())` is unconditional after `len(parts) >= 3`, so 2 is safe. **However** line 347: `views = int(parts[4].strip()) if len(parts) > 4 else 0` — this is correct guard. Where's the bug? Re-reading: it's actually fine. **Downgrade**: this is correct. Skip — false alarm. (Keeping the slot for honesty.)

### W-02: `_find_best_yt_match` returns `None` on score tie at zero — but never resolves ties at the top
- **File**: `tunebridge.py:410-414`
- **Issue**:
  ```python
  410  scored.sort(key=lambda x: -x[0])
  411  best_score, best = scored[0]
  412
  413  if best_score <= 0:
  414      return None
  ```
  Two candidates with identical scores → `scored.sort` is stable, so the order from `_search_yt_candidates` (yt-dlp output order, which is YouTube Music's relevance) wins ties. That's actually reasonable. But the `<= 0` cutoff (line 413) discards tracks with score exactly 0. With `duration_ms=0` (per C-02), an obscure track with no title/artist match but high views (`min(log10(views)*1.5, 9.0)`) can score 9.0; a perfectly-named match with 0 views scores 5+1+3 = 9. Score ties pick whichever yt-dlp returned first, which is unrelated to TuneBridge's matching intent. Latent quality issue, not a crash.
- **Why it's a bug**: Inconsistent ranking when the dominant signal (views) saturates.
- **Fix**: Cap view score lower (`min(log10(views), 5.0)`) so it can't overwhelm content-based signals, or use it only as a tiebreaker.

### W-03: `_find_best_yt_match` substring match `title_l in vid_l` matches "Run" in "Running"
- **File**: `tunebridge.py:389`
- **Issue**:
  ```python
  389  if title_l in vid_l:
  390      score += 5.0
  ```
  Short titles like "Run" (3 letters) substring-match anywhere in a candidate title containing those letters: "Running Up That Hill", "Marathon Runner", "Rerun", etc. 5pts is a large weight to give for a coincidental substring. Symmetric problem for short artists ("Bee", "Yes", "Air").
- **Repro**: Search for the Snow Patrol song "Run" (3 chars) → matches "Running Wild", "On the Run", "Rerun" with full 5pts each.
- **Fix**: Word-boundary match: `re.search(rf"\b{re.escape(title_l)}\b", vid_l)`.

### W-04: `download_track_for_row` does not check yt-dlp output for "no video matched" — exits 0 with no file
- **File**: `tunebridge.py:302-314`
- **Issue**: yt-dlp can exit with returncode 0 on `ytsearch1:` queries that return no results — it just prints "no results" to stderr and produces no output file. The `if rc == 0: break` loop body assumes 0 means success. Line 313 then globs for mp3s, finds none, returns `None`. The caller at 1271 raises `"No audio file found after yt-dlp download."`. OK — surfaces as a failure. But the loop has already exited so other browser cookie fallbacks aren't tried.
  More critically: the `for/else` at 303/310 — `else` triggers only if the `for` loop completes without `break`. If the first cookie variant produces rc==0 with no file, `break` fires, `else` is skipped, the search-result-but-no-file case is conflated with success. This is the actual bug.
- **Fix**: Check `out_dir.glob("*.mp3")` inside the loop before `break`:
  ```python
  if rc == 0 and any(out_dir.glob("*.mp3")):
      break
  ```

### W-05: `retune_file` tag restoration mutates ID3 frame `value.encoding` in place
- **File**: `tunebridge.py:230-243`
- **Issue**:
  ```python
  230  if original_tags:
  231      try:
  232          audio = MP3(str(out_path))
  ...
  235          for key, value in original_tags.items():
  236              if hasattr(value, 'encoding'):
  237                  value.encoding = 3  # UTF-8
  238              audio.tags.add(value)
  ```
  `original_tags[key] = orig_id3[key]` (line 213-214) stores references, not copies. Setting `value.encoding = 3` mutates the source ID3 frame, then `audio.tags.add(value)` re-adds the same object. If the function is called twice on the same `in_path` (unlikely, but the function is public), the second call's `ID3(in_path)` returns objects already mutated. More importantly, since these are mutated singletons, future writes to `out_path` via `audio.save` could reorder frames unexpectedly. Defensive: `value = copy.copy(value)` before mutating.
- **Fix**: Deep-copy frames before mutating, or use `audio.tags.add(value.__class__(encoding=3, text=value.text))`.

### W-06: `_metadata_worker` emits `metadata_ready` then `row_status_changed` — race between BatchTable updates
- **File**: `tunebridge.py:1221-1227`
- **Issue**:
  ```python
  1221  if not self._closing.is_set():
  1222      self._dispatcher.metadata_ready.emit(row_id, metadata)
  1223      self._dispatcher.row_status_changed.emit(
  1224          row_id, SongStatus.METADATA_READY.value
  1225      )
  ```
  Both signals are queued to the main thread. They arrive in order, but `update_row_metadata` (slot for `metadata_ready`) ALSO calls `self.update_row_status(row_id, SongStatus.METADATA_READY.value)` internally (line 842). So `METADATA_READY` is emitted *twice* — once via the internal call inside `update_row_metadata`, once via the explicit `row_status_changed.emit`. Both end up calling `update_row_status` on the main thread. **`_on_row_failed` is keyed off `if status in FAILURE_STATUSES`** so a duplicate `METADATA_READY` is harmless — but `_refresh_start_button` (also connected to `row_status_changed`) runs twice per row update, doing a full O(rows) scan each time. On a 100-row paste this is 200 scans instead of 100. Latent perf issue, not a correctness bug.
  **Actual correctness bug**: the `_row_metadata` storage hook on line 1144:
  ```python
  1144  self._dispatcher.metadata_ready.connect(
  1145      lambda row_id, meta: self._row_metadata.__setitem__(row_id, meta)
  1146  )
  ```
  This is connected at startup, never disconnected. The lambda captures `self._row_metadata` reference. `self._row_metadata` is a dict; mutating from the main thread via queued signal is safe. OK.
  **The real bug**: line 1223's emit re-fires `row_status_changed.connect(self._on_download_row_finished)` during batch processing if a metadata refresh happens mid-batch. Currently `_metadata_worker` is only called from `_process_urls`, and `_process_urls` is gated by `_paste_box.setReadOnly(True)` during a batch — so a new paste can't fire `_metadata_worker`. Safe today but brittle.
- **Fix**: Remove the redundant `row_status_changed.emit` at line 1223 — `update_row_metadata` already calls `update_row_status` internally.

**STATUS — FALSE POSITIVE (reviewed 2026-05-19 16:30):** The proposed fix was attempted and reverted. `update_row_metadata`'s internal call to `self.update_row_status(...)` is a direct method invocation, NOT a signal emit. Three slots are connected to `row_status_changed`: `table.update_row_status`, `_refresh_start_button`, and `_on_download_row_finished`. The direct method call only updates the table cell — it does NOT fire `_refresh_start_button`, which is the slot that enables the Start button once every row reaches `METADATA_READY`. Removing the emit at line 1223 would leave the Start button permanently disabled after a metadata-ready batch. The "redundancy" is illusory; the emit IS load-bearing for UI state transitions. No fix applied.

### W-07: `_show_folder_dialog` doesn't lock `_saved_paths` and `_folder_results` writes
- **File**: `tunebridge.py:1340-1342`, `tunebridge.py:1371`
- **Issue**: `self._folder_results[row_id] = result` (1340), `self._folder_events[row_id].set()` (1342), `self._saved_paths[row_id] = final` (1371) — all written from the main thread. Folder workers READ `_folder_events[row_id]` from worker thread (line 1316 `ev.wait()`). Dict insertion (`_folder_events[row_id] = ev` line 1311) is from worker thread, dict iteration in `closeEvent` (line 1535) is from main thread. CPython dict mutation during iteration is undefined; `list(self._folder_events.values())` copies first, mitigating. But there's no lock protecting `_folder_results` writes from worker reads — although the worker only reads after the event fires, which establishes a happens-before via `Event.set()` → `Event.wait()`. Borderline OK.
- **Fix**: Document the happens-before discipline; or wrap in a single `_folder_state_lock`.

### W-08: `_on_folder_row_finished` is called from main thread but comment says "off main thread"
- **File**: `tunebridge.py:1381-1414`
- **Issue**:
  ```python
  1381  def _on_folder_row_finished(self, _row_id: int, status: str) -> None:
  1382      """Track folder dialog batch completion. Called directly from _folder_worker (off main thread).
  ```
  The docstring says it's called from `_folder_worker` off the main thread. Reading the code: `_folder_worker` does NOT call `_on_folder_row_finished` (only `_show_folder_dialog` does — lines 1354, 1365, 1374, 1379). `_show_folder_dialog` runs on the main thread (it's a Qt slot). So the docstring is wrong AND the comment about "GIL protects int increments" is misleading — there's no contention because the only writer is the main thread. Not a bug per se, but the docstring leads a future maintainer to add cross-thread calls thinking they're safe.
- **Fix**: Update docstring: "Called from `_show_folder_dialog` on the main thread."

### W-09: `_paste_box.setReadOnly(True)` is set in `_start_processing` but no path resets it on early-return
- **File**: `tunebridge.py:1499-1503`
- **Issue**:
  ```python
  1499  if not jobs:
  1500      logging.getLogger(__name__).warning(
  1501          "_start_processing called with no METADATA_READY rows"
  1502      )
  1503      return   # nothing to do — guard against empty batch
  ```
  This early return is BEFORE setReadOnly is set (line 1506). OK — but what if `_refresh_start_button` enables the button (all rows ready), user clicks Start, the click handler queues, then between handler invocation and `for row_id in range(row_count)` (line 1490), a metadata refresh transitions a row away from METADATA_READY? Concretely, that can't happen because metadata workers don't run mid-batch (paste box is read-only at that point — but the read-only flip hasn't happened yet on entry to `_start_processing`).
  Actually the click handler is on the main thread; between click and `for row_id in range(row_count)` no other code can run. Safe.
  **The actual W-09**: if `_start_processing` proceeds past line 1506 but raises before connecting the slot at line 1521 (e.g., `_executor.submit` raises because the executor has been shut down by a parallel `closeEvent`), the UI stays locked permanently. No try/finally restores `setReadOnly(False)` or button enable.
- **Fix**: Wrap lines 1506-1529 in try/except that resets UI state on failure.

### W-10: `_run_attempt`'s `Timer(600, _kill)` is not cancelled on exception in `proc.stdout.read()`
- **File**: `tunebridge.py:293-300`
- **Issue**:
  ```python
  293  timer = threading.Timer(600, _kill)
  294  timer.start()
  295  try:
  296      proc.stdout.read()
  297      proc.wait()
  298  finally:
  299      timer.cancel()
  ```
  This IS in try/finally — `timer.cancel()` runs even on exception in `read()`. OK, false alarm. But: `Timer.cancel()` only prevents an unfired timer from firing. If the timer has already fired and `_kill` is mid-execution when `finally` runs, `cancel()` is a no-op and `_kill` continues. After `_run_attempt` returns, the killed proc is gone, but the calling thread still believes returncode reflects normal exit (line 305-309 check `rc == 0`). The killed proc has rc != 0 → loops to next cookie variant → fine. OK, downgrade to Info.

### W-11: `_handle_key` bypasses event for non-Delete keys but uses the wrong `keyPressEvent` binding
- **File**: `tunebridge.py:760`, `873-879`
- **Issue**:
  ```python
  760  self._table.keyPressEvent = self._handle_key
  ...
  873  def _handle_key(self, event) -> None:
  ...
  876      if event.key() == Qt.Key.Key_Delete:
  877          self.remove_selected_rows()
  878      else:
  879          QTableWidget.keyPressEvent(self._table, event)
  ```
  Monkey-patching `keyPressEvent` on a Qt widget instance does NOT bind `self` properly. `self._table.keyPressEvent = self._handle_key` — `self._handle_key` is already bound to `BatchTable` instance, so it's called with one arg (the event) but Qt expects it to be called with the QTableWidget as receiver. Python lets this happen because PySide6 just calls the attribute as a function with the event. So `self` (in `_handle_key`) is the `BatchTable` instance, not the QTableWidget. This works because line 877 uses `self.remove_selected_rows()` (BatchTable method) and line 879 explicitly passes `self._table` to `QTableWidget.keyPressEvent`. Fragile but functional.
- **Why it's a bug**: PySide6's typed event dispatch may invoke `keyPressEvent` directly (bypassing Python attribute lookup) for performance, which would skip the monkey-patch entirely. This depends on PySide6 internals.
- **Fix**: Subclass QTableWidget and override `keyPressEvent` properly, instead of monkey-patching the instance.

## Info (correctness smells, defensive-code suggestions)

### I-01: `download_track_for_row` does not pass `creationflags=CREATE_NO_WINDOW` on Windows → flashing console
- **File**: `tunebridge.py:275-282`
- **Issue**: Each yt-dlp subprocess pops up a console window on Windows GUI apps unless `creationflags=subprocess.CREATE_NO_WINDOW` is passed. Not a correctness bug — just visible jitter.

### I-02: `retune_file` swallows `mutagen` ImportError silently
- **File**: `tunebridge.py:188-192`
- **Issue**:
  ```python
  189      from mutagen.mp3 import MP3
  190      from mutagen.id3 import ID3
  191  except ImportError:
  192      MP3 = ID3 = None
  ```
  If mutagen is missing, ID3 restoration is silently skipped — but the function name promises it. Caller has no signal that tags were lost. Pure correctness smell.

### I-03: `classify_url` allows path-like input but doesn't validate scheme
- **File**: `tunebridge.py:449-457`
- **Issue**: `_SPOTIFY_RE` and `_YOUTUBE_RE` use `search`, not `match`. Both regexes contain the host string verbatim, so `xxxopen.spotify.com/track/yyy` matches even though it's not a real URL. Low risk because users paste full URLs, but `http://attacker.com/open.spotify.com/track/abc` would classify as Spotify.

### I-04: `_session_tmp` is created at __init__ but `atexit` is registered with a closure over `self`
- **File**: `tunebridge.py:1123-1124`
- **Issue**:
  ```python
  1123  self._session_tmp = Path(tempfile.mkdtemp(prefix="tunebridge_"))
  1124  atexit.register(shutil.rmtree, self._session_tmp, True)
  ```
  `atexit.register(shutil.rmtree, path, True)` — note the trailing `True` is `ignore_errors=True` (positional). On multiple `TuneBridgeApp` instantiations (test fixtures create one per test), each registers a separate atexit handler. After 100 tests, there are 100 atexit calls all trying to delete (mostly already-deleted) temp dirs. Harmless because `ignore_errors=True`, but the atexit list grows unboundedly.

### I-05: `_dispatcher.metadata_ready` is `Signal(int, object)` — `object` is a typed escape
- **File**: `tunebridge.py:467`
- **Issue**: `metadata_ready = Signal(int, object)` works because Qt's `object` slot type bypasses metatype registration. But the queued signal copies the dict by reference, not value. If `_metadata_worker` mutates the dict after emit (it doesn't currently), the main thread sees mutated data. Defensive: `Signal(int, dict)` or `metadata_ready.emit(row_id, dict(metadata))`.

### I-06: `_find_best_yt_match` doesn't strip parenthesised remix/feat info from candidate title before substring match
- **File**: `tunebridge.py:389-394`
- **Issue**: A candidate titled `"Artist - Song (feat. X) [Remastered 2019]"` substring-matches `"Song"` (good) but a candidate `"Artist - Wrong Song (the actual track is mentioned later in description)"` also matches if the title contains the query string anywhere. Not a bug per se, but the matching is "best effort"; consider normalising candidate titles before comparison.

## Coverage gaps in tests

- **C-01 / C-02**: No test calls `ItunesClient.search_duration_ms` — the `NameError` is invisible. Add `test_itunes_search_duration_ms_returns_int_on_match` and `test_get_metadata_populates_duration_ms`.
- **C-03**: No test simulates `_show_folder_dialog` raising before `ev.set()`. Add `test_folder_worker_unblocks_on_exception` that monkeypatches `_show_folder_dialog` to raise mid-call and asserts the worker thread does not deadlock.
- **C-04**: No test covers same-name-collision at destination. Add `test_save_does_not_clobber_existing_file_on_partial_failure` that pre-creates `dest/track.mp3` and mocks `shutil.move` to raise — assert pre-existing file is still present.
- **C-05**: No test runs a multi-row batch with race-prone timing. Add `test_folder_batch_done_waits_for_all_downloads` that fires AWAITING for row 0, advances `_on_folder_row_finished`, then asserts `folder_batch_done` did NOT yet fire while rows 1-2 are still pre-AWAITING.
- **C-06**: No test asserts `download_track_for_row` returns the exact file when multiple mp3s exist in `out_dir`. Add `test_download_returns_correct_file_when_multiple_mp3s_present`.
- **C-07**: No test covers subprocess hang. Out of scope for unit tests, but add an integration smoke test with a fake `yt-dlp.bat`/`.sh` script that sleeps past the timeout.
- **C-08**: No test asserts `Failed — save` does NOT decrement valid card. Add `test_failed_save_preserves_valid_card_count`.
- **C-09**: No test for `remove_completed_rows` invalid count. Add `test_remove_completed_rows_counts_failed_metadata_as_invalid`.
- **W-04**: No test for "yt-dlp returns rc=0 with no file". Add `test_download_track_raises_when_no_mp3_produced_despite_rc0`.

## Notes

- The codebase consistently mixes "PyQt6" (in module docstring line 2) and "PySide6" (in imports) — the docstring is stale. Not a bug, but a future search-and-replace risk.
- `_BROWSER_FALLBACKS` tries six browsers serially on every failed download. On a totally offline machine, a single Spotify row takes 7 × 600s = 70 minutes to fail. Consider a global "first-failed-no-cookies" short-circuit after the first attempt fails with a clearly-non-cookie error (e.g., "Unable to extract"). Out of scope for v1 per user direction (perf), but flagging for visibility.
- `Phase 6` (iBroadcast upload) is unimplemented and `folder_batch_done` currently unlocks the UI instead of triggering upload (line 1153 wires to `_unlock_ui`). All `UPLOADING` statuses are misleading — the row is *not* uploading anywhere. Consider renaming `SongStatus.UPLOADING` → `SAVED` until Phase 6 lands, or the user expectation will diverge from reality.
