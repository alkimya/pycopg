---
phase: 43-spatial-v2-spatial-aggregates
plan: "01"
subsystem: spatial
tags: [spatial, aggregates, postgis, group-by, tdd, sql-builder, parity]
dependency_graph:
  requires: [42-spatial-v2-processing-helpers]
  provides: [build_collect_geometries_sql, build_union_aggregate_sql, SpatialAccessor.collect_geometries, SpatialAccessor.union_aggregate, AsyncSpatialAccessor.collect_geometries, AsyncSpatialAccessor.union_aggregate]
  affects: [pycopg/spatial.py, tests/test_spatial.py]
tech_stack:
  added: []
  patterns:
    - _build_agg_geom_sql shared internal helper (mirrors _build_binary_geom_sql from Phase 42)
    - _append_tail extended with keyword-only group_by for GROUP BY between WHERE and ORDER BY (D-03)
    - group_by str->[str] normalization at accessor level, not builder level
    - validate_identifiers(*group_by) before any f-string interpolation (T-43-01)
key_files:
  modified:
    - pycopg/spatial.py
    - tests/test_spatial.py
decisions:
  - D-01: group_by str->list normalization done at accessor level (sync + async)
  - D-03: _append_tail extended with keyword-only group_by (None default preserves 20+ existing callers)
  - D-06: result columns frozen as 'collected' (collect_geometries) and 'dissolved' (union_aggregate)
  - D-07: NULL pass-through documented in all 4 method docstrings; no HAVING filter
  - D-08: layer (a) mock/SQL-shape tests authoritative; injection tests cover table+geom+group_by per builder
  - D-09: filter= only, no where= alias, all params keyword-only
  - D-10: sync+async edited in same change; KIND parity test passes
  - group_by=[]: raises ValueError (open-question-1 RESOLVED: explicit over silent, per D-01)
  - group_by t. qualification: t.region in both SELECT and GROUP BY for consistency (open-question-2 RESOLVED)
metrics:
  duration: "5 minutes"
  completed: "2026-06-29"
  tasks_completed: 2
  files_changed: 2
---

# Phase 43 Plan 01: Spatial Aggregates (collect_geometries + union_aggregate) Summary

**One-liner:** GROUP-BY geometry aggregates via ST_Collect/ST_Union with shared `_build_agg_geom_sql`, validate_identifiers-first injection guard, and full sync/async parity.

## What Was Built

Two new PostGIS geometry aggregate methods (`collect_geometries`, `union_aggregate`) on both
`SpatialAccessor` and `AsyncSpatialAccessor`, backed by a shared internal builder and an extended
`_append_tail` that inserts GROUP BY between WHERE and ORDER BY (D-03).

### New Symbols

**`pycopg/spatial.py`:**
- `_append_tail`: extended with keyword-only `group_by: str | None = None` (inserted after WHERE, before ORDER BY). All 20+ existing positional callers unaffected.
- `_build_agg_geom_sql(agg_func, result_col, table, geom, schema, *, group_by, filter, order_by, limit)`: shared internal helper mirroring `_build_binary_geom_sql`. `validate_identifiers(table, schema, geom)` on line 1; `validate_identifiers(*group_by)` before any f-string interpolation of group columns (T-43-01).
- `build_collect_geometries_sql(...)`: public builder → `ST_Collect(...) AS collected`, result col `collected` (D-06, SPAT2-07).
- `build_union_aggregate_sql(...)`: public builder → `ST_Union(...) AS dissolved`, result col `dissolved` (D-06, SPAT2-08).
- `SpatialAccessor.collect_geometries(table, *, geom, schema, group_by, into, filter, order_by, limit)`: str→list normalize, group_by=[] ValueError, _check_into, builder delegation, `_run(..., "collected")`.
- `SpatialAccessor.union_aggregate(...)`: identical shape, `_run(..., "dissolved")`.
- `AsyncSpatialAccessor.collect_geometries(...)`: async mirror, `await _check_postgis()` first (D-10).
- `AsyncSpatialAccessor.union_aggregate(...)`: async mirror, same pattern.

**`tests/test_spatial.py`:**
- Updated `from pycopg.spatial import (...)` block to include the 2 new builders.
- `_HELPER_CALLS` extended with `("collect_geometries", {})` and `("union_aggregate", {})`.
- `_GDF_CALLS` extended with `("collect_geometries", {}, "collected")` and `("union_aggregate", {}, "dissolved")`.
- `class TestAggregateBuilders`: 15 tests — whole-table shape, group_by shape, composite group_by, tail-clause placement (WHERE index < GROUP BY index < ORDER BY index < LIMIT index), no-params assertion, and 3 injection tests per builder (malicious table, geom, group_by).
- `class TestAggregateAccessorGuards`: 4 tests — group_by=[] raises ValueError on both sync methods, bare str group_by normalizes to list (verified via SQL content check).

## Verification Results

All acceptance criteria met:

- `uv run pytest tests/test_spatial.py::TestAggregateBuilders -x -q -o addopts=""` → 15 passed
- `uv run pytest tests/test_spatial.py::TestAccessorRouting -x -q -o addopts=""` → passed (rows + gdf routing for both new methods)
- `uv run pytest tests/test_parity.py::test_accessor_parity tests/test_parity.py::test_accessor_parameter_kind_parity -x -q -o addopts=""` → 14 passed (KIND parity: group_by keyword-only on both sync/async)
- `uv run pytest -W error::DeprecationWarning tests/test_spatial.py -k "collect_geometries or union_aggregate" -o addopts=""` → 27 passed (born clean, no DeprecationWarning)
- `uv run ruff check pycopg tests` → clean
- `uv run black --check pycopg tests` → clean (spatial.py reformatted during execution)

## Deviations from Plan

None — plan executed exactly as written.

The only minor note: `_append_tail` was extended with a keyword-only `*` separator added before `group_by` — exactly as specified in the plan (Pitfall 2 guard). Existing callers using the positional form `_append_tail(sql, f, o, l, has_where=False)` remain unaffected because `group_by` is keyword-only with default `None`.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. The new surface is:
- `validate_identifiers(*group_by)` before any f-string interpolation — T-43-01 mitigated.
- Injection test tripwires added: 3 tests per builder (table, geom, group_by) → 6 total injection tests.

No unplanned trust-boundary additions detected.

## Known Stubs

None. Both methods wire through to `build_*_sql` → `_run` → `db.execute` / `db.to_geodataframe`. No hardcoded empty values or placeholder text.

## Self-Check: PASSED
