---
phase: 19-sync-runner-query-surface
plan: "02"
subsystem: etl
tags: [python, etl, RunResult, psycopg3, pipeline_runs, dry_run]

# Dependency graph
requires:
  - phase: 19-sync-runner-query-surface/19-01
    provides: "RunResult frozen dataclass, _row_to_result mapper, ETL_GET_RUN constant"
  - phase: 18-load-modes-extract
    provides: "ETLAccessor.run() body, run-log isolation, load atomicity seam"
  - phase: 17-run-tracking-foundation
    provides: "pipeline_runs schema, ETL_LIST_RUNS, ETL_GET_LAST_RUN constants"
provides:
  - "run(pipeline, dry_run=False) -> RunResult: upgraded signature returning re-SELECTed RunResult"
  - "_fetch_run_result(run_id) -> RunResult: private helper using ETL_GET_RUN + _row_to_result"
  - "dry_run early fork: extract+transform only, no pipeline_runs row, RunResult(status='dry_run', run_id=None)"
  - "history(name, limit=100) -> list[RunResult]: newest-first via ETL_LIST_RUNS"
  - "last_run(name) -> RunResult | None: most-recent via ETL_GET_LAST_RUN"
affects:
  - 19-sync-runner-query-surface (Plan 03 will write integration tests for the query surface)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "_fetch_run_result() private helper: re-SELECT by run_id, one source of truth (D-11)"
    - "dry_run early fork before self.init(): extract+transform only, no write surface (D-08/D-09)"
    - "history()/last_run() follow same autocommit dict_row pattern as _start_run/_end_run (Pitfall 6)"

key-files:
  created: []
  modified:
    - pycopg/etl.py
    - tests/test_etl_accessor.py

key-decisions:
  - "_fetch_run_result extracted as private helper (not inline twice) — DRY for two return run_id sites (RESEARCH Open Q1)"
  - "dry_run fork placed before name = pipeline.name guard so init/_start_run/_end_run unreachable (D-09)"
  - "last_run() uses ETL_GET_LAST_RUN directly, not history(name, limit=1) — dedicated constant, no list allocation (D-07)"
  - "rows_extracted in dry_run re-computed after transform (len(df) after transform chain, not before)"

patterns-established:
  - "run() return upgrade: always re-SELECT from DB via ETL_GET_RUN after _end_run — never assemble in-memory (D-11)"
  - "dry_run branch: early return RunResult built in-memory from UTC bracket + extracted row count (D-08)"

requirements-completed: [ETL-10, ETL-11, ETL-15, ETL-17]

# Metrics
duration: 8min
completed: 2026-06-15
---

# Phase 19 Plan 02: run() RunResult upgrade + history() + last_run() Summary

**`run()` upgraded to return `RunResult` via `_fetch_run_result` re-SELECT (D-11); `dry_run=True` early fork writes no pipeline_runs row (D-08/D-09); `history()` and `last_run()` query surface added as autocommit dict_row read methods**

## Performance

- **Duration:** 8 min
- **Started:** 2026-06-15T18:33:00Z
- **Completed:** 2026-06-15T18:41:21Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Changed `run()` signature to `run(self, pipeline, dry_run=False) -> RunResult`; added `_fetch_run_result(run_id)` private helper that re-SELECTs from `pipeline_runs` via `ETL_GET_RUN`, maps through `_row_to_result` (D-11 — one source of truth, one mapper)
- Replaced both `return run_id` sites (empty-DataFrame early return and normal success path) with `return self._fetch_run_result(run_id)` — zero stale `return run_id` remaining (Pitfall 2)
- Added `dry_run` early fork before `self.init()`: runs extract + transform, builds `RunResult(status='dry_run', run_id=None, rows_loaded=0)` in-memory without touching the run-log (D-08/D-09)
- Added `history(name, limit=100) -> list[RunResult]` via `ETL_LIST_RUNS` with autocommit dict_row connection, newest-first (D-06/ETL-11)
- Added `last_run(name) -> RunResult | None` via `ETL_GET_LAST_RUN` directly, returns `None` when no row (D-07/ETL-17)

## Task Commits

Each task was committed atomically:

1. **Task 1: run() return upgrade + dry_run early fork** - `6642d18` (feat)
2. **Task 2: history() and last_run() read methods** - `42832fb` (feat)
3. **Deviation fix: update existing tests for RunResult return type** - `c0a5abf` (fix)

**Plan metadata:** (docs commit below)

## Files Created/Modified

- `pycopg/etl.py` — Added `_fetch_run_result()` helper, upgraded `run()` signature/return/docstring, added dry_run early fork, added `history()` and `last_run()` methods
- `tests/test_etl_accessor.py` — Added `RunResult` import; updated 6 existing tests that used `run_id = db.etl.run(p)` as a raw `int` to use `result = db.etl.run(p); result.run_id` instead

## Decisions Made

- Followed D-11: `_fetch_run_result` uses `ETL_GET_RUN` (run_id-keyed SELECT) not `ETL_GET_LAST_RUN` (pipeline_name-keyed — unsafe under concurrent runs, Pitfall 3)
- Followed D-09: dry_run fork placed before `self.init()` — cannot leave a 'running' row stranded (verified by comment removal from position check)
- Followed D-07: `last_run` runs `ETL_GET_LAST_RUN` directly (dedicated constant, avoids Python list allocation of `history(name, limit=1)[0]`)
- Dry_run `rows_extracted` is measured after the transform chain (`len(df)` post-transform) — this reflects how many rows would actually have been loaded, not just extracted (D-08 says "after transform")

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated existing tests expecting `int` return from `run()`**
- **Found during:** After Task 1 commit (pre-existing test assertions became incorrect)
- **Issue:** 6 tests in `test_etl_accessor.py` captured `run_id = db.etl.run(p)` and used it as a raw `int` (e.g., `assert isinstance(run_id, int)`, passing it directly to `WHERE run_id = %s`). With `run()` now returning `RunResult`, these tests would fail with type errors or incorrect query params.
- **Fix:** Added `RunResult` to imports; changed all 6 sites to `result = db.etl.run(p)` and `result.run_id` where the raw int was needed. Updated docstring of `test_run_accepts_pipeline_object` to reflect new return type.
- **Files modified:** `tests/test_etl_accessor.py`
- **Verification:** `uv run pytest tests/test_etl_accessor.py -x -q -o addopts=""` → 41 passed; `uv run pytest tests/test_etl.py -x -q -o addopts=""` → 53 passed
- **Committed in:** `c0a5abf` (separate fix commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — bug: test assertions incompatible with changed return type)
**Impact on plan:** Required fix — the return type change from `int` to `RunResult` necessarily breaks assertions that checked `isinstance(run_id, int)`. All tests updated and passing.

## Issues Encountered

None — both tasks executed cleanly. The only deviation was the expected consequence of the `int -> RunResult` return type change on existing tests.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `run()` returns `RunResult` via DB re-SELECT (D-11), `dry_run` fork works (D-08/D-09), `history()` and `last_run()` are in place (D-06/D-07)
- Plan 03 can now write `TestRunResultSurface` integration tests (SC-1..SC-4) and `TestRowToResult` pure unit tests
- All 41 ETL accessor integration tests and 53 DB-free unit tests pass
- No blockers

## Self-Check: PASSED

- `pycopg/etl.py` modified: verified (`_fetch_run_result` exists, `run()` signature correct, `dry_run` fork before `self.init()`, zero `return run_id` in `run()` body, `history()` and `last_run()` present)
- `tests/test_etl_accessor.py` modified: verified (6 test sites updated, 41 tests pass)
- Commit `6642d18` (Task 1): confirmed in `git log --oneline --grep="19-02"`
- Commit `42832fb` (Task 2): confirmed in `git log --oneline --grep="19-02"`
- Commit `c0a5abf` (test fixes): confirmed in `git log --oneline --grep="19-02"`
- `ruff check pycopg/etl.py tests/test_etl_accessor.py`: clean (warnings are pre-existing pyproject.toml deprecation notices, not code errors)

---
*Phase: 19-sync-runner-query-surface*
*Completed: 2026-06-15*
