---
phase: 43-spatial-v2-spatial-aggregates
reviewed: 2026-06-29T00:00:00Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - pycopg/spatial.py
  - tests/test_spatial.py
  - tests/test_parity.py
  - docs/stability.md
  - docs/api-reference.md
  - README.md
findings:
  critical: 0
  blocker: 0
  warning: 2
  info: 3
  total: 5
status: issues_found
---

# Phase 43: Code Review Report

**Reviewed:** 2026-06-29
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Summary

Adversarial review of the Spatial v2 aggregate methods (`collect_geometries`,
`union_aggregate`, `extent`), the shared `_build_agg_geom_sql` builder, the
`build_extent_sql` builder, and the GROUP-BY-aware `_append_tail` extension.
Scope: diff against `fc5a437^`.

The locked security and parity invariants all hold:

- **T-43-01 (injection):** Every builder calls `validate_identifiers(table,
  schema, geom)` as line 1, and `validate_identifiers(*group_by)` before any
  f-string interpolates a group column. The `validate_identifier` regex
  (`^[a-zA-Z_][a-zA-Z0-9_]*$`, utils.py:13) is a strict allowlist, so the
  `t.{col}` interpolation is safe. The `extent` builder's `{int(srid)}`
  interpolation is injection-safe — a non-integer raises before SQL assembly.
  Injection tests exist for table/geom/group_by on all three builders.
- **KIND parity:** The keyword-only `*` boundary is byte-identical on the sync
  and async signatures of all three methods, and is now auto-enforced by
  `test_accessor_parameter_kind_parity` plus the named-surface
  `test_spatial_aggregates_surface`.
- **GROUP BY placement:** `_append_tail` inserts GROUP BY strictly between
  WHERE and ORDER BY (spatial.py:191-196); the ordering is asserted in three
  `*_tail_clauses`/`*_clause_ordering` tests (WHERE < GROUP BY < ORDER BY <
  LIMIT).
- **`group_by=[]` → ValueError:** Handled in all 3 sync + 3 async accessor
  methods, with guard tests for each.

No BLOCKER or Critical findings. The two WARNINGs and three INFO items below
concern test-coverage gaps and minor maintainability nits — none affect
correctness of the shipped SQL.

## Warnings

### WR-01: No `into="gdf"` integration test for `collect_geometries` / `union_aggregate`

**File:** `tests/test_spatial.py:1177-1320` (integration block), `1471-1474` (`_GDF_CALLS`)
**Issue:** `extent` has a real DB-backed `into="gdf"` integration test
(`test_extent_gdf_returns_geodataframe`) that asserts `gdf.geometry.name ==
"extent"`. The other two geometry-returning aggregates — `collect_geometries`
(column `collected`) and `union_aggregate` (column `dissolved`) — are exercised
for `into="gdf"` only by the DB-free `_GDF_CALLS` stub path, which returns the
string `"GDF"` and never executes real SQL. The `gdf` path routes through
`_run` → `_to_named_binds` → `to_geodataframe(geometry_column=...)`. A wrong
geometry-column name or a SQL shape that GeoPandas cannot load would pass every
current test. The aggregate SELECT shape (group columns + single geometry
aggregate) is genuinely new for the gdf path; it deserves a live assertion.
**Fix:** Add two integration tests mirroring `test_extent_gdf_returns_geodataframe`:
```python
def test_collect_geometries_gdf(self, sdb):
    import geopandas as gpd
    t = _uniq("spat_agg_cg_gdf")
    try:
        self._make_points(sdb, t)
        gdf = sdb.spatial.collect_geometries(t, into="gdf")
        assert isinstance(gdf, gpd.GeoDataFrame)
        assert gdf.geometry.name == "collected"
    finally:
        sdb.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)
# same for union_aggregate with geometry.name == "dissolved"
```

### WR-02: `extent(into="gdf")` on an all-NULL group is untested and may break GeoPandas

**File:** `pycopg/spatial.py:366-367`, `tests/test_spatial.py` (extent gdf tests)
**Issue:** For an all-NULL group, `ST_Extent` returns NULL, so the gdf branch
emits `ST_SetSRID(NULL::geometry, 4326) AS extent` → a NULL geometry row. The
rows-branch NULL case is covered (`test_extent_null_group` asserts
`rows[0]["extent"] is None`), but the gdf branch is not. `to_geodataframe`
loading a result whose only geometry column is NULL can raise or produce an
all-NaN geometry column depending on the GeoPandas/SQLAlchemy version. Since the
docstrings explicitly advertise "into='gdf'" as valid and "NULL inputs yield one
row with a NULL extent value", the NULL-geometry gdf path is a documented
contract surface with zero coverage.
**Fix:** Add an integration test that builds an all-NULL group and calls
`extent(group_by="region", into="gdf")`, asserting either a clean empty/NaN
geometry or the documented behavior — and adjust the implementation/docstring if
GeoPandas rejects the NULL geometry.

## Info

### IN-01: `build_extent_sql` `select_prefix` ternary is redundant vs the shared helper

**File:** `pycopg/spatial.py:370`
**Issue:** `build_extent_sql` uses
`", ".join(group_cols + [agg_expr]) if group_cols else agg_expr`, whereas the
shared `_build_agg_geom_sql` (spatial.py:109) uses the unconditional
`", ".join(group_cols + [...])`. The `if group_cols else` branch is dead weight:
`", ".join([] + [agg_expr])` already equals `agg_expr`. The divergence makes the
two builders harder to keep in lockstep.
**Fix:** Drop the conditional for consistency with `_build_agg_geom_sql`:
```python
select_prefix = ", ".join(group_cols + [agg_expr])
```

### IN-02: `docs/api-reference.md` lists keyword params in a different order than the signature

**File:** `docs/api-reference.md:216-218`
**Issue:** The reference table lists `extent` params as
`... group_by=None, srid=4326, filter=None, into="rows", order_by=None, limit=None`,
but the actual signature order is `group_by, srid, into, filter, order_by, limit`
(spatial.py:565-570). Same `filter`/`into` swap for `collect_geometries` and
`union_aggregate`. All are keyword-only so behavior is unaffected, but a
reference table that contradicts the source signature erodes trust and was
flagged as a recurring doc-drift class in prior milestones.
**Fix:** Reorder the documented params to match the source signature (`into`
before `filter`), or standardize the signature param order; pick one and apply
across the three rows.

### IN-03: `_make_grouped_with_nulls` docstring/code comment claims "mixed-NULL group" pass-through but the aggregate is over a single non-NULL row

**File:** `tests/test_spatial.py` (`_make_grouped_with_nulls` + `*_null_rows_pass_through`)
**Issue:** The "north" group has one non-NULL point + one NULL geometry. The
pass-through tests assert only that the row is present and the result key
exists — they never assert the aggregate value reflects exactly the non-NULL
input (e.g., a single-point collection, not a 2-element collection with a NULL).
The test name promises NULL pass-through semantics it does not actually verify;
a regression where NULLs are erroneously included (or the group is dropped)
would still pass. Low risk because PostGIS aggregate NULL-skipping is stable, but
the assertion is weaker than the test name implies.
**Fix:** Strengthen at least one pass-through test to assert the aggregate
content, e.g. for `collect_geometries` assert
`ST_NumGeometries(collected) == 1` for the mixed-NULL "north" group via a
follow-up query, or assert the WKT of the dissolved/collected result.

---

_Reviewed: 2026-06-29_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
