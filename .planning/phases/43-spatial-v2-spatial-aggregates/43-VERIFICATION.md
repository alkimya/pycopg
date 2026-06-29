---
phase: 43-spatial-v2-spatial-aggregates
verified: 2026-06-29T00:00:00Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
---

# Phase 43: Spatial v2 — Spatial Aggregates Verification Report

**Phase Goal:** Users can aggregate geometry columns by group using PostGIS aggregate functions without writing raw SQL.
**Verified:** 2026-06-29
**Status:** PASSED
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | User can call `db.spatial.collect_geometries(table, geom, group_by=None)` and `db.spatial.union_aggregate(table, geom, group_by=None)` to get geometry collections and dissolved boundaries; optional `group_by` returns one row per group | VERIFIED | `SpatialAccessor.collect_geometries` at line 3273, `union_aggregate` at 3359; `AsyncSpatialAccessor` mirrors at 5079/5151; live integration 13/13 tests passed; SQL-shape tests confirm `ST_Collect(t.geom) AS collected` / `ST_Union(t.geom) AS dissolved`; grouped tests confirm one row per group |
| 2 | User can call `db.spatial.extent(table, geom, group_by=None)` to get the bounding box; `into="rows"` returns box2d text, `into="gdf"` returns geometry; behavior with optional `group_by` is consistent | VERIFIED | `build_extent_sql` at line 1675 branches on `into=`; `into="rows"` emits `ST_Extent(t.{geom})::text AS extent`, `into="gdf"` emits `ST_SetSRID(ST_Extent(t.{geom})::geometry, {int(srid)}) AS extent`; live test `test_extent_rows_returns_box2d_text` confirms `val.startswith("BOX")`; `test_extent_gdf_returns_geodataframe` confirms `gdf.geometry.name == "extent"` |
| 3 | NULL geometry rows propagate predictably (documented NULL-propagation behavior; fixture with intentional NULL geometry rows is tested) | VERIFIED | `_make_grouped_with_nulls` at line 1179 inserts 1 NULL geometry in "north" group; `test_collect_geometries_all_null_group` / `test_union_aggregate_all_null_group` / `test_extent_null_group` each assert `rows[0][col] is None` (not zero rows); D-07 "no HAVING" confirmed in all 3 builders |
| 4 | Passing a malicious identifier to any aggregate builder raises `InvalidIdentifierError` before any SQL is sent (dedicated injection test per builder) | VERIFIED | `_build_agg_geom_sql` line 1508: `validate_identifiers(table, schema, geom)` is literal line 1; line 1509-1510: `if group_by: validate_identifiers(*group_by)` before any f-string; `build_extent_sql` line 1765 same pattern; `TestAggregateBuilders` contains 9 injection tests (3 per builder: table, geom, group_by); all 30 tests in `TestAggregateBuilders` + `TestAggregateAccessorGuards` pass |
| 5 | Every new aggregate method has a working `AsyncSpatialAccessor` equivalent confirmed by `test_accessor_parity` | VERIFIED | `async def collect_geometries` at 5079, `async def union_aggregate` at 5151, `async def extent` at 5223; each calls `await self._check_postgis()` as first statement; `test_accessor_parity` + `test_accessor_parameter_kind_parity` 15/15 passed; `test_spatial_aggregates_surface` frozenset test passes for both classes |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `pycopg/spatial.py` | `_append_tail` GROUP BY extension + `_build_agg_geom_sql` + `build_collect_geometries_sql` + `build_union_aggregate_sql` + `build_extent_sql` + 3 sync + 3 async accessor methods | VERIFIED | All 8 functions confirmed present; `_append_tail` keyword-only `group_by: str | None = None` at line 156; `_build_agg_geom_sql` at 1455; builders at 1521, 1598, 1675; sync methods at 3273, 3359, 3446; async methods at 5079, 5151, 5223 |
| `tests/test_spatial.py` | `TestAggregateBuilders` (SQL-shape + injection), `TestAggregateAccessorGuards` (group_by guards), `_make_grouped_with_nulls` NULL fixture, 13 live integration tests, `_HELPER_CALLS`/`_GDF_CALLS` extensions | VERIFIED | `TestAggregateBuilders` at 1651; `TestAggregateAccessorGuards` at 1847; `_make_grouped_with_nulls` at 1179; `_HELPER_CALLS` lines 1455-1457 include `collect_geometries`, `union_aggregate`, `extent`; `_GDF_CALLS` lines 1474-1476 include all 3 with correct column names |
| `tests/test_parity.py` | `test_spatial_aggregates_surface` frozenset surface test | VERIFIED | `def test_spatial_aggregates_surface` at line 170; `v43_surface = frozenset({"collect_geometries", "union_aggregate", "extent"})` checks both accessor classes |
| `docs/stability.md` | 3 new Stable API Contract rows with `filter=` (not `where=`), extent srid/box2d note | VERIFIED | Lines 115-121: 3 rows present; no `where=` or `columns=`; extent note at lines 119-122 documents box2d text vs geometry dual return |
| `docs/api-reference.md` | 3 new Spatial Helpers rows with `filter=` and `group_by=None` | VERIFIED | Lines 216-218 confirmed; all use `filter=`, none use `where=`; `extent` includes `srid=4326` |
| `README.md` | Spatial count updated from 19 to 22 | VERIFIED | Line 89: `(22 methods)` confirmed by `grep -c "22 methods" README.md → 1` |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `SpatialAccessor.collect_geometries` | `build_collect_geometries_sql` | str-to-list normalize, `_check_into`, delegation, `self._run(sql, params, into, "collected")` | WIRED | Lines 3341-3357; routing test 73/73 passed |
| `_build_agg_geom_sql` | `validate_identifiers` | line-1 guard on table/schema/geom + `validate_identifiers(*group_by)` before group-column f-string | WIRED | Lines 1508-1510; 9 injection tests pass |
| `build_collect_geometries_sql / build_union_aggregate_sql` | `_append_tail(..., group_by=group_by_str)` | GROUP BY inserted between WHERE and ORDER BY (D-03) | WIRED | Line 1515-1516; tail-clause ordering confirmed by 2 test methods asserting `where_idx < group_idx < order_idx < limit_idx` |
| `SpatialAccessor.extent` | `build_extent_sql(..., into=into)` | str-to-list normalize, `_check_into`, delegation passing `into=`, `self._run(sql, params, into, "extent")` | WIRED | Lines 3535-3553; `into=` propagated to builder for dual-branch SQL |
| `AsyncSpatialAccessor.*` | `await self._check_postgis()` | First statement in each async method (D-10) | WIRED | Lines 5132, 5204, 5281; confirmed by code read |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `SpatialAccessor.collect_geometries` | `rows` / `GeoDataFrame` | `build_collect_geometries_sql` → `self._run` → `db.execute` / `db.to_geodataframe` | Yes — live PostGIS confirmed 13 integration tests pass | FLOWING |
| `SpatialAccessor.union_aggregate` | `rows` / `GeoDataFrame` | `build_union_aggregate_sql` → `self._run` | Yes — live PostGIS confirmed | FLOWING |
| `SpatialAccessor.extent` | `rows` / `GeoDataFrame` | `build_extent_sql` → `self._run` | Yes — live PostGIS confirmed; `val.startswith("BOX")` and `gdf.geometry.name == "extent"` | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| SQL-shape + injection tests (30 tests) | `uv run pytest tests/test_spatial.py::TestAggregateBuilders tests/test_spatial.py::TestAggregateAccessorGuards -x -q -o addopts=""` | 30 passed in 0.06s | PASS |
| Accessor routing tests (73 tests) | `uv run pytest tests/test_spatial.py::TestAccessorRouting -x -q -o addopts=""` | 73 passed in 0.15s | PASS |
| Parity + surface tests (15 tests) | `uv run pytest tests/test_parity.py::test_spatial_aggregates_surface tests/test_parity.py::test_accessor_parity tests/test_parity.py::test_accessor_parameter_kind_parity -x -q -o addopts=""` | 15 passed in 0.05s | PASS |
| Live PostGIS integration (13 tests) | `PGDATABASE=pycopg_test2 uv run pytest tests/test_spatial.py::TestIntegration -k "collect_geometries or union_aggregate or extent" -x -q -o addopts=""` | 13 passed in 3.20s | PASS |
| Born-clean DeprecationWarning gate | `uv run pytest -W error::DeprecationWarning tests/test_spatial.py -k "collect_geometries or union_aggregate or extent" -o addopts=""` | 42 passed, 13 skipped (PostGIS-skip), 0 warnings | PASS |
| Ruff lint | `uv run ruff check pycopg tests` | All checks passed | PASS |
| Black format | `uv run black --check pycopg tests` | 48 files would be left unchanged | PASS |

### Probe Execution

No explicit probe scripts declared for this phase. Behavioral spot-checks above serve as the verification layer.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|------------|------------|-------------|--------|---------|
| SPAT2-07 | 43-01, 43-03 | `db.spatial.collect_geometries` via ST_Collect aggregate | SATISFIED | `build_collect_geometries_sql` + accessor wired; live integration passes; result column `collected` confirmed |
| SPAT2-08 | 43-01, 43-03 | `db.spatial.union_aggregate` via ST_Union aggregate, result column `dissolved` | SATISFIED | `build_union_aggregate_sql` + accessor wired; `AS dissolved` (not `union_geom`) confirmed; live integration passes |
| SPAT2-09 | 43-02, 43-03 | `db.spatial.extent` via ST_Extent; `into="rows"` box2d text, `into="gdf"` geometry | SATISFIED | `build_extent_sql` dual-branch confirmed; live integration confirms `BOX...` text and GeoDataFrame geometry column name `extent` |

REQUIREMENTS.md traceability table marks SPAT2-07/08/09 as "Complete" at Phase 43. All 3 are confirmed.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | No TBD/FIXME/XXX debt markers | — | None |
| — | — | No placeholder/stub returns | — | None |
| — | — | No `return null` / empty stub implementations | — | None |

No anti-patterns detected in `pycopg/spatial.py`, `tests/test_spatial.py`, `tests/test_parity.py`, `docs/stability.md`, `docs/api-reference.md`, or `README.md`.

### Human Verification Required

None. All required behaviors are verified programmatically:
- SQL generation is testable via pure builder calls (no live DB needed).
- Identifier injection guards are directly testable.
- Async parity is enforced by `test_accessor_parameter_kind_parity`.
- Live PostGIS behavior (NULL pass-through, box2d text, GeoDataFrame geometry column) is covered by the integration tests that ran against the local PostGIS 3.6.4 instance.

---

_Verified: 2026-06-29_
_Verifier: Claude (gsd-verifier)_
