---
phase: 42-spatial-v2-processing-helpers
plan: "02"
subsystem: spatial
tags: [spatial, postgis, unary-ops, simplify, make_valid, convex_hull, parity, injection-guard]
dependency_graph:
  requires: [42-01]
  provides: [build_simplify_sql, build_convex_hull_sql, build_make_valid_sql, SpatialAccessor.simplify, SpatialAccessor.convex_hull, SpatialAccessor.make_valid, AsyncSpatialAccessor.simplify, AsyncSpatialAccessor.convex_hull, AsyncSpatialAccessor.make_valid]
  affects: [pycopg/spatial.py, tests/test_spatial.py]
tech_stack:
  added: []
  patterns: [builder-pur, kw-only-frozen-api, validate-identifiers-line-1, sync-async-parity, tdd-red-green]
key_files:
  created: []
  modified:
    - pycopg/spatial.py
    - tests/test_spatial.py
decisions:
  - D-02: method whitelist = {None, "linework", "structure"}; validate after validate_identifiers, before SQL; params string bound through %s (never f-string)
  - D-03: keep_collapsed with method!="structure" raises ValueError; keep_collapsed=True/False builds "method=structure keepcollapsed=true|false"
  - D-05: tolerance required kw-only; preserve_topology=True default (ST_SimplifyPreserveTopology, no NULL); preserve_collapsed=True + preserve_topology=True raises ValueError
  - D-07: NULL/type-change passthrough; simplify(preserve_topology=False) can return NULL (documented, no assertion); make_valid can change POLYGON->MULTIPOLYGON (documented)
  - D-09: make_valid(method="structure") tested live unguarded — PostGIS 3.6.4 in CI >> 3.2 floor
  - D-10: no where= on any of the 6 new methods (born clean)
  - D-11: sync + async edited in same change; parity + kind-parity green
metrics:
  duration: "18 minutes"
  completed: "2026-06-29T10:10:00Z"
  tasks_completed: 3
  files_changed: 2
---

# Phase 42 Plan 02: Unary Geometry Processing Operations Summary

**One-liner:** ST_SimplifyPreserveTopology/ST_Simplify (two-branch), ST_ConvexHull, and ST_MakeValid with method whitelist + keep_collapsed assembly, 6 accessor methods (3 sync + 3 async), full injection + live integration test coverage including bowtie repair and method="structure" unguarded.

## What Was Built

### pycopg/spatial.py

**New module-level constant:**

- `_VALID_MAKE_VALID_METHODS = {None, "linework", "structure"}` — module-level frozenset (D-02 guard source)

**New module-level functions (builders):**

- `build_simplify_sql(table, geom, schema, *, tolerance, preserve_topology=True, preserve_collapsed=False, columns, filter, order_by, limit)` — validate_identifiers LINE 1; contradictory-arg guard (preserve_collapsed + preserve_topology → ValueError, D-05); two-branch: `ST_SimplifyPreserveTopology(t.{geom}, %s) AS simplified` (1 param) or `ST_Simplify(t.{geom}, %s, %s) AS simplified` (2 params)
- `build_convex_hull_sql(table, geom, schema, *, columns, filter, order_by, limit)` — validate_identifiers LINE 1; `ST_ConvexHull(t.{geom}) AS convex_hull`; params `[]`
- `build_make_valid_sql(table, geom, schema, *, method, keep_collapsed, columns, filter, order_by, limit)` — validate_identifiers LINE 1; whitelist guard after identifiers (D-02); contradictory keep_collapsed guard (D-03); params string assembled from programmer-controlled literals bound via `%s` (Pitfall 4 — no f-string)

**New sync accessor methods (SpatialAccessor, after intersection):**

- `simplify(table, *, geom, schema, tolerance, preserve_topology, preserve_collapsed, into, columns, filter, order_by, limit)` — `_check_into` → `build_simplify_sql` → `_run(..., "simplified")`
- `convex_hull(...)` — `_run(..., "convex_hull")`
- `make_valid(...)` — `_run(..., "made_valid")`

**New async accessor methods (AsyncSpatialAccessor, after async intersection):**

- `async def simplify(...)` — `await _check_postgis()` → `_check_into` → builder → `await _run(..., "simplified")`
- `async def convex_hull(...)` / `async def make_valid(...)` — same pattern

### tests/test_spatial.py

- Added `build_simplify_sql`, `build_convex_hull_sql`, `build_make_valid_sql` to imports
- **TestBuilders (SQL-shape):** `test_simplify_preserve_topology_default` (exact SQL + `params=[0.5]`), `test_simplify_no_preserve_topology` (ST_Simplify, 2 params), `test_simplify_tail_clauses`
- **TestBuilders (SQL-shape):** `test_convex_hull_emits_st_convex_hull` (exact SQL + `params=[]`), `test_convex_hull_tail_clauses`
- **TestBuilders (SQL-shape):** `test_make_valid_no_method`, `test_make_valid_linework`, `test_make_valid_structure_keepcollapsed_true`, `test_make_valid_structure_keepcollapsed_false`, `test_make_valid_structure_no_keepcollapsed`
- **TestBuilders (ValueError guards):** `test_simplify_contradictory_args`, `test_make_valid_invalid_method`, `test_make_valid_keep_collapsed_without_structure`, `test_make_valid_keep_collapsed_without_any_method`
- **TestBuilders (injection):** `test_simplify_invalid_table`, `test_simplify_invalid_columns`, `test_convex_hull_invalid_table`, `test_convex_hull_invalid_columns`, `test_make_valid_invalid_table`, `test_make_valid_invalid_columns`
- **TestBuilderColumnsValidation:** `test_simplify_columns_validated`, `test_convex_hull_columns_validated`, `test_make_valid_columns_validated` — T-42-05 mitigated for unary trio
- **_HELPER_CALLS / _GDF_CALLS:** 3 new entries each (simplify/convex_hull/make_valid); parametrized routing tests now exercise unary trio
- **TestIntegration:** `_make_bowtie_table` (self-intersecting POLYGON((0 0, 1 1, 1 0, 0 1, 0 0)) SRID 4326) and `_make_tiny_polygon_table` (POLYGON((0 0, 0.0001 0, 0.0001 0.0001, 0 0.0001, 0 0)) SRID 4326) fixture helpers
- **TestIntegration (live):** `test_simplify_preserve_topology_non_null` (non-NULL guaranteed by ST_SimplifyPreserveTopology, D-07), `test_simplify_no_preserve_topology_succeeds` (succeeds without exception; NULL is valid, no value assert), `test_make_valid_bowtie` (non-NULL repaired output), `test_make_valid_structure` (UNGUARDED — CI PostGIS 3.6.4 ≥ 3.2, D-09)

## Verification Results

| Check | Status |
|-------|--------|
| `uv run pytest tests/test_spatial.py -k "simplify or convex_hull or make_valid" -o addopts=""` | 35 passed, 4 skipped |
| Live: `PGDATABASE=pycopg_test2 uv run pytest TestIntegration -k "simplify or make_valid"` | 4 passed |
| `PGDATABASE=pycopg_test2 uv run pytest tests/test_parity.py -k spatial -o addopts=""` | 2 passed |
| `uv run pytest tests/test_spatial.py -k "union or difference or intersection"` (wave-1 non-regression) | 36 passed |
| `uv run ruff check pycopg/spatial.py tests/test_spatial.py` | clean |
| `uv run black --check pycopg/spatial.py` | clean |
| `_SCALAR_HELPERS` unchanged | frozenset({"area","perimeter","distance","centroid"}) |
| No `where=` on new methods | confirmed (6 methods) |
| No f-string interpolation of method/params string | `grep` returns 0 |
| `test_make_valid_structure` has NO skipif guard | confirmed (D-09) |
| `test_accessor_parity` spatial | passed |
| `test_accessor_parameter_kind_parity` spatial | passed |

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| Task 1 RED | ef7b0eb | test(42-02): add failing tests for unary builder trio |
| Task 1 GREEN | b3e9eed | feat(42-02): add build_simplify_sql + build_convex_hull_sql + build_make_valid_sql builders |
| Task 2 RED | 8782809 | test(42-02): register simplify/convex_hull/make_valid in routing registries (RED) |
| Task 2 GREEN | b377248 | feat(42-02): add simplify/convex_hull/make_valid to SpatialAccessor + AsyncSpatialAccessor |
| Task 3 GREEN | 8ef20c8 | test(42-02): add SQL-shape, ValueError-guard, injection, routing, and live tests for unary trio |

## Deviations from Plan

None — plan executed exactly as written.

The `TestBuilderColumnsValidation` injection tests for the unary trio were added (plan specified "columns-injection variants") alongside the `TestBuilders` injection tests, consistent with the existing pattern for all other builders.

## Known Stubs

None. All 6 accessor methods are fully wired through to PostGIS execution via `_run`/`_arun`. No placeholder data.

## Threat Flags

No new security surface beyond what the plan's threat model covers:
- T-42-04: `validate_identifiers(table, schema, geom)` is LINE 1 of all 3 unary builders; per-builder injection tests (`test_simplify_invalid_table`, `test_convex_hull_invalid_table`, `test_make_valid_invalid_table`) assert `InvalidIdentifierError`
- T-42-05: `if columns: validate_identifiers(*columns)` after line 1; columns-injection tests in both `TestBuilders` and `TestBuilderColumnsValidation`
- T-42-06: `tolerance` bound through `%s` (psycopg3 float serialization); no `int()` shortcut
- T-42-07: `method` constrained to `_VALID_MAKE_VALID_METHODS` whitelist; params string assembled from literals, bound through `%s`; `test_make_valid_invalid_method` is the tripwire
- T-42-08: accepted passthrough — no server-version round-trip; documented in docstrings
- T-42-SC: no new packages installed

## Self-Check: PASSED

Files modified exist and commits are present in git history.
