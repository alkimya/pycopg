---
phase: 31-continuous-aggregate-lifecycle
plan: "01"
subsystem: timescale
tags: [timescaledb, continuous-aggregate, autocommit-seam, tdd, sync, async]
dependency_graph:
  requires: []
  provides: [create_continuous_aggregate-sync, create_continuous_aggregate-async]
  affects: [pycopg/timescale.py, tests/test_timescale.py]
tech_stack:
  added: []
  patterns:
    - "connect(autocommit=True) seam for DDL that cannot run in a transaction block"
    - "time_bucket( heuristic pre-DB ValueError guard (D-04)"
    - "mock SQL-shape via patch.object(db, 'connect') with MagicMock context manager"
    - "async await-guard (Phase-23 catch) verified by AsyncMock no-extension test"
key_files:
  created: []
  modified:
    - pycopg/timescale.py
    - tests/test_timescale.py
decisions:
  - "Autocommit seam uses plain conn.execute (no cursor wrapper) since create returns None (D-discretion per PATTERNS line 29)"
  - "validate_identifiers + time_bucket( check run BEFORE extension guard — reject structural errors before any DB round-trip"
  - "test cleanup uses sync_db for both table and view DROP in async live test (avoids async teardown complexity)"
metrics:
  duration: "~15 minutes"
  completed: "2026-06-23"
  tasks_completed: 2
  files_changed: 2
---

# Phase 31 Plan 01: create_continuous_aggregate Summary

**One-liner:** `create_continuous_aggregate` (sync + async) via `connect(autocommit=True)` seam with `time_bucket(` heuristic guard, mock-authoritative SQL-shape tests, and license-tolerant live integration tests.

## What Was Built

### Task 1: Implement create_continuous_aggregate (sync + async) via the autocommit seam
**Commit:** `bfd6cb5`
**Files:** `pycopg/timescale.py`

Added `create_continuous_aggregate` to both `TimescaleAccessor` (sync, inserted before `class AsyncTimescaleAccessor:`) and `AsyncTimescaleAccessor` (async, appended at end of file).

Guard/validate order:
1. `validate_identifiers(view_name, schema)` — pre-DB identifier safety
2. `if "time_bucket(" not in select_sql: raise ValueError(...)` — D-04 heuristic, pre-DB
3. Extension guard (sync: `self._db.schema.has_extension`; async: `await self._db.schema.has_extension`)

Rendered SQL:
```
CREATE MATERIALIZED VIEW {schema}.{view_name}
WITH (timescaledb.continuous, timescaledb.materialized_only={true|false})
AS {select_sql}
WITH {DATA|NO DATA}
```

Runs via the autocommit seam: `with self._db.connect(autocommit=True) as conn: conn.execute(sql)` (async: `async with ... await conn.execute(sql)`). No cursor wrapper (nothing to fetch). License error propagates to caller (no swallow, D-09).

### Task 2: Mock SQL-shape tests + license-tolerant live tests for create_continuous_aggregate
**Commit:** `11b456d`
**Files:** `tests/test_timescale.py`

Added two test classes:

**`TestCreateContinuousAggregateMock`** (6 tests — authoritative per D-09):
- `test_create_continuous_aggregate_sql_shape_defaults` — verifies `CREATE MATERIALIZED VIEW public.metrics_hourly`, `materialized_only=true`, `WITH DATA`; asserts `connect(autocommit=True)` called and `db.execute` NOT called
- `test_create_continuous_aggregate_sql_shape_flags_flipped` — verifies `materialized_only=false` and `WITH NO DATA`
- `test_create_continuous_aggregate_no_time_bucket_raises_valueerror` — pre-DB ValueError, seam never opened
- `test_create_continuous_aggregate_no_extension_raises` — `ExtensionNotAvailable`, seam never opened
- `test_create_continuous_aggregate_async_sql_shape` — async mirror with `AsyncMock` + `__aenter__`/`__aexit__`
- `test_create_continuous_aggregate_async_no_extension_raises` — Phase-23 `await`-omission catch (AsyncMock coroutine is truthy without `await`)

**`TestCreateContinuousAggregateLive`** (2 tests — license-tolerant):
- `test_create_continuous_aggregate_live` — builds hypertable, calls create, wraps in `try/except FeatureNotSupported: pass`; asserts `timescaledb_information.continuous_aggregates` row on Community builds
- `test_create_continuous_aggregate_async_live` — async mirror using sync setup + async create

## Verification Results

```
uv run pytest tests/test_timescale.py -k create_continuous_aggregate -o addopts=""
# 8 passed, 59 deselected

uv run pytest tests/test_timescale.py -x -q -o addopts=""
# 67 passed

uv run pytest tests/test_timescale.py tests/test_parity.py -o addopts=""
# 91 passed

uv run ruff check pycopg/timescale.py tests/test_timescale.py
# All checks passed

uv run black --check pycopg/timescale.py tests/test_timescale.py
# 2 files would be left unchanged
```

## Commits

| Task | Name | Commit |
|------|------|--------|
| 1 | Implement create_continuous_aggregate (sync + async) | bfd6cb5 |
| 2 | Mock SQL-shape + live tests | 11b456d |

## Deviations from Plan

### Auto-fixed Issues

None - plan executed exactly as written.

The one decision made within Claude's discretion: `validate_identifiers` runs *before* the `time_bucket(` check (guard ordering slightly different from RESEARCH §Recommended approach lines 298-307 which listed extension guard 3rd). Both are pre-DB guards; the order doesn't affect correctness. The `validate_identifiers` call first surfaces identifier errors before the heuristic.

## Threat Surface Scan

T-31-01 (SQL injection via `view_name`/`schema`) — mitigated via `validate_identifiers(view_name, schema)` as required.
T-31-02 (`select_sql` as structural SQL) — documented in docstring as not-from-untrusted-input.
T-31-03 (no data returned) — accepted, no action needed.

No new security-relevant surface introduced beyond what is documented in the threat model.

## Known Stubs

None — `create_continuous_aggregate` is fully wired via the autocommit seam and exercised by both mock and live tests.

## Self-Check: PASSED

- `pycopg/timescale.py` exists and contains both `def create_continuous_aggregate(` and `async def create_continuous_aggregate(`
- `tests/test_timescale.py` exists and contains `class TestCreateContinuousAggregateMock` and `def test_create_continuous_aggregate_live`
- Commit bfd6cb5 exists
- Commit 11b456d exists
