---
phase: 45-api-completeness-gaps-structured-logging
plan: "04"
subsystem: structured-logging
tags: [logging, instrumentation, etl, backup, migrations, dataframe, d09, d10]
dependency_graph:
  requires: ["45-01", "45-03"]
  provides: ["LOG-01 coarse instrumentation (D-09) — all heavyweight ops wrapped"]
  affects: [pycopg/etl.py, pycopg/backup.py, pycopg/migrations.py, pycopg/database.py, pycopg/async_database.py]
tech_stack:
  added: []
  patterns:
    - "with log_operation(op_name, rows=N): body — sync CM wraps awaited body for async paths"
    - "rows=len(df) passed at CM construction for COPY paths (count known up-front)"
    - "rows=None for etl.run (count not known at entry) and migrations.migrate (loop body wraps)"
key_files:
  created: []
  modified:
    - pycopg/etl.py
    - pycopg/backup.py
    - pycopg/migrations.py
    - pycopg/database.py
    - pycopg/async_database.py
    - tests/test_logging_module.py
decisions:
  - "D-09 coarse instrumentation ONLY: execute/fetch_* hot path intentionally excluded"
  - "rows=None for etl.run (run body executes before count is known; restructuring deferred)"
  - "rows=None for migrations.migrate (applied list grows inside the log_operation block)"
  - "rows=len(df)/len(gdf) for from_dataframe/from_geodataframe (count known at method entry)"
  - "sync log_operation CM wraps async bodies — timing brackets the await (no asyncio CM needed)"
metrics:
  duration: "12 minutes"
  completed_date: "2026-06-30T18:57:17Z"
  tasks_completed: 2
  files_modified: 6
---

# Phase 45 Plan 04: Coarse Structured-Logging Instrumentation Summary

Wrapped all D-09 heavyweight ops in `log_operation` — the second half of LOG-01. All 13 coarse instrumentation sites are present across etl, backup, migrations, and the COPY paths.

## What Was Built

Applied `with log_operation(op_name, rows=N):` wraps to:

- `ETLAccessor.run` + `AsyncETLAccessor.run` → `log_operation("etl.run")` (wraps full body including dry_run fork and try/except; rows=None — count not known at entry)
- `BackupAccessor.pg_dump` + `AsyncBackupAccessor.pg_dump` → `log_operation("backup.pg_dump")` (rows omitted)
- `BackupAccessor.pg_restore` + `AsyncBackupAccessor.pg_restore` → `log_operation("backup.pg_restore")` (rows omitted)
- `Migrator.migrate` loop → `log_operation("migrations.migrate")` (wraps the for-loop body; rows=None)
- `Database.from_dataframe` + `AsyncDatabase.from_dataframe` → `log_operation("database.from_dataframe", rows=len(df))`
- `Database.from_geodataframe` + `AsyncDatabase.from_geodataframe` → `log_operation("database.from_geodataframe", rows=len(gdf))`

Added `TestInstrumentationSites` class to `tests/test_logging_module.py`:
- `test_instrumentation_sites_from_dataframe_emits_debug`: no-DB smoke test using mocked internals, asserts DEBUG record with `operation == "database.from_dataframe"` and numeric `duration_ms`
- `test_instrumentation_sites_operation_strings_present_in_source`: AST audit asserting all 13 D-09 instrumentation sites appear in source (including 2 health sites from Plan 03)

## Commits

| Hash | Message |
|------|---------|
| 956452f | feat(45-04): wrap etl.run, backup pg_dump/pg_restore, migrations.migrate in log_operation |
| a9e439c | test(45-04): add failing test_instrumentation_sites smoke test (TDD RED) |
| 36a8701 | feat(45-04): wrap from_dataframe/from_geodataframe (sync+async) + green instrumentation tests |
| 71d5a8c | style(45-04): apply black formatting to instrumented files |

## Verification Results

- `uv run pytest tests/test_logging_module.py`: 12 passed (all green, no live DB)
- `PGDATABASE=pycopg_test2 uv run pytest tests/test_parity.py`: 37 passed
- `uv run ruff check pycopg tests && uv run black --check pycopg tests`: clean
- `uv run pytest -W error::DeprecationWarning tests/test_logging_module.py`: green
- Full suite: `PGDATABASE=pycopg_test2 uv run pytest` → 1735 passed, 2 skipped, coverage 96.40% (gate ≥95% passed)
- `grep -rn "with log_operation" etl.py backup.py migrations.py database.py async_database.py` → 13 sites
- Hot path NOT instrumented: `grep -n "log_operation" database.py | grep -E "def (execute|fetch_)"` → empty

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written, with two design decisions:

1. **rows=None for etl.run**: Plan allowed this fallback ("if threading the count is awkward, accept rows=None"). The `run` method has multiple return points at various indentation depths; the count is only available as `RunResult.rows_loaded` after the body completes, which can't be passed at CM construction. The method body is now properly re-indented inside the `with log_operation("etl.run"):` block.

2. **rows=None for migrations.migrate**: The `applied` list is populated inside the `with` block during the for-loop; `len(applied)` is 0 at CM construction time. Wrapped the loop body with `rows=None` per the plan fallback.

## TDD Gate Compliance

- RED gate: `a9e439c` — `test(45-04)` commit with failing tests (from_dataframe not yet wrapped)
- GREEN gate: `36a8701` — `feat(45-04)` commit with implementation, all tests pass
- No REFACTOR phase needed — implementation was clean

## Known Stubs

None — all instrumentation sites wire to real operations.

## Threat Flags

None — all new call sites emit only constant operation-name strings and integer row counts (T-45-09 mitigated). No new network endpoints, auth paths, or schema changes introduced.

## Self-Check: PASSED

- SUMMARY.md: FOUND
- Commit 956452f (Task 1 — etl/backup/migrations): FOUND
- Commit a9e439c (Task 2 RED — failing tests): FOUND
- Commit 36a8701 (Task 2 GREEN — implementation): FOUND
- Commit 71d5a8c (black formatting): FOUND
