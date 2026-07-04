---
phase: 52-spatial-finish
plan: 02
subsystem: database
tags: [postgis, spatial, sql-builder, measurement, validity]

# Dependency graph
requires: []
provides:
  - "db.spatial.length (ST_Length) — unit=m default (::geography->meters) or unit=srid, sync+async"
  - "db.spatial.is_valid (ST_IsValid boolean scalar) + db.spatial.is_valid_reason (ST_IsValidReason text scalar), sync+async"
  - "build_length_sql / build_is_valid_sql / build_is_valid_reason_sql pure builders"
  - "_SCALAR_HELPERS gains length/is_valid/is_valid_reason (into='gdf' fails fast)"
affects: [52-spatial-finish, spatial.py]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Scalar measurement/validity helper: mirrors build_perimeter_sql exactly (validate_identifiers first, _validate_unit for length only, bare AS label, has_where=False, params=[]) with no unit param on the two validity builders"

key-files:
  created: []
  modified:
    - pycopg/spatial.py
    - tests/test_spatial.py

key-decisions:
  - "D-09: bare operation-name AS labels — length/is_valid/is_valid_reason, no _geom suffix"
  - "D-10: length mirrors area/perimeter exactly (unit=m/srid via _validate_unit); ST_Length returns 0 for non-linear (areal/point) geometries, documented and live-verified"
  - "D-12: is_valid returns boolean scalar, is_valid_reason returns text scalar; both rows-only (into='gdf' raises ValueError via _SCALAR_HELPERS)"
  - "Scalar accessor methods use cast(\"list[dict[str, Any]]\", ...) narrowing, no @overload triplet (Phase 46 scalar-helper convention, matches area/perimeter/centroid)"

patterns-established:
  - "Born-clean scalar helper: no where= parameter, no DeprecationWarning shim, added directly to both SpatialAccessor and AsyncSpatialAccessor with identical kw-only signatures"

requirements-completed: [SPAT-F02, SPAT-F05]

# Metrics
duration: 20min
completed: 2026-07-04
---

# Phase 52 Plan 02: Length + Validity Scalar Helpers Summary

**Added `db.spatial.length` (ST_Length), `db.spatial.is_valid` (ST_IsValid), and `db.spatial.is_valid_reason` (ST_IsValidReason) as born-clean, rows-only scalar helpers on both `SpatialAccessor` and `AsyncSpatialAccessor`, completing the area/perimeter measurement family and complementing `make_valid`.**

## Performance

- **Duration:** 20 min
- **Started:** 2026-07-04T21:22:00Z (approx.)
- **Completed:** 2026-07-04
- **Tasks:** 3
- **Files modified:** 2

## Accomplishments
- Added `build_length_sql`, `build_is_valid_sql`, `build_is_valid_reason_sql` pure module-level builders to `pycopg/spatial.py`, mirroring `build_perimeter_sql`'s exact shape: `validate_identifiers` first, `_validate_unit` reused for `length` only, bare `AS length`/`AS is_valid`/`AS is_valid_reason` labels (D-09), `has_where=False`, `params == []`.
- Registered all 3 new names in `_SCALAR_HELPERS` so `into="gdf"` fails fast with a clean `ValueError` instead of a confusing deep geopandas error (D-12, RESEARCH Pitfall 2).
- Added `length`, `is_valid`, `is_valid_reason` accessor methods to both `SpatialAccessor` and `AsyncSpatialAccessor` — born-clean (no `where=`, no `DeprecationWarning` shim), rows-only via `cast("list[dict[str, Any]]", ...)` (no `@overload`, matching the `area`/`perimeter`/`centroid` scalar-helper convention).
- Added builder-level exact-string tests (unit=m/srid, tail clauses, injection on table/geom/columns) for all 3 builders; extended `_HELPER_CALLS` for routing coverage; extended `TestGuard`'s scalar-gdf-rejection parametrize (sync, and a new parametrized async variant) to cover all 7 scalar helpers; added 4 live `TestIntegration` tests — `ST_Length` on a polygon returns 0 (D-10), on a LineString returns a positive meter value, `is_valid` returns a Python bool, `is_valid_reason` returns descriptive text for a bowtie polygon.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add 3 scalar builders + register in _SCALAR_HELPERS** - `766f3fe` (feat)
2. **Task 2: Add 3 scalar accessor methods, born-clean, both classes** - `9248fb5` (feat)
3. **Task 3: Tests — builder strings, routing, gdf-rejection guard, injection, live polygon=0** - `001016e` (test)

**Plan metadata:** (pending — this commit)

## Files Created/Modified
- `pycopg/spatial.py` - 3 new pure builders (`build_length_sql`/`build_is_valid_sql`/`build_is_valid_reason_sql`), `_SCALAR_HELPERS` frozenset gains 3 entries, 3 new sync + 3 new async accessor methods (6 total)
- `tests/test_spatial.py` - 15 new `TestBuilders` tests, `_HELPER_CALLS` +3 entries, `TestGuard` parametrize extended (sync +3, new parametrized async test), 4 new live `TestIntegration` tests

## Decisions Made
- Followed 52-CONTEXT.md D-09/D-10/D-12 and 52-RESEARCH.md Pattern 2/Pattern 4 exactly — no deviation from the documented shape.
- Kept the original hardcoded `test_async_scalar_helper_rejects_gdf` (area-only) test intact and added a new parametrized async test (`test_async_scalar_helper_rejects_gdf_parametrized`) covering all 7 scalar helpers, rather than rewriting the existing test in place — avoids risk of losing test-name history/traceability while still satisfying "and the async equivalent" from the plan action.
- `length`/`is_valid`/`is_valid_reason` were NOT added to `_GDF_CALLS` (scalar, no geometry column) — confirmed correct per the plan's explicit instruction and RESEARCH Pitfall 2.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- SPAT-F02 + SPAT-F05 complete. Remaining Phase 52 plans (SPAT-F03/F04/F06: envelope/point_on_surface + overlaps/touches/crosses/disjoint) are independent additions to `pycopg/spatial.py` and can proceed without dependency on this plan.
- Full suite green: 2064 passed, 2 skipped, coverage 96.69% (gate ≥95%); mypy --strict 0 errors/18 files; interrogate 100%; `git diff --stat uv.lock pyproject.toml` empty (zero new deps).

---
*Phase: 52-spatial-finish*
*Completed: 2026-07-04*

## Self-Check: PASSED

- FOUND: pycopg/spatial.py
- FOUND: tests/test_spatial.py
- FOUND: .planning/phases/52-spatial-finish/52-02-SUMMARY.md
- FOUND: commit 766f3fe (Task 1)
- FOUND: commit 9248fb5 (Task 2)
- FOUND: commit 001016e (Task 3)
