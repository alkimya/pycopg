---
phase: 19-sync-runner-query-surface
plan: "01"
subsystem: etl
tags: [python, dataclass, etl, pipeline_runs, psycopg3]

# Dependency graph
requires:
  - phase: 18-load-modes-extract
    provides: "ETLAccessor.run() body, run-log isolation, load atomicity seam"
  - phase: 17-run-tracking-foundation
    provides: "pipeline_runs schema, ETL_LIST_RUNS, ETL_GET_LAST_RUN constants"
provides:
  - "RunResult frozen dataclass (8-field SC-1 value object)"
  - "_row_to_result pure mapper (error_message->error, drops error_traceback/watermark)"
  - "ETL_GET_RUN constant (SELECT * FROM pipeline_runs WHERE run_id = %s)"
affects:
  - 19-sync-runner-query-surface (Plans 02 and 03 depend on these symbols)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "RunResult frozen dataclass mirrors Pipeline style (D-01)"
    - "_row_to_result pure module-level mapper, DB-free, peers with _step_label (D-10)"
    - "ETL_GET_RUN run_id-keyed SELECT avoids pipeline_name concurrent-run race (D-11)"

key-files:
  created: []
  modified:
    - pycopg/queries.py
    - pycopg/etl.py

key-decisions:
  - "ETL_GET_RUN uses WHERE run_id = %s with no LIMIT (PK guarantees one row, D-11)"
  - "RunResult carries exactly 8 fields; no watermark (D-04), no __post_init__ (D-02)"
  - "error field maps from DB column error_message; error_traceback dropped from value object (D-03/D-10)"
  - "run_id typed int | None to accommodate dry-run case (D-05)"

patterns-established:
  - "RunResult: frozen dataclass value object placed after Pipeline, before _is_sql_source"
  - "_row_to_result: pure module-level function placed after _step_label, before class ETLAccessor"

requirements-completed: [ETL-10, ETL-11, ETL-15, ETL-17]

# Metrics
duration: 2min
completed: 2026-06-15
---

# Phase 19 Plan 01: ETL_GET_RUN + RunResult + _row_to_result Summary

**`RunResult` 8-field frozen dataclass and `_row_to_result` pure mapper added to `etl.py`; `ETL_GET_RUN` run_id-keyed SELECT constant added to `queries.py` — the DB-free foundation for the Phase 19 query surface**

## Performance

- **Duration:** 2 min
- **Started:** 2026-06-15T18:32:38Z
- **Completed:** 2026-06-15T18:34:04Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments

- Added `ETL_GET_RUN = SELECT * FROM pipeline_runs WHERE run_id = %s` to `queries.py` (no LIMIT, keyed on PK run_id — safe under concurrent runs, D-11)
- Added `RunResult` `@dataclass(frozen=True)` to `etl.py` with exactly the 8 SC-1 fields in order: `run_id`, `pipeline_name`, `status`, `rows_extracted`, `rows_loaded`, `started_at`, `finished_at`, `error` (D-01/D-02/D-03/D-04/D-05)
- Added `_row_to_result(row: dict) -> RunResult` pure module-level mapper to `etl.py`; renames `error_message → error`, drops `error_traceback` and `watermark` (D-10); zero I/O, unit-testable from a plain dict

## Task Commits

1. **Task 1: ETL_GET_RUN + RunResult dataclass + _row_to_result mapper** - `73bc664` (feat)

**Plan metadata:** (docs commit below)

## Files Created/Modified

- `pycopg/queries.py` — Added `ETL_GET_RUN` constant after `ETL_GET_LAST_RUN` in the ETL QUERIES block
- `pycopg/etl.py` — Added `RunResult` frozen dataclass (after `Pipeline`, before `_is_sql_source`); added `_row_to_result` pure function (after `_step_label`, before `class ETLAccessor`)

## Decisions Made

- Followed D-11: `ETL_GET_RUN` is `run_id`-keyed (not `pipeline_name`-keyed) to be safe under concurrent runs of the same pipeline name.
- Followed D-02: `RunResult` has no `__post_init__` — it is a pure snapshot, not a validated constructor.
- Followed D-10: `_row_to_result` is a module-level pure function (not a classmethod or ETLAccessor method) so it is callable without a DB connection.
- Followed D-03/D-04: `error_traceback` and `watermark` are dropped; only `error_message → error` is surfaced.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `RunResult`, `_row_to_result`, and `ETL_GET_RUN` are all in place and verified (plan automated check exits 0).
- Plan 02 can now upgrade `run()` return type and add `history()`/`last_run()` methods — all three symbols it needs exist.
- No blockers.

## Self-Check: PASSED

- `pycopg/queries.py` modified: verified (`ETL_GET_RUN` contains `run_id = %s`, no `LIMIT`)
- `pycopg/etl.py` modified: verified (`RunResult` has exactly 8 fields in correct order; `_row_to_result` maps `error_message → error`, drops `error_traceback`/`watermark`)
- Commit `73bc664` exists: `git log --oneline --grep="19-01"` returns the commit
- `ruff check pycopg/etl.py pycopg/queries.py`: clean (no errors)

---
*Phase: 19-sync-runner-query-surface*
*Completed: 2026-06-15*
