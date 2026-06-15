---
phase: 19-sync-runner-query-surface
plan: "03"
subsystem: etl
tags: [python, etl, RunResult, pytest, psycopg3, pipeline_runs, dry_run]

# Dependency graph
requires:
  - phase: 19-sync-runner-query-surface/19-01
    provides: "RunResult frozen dataclass, _row_to_result mapper, ETL_GET_RUN constant"
  - phase: 19-sync-runner-query-surface/19-02
    provides: "run()->RunResult, history(), last_run(), dry_run fork"
provides:
  - "TestRowToResult: DB-free unit class proving _row_to_result mapper contract (D-10)"
  - "TestRunResultSurface: integration class covering SC-1 (run/fields/status), SC-2 (history newest-first/two-entries/empty), SC-3 (last_run most-recent/None/not-older), SC-4 (dry_run status/run_id/rows_loaded/rows_extracted/no-row/target-unchanged)"
  - "Verified Task 2 migration already complete (6 sites + isinstance assertion fixed in 19-02 deviation c0a5abf)"
affects:
  - 19-sync-runner-query-surface (Wave 3 complete; Phase 19 ETL surface proven)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "TestRowToResult: pure unit class with _sample_row helper, mirrors TestPipeline style"
    - "TestRunResultSurface: integration class with db/cleanup_pipeline_runs/etl_table fixtures, mirrors TestRunPipelineIntegration"
    - "db.etl.init() called before COUNT(*) on pipeline_runs in dry_run no-row test (table not auto-created by dry run)"

key-files:
  created: []
  modified:
    - tests/test_etl.py
    - tests/test_etl_accessor.py

key-decisions:
  - "TestRowToResult uses UTC alias (from datetime import UTC) not timezone.utc — required by ruff UP017"
  - "RunResult imported in TestRowToResult and used in test_result_is_frozen isinstance check — satisfies ruff F401"
  - "test_dry_run_writes_no_pipeline_runs_row calls db.etl.init() first: dry_run skips init() so table may not exist"
  - "Task 2 migration already done in Plan 19-02 deviation fix (c0a5abf); verified via grep + pytest, no duplicate work"

patterns-established:
  - "Dry_run no-row test: call db.etl.init() before asserting COUNT(*) on pipeline_runs"
  - "SC-4 target-unchanged test: assert COUNT(*) == 0 on etl_table after dry run"

requirements-completed: [ETL-10, ETL-11, ETL-15, ETL-17]

# Metrics
duration: 4min
completed: 2026-06-15
---

# Phase 19 Plan 03: ETL Test Suite (TestRowToResult + TestRunResultSurface) Summary

**DB-free `TestRowToResult` proves the `_row_to_result` D-10 mapper contract; `TestRunResultSurface` integration class proves SC-1..SC-4 against pycopg_test including the dry_run no-row invariant; 115 ETL tests green**

## Performance

- **Duration:** 4 min
- **Started:** 2026-06-15T18:44:23Z
- **Completed:** 2026-06-15T18:48:28Z
- **Tasks:** 3 (Task 2 already-satisfied verification + Tasks 1 and 3 new code)
- **Files modified:** 2

## Accomplishments

- Added `TestRowToResult` (5 DB-free unit tests) to `tests/test_etl.py`: maps-all-8-fields, error_message→error rename, error_traceback dropped, watermark dropped, frozen raises
- Verified Task 2 migration already complete from Plan 19-02 deviation (c0a5abf): 0 `isinstance(run_id, int)` sites, 0 `run_id = db.etl.run(` sites, `RunResult` imported
- Added `TestRunResultSurface` (16 integration tests) to `tests/test_etl_accessor.py`: SC-1 (3 tests), SC-2 (4 tests), SC-3 (3 tests), SC-4 (6 tests)
- Full targeted ETL suite: 115 tests pass (58 in test_etl.py, 57 in test_etl_accessor.py)

## Task Commits

Each task was committed atomically:

1. **Task 1: TestRowToResult DB-free unit class** - `36c3f17` (test)
2. **Task 2: Migration already satisfied** - no new commit (verified against c0a5abf from 19-02)
3. **Task 3: TestRunResultSurface integration class** - `6233889` (test)

**Plan metadata:** (docs commit below)

## Files Created/Modified

- `tests/test_etl.py` — Added `from datetime import UTC` + `RunResult`/`_row_to_result` imports; added `TestRowToResult` class (5 tests + `_sample_row` helper)
- `tests/test_etl_accessor.py` — Added `TestRunResultSurface` class (16 integration tests covering SC-1..SC-4)

## Decisions Made

- Used `from datetime import UTC` (not `timezone.utc`) to satisfy ruff UP017 rule
- Added `isinstance(result, RunResult)` assertion to `test_result_is_frozen` so `RunResult` import satisfies ruff F401
- Called `db.etl.init()` in `test_dry_run_writes_no_pipeline_runs_row` before the COUNT(*) query: a dry run intentionally skips `init()` so the `pipeline_runs` table may not exist without it
- Task 2 treated as already-satisfied: Plan 19-02 deviation fix (c0a5abf) handled all 6 migration sites plus the isinstance assertion; grep verification confirms 0 remaining sites

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Ruff UP017/F401 violations in TestRowToResult**
- **Found during:** Task 1 (first ruff check after writing tests)
- **Issue:** `timezone.utc` usage raised UP017 (use `datetime.UTC`); `RunResult` was imported but not referenced by name (F401)
- **Fix:** Changed `from datetime import datetime, timezone` to `from datetime import UTC, datetime`; replaced all `tzinfo=timezone.utc` with `tzinfo=UTC`; added `isinstance(result, RunResult)` assertion to `test_result_is_frozen`
- **Files modified:** `tests/test_etl.py`
- **Verification:** `uv run ruff check tests/test_etl.py` → clean; 5 tests pass
- **Committed in:** `36c3f17` (included in Task 1 commit)

**2. [Rule 1 - Bug] `pipeline_runs` table does not exist for dry_run no-row assertion**
- **Found during:** Task 3 (first test run of TestRunResultSurface)
- **Issue:** `test_dry_run_writes_no_pipeline_runs_row` queried `pipeline_runs` with COUNT(*) but a dry run intentionally skips `self.init()` (D-09), so the table was never created → `psycopg.errors.UndefinedTable`
- **Fix:** Added `db.etl.init()` call before `db.etl.run(p, dry_run=True)` in that test
- **Files modified:** `tests/test_etl_accessor.py`
- **Verification:** All 16 `TestRunResultSurface` tests pass; full suite 115 pass
- **Committed in:** `6233889` (included in Task 3 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 1 — test correctness bugs found during first verify runs)
**Impact on plan:** Both fixes necessary for test correctness; no scope creep. All acceptance criteria met.

## Issues Encountered

None beyond the two auto-fixed deviations above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 19 Wave 3 complete: all 3 plans shipped (01: symbols, 02: implementation, 03: tests)
- 115 ETL tests green; SC-1..SC-4 proven against pycopg_test
- Phase gate prerequisite: `uv run pytest` full suite with coverage ≥ 94 (orchestrator runs this)
- Phase 20 can start: AsyncETLAccessor parity, Sphinx docs, coverage ratchet, v0.5.0 PyPI release (ETL-12/13)

## Self-Check: PASSED

- `tests/test_etl.py` modified: verified (`TestRowToResult` present, 5 tests, `RunResult`/`_row_to_result` imported)
- `tests/test_etl_accessor.py` modified: verified (`TestRunResultSurface` present, 16 tests, all SC-1..SC-4 covered)
- Commit `36c3f17` (Task 1): confirmed in `git log --oneline --grep="19-03"`
- Commit `6233889` (Task 3): confirmed in `git log --oneline --grep="19-03"`
- `uv run pytest tests/test_etl_accessor.py::TestRunResultSurface -x -o addopts=""` → 16 passed
- `uv run pytest tests/test_etl_accessor.py tests/test_etl.py -o addopts=""` → 115 passed
- `uv run ruff check tests/test_etl.py tests/test_etl_accessor.py` → clean

---
*Phase: 19-sync-runner-query-surface*
*Completed: 2026-06-15*
