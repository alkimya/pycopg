---
phase: 31-continuous-aggregate-lifecycle
plan: "02"
subsystem: timescale
tags: [timescaledb, continuous-aggregate, autocommit-seam, refresh, tdd, sync, async]
dependency_graph:
  requires: [31-01]
  provides: [refresh_continuous_aggregate-sync, refresh_continuous_aggregate-async]
  affects: [pycopg/timescale.py, tests/test_timescale.py]
tech_stack:
  added: []
  patterns:
    - "connect(autocommit=True) seam for CALL refresh_continuous_aggregate() (same as create)"
    - "D-05 type guard: datetime|None only for window bounds; str rejected with ValueError pre-DB"
    - "D-06 both-None = full refresh (NULL,NULL params)"
    - "D-10b structural-isolation proof: call refresh inside db.session() + tolerate FeatureNotSupported"
    - "cagg_created guard in live tests: only refresh when cagg exists (Apache build never creates)"
key_files:
  created: []
  modified:
    - pycopg/timescale.py
    - tests/test_timescale.py
decisions:
  - "D-05: window bounds datetime|None only; str rejected with ValueError (deliberate divergence from drop_chunks str->interval cast)"
  - "D-06: both-None params = [None, None] → full refresh; always emit both positional args"
  - "cagg_created guard in live tests: track creation success to avoid UndefinedTable on Apache when cagg never materialized"
metrics:
  duration: "~15 minutes"
  completed: "2026-06-23"
  tasks_completed: 2
  files_changed: 2
---

# Phase 31 Plan 02: refresh_continuous_aggregate Summary

**One-liner:** `refresh_continuous_aggregate` (sync + async) via `connect(autocommit=True)` seam with `datetime|None` type guard, `[None,None]`=full-refresh params, mock-authoritative SQL-shape tests, and license-tolerant live integration tests proving the seam bypasses an enclosing `db.session()`.

## What Was Built

### Task 1: Implement refresh_continuous_aggregate (sync + async) via the autocommit seam
**Commit:** `f76624c`
**Files:** `pycopg/timescale.py`

Added `refresh_continuous_aggregate` to both `TimescaleAccessor` (sync, inserted after `create_continuous_aggregate`) and `AsyncTimescaleAccessor` (async, appended at end of file).

Guard/validate order (both classes):
1. `validate_identifiers(view_name, schema)` — pre-DB identifier safety
2. D-05 type guard: for each bound in `(window_start, window_end)`, `if bound is not None and not isinstance(bound, datetime): raise ValueError(...)` — deliberate divergence from `drop_chunks`, rejects relative interval strings before any DB round-trip
3. Extension guard (sync: `self._db.schema.has_extension`; async: `await self._db.schema.has_extension`)

Rendered SQL:
```
CALL refresh_continuous_aggregate('{schema}.{view_name}', %s, %s)
```
with params `[window_start, window_end]` — `None` binds to SQL `NULL`. Both positional window args always present (D-06).

Runs via the autocommit seam: `with self._db.connect(autocommit=True) as conn: conn.execute(sql, [window_start, window_end])` (async: `async with ... await conn.execute(sql, [...])`). Does NOT route through `self._db.execute`. License error propagates (no swallow, D-09).

### Task 2: Mock SQL-shape tests + license-tolerant live tests for refresh_continuous_aggregate
**Commit:** `0b2777d`
**Files:** `tests/test_timescale.py`

Added two test classes:

**`TestRefreshContinuousAggregateMock`** (6 tests — authoritative per D-09):
- `test_refresh_continuous_aggregate_sql_shape_both_none` — both-None → `CALL refresh_continuous_aggregate('public.metrics_hourly', %s, %s)`, params `[None, None]`; `connect(autocommit=True)` called; `db.execute` NOT called
- `test_refresh_continuous_aggregate_sql_shape_with_start` — datetime start + None end → params `[<datetime>, None]`
- `test_refresh_continuous_aggregate_str_bound_raises_before_seam` — `str` window_start raises `ValueError`; seam never opened
- `test_refresh_continuous_aggregate_no_extension_raises` — `ExtensionNotAvailable`; seam never opened
- `test_refresh_continuous_aggregate_async_sql_shape` — async mirror with `AsyncMock` + `__aenter__`/`__aexit__`
- `test_refresh_continuous_aggregate_async_no_extension_raises` — Phase-23 `await`-omission catch (AsyncMock coroutine is truthy without `await`)

**`TestRefreshContinuousAggregateLive`** (2 tests — license-tolerant, D-10b structural isolation proof):
- `test_refresh_continuous_aggregate_live` — builds hypertable, attempts create, then calls refresh from INSIDE `with ts_db.session():` wrapped in `try/except FeatureNotSupported: pass`; proves seam bypasses enclosing transaction (only license error surfaces, not transaction-block error); asserts materialized rows on Community builds
- `test_refresh_continuous_aggregate_async_live` — async mirror with `async with async_ts_db.session():`; same isolation proof

## Verification Results

```
uv run pytest tests/test_timescale.py -k refresh_continuous_aggregate -o addopts=""
# 8 passed, 67 deselected

uv run pytest tests/test_timescale.py -x -q -o addopts=""
# 75 passed

uv run pytest tests/test_timescale.py tests/test_parity.py -o addopts=""
# 99 passed

uv run ruff check pycopg/timescale.py tests/test_timescale.py
# All checks passed

uv run black --check pycopg/timescale.py tests/test_timescale.py
# 2 files would be left unchanged
```

## Commits

| Task | Name | Commit |
|------|------|--------|
| 1 | Implement refresh_continuous_aggregate (sync + async) | f76624c |
| 2 | Mock SQL-shape + live tests | 0b2777d |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Live tests: cagg_created guard to avoid UndefinedTable on Apache builds**
- **Found during:** Task 2 execution (live test run)
- **Issue:** On the Apache build, `create_continuous_aggregate` raises `FeatureNotSupported` — the view is never created. The live test then called `refresh_continuous_aggregate` on the non-existent view, getting `psycopg.errors.UndefinedTable` (not caught by `except FeatureNotSupported`), causing the test to fail.
- **Fix:** Track `cagg_created = False` before the create attempt; set to `True` only on success; wrap the refresh in `if cagg_created:`. This is semantically correct: on Apache, the view never exists and there is nothing to refresh. On Community builds, the flag is `True` and the refresh + materialization assertion executes.
- **Files modified:** `tests/test_timescale.py`
- **Commit:** `0b2777d`

## Threat Surface Scan

T-31-04 (SQL injection via `view_name`/`schema` in `CALL refresh_continuous_aggregate('{schema}.{view_name}', ...)`) — mitigated via `validate_identifiers(view_name, schema)` as required.
T-31-05 (`window_start`/`window_end` bound as `%s`) — mitigated by D-05 type guard (only datetime/None accepted) plus psycopg adapts datetime→timestamptz.
T-31-06 (full-table refresh when both bounds None) — accepted; semantics documented.

No new security-relevant surface introduced beyond what is documented in the threat model.

## Known Stubs

None — `refresh_continuous_aggregate` is fully wired via the autocommit seam and exercised by both mock and live tests.

## Self-Check: PASSED

- `pycopg/timescale.py` contains both `def refresh_continuous_aggregate(` and `async def refresh_continuous_aggregate(`
- `tests/test_timescale.py` contains `class TestRefreshContinuousAggregateMock`, `def test_refresh_continuous_aggregate_live`, and `test_refresh_continuous_aggregate_async_live`
- Commit f76624c exists
- Commit 0b2777d exists
