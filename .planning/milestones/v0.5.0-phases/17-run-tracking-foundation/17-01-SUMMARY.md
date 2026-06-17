---
phase: 17-run-tracking-foundation
plan: "01"
subsystem: etl
tags: [etl, run-tracking, accessor, database, tests]
dependency_graph:
  requires:
    - "Phase 16 P01/P02: ETL_INIT_PIPELINE_RUNS / ETL_INSERT_RUN / ETL_UPDATE_RUN constants in queries.py"
    - "Phase 16: build_init_sql() / Pipeline dataclass in etl.py"
    - "Phase 12: Database.execute(sql, params, autocommit=True) in database.py"
  provides:
    - "pycopg.etl.ETLAccessor with init(), _start_run(), _end_run(), run()"
    - "Database.etl lazy property (db.etl accessor namespace)"
    - "tests/test_etl_accessor.py: unit + DB integration tests SC-1..SC-4"
  affects:
    - "Phase 18: inherits correct transaction-boundary behavior from ETLAccessor"
    - "Phase 19: full run() body, RunResult, history(), last_run() built on _start_run/_end_run"
    - "Phase 20: async-only wiring (AsyncETLAccessor + async_db.etl)"
tech_stack:
  added: []
  patterns:
    - "Lazy accessor namespace (db.etl mirrors db.spatial exactly — D-01/D-02)"
    - "Fresh autocommit connection per run-log write via db.execute(..., autocommit=True) (D-04/D-05)"
    - "Status literals: 'running' / 'success' / 'failed' — never 'error' (D-07)"
    - "No PostGIS guard, no schema arg on ETLAccessor.__init__ (D-08)"
    - "Exceptions propagate; no try/except-and-warn wrapper on run-log writes (D-06/D-11)"
key_files:
  created:
    - tests/test_etl_accessor.py
  modified:
    - pycopg/etl.py
    - pycopg/database.py
decisions:
  - "Used datetime.UTC (UP017-compliant) instead of timezone.utc for timezone-aware timestamps"
  - "Used conn.cursor() directly inside db.transaction() block in SC-4 test so the INSERT is part of the load transaction — db.execute() outside a session opens its own connection"
  - "Thin run() stub calls init()/_start_run()/_end_run() with zero counts — full body deferred to Phase 18/19 per D-03"
metrics:
  duration_minutes: 5
  completed_date: "2026-06-15"
  tasks_completed: 2
  tasks_total: 2
  files_created: 1
  files_modified: 2
---

# Phase 17 Plan 01: ETLAccessor + db.etl property + SC-1..SC-4 Tests Summary

**One-liner:** `ETLAccessor` with `init()`/`_start_run()`/`_end_run()`/`run()` wired as `db.etl` lazy property; all run-log writes on dedicated autocommit connections; 10 tests (6 unit + 4 integration) prove SC-1..SC-4 including rollback isolation.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add ETLAccessor to etl.py and wire db.etl property | 4a5458f | pycopg/etl.py, pycopg/database.py |
| 2 | Tests — unit (param/status) + DB integration (SC-1..SC-4) | 69158bc | tests/test_etl_accessor.py |

## What Was Built

### Task 1: ETLAccessor + db.etl

Added `class ETLAccessor` to `pycopg/etl.py` at module end, mirroring `SpatialAccessor` shape:

- `__init__(self, db)`: stores `self._db = db` only — no PostGIS guard, no schema arg (D-08)
- `init()`: executes `queries.ETL_INIT_PIPELINE_RUNS` with `autocommit=True` (idempotent DDL, D-10/D-15)
- `_start_run(name) -> int`: INSERT `[name, "running", datetime.now(UTC)]` → returns `rows[0]["run_id"]`
- `_end_run(run_id, status, rows_extracted, rows_loaded, error_message=None, error_traceback=None)`: UPDATE with `[status, datetime.now(UTC), rows_extracted, rows_loaded, error_message, error_traceback, run_id]`
- `run(name="pipeline") -> int`: thin stub — calls `init()`, `_start_run(name)`, `_end_run(run_id, "success", 0, 0)`, returns run_id (Phase 18/19 will flesh out the full body)

All run-log writes use `self._db.execute(..., autocommit=True)`, routing through `cursor(autocommit=True)` → `connect(autocommit=True)` → `_connect_with_retry`, opening a fresh short-lived connection per write (D-04/D-05).

Added to `pycopg/database.py`:
- `self._etl: ETLAccessor | None = None` field in `__init__` alongside `self._spatial`
- `from pycopg.etl import ETLAccessor` in the `TYPE_CHECKING` block
- `etl` property mirroring `spatial` exactly: None-check → in-property import → store → return

### Task 2: Tests

Created `tests/test_etl_accessor.py` with 10 tests:

**TestETLAccessorUnit (6 tests, no DB):**
- `test_start_run_param_order_and_returns_run_id`: verifies `[name, "running", <aware datetime>]` packing + returns 42
- `test_end_run_param_order`: verifies `[status, <datetime>, rows_extracted, rows_loaded, error_message, error_traceback, run_id]` packing
- `test_status_literal_is_failed_not_error`: asserts no call ever passes `"error"` as a value
- `test_constructor_has_no_postgis_guard`: fake has no `has_extension` and construction succeeds
- `test_end_run_none_defaults`: defaults for error_message and error_traceback are None
- `test_init_calls_etl_init_constant`: `init()` calls `ETL_INIT_PIPELINE_RUNS` with `autocommit=True`

**TestETLAccessorIntegration (4 tests, pycopg_test):**
- `test_init_idempotent` (SC-2): double init(), exactly one table in information_schema
- `test_first_run_auto_creates` (SC-3): drop + `run("auto")` → table exists
- `test_run_writes_full_row` (SC-1): row has all columns populated, watermark IS NULL
- `test_failed_run_commits_despite_load_rollback` (SC-4): transaction rollback + `_end_run("failed")` → pipeline_runs row committed with status='failed', load mutation absent from scratch table

## Verification Results

```
uv run pytest tests/test_etl_accessor.py -o addopts="" -q
10 passed in 0.84s

uv run ruff check pycopg/etl.py pycopg/database.py tests/test_etl_accessor.py
All checks passed!

uv run black --check pycopg/etl.py pycopg/database.py tests/test_etl_accessor.py
All done! 2 files would be left unchanged. (after reformatting)
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] SC-4 test: db.execute() inside db.transaction() doesn't use the transaction connection**

- **Found during:** Task 2 (first test run — test failed with `assert 999 not in [1, 999]`)
- **Issue:** `db.execute(sql)` without `autocommit=True` still opens its own connection (since `_session_conn` is None when not in `db.session()`). The INSERT ran outside the transaction and committed immediately.
- **Fix:** Changed the SC-4 test to use `conn.cursor()` directly on the yielded connection from `with db.transaction() as conn:`, so the INSERT is properly part of the load transaction and rolls back on exception.
- **Files modified:** tests/test_etl_accessor.py
- **Commit:** 69158bc (included in Task 2 commit)

**2. [Rule 2 - Missing functionality] Used datetime.UTC instead of timezone.utc**

- **Found during:** Task 1 (ruff UP017 warning)
- **Issue:** `from datetime import datetime, timezone` + `datetime.now(timezone.utc)` triggers UP017 in ruff (use `datetime.UTC` alias, Python 3.11+)
- **Fix:** Changed to `from datetime import UTC, datetime` and `datetime.now(UTC)` throughout etl.py
- **Files modified:** pycopg/etl.py
- **Commit:** 4a5458f (included in Task 1 commit)

## Known Stubs

`ETLAccessor.run()` is intentionally a thin stub (D-03): it calls `init()`, `_start_run()`, and `_end_run()` with zero row counts but does not implement extract, transform, or load logic. Full body lands in Phases 18/19. This is by design — the stub establishes the auto-create + start/end seam required by SC-1/SC-3 and is documented in the method docstring.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes beyond what the plan's threat model covers. The `pipeline_runs` table creation is runtime-only via idempotent DDL. All SQL uses `%s`-only constants (T-17-01 mitigated). Run-log writes on dedicated autocommit connection (T-17-04 mitigated). No new runtime dependencies added.

## Self-Check: PASSED

Files exist:
- /home/loc/workspace/pycopg/pycopg/etl.py — FOUND (contains ETLAccessor)
- /home/loc/workspace/pycopg/pycopg/database.py — FOUND (contains etl property)
- /home/loc/workspace/pycopg/tests/test_etl_accessor.py — FOUND (10 tests, all pass)

Commits exist:
- 4a5458f — feat(17-01): add ETLAccessor to etl.py and wire db.etl property on Database — FOUND
- 69158bc — test(17-01): unit + DB integration tests for ETLAccessor (SC-1..SC-4) — FOUND
