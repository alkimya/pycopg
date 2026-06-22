---
phase: 30-chunk-management-partitioning
plan: "03"
subsystem: timescaledb
tags: [add-dimension, add-reorder-policy, partitioning, by_hash, by_range, TimescaleError, D-08-reshape, mock-authoritative, license-tolerant, tdd, wave-3]
dependency_graph:
  requires:
    - pycopg.exceptions.TimescaleError (Plan 01)
    - pycopg.timescale.TimescaleAccessor.show_chunks / drop_chunks (Plan 02)
    - tests/test_timescale.py ts_db/async_ts_db fixtures (Plan 01)
  provides:
    - pycopg.timescale.TimescaleAccessor.add_dimension
    - pycopg.timescale.TimescaleAccessor.add_reorder_policy
    - pycopg.timescale.AsyncTimescaleAccessor.add_dimension
    - pycopg.timescale.AsyncTimescaleAccessor.add_reorder_policy
    - tests/test_timescale.py mock + live tests for add_dimension/add_reorder_policy
  affects:
    - tests/test_parity.py (TS-ADV-10 auto-satisfied, no edit needed)
    - Phase 31 cagg lifecycle (TimescaleError milestone-wide reuse)
tech_stack:
  added: []
  patterns:
    - "D-07 mutual-exclusivity ValueError at construction time, before any DB round-trip"
    - "D-08 reshape: attempt-DDL -> catch broad Exception -> re-raise as TimescaleError (dup-dim)"
    - "D-12 Apache-license tolerance: try/except FeatureNotSupported in live reorder test"
    - "mock-authoritative pattern for Community-only SQL shape assertions"
    - "async: await has_extension AND await execute; ValueError guards stay plain (no await)"
key_files:
  created: []
  modified:
    - pycopg/timescale.py
    - tests/test_timescale.py
decisions:
  - "D-08 reshape confirmed: wrap duplicate-dimension DB error (TS160) as TimescaleError (if_not_exists=False path only)"
  - "add_dimension ValueError fires before has_extension guard (pure Python, never needs connection)"
  - "chunk_interval='10 days' for TIMESTAMPTZ range column (integer columns need different form)"
  - "FeatureNotSupported propagates from add_reorder_policy — not swallowed in method body"
  - "noqa: F401 on TimescaleError/ExtensionNotAvailable imports kept (already present from Plan 01)"
metrics:
  duration_seconds: 1080
  completed_date: "2026-06-22"
  tasks_completed: 3
  tasks_total: 3
  files_changed: 2
---

# Phase 30 Plan 03: add_dimension + add_reorder_policy — Sync and Async

**One-liner:** add_dimension (by_hash/by_range D-06, construction-time ValueError D-07, dup-dim->TimescaleError D-08) + add_reorder_policy (mock-authoritative SQL + Apache-tolerant live test D-12) on both accessors; 46/46 test_timescale.py green; TS-ADV-10 parity confirmed.

## What Was Built

### Task 1 — add_dimension + add_reorder_policy on both accessors (commit `5409ce3`)

Added 4 methods to `pycopg/timescale.py`:

**`TimescaleAccessor.add_dimension` (sync):**
- D-07 mutual-exclusivity ValueError fires first (before any DB round-trip):
  - `partition_type="hash"` requires `number_partitions`; forbids `chunk_interval`
  - `partition_type="range"` requires `chunk_interval`; forbids `number_partitions`
  - Any other `partition_type` also raises ValueError
- Extension guard + `validate_identifiers(table, schema)` + `validate_identifier(column)`
- Hash form: `by_hash('{column}', {int(number_partitions)})` — TSDB 2.28 builder syntax
- Range form: `validate_interval(chunk_interval)` + `by_range('{column}', INTERVAL '{chunk_interval}')`
- D-08 reshape: `try/except Exception` around execute, re-raises as `TimescaleError` with message; guard raised BEFORE the try so ExtensionNotAvailable is not swallowed

**`TimescaleAccessor.add_reorder_policy` (sync):**
- Extension guard + `validate_identifiers(table, schema, index_name)`
- SQL: `SELECT add_reorder_policy('{schema}.{table}', '{index_name}', if_not_exists => true) AS job_id`
- FeatureNotSupported propagates (D-12 — method does not swallow it; callers tolerate)

**`AsyncTimescaleAccessor.add_dimension` (async mirror):**
- Identical logic with `await self._db.schema.has_extension(...)` AND `await self._db.execute(...)`
- D-07 ValueError guards stay plain (no await) — fire before any coroutine
- D-08 try/except wraps `await self._db.execute(sql)` specifically

**`AsyncTimescaleAccessor.add_reorder_policy` (async mirror):**
- `await self._db.schema.has_extension(...)` AND `await self._db.execute(...)`
- FeatureNotSupported propagates

Also imported `TimescaleError` at the top of `pycopg/timescale.py` (needed by both D-08 catches).

### Task 2 — Tests (commits `5f222da`, `18a75e7`)

Replaced Wave 0 xfail stubs (`TestAddDimensionStub`, `TestAddReorderPolicyStub`) with two
real test classes each (mock layer + live layer):

**`TestAddDimensionMock` (mock SQL-shape, no live DB):**
- `test_add_dimension_hash_sql_shape`: asserts `by_hash('device_id', 4)` and `if_not_exists => true` in SQL
- `test_add_dimension_range_sql_shape`: asserts `by_range('ts2', INTERVAL '7 days')` in SQL
- 4 mutual-exclusivity ValueError tests (hash w/o number_partitions, hash w/ chunk_interval, range w/o chunk_interval, range w/ number_partitions) — execute never called
- `test_add_dimension_db_error_reraises_as_timescale_error`: execute raises psycopg.DatabaseError → method raises TimescaleError
- Async equivalents for all of the above

**`TestAddReorderPolicyMock` (authoritative per D-12):**
- `test_add_reorder_policy_sql_shape`: asserts `add_reorder_policy(`, `idx_events_ts`, `if_not_exists => true`, `public.events`
- No-extension raises (sync + async)

**`TestAddDimensionLive` (live-DB, ts_db gated):**
- Hash dimension on a populated hypertable (verified via `timescaledb_information.dimensions`)
- Range dimension on a TIMESTAMPTZ secondary column (ts2) — interval form works for timestamp columns
- Duplicate dimension with `if_not_exists=False` → TimescaleError raised
- ValueError mutual-exclusivity fires pre-guard (no ts_db connection needed)
- Async variant for hash dimension

**`TestAddReorderPolicyLive` (live-DB, license-tolerant):**
- Sync + async: wrap call in `try/except FeatureNotSupported: pass` (D-12)
- On Community builds: assert job row in `timescaledb_information.jobs` with `proc_name='policy_reorder'`

### Task 3 — Full-suite gate

- `uv run pytest tests/test_parity.py -k accessor_parity` → 7 passed (all 4 Phase-30 methods mirrored, TS-ADV-10 confirmed)
- `uv run pytest tests/test_timescale.py` → 46 passed (all stubs replaced)
- `uv run pytest` (full suite) → 1226 passed, 2 pre-existing flaky failures, coverage 94.96% ≥ 94% ratchet
- `uv run ruff check pycopg tests` → clean (pre-existing N818/F841/W291 in unrelated files)
- `uv run black --check pycopg/timescale.py tests/test_timescale.py` → clean

## Verification Results

- `uv run pytest tests/test_timescale.py -k "add_dimension or reorder" -q -o addopts=""` → 22 passed
- `uv run pytest tests/test_timescale.py -q -o addopts=""` → 46 passed
- `uv run pytest tests/test_parity.py -k accessor_parity -q -o addopts=""` → 7 passed (TS-ADV-10)
- `uv run pytest` (full suite) → 1226 passed, coverage 94.96% ≥ 94%

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] test_add_dimension_by_range_succeeds used invalid interval for INTEGER column**
- **Found during:** Task 2 live test execution (first attempt)
- **Issue:** Test used `chunk_interval="10"` (bare integer) and `sensor_id INTEGER` column. PostgreSQL's `by_range` with an `INTERVAL` literal is for timestamp columns; integer columns need a different form. `validate_interval("10")` correctly rejected the bare integer string.
- **Fix:** Changed the range test to use a `ts2 TIMESTAMPTZ` secondary column with `chunk_interval="7 days"` — a valid INTERVAL form for a timestamp column. This matches the by_range live-verified form in RESEARCH.
- **Files modified:** `tests/test_timescale.py`
- **Commit:** `5f222da`

**2. [Rule 1 - Bug] test_add_dimension_by_range_succeeds (second issue): by_range on TIMESTAMPTZ also failed**
- **Found during:** Same test run (second error after first fix)
- **Issue:** Even with `"10 days"` as the interval for `sensor_id INTEGER`, psycopg surfaced `invalid interval type for integer dimension` — TSDB requires integer-typed intervals for integer dimensions. This wrapped as TimescaleError (D-08 working as intended), but the test expected success.
- **Fix:** Changed to use `ts2 TIMESTAMPTZ` column (timestamp range dimension), which accepts `INTERVAL '7 days'` correctly. The live test now verifies that `ts2` appears in `timescaledb_information.dimensions`.
- **Files modified:** `tests/test_timescale.py`
- **Commit:** `5f222da`

### Notes

1. `timescale.py` coverage is 91% (uncovered branches: `partition_type` invalid ValueError in sync, `ExtensionNotAvailable` in sync `add_dimension`, several async `add_dimension` mutual-exclusivity branches, async extension guards). Total coverage 94.96% holds the ≥94% ratchet — no additional tests needed per plan criteria.
2. The 2 pre-existing full-suite failures (`test_async_transaction_fix`, `test_create_spatial_index_name_parameter`) re-occurred as expected — not Phase 30 regressions.
3. `noqa: F401` on `TimescaleError` and `FeatureNotSupported` imports in test_timescale.py were already present from Plan 01; they're still needed because the imports are used in the test bodies after stub replacement.

## Known Stubs

None — all 6 Wave 0 stubs (TestAddDimensionStub × 3, TestAddReorderPolicyStub × 3) were replaced with real test assertions.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| T-30-06 mitigated | pycopg/timescale.py | `validate_identifier(column)` + `validate_identifiers(table, schema)` + `validate_interval(chunk_interval)` + `int(number_partitions)` cast applied before interpolation in `add_dimension` |
| T-30-07 mitigated | pycopg/timescale.py | `validate_identifiers(table, schema, index_name)` applied in `add_reorder_policy` before interpolation |
| T-30-08 mitigated | pycopg/timescale.py | D-08 reshape: raw DB error caught broadly, re-raised as clean `TimescaleError`; `ExtensionNotAvailable` guard raised BEFORE the try block |
| T-30-09 mitigated | pycopg/timescale.py | All 4 async methods explicitly `await` both `has_extension` and `execute`; verified by async mock tests |

## Self-Check: PASSED

- `pycopg/timescale.py` contains `def add_dimension` (sync): FOUND
- `pycopg/timescale.py` contains `def add_reorder_policy` (sync): FOUND
- `pycopg/timescale.py` contains `async def add_dimension`: FOUND
- `pycopg/timescale.py` contains `async def add_reorder_policy`: FOUND
- `tests/test_timescale.py` contains `TestAddDimensionMock`: FOUND
- `tests/test_timescale.py` contains `TestAddReorderPolicyMock`: FOUND
- `tests/test_timescale.py` contains `TestAddDimensionLive`: FOUND
- `tests/test_timescale.py` contains `TestAddReorderPolicyLive`: FOUND
- Commit `5409ce3` exists: FOUND
- Commit `5f222da` exists: FOUND
- Commit `18a75e7` exists: FOUND
