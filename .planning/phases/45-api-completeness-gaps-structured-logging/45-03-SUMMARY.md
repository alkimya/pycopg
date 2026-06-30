---
phase: 45-api-completeness-gaps-structured-logging
plan: "03"
subsystem: database
tags: [psycopg, typing, health-probe, params, monitoring, pooling, async]

# Dependency graph
requires:
  - phase: 45-01
    provides: "Params alias + _decode_server_version in base.py; log_operation in logging.py; IsolationLevel + Params in __init__.__all__"
  - phase: 45-02
    provides: "savepoint() on Database + AsyncDatabase (insertion point for health())"
provides:
  - "Params annotation on execute/fetch_one/fetch_val/fetch_all/to_dataframe (both sync+async flat classes)"
  - "Database.health() + AsyncDatabase.health(): never-raises dict probe with dotted server_version"
  - "PooledDatabase.health() + AsyncPooledDatabase.health(): same + pool_stats from .stats property"
  - "tests/test_named_params.py: PARAM-01 coverage including RESEARCH Q1 resolution (to_dataframe :name style)"
  - "tests/test_health.py: HEALTH-01 coverage (unit + mocked + live smoke)"
affects: [46-mypy-strict, 47-release-v100]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "health() never-raises pattern: try/connect/SELECT1/except-returns-dict (D-05)"
    - "Params union alias: Sequence[Any] | Mapping[str,Any] | None — single source in base.py"
    - "to_dataframe divergence documented: SQLAlchemy :name vs psycopg %(name)s"
    - "Pooled health() uses self.stats property (NOT self.stats()) — prevents runtime TypeError"

key-files:
  created:
    - tests/test_named_params.py
    - tests/test_health.py
  modified:
    - pycopg/database.py
    - pycopg/async_database.py
    - pycopg/pool.py

key-decisions:
  - "PARAM-01 + D-12: annotation widening only — no translator/parser built; dict %(name)s params work natively via psycopg"
  - "RESEARCH Q1 resolved: to_dataframe uses SQLAlchemy :name style (colon-prefix) via pd.read_sql(text(sql)); divergence documented in docstring + test"
  - "HEALTH-01 + D-05: health() catches ALL exceptions and returns connected=False dict — never re-raises"
  - "D-07: all four classes get health(); pooled classes add pool_stats from self.stats @property"
  - "D-09: log_operation('database.health') wraps every health() body"
  - "T-45-07: error key is str(exc) of psycopg's own message; DSN/password never appended"

patterns-established:
  - "Async mocking pattern: use @asynccontextmanager factories instead of AsyncMock for conn.cursor() — avoids RuntimeWarning: coroutine never awaited"
  - "health() placement: after savepoint() on all four classes"

requirements-completed: [PARAM-01, HEALTH-01]

# Metrics
duration: 9min
completed: "2026-06-30"
---

# Phase 45 Plan 03: PARAM-01 + HEALTH-01 Summary

**Named-params Params annotation widened on 5 methods x 2 classes; never-raises health() added to all four DB/pool classes with dotted server_version and pool_stats**

## Performance

- **Duration:** 9 min
- **Started:** 2026-06-30T18:28:15Z
- **Completed:** 2026-06-30T18:37:50Z
- **Tasks:** 2
- **Files modified:** 5 (database.py, async_database.py, pool.py, tests/test_named_params.py, tests/test_health.py)

## Accomplishments

- Widened `params` from `Sequence | None` / `dict | None` to `Params` on execute, fetch_one, fetch_val, fetch_all, to_dataframe on both `Database` and `AsyncDatabase`; docstrings updated to explain both positional (`%s`) and named (`%(name)s`) forms
- Confirmed RESEARCH Q1 empirically: `to_dataframe` uses SQLAlchemy `:name` colon style (not `%(name)s`); divergence is documented in the docstring and proven by `test_to_dataframe_named_style`
- Added `health()` to `Database`, `AsyncDatabase`, `PooledDatabase`, `AsyncPooledDatabase` — returns `{connected, latency_ms, server_version}` (or `{connected: False, ..., error}`) and NEVER raises; pooled variant adds `pool_stats` from the `self.stats` @property; each wrapped in `log_operation("database.health")`
- `tests/test_named_params.py` (6 tests): export check, dict params live on 4 methods, to_dataframe style, async mirrors
- `tests/test_health.py` (12 tests): version decode, sync/async mocked connected + never-raises, pooled pool_stats, async pooled, two live smokes

## Task Commits

1. **Task 1: Widen params to Params + PARAM-01 tests** - `5797d94` (feat)
2. **Task 2: health() on all four classes + HEALTH-01 tests** - `b2f63f3` (feat)

## Files Created/Modified

- `pycopg/database.py` — added `import time`, `_decode_server_version`, `log_operation` imports; Params widening on 5 methods; `health()` after `savepoint()`
- `pycopg/async_database.py` — same imports + widening; `async def health()` after `savepoint()`
- `pycopg/pool.py` — added `time`, `_decode_server_version`, `log_operation` imports; `health()` on `PooledDatabase` after `stats`; `async def health()` on `AsyncPooledDatabase` after `stats`
- `tests/test_named_params.py` — new: PARAM-01 test suite
- `tests/test_health.py` — new: HEALTH-01 test suite

## Decisions Made

- D-12 HARD LOCK: no `_rewrite_named_params` or translator built; `grep -r "_rewrite_named_params" pycopg/` returns nothing
- to_dataframe divergence (RESEARCH Q1): confirmed `:name` style via live test; documented in docstring; no translation added
- pool_stats uses `self.stats` property access (not `self.stats()` call) — verified by `test_pooled_health_stats_is_property_not_call` using `PropertyMock`
- Async mock pattern: replaced `AsyncMock` connection CMs with `@asynccontextmanager` factory functions to avoid `RuntimeWarning: coroutine never awaited` when `conn.cursor()` returns an async context manager

## Deviations from Plan

None — plan executed exactly as written. The async mock refactoring (using `@asynccontextmanager` factories instead of pure `AsyncMock`) was a test-implementation detail required to get the mocks working correctly, not a plan deviation.

## Issues Encountered

- Async mocks for `AsyncDatabase.health()` and `AsyncPooledDatabase.health()` failed initially because `AsyncMock` objects returned by `conn.cursor.return_value` do not behave as async context managers in the way psycopg expects. Fixed by writing explicit `@asynccontextmanager` factory functions for both `connect()` and `cursor()` call sites. All 12 health tests pass after the fix.

## Threat Surface Scan

No new security-relevant surface beyond what the plan's threat model covers:
- T-45-06 (SQL injection via named params): annotation-only change, psycopg binds values; `grep` confirms no translator
- T-45-07 (error leaks DSN): `error` key is `str(exc)` of psycopg's own exception; no credential appending

## Next Phase Readiness

- Plan 45-04 (structured logging instrumentation on ETL + from_dataframe) can proceed; all substrate (`log_operation`, `Params`, `_decode_server_version`) is in place
- Phase 46 (mypy strict) will need to handle `Params = Sequence[Any] | Mapping[str, Any] | None` — type alias is already correctly placed in `base.py`

---
*Phase: 45-api-completeness-gaps-structured-logging*
*Completed: 2026-06-30*
