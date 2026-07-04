---
phase: 52-spatial-finish
plan: 03
subsystem: database
tags: [postgis, spatial, sql-builder, geometry]

# Dependency graph
requires: []
provides:
  - "db.spatial.envelope (ST_Envelope) — geometry bounding-box column, sync+async, into=rows/gdf"
  - "db.spatial.point_on_surface (ST_PointOnSurface) — geometry point column, sync+async, into=rows/gdf"
  - "build_envelope_sql / build_point_on_surface_sql pure builders"
affects: [52-spatial-finish, spatial.py]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Geometry-returning helper: mirrors build_convex_hull_sql exactly (validate_identifiers first, bare AS label, has_where=False, params=[]), full @overload triplet on the accessor (Literal['rows']->list[dict], Literal['gdf']->GeoDataFrame, str-> union), gdf path passes the result alias as _run's geometry_column"

key-files:
  created: []
  modified:
    - pycopg/spatial.py
    - tests/test_spatial.py

key-decisions:
  - "D-05: point_on_surface returns a real GEOMETRY point column (NOT centroid's scalar x/y shape) — guaranteed-inside representative point for labels/markers/mapping, preserves SRID"
  - "D-09: bare operation-name AS labels — envelope, point_on_surface, no _geom suffix"
  - "D-11: envelope returns a geometry column, valid for into='gdf' like the other geometry-returning helpers (NOT in _SCALAR_HELPERS)"

patterns-established:
  - "Born-clean geometry helper: no where= parameter, full @overload triplet, both SpatialAccessor and AsyncSpatialAccessor gain identical kw-only signatures; async mirror calls await self._check_postgis() first-call guard"

requirements-completed: [SPAT-F03, SPAT-F04]

# Metrics
duration: 25min
completed: 2026-07-04
---

# Phase 52 Plan 03: Envelope + Point-on-Surface Geometry Helpers Summary

**Added `db.spatial.envelope` (ST_Envelope) and `db.spatial.point_on_surface` (ST_PointOnSurface) as born-clean, geometry-returning helpers on both `SpatialAccessor` and `AsyncSpatialAccessor`, completing the geometry-output family alongside `convex_hull`/`buffer`/`make_valid` and deliberately NOT mirroring `centroid`'s scalar x/y shape.**

## Performance

- **Duration:** 25 min
- **Started:** 2026-07-04 (approx.)
- **Completed:** 2026-07-04
- **Tasks:** 3
- **Files modified:** 2

## Accomplishments
- Added `build_envelope_sql` and `build_point_on_surface_sql` pure module-level builders to `pycopg/spatial.py`, mirroring `build_convex_hull_sql`'s exact shape: `validate_identifiers` first, bare `AS envelope`/`AS point_on_surface` labels (D-09), `has_where=False`, `params == []`. Placed directly after `build_convex_hull_sql` in the geometry-helper group. Neither name was added to `_SCALAR_HELPERS` (they return geometry, valid for `into="gdf"`).
- Added `envelope` and `point_on_surface` accessor methods to both `SpatialAccessor` and `AsyncSpatialAccessor`, each with the full `@overload` triplet (`Literal["rows"]` → `list[dict]`, `Literal["gdf"]` → `gpd.GeoDataFrame`, `str` → union), mirroring `convex_hull` exactly — born-clean (no `where=`), gdf path passes the result alias (`"envelope"`/`"point_on_surface"`) as `_run`'s `geometry_column`. Async mirrors call `await self._check_postgis()` first (parity with `convex_hull`/`make_valid` async siblings).
- Added builder-level exact-string tests (tail clauses, injection on table/schema/geom/columns) for both builders; extended `_HELPER_CALLS`/`_GDF_CALLS` so `TestAccessorRouting` auto-covers sync/async rows+gdf routing; added 3 live `TestIntegration` tests: `envelope(into="gdf")` returns the correct bounding-box polygon (shapely `box()` equality check), `point_on_surface` returns a real geometry value (not centroid's `centroid_x`/`centroid_y` scalar keys) on the rows path, and `point_on_surface(into="gdf")` returns a `Point` geometry guaranteed to lie on the polygon.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add 2 geometry builders envelope + point_on_surface (D-05/D-09/D-11)** - `98c9489` (feat)
2. **Task 2: Add envelope + point_on_surface accessors with @overload triplets, both classes** - `40f9c1d` (feat)
3. **Task 3: Tests — builder strings, rows+gdf routing, injection, live geometry proof** - `177234d` (test)

**Plan metadata:** (pending — this commit)

## Files Created/Modified
- `pycopg/spatial.py` - 2 new pure builders (`build_envelope_sql`/`build_point_on_surface_sql`), 2 new sync + 2 new async accessor methods (4 total) each with a full `@overload` triplet
- `tests/test_spatial.py` - 14 new `TestBuilders` tests, `_HELPER_CALLS`/`_GDF_CALLS` +2 entries each, 3 new live `TestIntegration` tests

## Decisions Made
- Followed 52-CONTEXT.md D-05/D-09/D-11 and 52-RESEARCH.md Pattern 3 exactly — no deviation from the documented shape.
- Placed the new builders immediately after `build_convex_hull_sql` (the geometry-helper group) rather than near the plan-02 scalar helpers, since they are geometry-returning siblings of `convex_hull`/`make_valid`, not scalar siblings of `length`/`is_valid`.
- Live gdf test for `envelope` asserts exact bounding-box geometry equality via `shapely.geometry.box(...)` (already a transitive geopandas dependency, no new runtime dependency) rather than just checking non-null, giving a stronger D-11 proof.
- `test_point_on_surface_returns_geometry_not_scalar` explicitly asserts the centroid columns are `centroid_x`/`centroid_y` (verified against `build_centroid_sql`'s real column names) and that `point_on_surface` is absent from the centroid row and vice versa — a direct, live contrast proof of D-05.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None. One self-correction during test authoring: `gdf.iloc[0].geometry` does not work when the GeoDataFrame's active geometry column is named `envelope`/`point_on_surface` rather than `geometry` (pandas `Series.__getattr__` for a non-existent `geometry` attribute) — fixed by indexing `gdf.iloc[0]["envelope"]` / `gdf.iloc[0]["point_on_surface"]` directly. Caught and fixed before commit (task-1 auto-fix attempt, within scope).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- SPAT-F03 + SPAT-F04 complete. Remaining Phase 52 work (SPAT-F06: overlaps/touches/crosses/disjoint DE-9IM predicates) is an independent addition to `pycopg/spatial.py` and can proceed without dependency on this plan.
- Full suite green: 2087 passed, 2 skipped, coverage 96.71% (gate ≥95%); mypy --strict 0 errors/18 files; `git diff --stat uv.lock pyproject.toml` empty (zero new deps).

---
*Phase: 52-spatial-finish*
*Completed: 2026-07-04*

## Self-Check: PASSED

- FOUND: pycopg/spatial.py
- FOUND: tests/test_spatial.py
- FOUND: .planning/phases/52-spatial-finish/52-03-SUMMARY.md
- FOUND: commit 98c9489 (Task 1)
- FOUND: commit 40f9c1d (Task 2)
- FOUND: commit 177234d (Task 3)
