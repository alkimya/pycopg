---
phase: 52-spatial-finish
plan: 01
subsystem: database
tags: [postgis, spatial, sql-builder, gridsize]

# Dependency graph
requires: []
provides:
  - "keyword-only gridSize= (float | None = None) on union/difference/intersection, both sync and async accessors"
  - "grid_size threaded through _build_binary_geom_sql + build_union_sql/build_difference_sql/build_intersection_sql"
  - "byte-identical default path (D-03) preserved for gridSize=None"
affects: [52-spatial-finish, spatial.py]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Fixed-precision overlay threading: shared binary-geom builder gains an optional grid_size kwarg, branches on None to preserve byte-identical SQL/params, forwards via grid_size=grid_size in the 3 public builders and grid_size=gridSize at the accessor boundary (camelCase user-facing, snake_case internal)"

key-files:
  created: []
  modified:
    - pycopg/spatial.py
    - tests/test_spatial.py

key-decisions:
  - "D-01: gridSize is keyword-only float | None = None on all three overlay accessors and builders, becomes the 3rd positional %s arg of ST_Union/ST_Difference/ST_Intersection when set"
  - "D-02: pure passthrough, no client-side range guard on gridSize (0 and negative are valid PostGIS values)"
  - "D-03: gridSize=None emits byte-identical SQL + empty params to the pre-change builders; the 3 pre-existing exact-string tests were left unmodified as the regression guard"
  - "D-04: no server-version pre-check; docstrings document PostGIS >=3.1 / GEOS >=3.9, older servers raise a native PostGIS error"

patterns-established:
  - "Accessor-level user-facing camelCase param (gridSize) mapped to builder-level snake_case param (grid_size) via explicit keyword forwarding — first instance of this camelCase/snake_case split in the spatial module"

requirements-completed: [SPAT-F01]

# Metrics
duration: 7min
completed: 2026-07-04
---

# Phase 52 Plan 01: gridSize= Overlay Precision Summary

**Keyword-only `gridSize=` fixed-precision overlay control added to `union`/`difference`/`intersection` (sync + async), threaded through the shared `_build_binary_geom_sql` funnel with a byte-identical `None` default path.**

## Performance

- **Duration:** 7 min
- **Started:** 2026-07-04T21:11:44Z
- **Completed:** 2026-07-04T21:18:59Z
- **Tasks:** 3
- **Files modified:** 2

## Accomplishments
- `_build_binary_geom_sql` and `build_union_sql`/`build_difference_sql`/`build_intersection_sql` gained a keyword-only `grid_size: float | None = None` parameter; the `None` branch emits byte-for-byte identical SQL/params to the shipped builders (D-03), verified by the 3 pre-existing exact-string tests passing unmodified.
- All 6 overlay accessor methods (`SpatialAccessor` and `AsyncSpatialAccessor` × `union`/`difference`/`intersection`) gained `gridSize: float | None = None` on the implementation signature and every `@overload` stub, forwarded to the builders as `grid_size=gridSize`.
- Added grid_size-set unit tests for all 3 builders (asserting the `, %s)` 3rd arg and `params == [0.001]`) plus live `TestIntegration` tests exercising `gridSize=0.001` against `pycopg_test3` for `union` and `difference` (server PostGIS 3.6.4 / GEOS 3.13.1 comfortably exceeds the ≥3.1/≥3.9 gate).

## Task Commits

Each task was committed atomically:

1. **Task 1: Thread grid_size through the overlay builders** - `26b8457` (feat)
2. **Task 2: Add gridSize= to the overlay accessors + @overload stubs** - `6608c3a` (feat)
3. **Task 3: Tests — grid_size unit assertions + live positive-path integration** - `d6e2f9a` (test)

**Plan metadata:** (pending — this commit)

## Files Created/Modified
- `pycopg/spatial.py` - `_build_binary_geom_sql` + 3 public builders gain `grid_size`; 6 accessor methods (sync/async × union/difference/intersection) + 18 `@overload` stubs gain `gridSize=`
- `tests/test_spatial.py` - 3 new grid_size-set builder unit tests + 2 new live `TestIntegration` gridSize tests

## Decisions Made
- Followed 52-CONTEXT.md D-01..D-04 and 52-RESEARCH.md Pattern 1 exactly — no deviation from the documented shape.
- Bound `grid_size` only via `%s`, never f-string-interpolated, per D-02 and the standing security bar.
- Live-tested `gridSize` on `union` and `difference` (plan required "at least one of difference/intersection" beyond `union`); `intersection`'s builder-level unit test + parity coverage still assert correctness for the 3rd overlay method without a redundant live test.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- SPAT-F01 complete. Remaining plans in Phase 52 (SPAT-F02..F06: length/envelope/point_on_surface/is_valid/is_valid_reason + overlaps/touches/crosses/disjoint) are independent additions to `pycopg/spatial.py` and can proceed without dependency on this plan.
- Full suite green: 2026 passed, 2 skipped, coverage 96.65% (gate ≥95%); mypy --strict 0 errors/18 files; `git diff --stat uv.lock pyproject.toml` empty (zero new deps).

---
*Phase: 52-spatial-finish*
*Completed: 2026-07-04*

## Self-Check: PASSED

- FOUND: pycopg/spatial.py
- FOUND: tests/test_spatial.py
- FOUND: .planning/phases/52-spatial-finish/52-01-SUMMARY.md
- FOUND: commit 26b8457 (Task 1)
- FOUND: commit 6608c3a (Task 2)
- FOUND: commit d6e2f9a (Task 3)
