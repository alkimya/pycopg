---
phase: 42-spatial-v2-processing-helpers
plan: "01"
subsystem: spatial
tags: [spatial, postgis, binary-ops, parity, injection-guard]
dependency_graph:
  requires: []
  provides: [build_union_sql, build_difference_sql, build_intersection_sql, SpatialAccessor.union, SpatialAccessor.difference, SpatialAccessor.intersection, AsyncSpatialAccessor.union, AsyncSpatialAccessor.difference, AsyncSpatialAccessor.intersection]
  affects: [pycopg/spatial.py, tests/test_spatial.py]
tech_stack:
  added: []
  patterns: [builder-pur, kw-only-frozen-api, validate-identifiers-line-1, sync-async-parity]
key_files:
  created: []
  modified:
    - pycopg/spatial.py
    - tests/test_spatial.py
decisions:
  - D-01: union->union_geom, difference->difference, intersection->intersection (frozen D-01 result column names passed as geometry_column to _run/_arun)
  - D-06: mixed-SRID raises native PostGIS error — no pre-check, documented in docstrings, live test asserts raise
  - D-10: no where= deprecated alias on any of the 6 new methods — born clean for 1.0 freeze
  - D-11: sync + async edited in same change; test_accessor_parity + test_accessor_parameter_kind_parity confirm balance
  - D-12: validate_identifiers(table, schema, geom, other_geom) is line 1 of _build_binary_geom_sql; columns validated when provided
  - Claude's Discretion: shared _build_binary_geom_sql helper (DRY); each public builder keeps its own injection test
metrics:
  duration: "6 minutes"
  completed: "2026-06-29T09:05:49Z"
  tasks_completed: 3
  files_changed: 2
---

# Phase 42 Plan 01: Pairwise Binary Geometry Operations Summary

**One-liner:** ST_Union/ST_Difference/ST_Intersection pairwise overlay builders with shared _build_binary_geom_sql helper, 6 accessor methods (3 sync + 3 async), and full injection + live integration test coverage.

## What Was Built

### pycopg/spatial.py

**New module-level functions (builders):**

- `_build_binary_geom_sql(op_func, result_col, table, geom, schema, *, other_geom, columns, filter, order_by, limit)` — shared internal DRY helper; `validate_identifiers(table, schema, geom, other_geom)` is line 1 (T-42-01 mitigated); returns `(sql, [])` — no user values bound
- `build_union_sql(...)` — `ST_Union(t.{geom}, t.{other_geom}) AS union_geom`; delegates to helper
- `build_difference_sql(...)` — `ST_Difference(t.{geom}, t.{other_geom}) AS difference`
- `build_intersection_sql(...)` — `ST_Intersection(t.{geom}, t.{other_geom}) AS intersection`

**New sync accessor methods (SpatialAccessor, after `transform`):**

- `union(table, *, geom, schema, other_geom, into, columns, filter, order_by, limit)` — `_check_into` → `build_union_sql` → `_run(..., "union_geom")`
- `difference(...)` — `_run(..., "difference")`
- `intersection(...)` — `_run(..., "intersection")`

**New async accessor methods (AsyncSpatialAccessor, after async `transform`):**

- `async def union(...)` — `await _check_postgis()` → `_check_into` → `build_union_sql` → `await _run(..., "union_geom")`
- `async def difference(...)` / `async def intersection(...)` — same pattern

### tests/test_spatial.py

- Added `build_union_sql`, `build_difference_sql`, `build_intersection_sql` to imports
- **TestBuilders:** SQL-shape tests (`test_union_emits_st_union`, `test_difference_emits_st_difference`, `test_intersection_emits_st_intersection`) asserting exact SQL + `params == []`; tail-clause tests (`test_union_tail_clauses` etc.) asserting startswith/endswith
- **TestBuilders:** per-builder injection tests: `test_union_invalid_table`, `test_union_invalid_other_geom`, `test_difference_invalid_table`, `test_difference_invalid_other_geom`, `test_intersection_invalid_table`, `test_intersection_invalid_other_geom` — all asserting `InvalidIdentifierError`
- **TestBuilderColumnsValidation:** `test_union_columns_validated`, `test_difference_columns_validated`, `test_intersection_columns_validated` — T-42-02 mitigated
- **_HELPER_CALLS / _GDF_CALLS:** 3 new entries each; parametrized routing tests now exercise binary trio
- **TestIntegration:** `_make_two_geom_table` (overlapping polygons 4326/4326) and `_make_mixed_srid_table` (4326/32632) fixture helpers
- **TestIntegration:** 9 live tests — pairwise rows, `into="gdf"` with `gdf.geometry.name` check, mixed-SRID raises — for each of union/difference/intersection

## Verification Results

| Check | Status |
|-------|--------|
| `uv run pytest tests/test_spatial.py -k "union or difference or intersection" -o addopts=""` | 36 passed |
| `PGDATABASE=pycopg_test2 uv run pytest tests/test_parity.py -k spatial -o addopts=""` | 2 passed |
| `uv run ruff check pycopg/spatial.py tests/test_spatial.py` | clean |
| `uv run black --check pycopg/spatial.py tests/test_spatial.py` | clean |
| `_SCALAR_HELPERS` unchanged | frozenset({"area","perimeter","distance","centroid"}) |
| No `where=` on new methods | confirmed (6 methods) |
| No `gridSize` emitted | confirmed (grep returns 0) |
| `test_accessor_parity` spatial | passed |
| `test_accessor_parameter_kind_parity` spatial | passed |

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| Task 1 | 8e22f0f | feat(42-01): add _build_binary_geom_sql helper + 3 public binary builders |
| Task 2 | 5767e65 | feat(42-01): add union/difference/intersection to SpatialAccessor + AsyncSpatialAccessor |
| Task 3 | 086aba5 | test(42-01): add SQL-shape, injection, routing, and live integration tests for binary trio |

## Deviations from Plan

None — plan executed exactly as written. The shared `_build_binary_geom_sql` helper was recommended as Claude's Discretion and implemented as planned.

## Known Stubs

None. All 6 accessor methods (3 sync + 3 async) are fully wired through to PostGIS execution via `_run`/`_arun`. No placeholder data.

## Threat Flags

No new security surface beyond what the plan's threat model covers (T-42-01 through T-42-SC all addressed):
- T-42-01: `validate_identifiers(table, schema, geom, other_geom)` is line 1 of `_build_binary_geom_sql`; 6 injection tests assert `InvalidIdentifierError`
- T-42-02: `if columns: validate_identifiers(*columns)` immediately after line 1; 3 columns-injection tests
- T-42-03: No user values in binary op params (params always `[]`); no `%s` injection risk
- T-42-SC: No new packages installed

## Self-Check: PASSED

Files created/modified exist and commits are present in git history.
