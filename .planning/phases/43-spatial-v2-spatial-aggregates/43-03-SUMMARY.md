---
phase: 43-spatial-v2-spatial-aggregates
plan: "03"
subsystem: spatial
tags: [spatial, aggregates, postgis, integration-tests, surface-test, docs, closeout]
dependency_graph:
  requires: [43-01-SUMMARY (collect_geometries + union_aggregate builders + accessors), 43-02-SUMMARY (extent builder + accessor)]
  provides: [live-integration-tests, test_spatial_aggregates_surface, stability.md-rows, api-reference-rows, README-count-22]
  affects: [tests/test_spatial.py, tests/test_parity.py, docs/stability.md, docs/api-reference.md, README.md]
tech_stack:
  added: []
  patterns:
    - _make_grouped_with_nulls live fixture (adapts _make_points pattern with intentional NULL geometry rows)
    - try/finally DROP TABLE IF EXISTS CASCADE (existing TestIntegration convention)
    - frozenset surface test (v43_surface pattern mirrors v42_surface from Phase 42)
key_files:
  modified:
    - tests/test_spatial.py
    - tests/test_parity.py
    - docs/stability.md
    - docs/api-reference.md
    - README.md
decisions:
  - D-07 confirmed live: all-NULL group returns 1 row with NULL aggregate (not 0 rows); mixed-NULL group skips NULL inputs and returns its row
  - D-04 confirmed live: extent into="rows" => BOX-prefixed text string; into="gdf" => GeoDataFrame with geometry.name=="extent"
  - D-06 confirmed live: result columns "collected" / "dissolved" / "extent" present on all returned rows
  - T-43-02 tripwire: all 23 TestAggregateBuilders injection tests green under full suite (6 inject + 17 SQL-shape)
metrics:
  duration: "5 minutes"
  completed: "2026-06-29"
  tasks_completed: 3
  files_changed: 5
---

# Phase 43 Plan 03: Spatial Aggregates Closeout Summary

**One-liner:** Phase 43 closeout — live PostGIS integration tests for all 3 aggregate methods, frozenset surface assertion on both accessor classes, stability.md/api-reference.md/README docs published; full suite green at 96.10% coverage (ratchet >= 95%).

## What Was Built

### Task 1 — Live integration tests for the 3 aggregates

Added `_make_grouped_with_nulls` helper and 13 new live integration tests to `TestIntegration` in `tests/test_spatial.py`, covering all SPAT2-07/08/09 Layer-(b) requirements (D-08):

**`_make_grouped_with_nulls(self, db, t)`:**
Creates a table with `(id INT, region TEXT, geometry geometry(Point, 4326))` and inserts 3 rows: 2 in region "north" (one non-NULL point + one intentional NULL geometry) and 1 in region "south" (non-NULL point). Satisfies D-07 NULL-fixture requirement for criterion 3.

**Per-aggregate coverage (3 aggregates × 3–5 sub-cases each = 13 tests):**

| Test | Aggregate | Case |
|------|-----------|------|
| `test_collect_geometries_whole_table` | collect_geometries | group_by=None → 1 row with `collected` |
| `test_collect_geometries_grouped` | collect_geometries | group_by="region" → 2 rows |
| `test_collect_geometries_null_rows_pass_through` | collect_geometries | mixed-NULL: both groups present (D-07) |
| `test_collect_geometries_all_null_group` | collect_geometries | all-NULL group → 1 row, `collected` is None (D-07) |
| `test_union_aggregate_whole_table` | union_aggregate | group_by=None → 1 row with `dissolved` |
| `test_union_aggregate_grouped` | union_aggregate | group_by="region" → 2 rows |
| `test_union_aggregate_null_rows_pass_through` | union_aggregate | mixed-NULL: both groups present (D-07) |
| `test_union_aggregate_all_null_group` | union_aggregate | all-NULL group → 1 row, `dissolved` is None (D-07) |
| `test_extent_whole_table` | extent | group_by=None → 1 row with `extent` |
| `test_extent_rows_returns_box2d_text` | extent | into="rows" → string starting with "BOX" (D-04) |
| `test_extent_gdf_returns_geodataframe` | extent | into="gdf" → GeoDataFrame, geometry.name=="extent" (D-04) |
| `test_extent_grouped` | extent | group_by="region" → 2 rows |
| `test_extent_null_group` | extent | all-NULL group → 1 row, `extent` is None (D-07) |

All 13 passed live against PostGIS 3.6.4 on `pycopg_test2`.

### Task 2 — Surface test + docs

**`tests/test_parity.py` — `test_spatial_aggregates_surface`:**
Frozenset `v43_surface = {"collect_geometries", "union_aggregate", "extent"}` asserted to be a subset of both `SpatialAccessor` and `AsyncSpatialAccessor` public members. Mirrors `test_spatial_v1_processing_surface` (Phase 42) exactly.

**`docs/stability.md` — 3 new Stable API Contract rows:**
- `collect_geometries`: positional `table`, kw-only `geom`, `schema`, `group_by`, `filter`, `into`, `order_by`, `limit`
- `union_aggregate`: same set as collect_geometries
- `extent`: same + kw-only `srid` (the extra SRID arg, D-05)
- Added note: `extent into="rows"` returns `BOX(...)` text; `into="gdf"` returns SRID-tagged geometry with active column `"extent"` (D-04/D-05). No `columns=` on any (D-02).

**`docs/api-reference.md` — 3 new Spatial Helpers rows:**
Using `filter=` (not `where=`), no `columns=`, `group_by=None` default on all three, `srid=4326` on `extent`, return type `list[dict] | GeoDataFrame`.

**`README.md`:** Bumped spatial count from "(19 methods)" to "(22 methods)" and named `collect_geometries`, `extent` in the example list.

### Task 3 — Full-suite + coverage + lint gate (T-43-02 tripwire)

- **Full suite:** `PGDATABASE=pycopg_test2 uv run pytest` → **1623 passed, 2 skipped, 0 failures**
- **Coverage:** 96.10% — well above the 95% ratchet (Required test coverage of 95% reached)
- **TestAggregateBuilders injection tests:** All 23 passed (9 inject + 14 SQL-shape tests) — T-43-01/T-43-02 tripwires green
- **ruff:** `uv run ruff check pycopg tests` → clean
- **black:** Applied black reformatting to test_spatial.py (new integration test methods), then `uv run black --check pycopg tests` → clean
- **DeprecationWarning gate:** `-W error::DeprecationWarning` on the 3 methods → 42 passed, 0 warnings

## Verification Results

All acceptance criteria met:

- `PGDATABASE=pycopg_test2 uv run pytest tests/test_spatial.py::TestIntegration -x -q -o addopts="" -k "collect_geometries or union_aggregate or extent"` → 13 passed
- `uv run pytest tests/test_parity.py::test_spatial_aggregates_surface -x -q -o addopts=""` → passed
- `uv run pytest tests/test_parity.py::test_accessor_parity tests/test_parity.py::test_accessor_parameter_kind_parity -x -q -o addopts=""` → 15 passed
- `grep -c "collect_geometries\|union_aggregate\|extent" docs/stability.md` → 5
- `grep -c "collect_geometries\|union_aggregate\|extent" docs/api-reference.md` → 3
- `grep -c "22 methods" README.md` → 1
- `uv run sphinx-build -W -b html docs docs/_build/html` → La compilation a réussi (Sphinx -W clean)
- `uv run ruff check pycopg tests` → All checks passed
- `uv run black --check pycopg tests` → 48 files would be left unchanged
- `PGDATABASE=pycopg_test2 uv run pytest` → 1623 passed, 96.10% coverage

## Deviations from Plan

**1. [Rule 2 - Auto-fix] Black formatting applied to test_spatial.py after Task 1 commit**

- **Found during:** Task 3 lint gate
- **Issue:** `uv run black --check` reported `tests/test_spatial.py` would be reformatted (string line-continuation style in new integration test methods)
- **Fix:** `uv run black tests/test_spatial.py` reformatted the file; committed as a separate `style(43-03)` commit
- **Files modified:** `tests/test_spatial.py`
- **Commit:** 42a198a

All other plan items executed exactly as written.

## SPAT2-07/08/09 Criterion 3 — NULL Pass-through Satisfaction

The D-07 documented NULL-propagation behavior is confirmed live:

| Scenario | Method | Result | Assertion |
|----------|--------|--------|-----------|
| Mixed-NULL group | collect_geometries | both groups present, NULL row skipped | `len(rows) == 2`, `"collected" in row` |
| All-NULL group | collect_geometries | 1 row, aggregate is None | `rows[0]["collected"] is None` |
| Mixed-NULL group | union_aggregate | both groups present | `len(rows) == 2`, `"dissolved" in row` |
| All-NULL group | union_aggregate | 1 row, aggregate is None | `rows[0]["dissolved"] is None` |
| All-NULL group | extent | 1 row, aggregate is None | `rows[0]["extent"] is None` |

No `HAVING ... IS NOT NULL` filter was applied in any builder (D-07 confirmed).

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. This plan added only tests and documentation.

T-43-01 and T-43-02 confirmed under the full suite run:
- 9 injection tests (3 per builder × 3 builders) passed in `TestAggregateBuilders`
- Coverage 96.10% proves the `validate_identifiers` branches are exercised

T-43-04 (docs drift) confirmed clean: grep of new api-reference rows shows `filter=` not `where=`; no `columns=` on any aggregate row.

## Known Stubs

None. All 3 aggregate methods are fully wired: live PostGIS confirms end-to-end data flow through builder → accessor → DB → result.

## Self-Check: PASSED
