---
phase: 32-query-helpers-parity-verification
plan: 01
subsystem: database
tags: [timescaledb, time_bucket, gapfill, accessor, sync-async-parity, query-helper]

# Dependency graph
requires:
  - phase: 23-schema-spatial-accessor
    provides: SpatialAccessor _check_into / _to_named_binds / _run into= dispatch precedent
  - phase: 31-continuous-aggregate-lifecycle
    provides: TimescaleAccessor / AsyncTimescaleAccessor classes + per-method has_extension guard pattern
provides:
  - Module-level pure builders _build_time_bucket_sql / _build_time_bucket_gapfill_sql in timescale.py
  - Timescale-local _check_into (("df","rows")) + local _to_named_binds copy
  - TimescaleAccessor._run + time_bucket + time_bucket_gapfill (sync, TS-ADV-06/07)
  - AsyncTimescaleAccessor._run + time_bucket + time_bucket_gapfill (async, TS-ADV-10 parity)
affects: [32-02-tests, phase-33-release-v0.8.0]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Query-helper into= routing with df/rows valid set (inverse of spatial's rows/gdf)"
    - "Gapfill double-binds start/finish: [bucket_width, start, finish, start, finish]"
    - "Builder owns fixed 'AS bucket' alias so output column is deterministic"

key-files:
  created: []
  modified:
    - pycopg/timescale.py

key-decisions:
  - "D-01: builder owns fixed AS bucket alias (deterministic output column)"
  - "D-03: timescale-local _check_into valid set is ('df','rows') — inverse of spatial; into='gdf' raises ValueError pre-DB"
  - "D-06: local _to_named_binds copy (no timescale->spatial private-helper import)"
  - "D-09: no Python start<finish guard, no locf-presence heuristic — DB is authority"
  - "D-10: gapfill binds start/finish twice (gapfill args + WHERE range >=/<)"
  - "D-12: no new autocommit branches, zero new dependencies"

patterns-established:
  - "Pure module-level (sql, params) builders shared by sync + async accessor methods"
  - "into='df' -> _to_named_binds + to_dataframe(sql=, params=dict); into='rows' -> execute(sql, params)"
  - "async methods await the has_extension guard, _run, to_dataframe, and execute (no missing-await regression)"

requirements-completed: [TS-ADV-06, TS-ADV-07]

# Metrics
duration: ~25min
completed: 2026-06-23
---

# Phase 32 Plan 01: Query Helpers (time_bucket / time_bucket_gapfill) Summary

**Sync + async `db.timescale.time_bucket` and `time_bucket_gapfill` query helpers with `into="df"/"rows"` routing, module-level pure SQL builders (fixed `AS bucket` alias, gapfill double-binding `start`/`finish`), and full TS-ADV-10 sync/async parity.**

## Performance

- **Duration:** ~25 min
- **Completed:** 2026-06-23
- **Tasks:** 3
- **Files modified:** 1 (`pycopg/timescale.py`)

## Accomplishments
- Added two module-level pure builders `_build_time_bucket_sql` / `_build_time_bucket_gapfill_sql` returning `(sql, params)`, validating identifiers and binding only runtime values as `%s`.
- Added a timescale-local `_check_into` (valid set `("df", "rows")`, the inverse of spatial's) and a local `_to_named_binds` copy (D-03, D-06) — no `timescale → spatial` private-helper import.
- Added sync `TimescaleAccessor._run` + `time_bucket` + `time_bucket_gapfill` (TS-ADV-06/07) — `into="gdf"` raises `ValueError` before any DB call; `into="df"` routes through the named-bind `to_dataframe` path, `into="rows"` through positional `execute`.
- Added async `AsyncTimescaleAccessor._run` + `time_bucket` + `time_bucket_gapfill` with byte-identical signatures, correctly awaiting the `has_extension` guard, `_run`, `to_dataframe`, and `execute` (the recurring Phase-23/30/31 missing-`await` gotcha avoided; AST verify enforces it).
- `test_accessor_parity` stays green (24 passed); `test_timescale.py` green (86 passed); `ruff`/`black --check`/`interrogate` (100%) all clean on `timescale.py`.

## Task Commits

Each task was committed atomically:

1. **Task 1: Module-level builders + local routing helpers** - `7743627` (feat)
2. **Task 2: Sync time_bucket / time_bucket_gapfill on TimescaleAccessor** - `63ac0d2` (feat)
3. **Task 3: Async time_bucket / time_bucket_gapfill on AsyncTimescaleAccessor** - `3ec345b` (feat)

## Files Created/Modified
- `pycopg/timescale.py` - Added `_VALID_INTO`, `_check_into`, `_to_named_binds`, `_build_time_bucket_sql`, `_build_time_bucket_gapfill_sql` (module level) and `_run` + `time_bucket` + `time_bucket_gapfill` on both `TimescaleAccessor` and `AsyncTimescaleAccessor`; added `import pandas as pd` under `TYPE_CHECKING` for the new return annotations.

## Decisions Made
- Used unquoted `pd.DataFrame | list[dict]` return annotations (with `pandas` imported under `TYPE_CHECKING`) rather than string annotations, because `from __future__ import annotations` is active and `ruff` UP037 flags quoted annotations. The `TYPE_CHECKING` import satisfies F821 without a runtime pandas dependency at import time.
- All other choices followed the plan and locked decisions D-01..D-12 exactly.

## Deviations from Plan

None - plan executed exactly as written.

(The only judgement call was the `TYPE_CHECKING` `import pandas as pd` needed to satisfy the unquoted return annotation under ruff/black — explicitly within Claude's discretion per the plan's annotation choice; the plan's `_run` signature in Task 2 read_first used a quoted form, which ruff UP037 rejects under `from __future__ import annotations`. Not a behavioral deviation.)

## Issues Encountered
- Initial `import pandas as pd` added then removed in Task 1 (unused there → ruff F401), re-added in Task 2 where the return annotation actually references it. Resolved by deferring the import to the task that uses it.
- `black` reformatted one over-long `ValueError` line in Task 1 (collapsed to a single line) — applied with `uv run black`, in scope (all new code).

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Production code for both query helpers (sync + async) is complete and parity-clean. Plan 02 delivers the mock SQL-shape unit tests + live integration tests (`time_bucket` asserts real output; `time_bucket_gapfill` uses the Phase-31 license-tolerant `try/except FeatureNotSupported` pattern per the corrected D-08, with the mock shape test authoritative) plus the explicit 9-name parity assertion and the coverage ratchet (≥94%).
- No blockers. Zero new dependencies; no autocommit code added (D-12).

## Self-Check: PASSED

- `32-01-SUMMARY.md` exists on disk.
- Task commits `7743627`, `63ac0d2`, `3ec345b` all present in git log.
- `def time_bucket` present in `pycopg/timescale.py`.

---
*Phase: 32-query-helpers-parity-verification*
*Completed: 2026-06-23*
