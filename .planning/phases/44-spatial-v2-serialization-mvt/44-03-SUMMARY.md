---
phase: 44-spatial-v2-serialization-mvt
plan: 03
subsystem: database
tags: [postgis, spatial, geojson, wkt, mvt, parity, documentation, pycopg]

# Dependency graph
requires:
  - phase: 44-01
    provides: "as_geojson + as_text on both accessors, _SCALAR_HELPERS extension"
  - phase: 44-02
    provides: "as_mvt on both accessors, _run_mvt/_arun_mvt bytea runners"
  - phase: 43-spatial-v2-spatial-aggregates
    provides: "test_spatial_aggregates_surface template for named frozenset surface test"
provides:
  - "test_spatial_serialization_surface (named frozenset surface guard for as_geojson/as_text/as_mvt)"
  - "docs/api-reference.md: 3 new rows with born-clean filter= signatures"
  - "docs/stability.md: 3 stable-tier rows + PostGIS-3.0 ST_AsMVT note + GeoJSON/WKT/MVT behaviour notes"
  - "docs/spatial.md: as_geojson/as_text/as_mvt usage examples + tile-endpoint pattern"
  - "README.md: db.spatial.* count 22→25; 3 new methods in example list"
affects:
  - "SPAT2-13 finalized: full P42+P43+P44 surface asserted at name-level and kind-level parity"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Named frozenset surface-test pattern: clone test_spatial_aggregates_surface, change frozenset + docstring"
    - "D-09 born-clean docs: no where= on any P44 method row in any doc surface"
    - "Tile-endpoint recipe: as_mvt bytes + Content-Type application/vnd.mapbox-vector-tile"

key-files:
  created: []
  modified:
    - "tests/test_parity.py"
    - "docs/api-reference.md"
    - "docs/stability.md"
    - "docs/spatial.md"
    - "README.md"

key-decisions:
  - "SPAT2-13 finalized: test_spatial_serialization_surface + test_accessor_parity + test_accessor_parameter_kind_parity together assert the full P42+P43+P44 spatial v2 surface on both accessors"
  - "D-09 confirmed across all doc surfaces: zero new where= rows for P44 methods"
  - "PostGIS 3.0 floor documented for ST_AsMVT/ST_AsMVTGeom/ST_TileEnvelope (not gated at runtime since floor already 3.0)"

requirements-completed: [SPAT2-13]

# Metrics
duration: 4min
completed: 2026-06-30
---

# Phase 44 Plan 03: Parity Test + Documentation Summary

**SPAT2-13 finalized: test_spatial_serialization_surface named frozenset guard + four doc surfaces updated with born-clean filter= for as_geojson/as_text/as_mvt; full suite 1690 tests @ 96.18% coverage**

## Performance

- **Duration:** 4 min
- **Started:** 2026-06-30T07:05:05Z
- **Completed:** 2026-06-30T07:09:XX Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- `test_spatial_serialization_surface` added to `tests/test_parity.py` immediately after `test_spatial_aggregates_surface`: a `frozenset({"as_geojson", "as_text", "as_mvt"})` checked as a subset of the public members of BOTH `SpatialAccessor` and `AsyncSpatialAccessor`; docstring explains it is the SPAT2-13 full-surface acceptance complement to `test_accessor_parity` and `test_accessor_parameter_kind_parity`; `ACCESSOR_PAIRS` unchanged
- `docs/api-reference.md`: 3 new spatial rows (`as_geojson`, `as_text`, `as_mvt`) with born-clean `filter=` (no `where=`); `as_mvt` returns `bytes` with no `into=`; signatures match D-01/D-06/D-07/D-09
- `docs/stability.md`: 3 stable-tier rows (positional `table`; all other params keyword-only); note block covering: D-06 GeoJSON 6-digit vs D-07 WKT full-precision asymmetry; D-05 empty-tile `b""` contract and D-04 SRID rescue; PostGIS ≥ 3.0 requirement for `ST_AsMVT`/`ST_AsMVTGeom`/`ST_TileEnvelope` (documented, not gated)
- `docs/spatial.md`: new "Serialization Helpers" section with `as_geojson`/`as_text` examples + `as_mvt` tile-endpoint pattern (returning `bytes` with `Content-Type: application/vnd.mapbox-vector-tile`); `srid=` rescue example for stored-SRID mismatch
- `README.md`: `db.spatial.*` count corrected `22→25`; `as_geojson`, `as_text`, `as_mvt` added to example method list
- Full suite: 1690 passed, 2 skipped — 96.18% coverage, gate ≥95% held; lint (`ruff`) and format (`black --check`) clean

## Task Commits

1. **Task 1: test_spatial_serialization_surface + full-surface parity assertion** - `67766a7` (test)
2. **Task 2: docs (api-reference, stability, spatial guide, README count) + full-suite coverage gate** - `d7d0430` (docs)

## Files Created/Modified

- `/home/loc/workspace/pycopg/tests/test_parity.py` - Added `test_spatial_serialization_surface` (37 lines, frozenset surface guard for P44)
- `/home/loc/workspace/pycopg/docs/api-reference.md` - Added 3 spatial serialization rows (as_geojson/as_text/as_mvt) with born-clean filter=
- `/home/loc/workspace/pycopg/docs/stability.md` - Added 3 stable-tier rows + PostGIS-3.0 ST_AsMVT note + GeoJSON-6-digit/empty-tile/SRID-0 notes
- `/home/loc/workspace/pycopg/docs/spatial.md` - Added "Serialization Helpers" section with as_mvt tile-endpoint example
- `/home/loc/workspace/pycopg/README.md` - db.spatial.* count 22→25; added as_geojson/as_text/as_mvt to method example list

## Decisions Made

- **SPAT2-13 finalized (D-10):** The named frozenset in `test_spatial_serialization_surface` + the auto-extending `test_accessor_parity` (bidirectional set-diff) + `test_accessor_parameter_kind_parity` (KIND check) together assert the full P42+P43+P44 spatial v2 surface on both accessors. No modification to `ACCESSOR_PAIRS` needed.
- **D-09 docs confirmed:** No `where=` token appears in any new doc row for the three P44 methods. All rows use born-clean `filter=`.
- **PostGIS-3.0 note (documented, not gated):** `ST_AsMVT`/`ST_AsMVTGeom`/`ST_TileEnvelope` require PostGIS ≥ 3.0. The pycopg floor is already 3.0, so this is documentation-only with no runtime gate added.

## Deviations from Plan

None — plan executed exactly as written. All four doc surfaces updated, test added, full suite green.

## Issues Encountered

None.

## Threat Surface Scan

- T-44-03 mitigated: `test_spatial_serialization_surface` (named frozenset) + auto-extending `test_accessor_parity` and `test_accessor_parameter_kind_parity` fail loudly if any of the 3 P44 methods is missing or KIND-diverges; full-suite coverage gate (≥95%) keeps the injection tests from Plans 01-02 exercised.
- T-44-03b mitigated: New docs rows use born-clean `filter=` only (D-09); manual scan confirmed no new `where=` token on P44 method rows.

## Known Stubs

None.

## Phase 44 Close-Out

Phase 44 (spatial-v2-serialization-mvt) is complete:
- Plan 01: `build_geojson_sql` + `build_text_sql` + `as_geojson`/`as_text` on both accessors (SPAT2-10/SPAT2-11)
- Plan 02: `build_mvt_sql` + `_run_mvt`/`_arun_mvt` + `as_mvt` on both accessors, live decode proof (SPAT2-12)
- Plan 03: `test_spatial_serialization_surface` + four doc surfaces updated (SPAT2-13 — this plan)

`db.spatial.*` surface now stands at 25 methods; `test_accessor_parity`, `test_accessor_parameter_kind_parity`, and the three named surface tests (P42/P43/P44) together form the full SPAT2-13 parity acceptance.

---
*Phase: 44-spatial-v2-serialization-mvt*
*Completed: 2026-06-30*

## Self-Check: PASSED
