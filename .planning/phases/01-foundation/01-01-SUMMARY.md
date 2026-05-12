---
phase: 01-foundation
plan: 01
subsystem: testing
tags: [pytest, tkinter, tdd, red-state, test-scaffold]

# Dependency graph
requires: []
provides:
  - pytest.ini with testpaths=tests configuration
  - tests/__init__.py making tests/ a Python package
  - tests/test_tunebridge.py with 7 RED test cases covering SongStatus enum, BatchTable API, dark theme colors, worker count formula, app init, and status tags
  - TDD gate: Plan 02 must turn all 7 tests GREEN
  - .gitignore excluding Python generated files
affects: [01-02, all future test phases]

# Tech tracking
tech-stack:
  added: [pytest 8.3.2]
  patterns:
    - try/except import guard at module level to allow pytest collection in RED state before implementation exists
    - coding: utf-8 header for unicode ✓/✗ handling without stdout wrapper conflicts

key-files:
  created:
    - pytest.ini
    - tests/__init__.py
    - tests/test_tunebridge.py
    - .gitignore
  modified: []

key-decisions:
  - "sys.stdout UTF-8 wrapper removed from test file — conflicts with pytest capture plugin (ValueError: I/O operation on closed file). UTF-8 encoding header sufficient for source file parsing."
  - "Import from tunebridge wrapped in try/except so pytest collects all 7 tests even in RED state before tunebridge.py exists"

patterns-established:
  - "Pattern: TDD scaffold with deferred import guard — from X import Y wrapped in try/except ImportError: X=None allows collection before implementation"
  - "Pattern: tests/__init__.py as empty file to make tests/ a package"

requirements-completed: [PROC-01, PROC-02, GUI-01]

# Metrics
duration: 15min
completed: 2026-05-12
---

# Phase 1 Plan 01: Test Scaffold Summary

**pytest TDD scaffold with 7 RED test cases verifying SongStatus enum, BatchTable API, dark theme colors, and thread count formula — collection works, all tests fail until tunebridge.py is implemented**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-05-12T14:27:00Z
- **Completed:** 2026-05-12T14:42:00Z
- **Tasks:** 1
- **Files modified:** 4

## Accomplishments
- 7 pytest test cases collected without errors (`--collect-only` shows 7 items)
- RED state confirmed — tests fail with TypeError/NameError because tunebridge.py does not exist
- `test_worker_count_formula` passes (pure arithmetic, no import dependency) — correct behavior
- .gitignore added to exclude __pycache__ and .pytest_cache from version control

## Task Commits

1. **Task 1: Create pytest config and test scaffold with 7 test cases** - `44f4311` (test)
2. **Deviation: .gitignore for Python generated files** - `ea931aa` (chore)

**Plan metadata:** (to be added by final commit)

## Files Created/Modified
- `pytest.ini` - pytest configuration: testpaths=tests, addopts=-x -q
- `tests/__init__.py` - empty file making tests/ a Python package
- `tests/test_tunebridge.py` - 7 test cases: test_worker_count_formula, test_status_enum_values, test_app_initializes, test_dark_theme_colors, test_batch_table_columns, test_batch_table_api, test_status_tags
- `.gitignore` - excludes __pycache__, *.pyc, .pytest_cache, .env, dist, build

## Decisions Made
- Removed module-level `sys.stdout = io.TextIOWrapper(...)` — the plan specified this for unicode safety but it conflicts with pytest's capture plugin (`ValueError: I/O operation on closed file`). The `# -*- coding: utf-8 -*-` header is sufficient for source file encoding; pytest handles stdout encoding internally.
- Wrapped `from tunebridge import TuneBridgeApp, BatchTable, SongStatus` in `try/except ImportError` with sentinel `None` assignments — required to allow `--collect-only` to discover all 7 tests before tunebridge.py exists. The import line is present in the file per plan spec.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed sys.stdout UTF-8 wrapper that crashes pytest capture**
- **Found during:** Task 1 verification (--collect-only)
- **Issue:** `sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")` at module import time replaced pytest's capture stdout object. When pytest tried to restore capture state, it hit `ValueError: I/O operation on closed file` — crash before any tests ran.
- **Fix:** Removed the wrapper entirely. `# -*- coding: utf-8 -*-` header handles source encoding. Tests don't print unicode chars to stdout so no runtime encoding issue.
- **Files modified:** tests/test_tunebridge.py
- **Verification:** `--collect-only` completed successfully, 7 items collected
- **Committed in:** 44f4311

**2. [Rule 2 - Missing Critical] Added .gitignore for Python generated files**
- **Found during:** Post-commit untracked file check
- **Issue:** No .gitignore existed; `tests/__pycache__/` appeared as untracked after pytest run
- **Fix:** Created .gitignore with standard Python entries (__pycache__, *.pyc, .pytest_cache, etc.)
- **Files modified:** .gitignore (created)
- **Committed in:** ea931aa

**3. [Rule 1 - Bug] Wrapped tunebridge import in try/except to allow RED-state collection**
- **Found during:** Task 1 verification (--collect-only)
- **Issue:** Top-level `from tunebridge import ...` raised `ModuleNotFoundError` at collection time, preventing pytest from discovering any of the 7 tests (collection error, not test failure)
- **Fix:** Wrapped in `try/except ImportError` with `None` sentinels so collection succeeds; tests then fail at runtime with TypeError when they call `None(...)` — satisfies both "7 items collected" and "RED state" criteria
- **Files modified:** tests/test_tunebridge.py
- **Verification:** --collect-only reports 7 items; running tests fails RED
- **Committed in:** 44f4311

---

**Total deviations:** 3 auto-fixed (2 Rule 1 bugs, 1 Rule 2 missing critical)
**Impact on plan:** All fixes necessary for the scaffold to work correctly under pytest. No scope creep.

## Issues Encountered
- pytest's stdout capture plugin is incompatible with module-level sys.stdout replacement — documented and fixed (see deviation 1 above).

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Plan 02 (tunebridge.py implementation) can begin immediately
- TDD gate: Plan 02 is done only when all 7 tests pass GREEN
- Run `python -m pytest tests/test_tunebridge.py -x -q` to verify GREEN state after Plan 02

---
*Phase: 01-foundation*
*Completed: 2026-05-12*
