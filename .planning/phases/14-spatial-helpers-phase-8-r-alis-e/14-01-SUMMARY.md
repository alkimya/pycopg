---
phase: 14-spatial-helpers-phase-8-r-alis-e
plan: 01
subsystem: database
tags: [postgis, spatial, sql-builders, psycopg, security]

# Dependency graph
requires:
  - phase: 10-securite-residuelle-robustesse
    provides: validate_identifiers + %s parameterization discipline for all generated SQL
  - phase: 12-refactoring-brancher-les-abstractions
    provides: module-level pure builder pattern (build_pg_dump_cmd) shared sync/async
  - phase: 13-qualite-documentaire
    provides: numpydoc-shallow docstring convention + interrogate >= 95 gate
provides:
  - pycopg/spatial.py with _resolve_geometry (4 input forms, D-05) and 11 pure SQL builders
  - tests/test_spatial.py TestGeometryResolver + TestBuilders (59 DB-free tests, 97% module coverage)
affects: [14-02 accessors, 14-04 coverage ratchet, ETL milestone (into="query" foundation)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure spatial builders return (sql, params); identifiers validated first line, values always %s"
    - "_REF_SENTINEL sentinel: _resolve_geometry returns ('__ref__', [ref_table, ref_col]); caller builds EXISTS (D-08)"

key-files:
  created:
    - pycopg/spatial.py
    - tests/test_spatial.py
  modified: []

key-decisions:
  - "ref= input form supported only on predicate helpers (contains, intersects, dwithin); distance/nearest omit it — EXISTS semantics define no scalar distance or KNN target"
  - "nearest uses ::geography <-> casts (meters, D-09-consistent); GiST index note in docstring"
  - "unit= validated via _validate_unit raising ValueError for anything outside {'m','srid'}"

patterns-established:
  - "Spatial builder signature: (table, geom='geometry', schema='public', *, <inputs>, columns=None, where=None, order_by=None, limit=None) -> tuple[str, list]"
  - "_append_tail(sql, where, order_by, limit, has_where) mirrors _build_select_sql clause convention"

requirements-completed: [SPA-02, SPA-03, SPA-04, SPA-06]

# Metrics
duration: 12min
completed: 2026-06-12
---

# Phase 14 Plan 01: Pure spatial SQL builders Summary

**Geometry resolver (point/wkt/geojson/ref, D-05) + 11 pure PostGIS SQL builders in pycopg/spatial.py with 59 exact-SQL DB-free tests at 97% module coverage**

## Performance

- **Duration:** ~12 min
- **Tasks:** 2
- **Files modified:** 2 (both created)

## Accomplishments
- `_resolve_geometry` handles all 4 D-05 input forms with strict mutual exclusivity (`ValueError` otherwise); `ref=` returns the documented `__ref__` sentinel consumed by predicate builders as an EXISTS subquery (D-08)
- 11 builders (`contains`, `within`, `intersects`, `dwithin`, `distance`, `nearest`, `area`, `perimeter`, `centroid`, `buffer`, `transform`) — every identifier through `validate_identifiers` first, every value as `%s`, SRID only via `int()` coercion
- `unit="m"`/`unit="srid"` branches per D-09/D-10 (geography cast on metric helpers only); `within` keeps its dedicated two-table JOIN signature (Pitfall 6)
- 59 DB-free tests with exact SQL string + params assertions covering every resolver and builder branch; 97% line coverage on `pycopg/spatial.py`; ruff, black, interrogate 100% all green

## Task Commits

1. **Task 1: Geometry resolver + all pure SQL builders** - `d8a5609` (feat)
2. **Task 2: DB-free unit tests for resolver and all builders** - `2d9c3cb` (test, includes black reformat of both files)

## Files Created/Modified
- `pycopg/spatial.py` - Resolver + 11 pure builders, numpydoc-shallow docstrings, module docstring with security invariants
- `tests/test_spatial.py` - TestGeometryResolver (9 tests) + TestBuilders (50 tests)

## Decisions Made
- `ref=` omitted from `build_distance_sql` / `build_nearest_sql` signatures: D-08 EXISTS semantics yield a boolean predicate, not a scalar distance or KNN ordering target. Documented in both docstrings. Predicate helpers (contains, intersects, dwithin) fully support it.
- `nearest` KNN uses `::geography <->` casts for metric ordering (research recommendation), with GiST index note in the docstring.
- Invalid `unit=` raises `ValueError("unit must be 'm' or 'srid', got ...")` (Claude's discretion per D-09).

## Deviations from Plan

None - plan executed exactly as written. (The `ref=` omission on distance/nearest is within the plan's stated discretion on exact builder signatures.)

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Builders ready for byte-identical consumption by `SpatialAccessor` / `AsyncSpatialAccessor` (Plan 14-02)
- Remaining uncovered 4 lines in spatial.py are columns-validation branches reachable from accessor-level tests

---
*Phase: 14-spatial-helpers-phase-8-r-alis-e*
*Completed: 2026-06-12*
