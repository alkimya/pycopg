---
phase: 44-spatial-v2-serialization-mvt
plan: 01
subsystem: database
tags: [postgis, spatial, geojson, wkt, sql-builder, serialization, pycopg]

# Dependency graph
requires:
  - phase: 43-spatial-v2-spatial-aggregates
    provides: "_SCALAR_HELPERS pattern, _append_tail with group_by, build_extent_sql int(srid) precedent"
  - phase: 42-spatial-v2-processing-helpers
    provides: "builder-pur pattern, injection-test template, KIND-parity guard"
  - phase: 41-api-homogenization
    provides: "filter= born-clean convention, D-09 kw-only, validate_identifiers line-1 rule"
provides:
  - "build_geojson_sql module-level builder (ST_AsGeoJSON, options bitmask, AS geojson alias)"
  - "build_text_sql module-level builder (ST_AsText one-arg/two-arg conditional, AS wkt alias)"
  - "SpatialAccessor.as_geojson + as_text (born-clean filter=, kw-only, _SCALAR_HELPERS)"
  - "AsyncSpatialAccessor.as_geojson + as_text (parity: await _check_postgis + await _run)"
  - "_SCALAR_HELPERS extended: as_geojson, as_text (into='gdf' raises ValueError)"
  - "TestBuildGeojsonSql + TestBuildTextSql (injection + SQL-shape mock tests)"
  - "Live PostGIS integration: geojson/wkt key presence, JSON parseable, WKT POINT prefix"
affects:
  - "44-02 (as_mvt plan builds on this clean scalar surface)"
  - "44-03 (parity test will cover this plan's methods)"
  - "test_parity.py serialization surface test (plan 03)"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Scalar builder clone: validate_identifiers line-1 + columns validate + _cols_str + ST_*(...) AS alias + _append_tail + return (sql, params)"
    - "D-06 options bitmask: (1 if include_bbox else 0) | (2 if include_crs else 0), two %s params"
    - "D-07 conditional precision: max_decimal_digits is None -> one-arg ST_AsText, set -> two-arg ST_AsText(%s)"
    - "D-09 born-clean: no where= shim block on new methods"
    - "D-10 KIND-parity: identical * boundary position in sync and async signatures"

key-files:
  created: []
  modified:
    - "pycopg/spatial.py"
    - "tests/test_spatial.py"

key-decisions:
  - "D-06: options bitmask (include_bbox bit1 + include_crs bit2) passed as %s param alongside max_decimal_digits; frozen result key 'geojson'"
  - "D-07: max_decimal_digits=None (default) -> one-arg ST_AsText (full precision, no silent truncation); set -> two-arg; frozen result key 'wkt'"
  - "D-08: both methods in _SCALAR_HELPERS so into='gdf' auto-raises ValueError; into= param present on both"
  - "D-09: no where= deprecated alias on as_geojson/as_text (born-clean 1.0 methods)"
  - "D-10: sync+async edited in same change; identical kw-only * boundary (KIND parity)"

patterns-established:
  - "Scalar serializer pattern: build_geojson_sql / build_text_sql as near-exact clones of build_area_sql / build_perimeter_sql"
  - "D-06 bitmask formula for ST_AsGeoJSON options (reusable for any future bitmask flag composition)"
  - "D-07 conditional ST_AsText one-arg vs two-arg (template for optional-precision parameters)"

requirements-completed: [SPAT2-10, SPAT2-11]

# Metrics
duration: 5min
completed: 2026-06-30
---

# Phase 44 Plan 01: Scalar Serialization Helpers Summary

**ST_AsGeoJSON + ST_AsText scalar builders with D-06 options bitmask and D-07 conditional precision wired on both SpatialAccessor and AsyncSpatialAccessor (born-clean filter=, _SCALAR_HELPERS, injection-guarded)**

## Performance

- **Duration:** 5 min
- **Started:** 2026-06-30T06:40:19Z
- **Completed:** 2026-06-30T06:45:40Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- `build_geojson_sql` and `build_text_sql` module-level builders: `validate_identifiers` line-1 guard (T-44-01 mitigated), D-06 bitmask for `include_bbox`/`include_crs`, D-07 one-arg vs two-arg `ST_AsText` conditional, frozen `geojson`/`wkt` result key aliases, `_append_tail` tail
- Both methods wired on `SpatialAccessor` and `AsyncSpatialAccessor` (D-10 same-change parity): born-clean `filter=` only (D-09), no `where=` shim
- `_SCALAR_HELPERS` frozenset extended with `"as_geojson"` and `"as_text"` (NOT `"as_mvt"`); `into="gdf"` auto-raises `ValueError` for both (D-08)
- `_HELPER_CALLS` updated; `TestAccessorRouting` now covers both helpers sync + async rows paths (77 routing tests green)
- Live PostGIS integration tests: `geojson` key is a JSON string parseable to a dict with `"type"`; `wkt` key is a WKT string starting with `"POINT"`; async mirror verified end-to-end

## Task Commits

1. **Task 1: build_geojson_sql + build_text_sql builders + injection/SQL-shape tests** - `baa5ddb` (feat)
2. **Task 2: as_geojson + as_text accessor methods + _SCALAR_HELPERS + routing/gdf/live tests** - `2136fa2` (feat)

## Files Created/Modified

- `/home/loc/workspace/pycopg/pycopg/spatial.py` - Added `build_geojson_sql`, `build_text_sql` builders; `SpatialAccessor.as_geojson/as_text`; `AsyncSpatialAccessor.as_geojson/as_text`; `_SCALAR_HELPERS` extended
- `/home/loc/workspace/pycopg/tests/test_spatial.py` - Added `build_geojson_sql`/`build_text_sql` imports; `TestBuildGeojsonSql` + `TestBuildTextSql` classes; `_HELPER_CALLS` entries; gdf-rejection tests; live integration tests (sync + async)

## Decisions Made

- **D-06 options bitmask:** `options = (1 if include_bbox else 0) | (2 if include_crs else 0)` computed inline before the SQL f-string; two `%s` params `[max_decimal_digits, options]`. No separate helper needed (single expression).
- **D-07 conditional precision:** one-arg form when `max_decimal_digits is None` (params=[]); two-arg form otherwise (params=[value]). Asymmetric with `as_geojson` default-6 intentionally (WKT = exact interchange, GeoJSON = web payload).
- **D-09 born-clean confirmed:** `as_geojson`/`as_text` have no `where=` parameter whatsoever; the shim block in `area`/`perimeter` was not copied.
- **D-10 KIND-parity confirmed:** both sync and async signatures have `*` in the same position (after `table`); enforced by existing `test_accessor_parameter_kind_parity`.

## Deviations from Plan

None — plan executed exactly as written. Both builders and both accessor pairs follow the exact templates from `44-PATTERNS.md`. Formatting applied via `black` after implementation (routine step, not a deviation).

## Issues Encountered

None.

## Threat Surface Scan

No new security-relevant surface beyond what the plan's `<threat_model>` covers:
- T-44-01: `validate_identifiers(table, schema, geom)` is line 1 of both builders; `columns` entries validated on non-None list. Verified by `TestBuildGeojsonSql`/`TestBuildTextSql` injection tests.
- T-44-01b: `max_decimal_digits` and options bitmask are `%s` bind params (geojson) or computed `int` (bitmask) — no caller string reaches SQL text.
- T-44-01c: `filter=` raw fragment is accepted risk (documented escape hatch, consistent with full spatial surface).

## Known Stubs

None — both methods make real DB calls and return live data in integration tests.

## Next Phase Readiness

- `build_geojson_sql` and `build_text_sql` are stable, tested surfaces; Plan 02 (`as_mvt`) builds on the same scalar pattern and need not change these.
- `_SCALAR_HELPERS` is correct (does not include `as_mvt`, which uses a separate bytea runner).
- All plan verification commands pass (builder mock/injection, routing, live PostGIS, lint/format).

---
*Phase: 44-spatial-v2-serialization-mvt*
*Completed: 2026-06-30*

## Self-Check: PASSED
