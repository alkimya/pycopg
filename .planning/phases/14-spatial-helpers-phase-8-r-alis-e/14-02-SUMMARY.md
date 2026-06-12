---
phase: 14-spatial-helpers-phase-8-r-alis-e
plan: 02
subsystem: database
tags: [postgis, spatial, accessor, async, geopandas, parity]

# Dependency graph
requires:
  - phase: 14-spatial-helpers-phase-8-r-alis-e
    provides: pure SQL builders + _resolve_geometry from plan 14-01
  - phase: 11-parite-sync-async
    provides: test_parity full-surface introspection + async run_sync geopandas pattern
provides:
  - SpatialAccessor (sync, guard at construction) and AsyncSpatialAccessor (async, lazy guard) in pycopg/spatial.py
  - lazy `spatial` property on Database and AsyncDatabase (deferred imports, no circular import)
  - SpatialAccessor/AsyncSpatialAccessor exported from pycopg top level
  - TestGuard (mocked) + TestIntegration (real PostGIS) in tests/test_spatial.py
affects: [14-04 coverage ratchet, 15-documentation-release]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "into= routing: 'rows' -> execute; 'gdf' -> to_geodataframe via %s->named-binds adapter (_to_named_binds)"
    - "Async PostGIS guard: lazy _postgis_ok flag checked at every method entry (init cannot await)"

key-files:
  created: []
  modified:
    - pycopg/spatial.py
    - pycopg/database.py
    - pycopg/async_database.py
    - pycopg/__init__.py
    - tests/test_spatial.py

key-decisions:
  - "gdf path adaptation: builders emit psycopg %s + positional list, but to_geodataframe wraps SQL in SQLAlchemy text() which needs :name binds — added _to_named_binds() converting %s -> :p0..:pN with a params dict; proven by buffer/transform into='gdf' integration tests"
  - "Integration tests use regular uniquely-named tables (not TEMP) because each execute() opens a fresh connection and builders qualify schema.table"

patterns-established:
  - "Accessor method shape: _check_into first (before any SQL), build_*_sql, then _run(sql, params, into, geometry_column)"

requirements-completed: [SPA-02, SPA-04, SPA-05, SPA-06]

# Metrics
duration: 25min
completed: 2026-06-12
---

# Phase 14 Plan 02: Spatial accessors + parity Summary

**SpatialAccessor/AsyncSpatialAccessor with 11 helpers each, lazy db.spatial properties, into= routing with %s→named-binds gdf adapter, and green guard + PostGIS integration + parity tests (92 passed)**

## Performance

- **Duration:** ~25 min
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments
- `SpatialAccessor` (PostGIS guard at construction) and `AsyncSpatialAccessor` (lazy `_postgis_ok` guard at first call) share the 14-01 builders byte-identically; public method sets verified identical (11 helpers each)
- Lazy `spatial` property on both `Database` and `AsyncDatabase` with deferred imports; `SpatialAccessor`/`AsyncSpatialAccessor` exported from `pycopg`; parity introspection shows sync-only = `{'engine'}` exactly
- `into=` routing per D-01/D-02: scalar helpers (area, perimeter, distance, centroid) reject `into="gdf"` before any SQL runs; geometry helpers deliver real GeoDataFrames
- 33 new tests: TestGuard (sync construction guard, async first-call guard, scalar-gdf rejection sync+async, invalid into=) + TestIntegration on live PostGIS (contains, dwithin meters, nearest KNN order, area scalar, buffer→gdf, transform→EPSG:3857 crs, distance-gdf ValueError, async contains end-to-end)

## Task Commits

1. **Task 1: SpatialAccessor + AsyncSpatialAccessor classes** - `e06ffea` (feat)
2. **Task 2: Lazy spatial property + exports** - `4e3667d` (feat)
3. **Task 3: Guard + PostGIS integration tests** - `ebf7375` (test)

## Files Created/Modified
- `pycopg/spatial.py` - Accessor classes + `_check_into`/`_to_named_binds` helpers appended to the pure builders
- `pycopg/database.py` - `_spatial` field + lazy `spatial` property (deferred import)
- `pycopg/async_database.py` - `_spatial` field + lazy `spatial` property (deferred import)
- `pycopg/__init__.py` - Spatial accessor exports + `__all__` entries
- `tests/test_spatial.py` - TestGuard + TestIntegration classes

## Decisions Made
- **gdf params adaptation (anticipated by the plan):** `to_geodataframe` passes SQL through SQLAlchemy `text()`, which requires `:name` binds — incompatible with the builders' psycopg `%s` + positional list. Added `_to_named_binds()` rewriting `%s` → `:p0..:pN` with a matching dict, used only on the gdf path. Proven by `buffer`/`transform` `into="gdf"` integration tests returning real GeoDataFrames (transform's gdf carries EPSG:3857).
- Integration fixtures use regular uniquely-named public-schema tables with try/finally drop (TEMP tables don't survive pycopg's per-call connections and aren't in the `public` schema the builders qualify).

## Deviations from Plan

None - plan executed exactly as written (the gdf adaptation was explicitly delegated to execution by the plan).

## Issues Encountered
- Pre-existing repo-wide black/ruff non-compliance (newer tool versions flag ~82 issues in files untouched by this phase). All phase-14 files pass ruff/black/interrogate cleanly; pre-existing issues left alone per scope boundary.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Full spatial surface live on both sync and async sides; ready for 14-04 coverage measurement and ratchet decision

---
*Phase: 14-spatial-helpers-phase-8-r-alis-e*
*Completed: 2026-06-12*
