---
phase: 14-spatial-helpers-phase-8-r-alis-e
plan: 04
subsystem: testing
tags: [coverage, pytest, cliquet, interrogate, sphinx]

# Dependency graph
requires:
  - phase: 14-spatial-helpers-phase-8-r-alis-e
    provides: spatial.py builders (14-01) and accessors + tests (14-02)
  - phase: 12-refactoring-brancher-les-abstractions
    provides: cliquet discipline (measure then flip, never freeze an unmet gate)
provides:
  - coverage gate ratcheted 92 -> 94 (measured 94.09% full suite)
  - pycopg/spatial.py at 100% coverage via DB-free routing + columns-validation tests
affects: [15-documentation-release, next-milestone coverage target 95]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Recording fake-db pattern (_RecordingSyncDb/_RecordingAsyncDb) covers accessor routing DB-free"

key-files:
  created: []
  modified:
    - tests/test_spatial.py
    - pyproject.toml

key-decisions:
  - "Gate set to 94 (floor of measured 94.09%), not 95: cliquet rule forbids freezing an unmet gate; 95 milestone target remains deferred (REF-05/D-07 disposition)"

patterns-established: []

requirements-completed: [SPA-06]

# Metrics
duration: 10min
completed: 2026-06-12
---

# Phase 14 Plan 04: Coverage ratchet Summary

**Coverage gate ratcheted 92→94 after DB-free accessor-routing tests brought spatial.py to 100% and the full suite to 94.09%; interrogate 100% and Sphinx -W green**

## Performance

- **Duration:** ~10 min
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments
- Measured full-suite coverage: 92% (91.66% precise) post-14-02 — spatial.py accessor bodies were the gap (81%)
- Added `TestAccessorRouting` (recording fakes prove every sync+async helper's rows and gdf paths, named-binds conversion, geometry column selection) and `TestBuilderColumnsValidation` (residual `columns=` branches) — spatial.py now 100%, suite total 94.09% with 820 passed
- Cliquet applied: `--cov-fail-under` raised 92 → 94 (floor of measured; `uv run pytest` confirms "Required test coverage of 94% reached")
- Documentation gates re-confirmed with the new public surface: `interrogate pycopg` 100% (min 95), `sphinx-build -W --keep-going` succeeds

## Task Commits

1. **Task 1: Measure coverage, fill residual gaps, apply cliquet decision** - `5835dc2` (test)

## Files Created/Modified
- `tests/test_spatial.py` - TestAccessorRouting + TestBuilderColumnsValidation (DB-free, 169 spatial tests total)
- `pyproject.toml` - `--cov-fail-under=94`

## Decisions Made
- **Gate = 94, milestone 95 deferred:** measured TOTAL is 94.09% — below 95, so flipping to 95 would freeze an unmet gate (forbidden by the cliquet rule, REF-05/D-07 precedent). 94 is achieved and monotonic above the previous 92. Remaining uncovered lines are DB-error paths in database.py/async_database.py (90-91%), out of Phase 14 scope.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- The 2 known pre-existing flaky DB tests (`test_async_transaction_fix`, `test_create_spatial_index_name_parameter`) still fail in the local environment — documented in MEMORY.md as not regressions; coverage gate itself passes.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase coverage contract closed; all 4 plans complete — phase ready for verification
- Path to 95: cover residual error branches in database.py/async_database.py (future quality phase)

---
*Phase: 14-spatial-helpers-phase-8-r-alis-e*
*Completed: 2026-06-12*
