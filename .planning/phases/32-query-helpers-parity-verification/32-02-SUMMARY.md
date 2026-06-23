---
phase: 32-query-helpers-parity-verification
plan: 02
subsystem: testing
tags: [timescaledb, time_bucket, gapfill, mock-tests, live-integration, sync-async-parity]

# Dependency graph
requires:
  - phase: 32-query-helpers-parity-verification (plan 01)
    provides: TimescaleAccessor/AsyncTimescaleAccessor time_bucket + time_bucket_gapfill (the production code under test)
  - phase: 31-continuous-aggregate-lifecycle
    provides: license-tolerant try/except FeatureNotSupported live-test pattern (test_create_continuous_aggregate_live)
provides:
  - Mock SQL-shape unit tests (TestTimeBucketMock / TestTimeBucketGapfillMock, sync + async)
  - Live integration tests (TestTimeBucketLive REAL output; TestTimeBucketGapfillLive license-tolerant)
  - Explicit 9-name v0.8.0 timescale surface assertion (test_timescale_v080_surface)
affects: [phase-33-release-v0.8.0]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Two-layer test pattern: mock SQL-shape (authoritative for shape) + live integration (REAL output where Apache-free, license-tolerant where TSL-gated)"
    - "Named-frozenset surface assertion as a loud guard against silently dropped/renamed accessor methods"

key-files:
  created: []
  modified:
    - tests/test_timescale.py
    - tests/test_parity.py

key-decisions:
  - "D-08 (corrected): time_bucket asserts REAL output (Apache-free); time_bucket_gapfill uses try/except FeatureNotSupported (TSL-gated on local Apache 2.28)"
  - "D-10: gapfill mock asserts the double-bind params == [bucket_width, start, finish, start, finish] with datetime start/finish"
  - "D-07: async mock tests assert has_extension was AWAITED (assert_awaited_once_with)"
  - "D-03: into='gdf' raises ValueError before any DB call — neither execute nor to_dataframe touched"
  - "D-11: explicit 9-name frozenset subset check on both classes; ACCESSOR_PAIRS unchanged; no per-method signature parity"

patterns-established:
  - "Mock SchemaAccessor (MagicMock spec) assigned to db._schema with has_extension->True; db.execute / db.to_dataframe mocked to read call_args"
  - "Live gapfill tests build a hypertable with a deliberate gap and assert at least one NULL aggregate inside try, tolerating the Apache license gate in except"

requirements-completed: [TS-ADV-06, TS-ADV-07, TS-ADV-10]

# Metrics
duration: ~20min
completed: 2026-06-23
---

# Phase 32 Plan 02: Query Helpers & Parity Verification Summary

**Two-layer test coverage (mock SQL-shape + live integration) for `time_bucket` / `time_bucket_gapfill` plus an explicit 9-name v0.8.0 timescale surface parity assertion, holding the coverage ratchet at 95.11%.**

## Performance

- **Duration:** ~20 min
- **Completed:** 2026-06-23
- **Tasks:** 3
- **Files modified:** 2 (`tests/test_timescale.py`, `tests/test_parity.py`)

## Accomplishments
- Added `TestTimeBucketMock` and `TestTimeBucketGapfillMock` (15 mock tests, sync + async) proving the fixed `AS bucket` alias, named-bind `to_dataframe` df-routing (`:p0`, not `%s`), positional-`execute` rows-routing, the gapfill double-bind (`[bucket_width, start, finish, start, finish]`, D-10), the `into="gdf"` ValueError before any DB call (D-03), the extension guard, and the awaited async `has_extension` (D-07).
- Added `TestTimeBucketLive` (REAL output — Apache-free, D-08) and `TestTimeBucketGapfillLive` (license-tolerant `try/except FeatureNotSupported`, D-08 correction) with sync + async twins, passing Python `datetime` `start`/`finish`, each dropping its table in `finally`.
- Added `test_timescale_v080_surface` to `tests/test_parity.py` asserting the exact 9-name v0.8.0 frozenset is a subset of both `TimescaleAccessor` and `AsyncTimescaleAccessor` public members (TS-ADV-10, D-11) — `ACCESSOR_PAIRS` untouched, `test_accessor_parity` unmodified.
- Full suite: 1288 passed, coverage 95.11% (≥94% ratchet held); the only 2 failures are the named pre-existing flaky DB tests (`test_async_transaction_fix`, `test_create_spatial_index_name_parameter`), which also fail on targeted re-run and touch none of the files changed here.

## Task Commits

Each task was committed atomically:

1. **Task 1: Mock SQL-shape unit tests for time_bucket / time_bucket_gapfill** - `b2acb16` (test)
2. **Task 2: Live integration tests — time_bucket REAL, gapfill license-tolerant** - `72ef0fe` (test)
3. **Task 3: Explicit 9-name parity assertion + full-suite ratchet gate** - `5a04e1d` (test)

## Files Created/Modified
- `tests/test_timescale.py` - Added `TestTimeBucketMock`, `TestTimeBucketGapfillMock` (mock SQL-shape, sync + async), `TestTimeBucketLive` (REAL output), `TestTimeBucketGapfillLive` (license-tolerant). +550 lines.
- `tests/test_parity.py` - Added `test_timescale_v080_surface` (explicit 9-name v0.8.0 surface assertion).

## Decisions Made
- Followed the plan and locked decisions D-01..D-12 exactly, including the planner's corrected D-08 (`time_bucket` REAL / `time_bucket_gapfill` license-tolerant).
- Left the `# noqa: F401` on the `FeatureNotSupported` import untouched: RUF100 (unused-noqa) is not enabled in this project's ruff config, so the now-redundant noqa is harmless and removing it would touch an unrelated import line — out of this plan's scope.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- The targeted append anchor (`finally: ... sync_db.execute(... DROP TABLE ...)`) appeared 3 times in `test_timescale.py`, so a unique-match Edit was not possible; appended the new test classes to end-of-file via a small Python script writing in `"a"` mode (test-only content, no existing lines modified). Verified by running the new tests immediately after.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- TS-ADV-06, TS-ADV-07, TS-ADV-10 are now closed with executable proof (mock shape + live behavior + parity). This is the last v0.8.0 *feature* phase; Phase 33 is the release phase (REL-08).
- No blockers. The 2 named pre-existing flaky DB tests remain (documented, not Phase-32 regressions). Zero new dependencies; no autocommit branches added (D-12).

## Self-Check: PASSED

---
*Phase: 32-query-helpers-parity-verification*
*Completed: 2026-06-23*
