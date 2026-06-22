---
phase: 30-chunk-management-partitioning
plan: "01"
subsystem: timescaledb
tags: [exception, sql-constant, test-scaffold, wave-0]
dependency_graph:
  requires: []
  provides:
    - pycopg.exceptions.TimescaleError
    - pycopg.queries.TSDB_SHOW_CHUNKS
    - pycopg.queries.TSDB_DROP_CHUNKS
    - tests/test_timescale.py (ts_db + async_ts_db fixtures, Wave 0 stubs)
  affects:
    - Plans 02 and 03 (depend on TimescaleError, TSDB_SHOW_CHUNKS, test fixtures)
tech_stack:
  added: []
  patterns:
    - "one-liner-docstring + pass exception subclass (mirrors ExtensionNotAvailable)"
    - "%%I.%%I regclass JOIN key in SQL constants (mirrors HYPERTABLE_INFO / TABLE_SIZES)"
    - "create-extension-or-skip ts_db fixture (ported from TestDatabaseTimescaleCoverage)"
    - "asyncio_mode=auto async fixture (no per-test marker)"
    - "xfail Wave 0 stubs for keyword-matchable test collection"
key_files:
  created:
    - tests/test_timescale.py
  modified:
    - pycopg/exceptions.py
    - pycopg/queries.py
decisions:
  - "TSDB_SHOW_CHUNKS uses {schema}.{table}{older_arg}{newer_arg} Python format placeholders so the Plan 02 builder can str.format() the final SQL after validate_identifiers"
  - "TSDB_DROP_CHUNKS added alongside TSDB_SHOW_CHUNKS (names per Claude discretion)"
  - "TimescaleError placed before ETLError in exceptions.py (after existing subclasses, D-09)"
  - "Wave 0 stubs use xfail(strict=False) rather than pytest.skip() so pytest --collect-only shows them without needing a live DB"
  - "noqa: F401 applied to FeatureNotSupported + TimescaleError + ExtensionNotAvailable imports (forward-declared for Plans 02/03 stub body replacement)"
metrics:
  duration_seconds: 210
  completed_date: "2026-06-22"
  tasks_completed: 2
  tasks_total: 2
  files_changed: 3
---

# Phase 30 Plan 01: Foundation — TimescaleError, TSDB_SHOW_CHUNKS, test scaffold

**One-liner:** TimescaleError exception + TSDB_SHOW_CHUNKS SQL constant (%%I.%%I regclass JOIN, range_start ASC) + tests/test_timescale.py with ts_db/async_ts_db skip-fixtures and 19 xfail Wave 0 stubs.

## What Was Built

### Task 1 — TimescaleError + TSDB_SHOW_CHUNKS (commit `6e01914`)

Added `class TimescaleError(PycopgError)` to `pycopg/exceptions.py` using the exact
one-liner-docstring + `pass` form of `ExtensionNotAvailable`/`TableNotFound`.  This is the
milestone-wide domain error reused in Phases 31-32 (D-09).

Added two SQL constants to `pycopg/queries.py` in the TIMESCALEDB section alongside
`LIST_HYPERTABLES` / `HYPERTABLE_INFO`:

- `TSDB_SHOW_CHUNKS`: SELECT with SRF + `timescaledb_information.chunks` JOIN via
  `format('%%I.%%I', chunk_schema, chunk_name)::regclass = sc`, ordered by `c.range_start ASC`.
  Uses `{schema}.{table}{older_arg}{newer_arg}` Python format placeholders for the Plan 02 builder.
- `TSDB_DROP_CHUNKS`: Minimal `SELECT drop_chunks(...)` template with the same placeholder shape.

The `%%I` escaping follows the existing codebase convention (psycopg eats a single `%`; both
`HYPERTABLE_INFO` and `TABLE_SIZES` use this same pattern).

### Task 2 — tests/test_timescale.py (commit `669b828`)

Created the new test file (184 lines) as the home for all v0.8.0 advanced-TSDB tests (D-10):

- `db` fixture: Database connected to pycopg_test (mirrors test_database_integration.py pattern).
- `ts_db` fixture: create-extension-or-skip guard, ported verbatim from
  `TestDatabaseTimescaleCoverage` (test_database_integration.py:839).
- `async_ts_db` fixture: async equivalent using `asyncio_mode = "auto"` (no per-test marker).
- `FeatureNotSupported` imported with `noqa: F401` for D-12 Apache-license tolerance in Plan 03.
- `TimescaleError` / `ExtensionNotAvailable` forward-imported with `noqa: F401` for Plan 02/03 bodies.
- 19 xfail stubs across 4 classes (TestShowChunksStub, TestDropChunksStub, TestAddDimensionStub,
  TestAddReorderPolicyStub) — keyword-matchable via -k show_chunks, drop_chunks, add_dimension, reorder.

## Verification Results

- `from pycopg.exceptions import TimescaleError, PycopgError; issubclass(TimescaleError, PycopgError)` → True
- `'%%I.%%I' in queries.TSDB_SHOW_CHUNKS and 'range_start ASC' in queries.TSDB_SHOW_CHUNKS` → True
- `uv run pytest tests/test_timescale.py -q -o addopts=""` → 19 xfailed (green)
- `-k show_chunks` collects 5 tests; `-k reorder` collects 4 tests (both > 0)
- `uv run ruff check pycopg/exceptions.py pycopg/queries.py tests/test_timescale.py` → clean (only pre-existing N818 in other exceptions)

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written.

### Notes

1. Pre-existing N818 lint errors (`ExtensionNotAvailable`, `TableNotFound`, `InvalidIdentifier`,
   `DatabaseExists` — exception names without "Error" suffix) appear in `uv run ruff check pycopg tests`
   but are pre-existing across all phases. Not introduced by this plan.
2. `TSDB_SHOW_CHUNKS` uses Python `str.format()`-style `{schema}`, `{table}`, `{older_arg}`,
   `{newer_arg}` placeholders — these must be filled by the Plan 02 builder via `str.format()` after
   `validate_identifiers()`. The `%%I` in the constant body is NOT a placeholder; it is a literal
   SQL `format('%I.%I', ...)` escape for psycopg.

## Known Stubs

Wave 0 xfail stubs in `tests/test_timescale.py` are intentional scaffolding per the plan spec.
Plans 02 and 03 replace these stub bodies with real assertions. They do not block Plan 01's goals.

## Threat Flags

No new threat surface beyond T-30-01 (already in plan threat model). `TSDB_SHOW_CHUNKS`/`TSDB_DROP_CHUNKS`
carry template placeholders only — no runtime values. Identifier validation is Plan 02's responsibility
at the call site.

## Self-Check: PASSED

- `pycopg/exceptions.py` exists and contains `class TimescaleError(PycopgError)`: FOUND
- `pycopg/queries.py` exists and contains `TSDB_SHOW_CHUNKS`: FOUND
- `tests/test_timescale.py` exists (184 lines, > 40): FOUND
- Commit `6e01914` exists: FOUND
- Commit `669b828` exists: FOUND
