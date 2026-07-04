---
phase: 52-spatial-finish
reviewed: 2026-07-05T00:00:00Z
depth: standard
files_reviewed: 5
files_reviewed_list:
  - pycopg/spatial.py
  - tests/test_spatial.py
  - tests/test_parity.py
  - docs/spatial.md
  - docs/api-reference.md
findings:
  critical: 0
  warning: 0
  info: 3
  total: 3
status: issues_found
---

# Phase 52: Code Review Report

**Reviewed:** 2026-07-05
**Depth:** standard
**Files Reviewed:** 5
**Status:** issues_found (Info-only — no BLOCKER/WARNING)

## Summary

Phase 52 (Spatial Finish) adds to `pycopg/spatial.py`: (1) a keyword-only
`gridSize=` fixed-precision param on `union`/`difference`/`intersection`, threaded
through `_build_binary_geom_sql`; (2) scalar helpers `length`/`is_valid`/
`is_valid_reason`; (3) geometry-returning helpers `envelope`/`point_on_surface`
(`into="gdf"` support); (4) DE-9IM predicates `overlaps`/`touches`/`crosses`/
`disjoint`. All added to both `SpatialAccessor` and `AsyncSpatialAccessor`.

I reviewed against the five stated project priorities and traced each new SQL
builder, accessor, and overload chain end-to-end. **The implementation is clean.**
No injection, parity, default-invariance, routing, or overload defects were found.
The three findings below are all Info-level (documentation staleness and one
acknowledged, intentional design footgun).

Verification performed and passed:

1. **SQL injection (priority 1) — PASS.** Every new builder calls
   `validate_identifiers(table, schema, geom[, other_geom])` as its first
   statement, plus `validate_identifiers(*columns)` when `columns` is set. All
   user *values* are bound via `%s` (grid_size at `_build_binary_geom_sql:1827`;
   point/wkt/geojson via `_resolve_geometry`). The `ref=` EXISTS path interpolates
   `ref_table`/`ref_col` identifiers, but these are validated inside
   `_resolve_geometry` (`spatial.py:133`) before the sentinel is returned — so the
   overlaps/touches/crosses/disjoint EXISTS subqueries are safe. Only the SRID is
   interpolated, via `int(srid)` coercion. Injection tests exist for table/schema/
   geom/column/ref across all four predicates.
2. **Sync/async parity (priority 2) — PASS.** All 9 new methods exist on both
   accessors with byte-identical signatures; `gridSize: float | None = None`
   keyword-only on all 6 overlay methods (3 sync + 3 async). `grid_size=gridSize`
   threading confirmed at 6 call sites; result columns match
   (`union_geom`/`difference`/`intersection`). Async methods correctly prepend the
   established `await self._check_postgis()` guard (consistent with every existing
   async spatial method) then `_check_into`. `test_spatial_finish_surface` asserts
   the 9-method surface on both classes.
3. **Default-path invariance / D-03 (priority 3) — PASS.**
   `_build_binary_geom_sql` branches on `grid_size is None` (identity check, not
   truthiness — so `gridSize=0.0` correctly emits the 3-arg form). The `None` branch
   emits the exact pre-52 2-arg `ST_Union(t.a, t.b)` expression with `params=[]`.
   Pre-existing `test_union_emits_st_union` etc. still assert the 2-arg form.
4. **DE-9IM `into="gdf"`/`ref=` routing + disjoint EXISTS semantics (priority 4)
   — PASS.** Predicates pass the table's own `geom` as the GeoDataFrame geometry
   column; `envelope`/`point_on_surface` correctly pass their computed alias
   (`"envelope"`/`"point_on_surface"`). `length`/`is_valid`/`is_valid_reason` are
   all present in `_SCALAR_HELPERS` (`spatial.py:2769`), so `into="gdf"` is rejected
   with `ValueError` as documented. The `disjoint(ref=...)` existential-quantifier
   behavior is intentional (D-07) and heavily warned — see IN-03.
5. **mypy-strict `@overload` stubs (priority 5) — PASS.** Geometry-returning and
   predicate methods carry the standard 3-overload pattern (`Literal["rows"]`
   default → `list[dict]`; `Literal["gdf"]` no-default → `GeoDataFrame`; `str` →
   union). Scalar helpers correctly carry no overloads and a `cast(...)` on the
   `_run` result, mirroring `area`/`perimeter`.

## Info

### IN-01: Overlay builder docstring summary "No `%s` parameters are emitted" is now stale

**File:** `pycopg/spatial.py:1853` (`build_union_sql`), `pycopg/spatial.py:1929`
(`build_difference_sql`), `pycopg/spatial.py:2007` (`build_intersection_sql`)
**Issue:** Each builder's summary sentence still states "No ``%s`` parameters are
emitted — both geometry columns are identifier-validated and interpolated directly
into the SQL." With the new `grid_size=` path this is no longer true: when
`grid_size` is set the builder emits `ST_Union(a, b, %s)` and returns
`params=[grid_size]`. The dedicated `grid_size` parameter paragraph below correctly
documents the `%s` binding, so the two statements contradict each other. A
maintainer reading only the summary would be misled.
**Fix:** Soften the summary sentence, e.g. "No ``%s`` parameters are emitted unless
`grid_size` is set (see below)." in all three builders.

### IN-02: Async-usage helper count in docs is stale ("All 11 helpers")

**File:** `docs/spatial.md:406`
**Issue:** The Async Usage section still reads "All 11 helpers are available on
`async_db.spatial`…". The accessor exposed ~25 methods before Phase 52 and ~34
after this phase's 9 additions, so "11" grossly undercounts. Phase 52 edited this
file extensively (adding the six new helper-family sections) but left the count
stale. (Pre-existing debt, but the phase touched this file.)
**Fix:** Replace "All 11 helpers" with a non-numeric phrasing such as "Every
`db.spatial.*` helper is available on `async_db.spatial` with the same signature",
which avoids future drift.

### IN-03: `disjoint(ref=...)` existential-quantifier footgun (intentional, documented — surfaced for the record)

**File:** `pycopg/spatial.py:694-699` (`build_disjoint_sql`), accessor at
`pycopg/spatial.py:3818` / `pycopg/spatial.py:7562`
**Issue:** The `ref=` form emits `EXISTS (SELECT 1 FROM ref AS _ref WHERE
ST_Disjoint(_ref.col, t.geom))`, which is true as soon as **any** reference row is
disjoint from the current row (near-always true for a sparse reference table) —
not "disjoint from all reference rows", which is the intuitive user expectation.
This is a deliberate decision (D-07: keep the EXISTS pattern uniform across all
predicates rather than special-casing `NOT EXISTS`) and is extensively warned in
the builder docstring, the accessor docstrings (sync + async), and
`docs/spatial.md`, with a dedicated live "footgun" test (commit `8cf3d24`). Recorded
as Info only — not a defect, since the semantics are ratified, documented, and
tested. No action required; flagged so the surprising semantics are on the record
for downstream reviewers.
**Fix:** None required. Optionally, consider a future keyword (e.g.
`quantifier="any"|"all"`) if user confusion materializes; out of scope for Phase 52.

---

_Reviewed: 2026-07-05_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
