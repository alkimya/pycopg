---
phase: 43-spatial-v2-spatial-aggregates
plan: "02"
subsystem: spatial
tags: [spatial, aggregates, postgis, extent, box2d, tdd, sql-builder, parity, injection-guard]
dependency_graph:
  requires: [43-01-SUMMARY (build_agg_geom_sql, _append_tail group_by extension)]
  provides: [build_extent_sql, SpatialAccessor.extent, AsyncSpatialAccessor.extent]
  affects: [pycopg/spatial.py, tests/test_spatial.py]
tech_stack:
  added: []
  patterns:
    - build_extent_sql dual-branch on into= (D-04 exception — only aggregate builder that sees into=)
    - int(srid) injection-safe SRID interpolation in the gdf branch (T-43-03, D-05)
    - _append_tail group_by kwarg reused from 43-01 (same GROUP BY placement D-03)
    - validate_identifiers line-1 + validate_identifiers(*group_by) before any f-string (T-43-01)
    - extent NOT in _SCALAR_HELPERS — into="gdf" valid via box2d::geometry cast (D-04)
key_files:
  modified:
    - pycopg/spatial.py
    - tests/test_spatial.py
decisions:
  - D-04: build_extent_sql sees into= (unique exception) — one builder, one branch (DRY)
  - D-05: srid=4326 keyword-only, int(srid) injection-safe, ignored for into="rows"
  - D-06: result column frozen as "extent" (dict key + geometry_column)
  - D-07: NULL pass-through documented in docstrings; no HAVING filter
  - D-09: filter= only, no where= alias; srid and group_by keyword-only
  - D-10: sync+async edited in same change; KIND parity test passes (srid kw-only on both)
  - group_by=[]: raises ValueError (consistent with collect_geometries/union_aggregate)
  - _GDF_CALLS entry uses empty kwargs {}: routing test already injects into="gdf"; no double-pass
metrics:
  duration: "5 minutes"
  completed: "2026-06-29"
  tasks_completed: 2
  files_changed: 2
---

# Phase 43 Plan 02: Spatial Aggregates (extent) Summary

**One-liner:** ST_Extent bounding-box aggregate with dual into= SQL branch (::text rows vs ST_SetSRID::geometry gdf), srid=4326 kw-only, and full sync/async parity.

## What Was Built

The third PostGIS geometry aggregate method (`extent`) on both `SpatialAccessor` and
`AsyncSpatialAccessor`, backed by a dedicated `build_extent_sql` that branches on `into=`
(the only aggregate builder permitted to see `into=`, per D-04). The GROUP-BY machinery,
`_append_tail`, and identifier validation all come from 43-01 and were reused unchanged.

### New Symbols

**`pycopg/spatial.py`:**
- `build_extent_sql(table, geom, schema, *, group_by, srid, into, filter, order_by, limit)`: public dual-branch builder.
  - `into="rows"` (default): `ST_Extent(t.{geom})::text AS extent` — returns the PostgreSQL `BOX(xmin ymin, xmax ymax)` string.
  - `into="gdf"`: `ST_SetSRID(ST_Extent(t.{geom})::geometry, {int(srid)}) AS extent` — real SRID-tagged polygon geometry for GeoPandas.
  - `validate_identifiers(table, schema, geom)` on line 1; `validate_identifiers(*group_by)` before any f-string interpolation (T-43-01).
  - `int(srid)` cast in the gdf f-string (T-43-03, D-05): non-integer raises before SQL assembly.
  - NOT in `_SCALAR_HELPERS` — `into="gdf"` is valid (D-04, Pitfall 3).
- `SpatialAccessor.extent(table, *, geom, schema, group_by, srid, into, filter, order_by, limit)`: str→list normalize, group_by=[] ValueError, `_check_into`, builder delegation passing `into=into`, `_run(..., "extent")` (D-06).
- `AsyncSpatialAccessor.extent(...)`: async mirror, `await self._check_postgis()` first (D-10), identical keyword-only signature including `srid=4326`.

**`tests/test_spatial.py`:**
- Import block extended with `build_extent_sql`.
- `_HELPER_CALLS` extended with `("extent", {})`.
- `_GDF_CALLS` extended with `("extent", {}, "extent")` — empty kwargs because the routing test loop injects `into="gdf"` itself; no double-keyword conflict.
- `TestAggregateBuilders` extended with 10 extent tests:
  - `test_extent_rows_branch`: `::text AS extent` present, `ST_SetSRID` absent.
  - `test_extent_gdf_branch`: `ST_SetSRID(ST_Extent(t.geometry)::geometry, 4326) AS extent`.
  - `test_extent_custom_srid`: `srid=3857` appears in cast as integer.
  - `test_extent_with_group_by`: `SELECT t.region,` + `GROUP BY t.region`.
  - `test_extent_group_by_clause_ordering`: WHERE < GROUP BY < ORDER BY < LIMIT.
  - `test_extent_invalid_table`, `test_extent_invalid_geom`, `test_extent_invalid_group_by`: `InvalidIdentifierError` (T-43-01).
- `TestAggregateAccessorGuards` extended with 3 extent tests:
  - `test_extent_empty_group_by_raises`: `group_by=[]` raises `ValueError`.
  - `test_extent_str_group_by_normalized`: bare str `group_by` → list, GROUP BY in SQL.
  - `test_extent_gdf_not_rejected`: `into="gdf"` does NOT raise (extent not in `_SCALAR_HELPERS`, D-04/Pitfall 3).

## Verification Results

All acceptance criteria met:

- `uv run pytest tests/test_spatial.py::TestAggregateBuilders -x -q -o addopts=""` → 23 passed (10 extent tests + 13 from 43-01)
- `uv run pytest tests/test_spatial.py::TestAccessorRouting -x -q -o addopts=""` → 73 passed (extent rows + gdf routing)
- `uv run pytest tests/test_parity.py::test_accessor_parity tests/test_parity.py::test_accessor_parameter_kind_parity -x -q -o addopts=""` → 14 passed (extent on both classes; srid+group_by keyword-only on both — KIND parity)
- `uv run pytest -W error::DeprecationWarning tests/test_spatial.py -k "extent" -o addopts=""` → 15 passed (born clean, no DeprecationWarning)
- `uv run ruff check pycopg tests` → clean
- `uv run black --check pycopg tests` → clean (spatial.py reformatted post-implementation)
- `grep -nc "def extent\|async def extent" pycopg/spatial.py` → 2 (one sync, one async)
- `grep "_SCALAR_HELPERS = frozenset" pycopg/spatial.py` → `frozenset({"area", "perimeter", "distance", "centroid"})` (extent absent — D-04)

## Deviations from Plan

**1. [Rule 1 - Bug] `_GDF_CALLS` extent entry kwargs changed from `{"into": "gdf"}` to `{}`**

- **Found during:** Task 2 GREEN verification
- **Issue:** Plan specified `("extent", {"into": "gdf"}, "extent")` in `_GDF_CALLS`. The `TestAccessorRouting.test_sync_gdf_path_uses_named_binds` test loop calls `getattr(acc, helper)("parcels", into="gdf", **kwargs)` — when kwargs contains `into="gdf"`, Python raises `TypeError: got multiple values for keyword argument 'into'`.
- **Fix:** Changed the `_GDF_CALLS` entry to `("extent", {}, "extent")`. The routing test already passes `into="gdf"` from the loop; the builder branches correctly because it receives `into="gdf"` from the accessor.
- **Files modified:** `tests/test_spatial.py`
- **Note:** This is the correct design — other gdf entries (e.g. `convex_hull`, `collect_geometries`) also use empty kwargs in `_GDF_CALLS` since the loop always adds `into="gdf"`.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced.

New threat surface (both mitigated per threat register):
- **T-43-01:** `validate_identifiers(table, schema, geom)` line 1 of `build_extent_sql`; `validate_identifiers(*group_by)` before f-string interpolation. 3 injection tests verify `InvalidIdentifierError` fires before any SQL.
- **T-43-03:** `int(srid)` cast in the gdf f-string — non-integer input raises `ValueError`/`TypeError` before SQL assembly. `test_extent_custom_srid` confirms the integer reaches the cast.

## Known Stubs

None. `extent` wires through `build_extent_sql` → `_run` → `db.execute` / `db.to_geodataframe`. No hardcoded empty values or placeholder text.

## Self-Check: PASSED
