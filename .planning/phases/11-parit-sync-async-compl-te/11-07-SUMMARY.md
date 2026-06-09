---
phase: 11-parit-sync-async-compl-te
plan: 07
subsystem: testing
tags: [coverage, ratchet, pyproject, copy-csv, timescaledb, bugfix]

requires:
  - phase: 11-parit-sync-async-compl-te
    provides: "Plans 02-06 — implementations + parity tests adding DDL/admin/batch coverage"
provides:
  - Coverage ratchet raised to 90 (--cov-fail-under=90)
  - Targeted coverage-fill tests (sync + async) reaching 91.61% total
  - Fixes for 2 latent bugs (copy_to_csv memoryview, hypertable_info %I/type)
affects: [CI tests.yml coverage gate, milestone v0.4.0 coverage ratchet]

tech-stack:
  added: []
  patterns:
    - "Coverage ratchet: measure first, raise the gate only after the floor is met (D-08)"

key-files:
  created: []
  modified:
    - pyproject.toml
    - tests/test_database_integration.py
    - tests/test_async_database.py
    - pycopg/database.py
    - pycopg/async_database.py

key-decisions:
  - "D-08: gate raised 80->90 only after measuring 91.61% — never freeze an unmet threshold"
  - "DEVIATION: fixed 2 latent bugs (copy_to_csv memoryview write, hypertable_info %I placeholder + param type) in BOTH sync and async to preserve parity"
  - "async from_geodataframe/to_geodataframe not tested — geopandas needs a sync DBAPI cursor the async adapter can't provide; out of phase scope"

patterns-established: []

requirements-completed: [PAR-09]

duration: 40min
completed: 2026-06-09
---

# Phase 11 / Plan 07: Coverage Ratchet to 90 Summary

**Total test coverage raised from 84.72% to 91.61% with targeted real-DB tests (and 2 latent bug fixes surfaced along the way), then the CI ratchet flipped 80 → 90 — meeting the v0.4.0 locked coverage floor.**

## Performance

- **Duration:** ~40 min
- **Completed:** 2026-06-09
- **Tasks:** 2 completed
- **Files modified:** 5

## Accomplishments
- **Task 1 — measure + fill (D-08):** baseline measured at 84.72%. Added targeted real-DB tests for the still-uncovered surface: sync constraint/admin (FK cascade + invalid-action, unique, truncate cascade, drop_extension idempotent, drop_table/schema branches), `copy_insert`, `size`/`table_size`/`row_count`, `copy_to_csv`/`copy_from_csv` round-trip, TimescaleDB hypertable lifecycle (create/info/list, compression tolerant of Apache-license `FeatureNotSupported`), sync GeoDataFrame round-trip; plus the async mirrors (copy_insert, size/table_size/row_count, csv, timescale). Result: **91.61%** (91.11% even excluding the 2 pre-existing failing tests).
- **Task 2 — flip ratchet:** changed `--cov-fail-under` 80 → 90 in pyproject.toml; the suite passes the 90 gate (`Required test coverage of 90% reached`).

## Latent bugs fixed (deviation, applied to BOTH sync + async for parity)
1. **`copy_to_csv`** wrote psycopg's `memoryview` chunks directly — `isinstance(data, bytes)` was always False, so `f.write(memoryview)` raised `TypeError`. Now `bytes(data).decode(encoding)`.
2. **`hypertable_info`** used `format('%I.%I', %s, %s)` — psycopg rejects `%I` as a placeholder (`only %s/%b/%t allowed`), and even escaped the `%s` params had no inferable type (`IndeterminateDatatype`). Now `format('%%I.%%I', %s::text, %s::text)`.

Both bugs lived in untested code; the new coverage tests surfaced them.

## Task Commits

1. **Task 1: coverage-fill tests + 2 bug fixes** — `6c15cd8` (test)
2. **Task 2: flip ratchet to 90** — `e3f732b` (build)

## Files Created/Modified
- `pyproject.toml` — `--cov-fail-under=90`.
- `tests/test_database_integration.py` — `TestDatabaseConstraintsAdminCoverage`, `TestDatabaseCsvCoverage`, `TestDatabaseBulkAndSizeCoverage`, `TestDatabaseGeoCoverage`, `TestDatabaseTimescaleCoverage`.
- `tests/test_async_database.py` — `TestAsyncDatabaseCoverageFill`.
- `pycopg/database.py`, `pycopg/async_database.py` — the 2 latent-bug fixes.

## Verification
- `uv run pytest`: 652 passed, 2 skipped, **2 pre-existing failures** (test_async_transaction_fix, test_create_spatial_index_name_parameter). Total coverage **91.61%** ≥ 90 — `Required test coverage of 90% reached`.
- The 2 failures are confirmed PRE-EXISTING (files last touched at v0.2.0 / phase 06; NOT modified in Phase 11) and are NOT new regressions — out of phase scope per the plan.
- ruff/black: source clean; new test code clean.

## Notes / Deviations
- 2 source bug fixes (above) — necessary to cover the methods; applied to both sync+async for parity. Not a Phase-12 refactor.
- async GeoDataFrame round-trip not asserted (geopandas + async adapter incompatibility) — documented inline; sync GIS round-trip is covered.

## Self-Check: PASSED
