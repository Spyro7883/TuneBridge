# Coding Conventions

**Analysis Date:** 2026-05-05

## Naming Patterns

**Files:**
- Single-file app: `retune_app.py` — snake_case, descriptive

**Functions (module-level):**
- snake_case: `retune_file`, `download_track`, `process_one`, `spotify_to_search_query`, `semitones_for_ratio`
- Verb-first naming: `retune_`, `download_`, `process_`

**Methods (class):**
- Private methods prefixed with underscore: `_browse`, `_log`, `_stop`, `_start`, `_run_all`, `_parse_links`
- Public interface: only `__init__` is truly public

**Variables:**
- snake_case throughout: `out_dir`, `raw_dir`, `final_path`, `search_url`
- Single-letter loop vars accepted for short scopes: `ch`, `p`, `d`, `f`
- Tkinter widget vars use `_var` suffix: `folder_var`, `workers_var`, `status_var`

**Constants:**
- UPPER_SNAKE_CASE at module level: `SRC_A4`, `DST_A4`, `RATIO`

**Classes:**
- PascalCase: `RetuneApp`

**Type Annotations:**
- Used on all module-level functions: `retune_file(in_path: Path, out_path: Path) -> None`
- Union return type uses PEP 604 syntax: `Path | None`
- Class methods omit annotations (standard tkinter pattern)

## Code Style

**Formatting:**
- No formatter config detected (no `.prettierrc`, `pyproject.toml`, `.flake8`, or `setup.cfg`)
- Indentation: 4 spaces (PEP 8 compliant)
- Line length: kept short, no lines obviously exceed 100 chars
- Blank lines between logical sections (PEP 8 two blank lines between top-level defs)

**Linting:**
- No linting config detected
- Code follows PEP 8 style conventions manually

**Section Headers:**
- Visual separators use `# ── Section Name ────...─` unicode dash style (consistent throughout)
- Sections: `Retune`, `Download`, `Full pipeline`, `GUI`

## Import Organization

**Order:**
1. Standard library: `json`, `math`, `shutil`, `subprocess`, `tempfile`, `threading`, `tkinter`, `concurrent.futures`, `pathlib`, `urllib.request`
2. Third-party: `numpy`, `librosa`, `soundfile`
3. Deferred / conditional imports inside functions: `mutagen.mp3`, `mutagen.id3`, `uuid`

**Path Aliases:**
- None — `pathlib.Path` used for all file paths

**Conditional imports:**
- `mutagen` imported inside `retune_file` inside `try/except` blocks — treated as optional dependency
- `uuid` imported inside `process_one` — no apparent reason to defer, minor inconsistency

## Error Handling

**Patterns:**
- Hard failures raise `RuntimeError` with human-readable messages: `raise RuntimeError("ffmpeg not found in PATH.")`
- Optional-dependency blocks use bare `except Exception: pass` — silently swallows failures (e.g. mutagen tag reading/writing at lines 62–69, 84–98)
- Subprocess return codes checked explicitly; stderr truncated to 300 chars in error message
- `process_one` propagates exceptions upward; caller (`_run_all`) catches `Exception` and logs to UI
- GUI layer logs failures with `✗` prefix but does not re-raise
- `download_track` uses `threading.Timer` as a 600-second watchdog; kills subprocess on timeout

**Missing error handling:**
- `spotify_to_search_query` — `urlopen` can raise `URLError`; not caught; propagates to `process_one`
- `_parse_links` — no validation beyond URL-pattern substring check

## Logging

**Framework:** No logging module — uses callback pattern

**Patterns:**
- Module-level functions accept an optional `on_log=None` callback: `on_log(msg: str)`
- GUI wires `on_log` via `self.after(0, self._log, msg)` for thread-safe UI updates
- `_log` appends to `log_text` widget with auto-scroll (`see("end")`)
- No structured logging, no log levels, no timestamps

## Comments

**When to Comment:**
- Section separators used to divide file into logical layers
- Inline comments explain non-obvious decisions: cookie DB lock, safety timeout, UTF-8 encoding value `3`
- Module docstring explains purpose, URL handling differences, and dependencies

**Style:**
- Block comments use `#` with one space
- Inline comments: `# comment` after two spaces

## Function Design

**Size:** Functions are compact; `retune_file` is the longest at ~40 lines including subprocess call
**Parameters:** Prefer `Path` objects over strings for file paths; strings converted with `str()` at call sites that require it
**Return Values:** Functions return `None` (side-effect only), `Path | None` (download), or `str` (filename); consistent with annotated signatures
**Default parameters:** `on_log=None` used as optional callback pattern throughout pipeline

## Module Design

**Structure:** Single-file application — no package, no modules
**Exports:** No `__all__` — not a library
**Global state:** One module-level lock `_download_lock` (line 113); documented with comment explaining purpose
**Entry point:** Standard `if __name__ == "__main__":` guard at line 352

## Threading Model

**Pattern:** Main thread = tkinter event loop; background thread spawned via `threading.Thread(daemon=True)` in `_start`
**Thread pool:** `ThreadPoolExecutor` used inside background thread for parallel track processing
**UI updates from threads:** Always via `self.after(0, callback, args)` — correct tkinter pattern
**Shared state:** `_cancel` flag read from worker threads (no lock — acceptable for boolean flag reads)
**Download serialization:** `_download_lock` mutex ensures yt-dlp calls are sequential to avoid browser cookie DB conflicts

---

*Convention analysis: 2026-05-05*
