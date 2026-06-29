---
phase: 42-spatial-v2-processing-helpers
verified: 2026-06-29T12:00:00Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
---

# Phase 42: Spatial v2 — Processing Helpers Verification Report

**Phase Goal:** Users can perform the 6 core pairwise and unary geometry processing operations on PostGIS tables without writing raw SQL.
**Verified:** 2026-06-29
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | User can call `db.spatial.union/difference/intersection(table, geom, other_geom=...)` to get pairwise geometry results without raw SQL; both sync and async variants return identical shape | VERIFIED | `SpatialAccessor.union/difference/intersection` at lines 2509/2577/2645 and `AsyncSpatialAccessor.union/difference/intersection` at lines 4021/4092/4163 of `pycopg/spatial.py`; identical kw-only signatures; 36 SQL-shape + routing + injection tests pass (DB-free); `test_accessor_parity` + `test_accessor_parameter_kind_parity` green (15 passed) |
| 2 | User can call `db.spatial.simplify(table, geom, tolerance)` (ST_SimplifyPreserveTopology default) and `db.spatial.convex_hull(table, geom)` to get derived geometry columns | VERIFIED | `build_simplify_sql` line 1185 defaults to `ST_SimplifyPreserveTopology` (1 param, no NULL collapse); `build_convex_hull_sql` line 1275 emits `ST_ConvexHull AS convex_hull`; sync/async accessors at lines 2714/2793 and 4235/4317; `test_simplify_preserve_topology_default` + `test_convex_hull_emits_st_convex_hull` verify exact SQL strings |
| 3 | User can repair invalid geometries via `db.spatial.make_valid(table, geom, method=None)` with a whitelist-enforced method parameter; `method="structure"` documented as requiring PostGIS >= 3.2 | VERIFIED | `build_make_valid_sql` line 1329: `_VALID_MAKE_VALID_METHODS = {None, "linework", "structure"}` at line 1182; whitelist guard raises `ValueError` (tested by `test_make_valid_invalid_method`); `docs/stability.md` lines 248-252 carry the D-04 PostGIS >= 3.2 note; sync/async accessors at lines 2854/4381 |
| 4 | Passing a malicious identifier to any new builder raises `InvalidIdentifierError` before any SQL is sent (dedicated injection test per builder) | VERIFIED | `validate_identifiers` is LINE 1 of `_build_binary_geom_sql` (line 971) and of `build_simplify_sql` (line 1252), `build_convex_hull_sql` (line 1318), `build_make_valid_sql` (line 1401) — each carries the `# LINE 1 — security invariant` comment; 6 per-builder injection tests confirmed present (`test_union_invalid_table`, `test_difference_invalid_table`, `test_intersection_invalid_table`, `test_simplify_invalid_table`, `test_convex_hull_invalid_table`, `test_make_valid_invalid_table`); DB-free run: 62 passed 0 failures |
| 5 | Every new method has a working `AsyncSpatialAccessor` equivalent with identical signature, confirmed by `test_accessor_parity` | VERIFIED | 6 `async def` methods confirmed (`async def union/difference/intersection/simplify/convex_hull/make_valid` at lines 4021/4092/4163/4235/4317/4381); `test_spatial_v1_processing_surface` frozenset assertion passes; `test_accessor_parity` + `test_accessor_parameter_kind_parity` — 15 passed |

**Score:** 5/5 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `pycopg/spatial.py` | `_build_binary_geom_sql` + 3 binary builders + 3 unary builders + 6 sync + 6 async accessor methods | VERIFIED | All 14 symbols confirmed. Binary builders share `_build_binary_geom_sql` DRY helper. `_VALID_MAKE_VALID_METHODS` constant at line 1182. `_SCALAR_HELPERS` unchanged (frozenset{"area","perimeter","distance","centroid"}). No `where=` on new methods, no `gridSize` emitted. |
| `tests/test_spatial.py` | SQL-shape + per-builder injection + routing registry + live integration tests | VERIFIED | `test_union_emits_st_union`, `test_difference_emits_st_difference`, `test_intersection_emits_st_intersection` at lines 475/509/543 confirm exact SQL. `test_simplify_preserve_topology_default`, `test_convex_hull_emits_st_convex_hull`, `test_make_valid_linework` + all `make_valid` params-string variants confirmed. All 6 per-builder injection tests present. `_HELPER_CALLS`/`_GDF_CALLS` registries contain union/difference/intersection/simplify/convex_hull/make_valid entries at lines 1239-1260. |
| `tests/test_parity.py` | `test_spatial_v1_processing_surface` frozenset surface test | VERIFIED | Present at line 135 with `v42_surface = frozenset({"union","difference","intersection","simplify","convex_hull","make_valid"})`. Asserts both `SpatialAccessor` and `AsyncSpatialAccessor` expose all 6 methods. Passes (1 passed). |
| `docs/stability.md` | 6 new Stable API Contract rows + make_valid structure >= 3.2 note | VERIFIED | Lines 109-114: all 6 method rows present with kw-only param contracts. Lines 248-252: D-04 version note (`ST_MakeValid(method="structure")` requires PostGIS >= 3.2 / GEOS >= 3.10). |
| `docs/api-reference.md` | 6 new rows using `filter=` (not `where=`) | VERIFIED | Lines 210-215: all 6 rows present with `filter=None` in signatures; confirmed no `where=` on new rows. |
| `README.md` | Updated spatial method count | VERIFIED | Line 89: `(19 methods)` — updated from previous 13. |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `SpatialAccessor.union` | `build_union_sql` | delegation then `_run(sql, params, into, "union_geom")` | WIRED | Line 2565-2575 confirmed |
| `SpatialAccessor.make_valid` | `build_make_valid_sql` | delegation then `_run(sql, params, into, "made_valid")` | WIRED | Lines 2915-2932 confirmed |
| `AsyncSpatialAccessor.union` | `build_union_sql` | `await _check_postgis()` then builder then `await _run` | WIRED | Lines 4078-4090 confirmed |
| `_build_binary_geom_sql` | `validate_identifiers` | line 1 of helper | WIRED | Line 971: `validate_identifiers(table, schema, geom, other_geom)` |
| `build_simplify_sql` | `validate_identifiers` | line 1 of builder | WIRED | Line 1252 with `# LINE 1 — security invariant` comment |
| `build_make_valid_sql` | `validate_identifiers` | line 1, then whitelist check | WIRED | Line 1401 validate, lines 1405-1416 whitelist + contradictory-arg guards |
| `test_spatial_v1_processing_surface` | `SpatialAccessor`/`AsyncSpatialAccessor` | frozenset subset check via `inspect.getmembers` | WIRED | Line 160-167 confirmed |

---

### Data-Flow Trace (Level 4)

All 6 methods are processing helpers that generate SQL and delegate to `_run`/`_arun`, which call the DB via `Database.execute` or `Database.to_geodataframe`. The data flows: user call → `_check_into` → `build_*_sql` (returns SQL + params) → `_run/_arun` → DB execution → result rows. No hardcoded empty returns. Binary builders return `params=[]` (identifiers in SQL, no user values); simplify/make_valid bind user values through `%s` (tolerance float, params string). The routing registries `_HELPER_CALLS`/`_GDF_CALLS` confirm all 6 ops exercise the parametrized routing tests that call the real accessor dispatch path.

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| SQL-shape + injection (DB-free) | `uv run pytest tests/test_spatial.py -k "union or difference or intersection or simplify or convex_hull or make_valid" -o addopts="" -q` | 62 passed, 13 skipped (live integration skipped without DB) | PASS |
| Parity surface + kind parity | `uv run pytest tests/test_parity.py::test_spatial_v1_processing_surface tests/test_parity.py::test_accessor_parity tests/test_parity.py::test_accessor_parameter_kind_parity -o addopts="" -q` | 15 passed | PASS |
| Ruff lint | `uv run ruff check pycopg/spatial.py tests/test_spatial.py tests/test_parity.py` | All checks passed | PASS |

---

### Probe Execution

No `scripts/*/tests/probe-*.sh` probes declared for this phase. Phase-level verification uses pytest.

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| SPAT2-01 | 42-01, 42-03 | Pairwise union via `db.spatial.union` (ST_Union) | SATISFIED | `build_union_sql` + `SpatialAccessor.union` + `AsyncSpatialAccessor.union` confirmed; injection + parity tests green |
| SPAT2-02 | 42-02, 42-03 | Simplify via `db.spatial.simplify` (ST_SimplifyPreserveTopology default) | SATISFIED | `build_simplify_sql` defaults to `ST_SimplifyPreserveTopology`; `test_simplify_preserve_topology_default` asserts exact SQL |
| SPAT2-03 | 42-02, 42-03 | Convex hull via `db.spatial.convex_hull` (ST_ConvexHull) | SATISFIED | `build_convex_hull_sql` + accessors; `test_convex_hull_emits_st_convex_hull` confirmed |
| SPAT2-04 | 42-02, 42-03 | Repair via `db.spatial.make_valid` (ST_MakeValid, method whitelist, structure >= 3.2 documented) | SATISFIED | `_VALID_MAKE_VALID_METHODS` whitelist; D-04 note in `docs/stability.md` lines 248-252; `test_make_valid_invalid_method` tests whitelist enforcement |
| SPAT2-05 | 42-01, 42-03 | Pairwise difference via `db.spatial.difference` (ST_Difference) | SATISFIED | `build_difference_sql` + accessors confirmed; injection test present |
| SPAT2-06 | 42-01, 42-03 | Pairwise intersection via `db.spatial.intersection` (ST_Intersection) | SATISFIED | `build_intersection_sql` + accessors confirmed; injection test present |

No orphaned requirements: SPAT2-01..06 are all mapped to Phase 42 in REQUIREMENTS.md traceability table and all marked `[x]` (Complete).

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | — | — | No TBD/FIXME/XXX markers; no stubs; no empty handlers; no hardcoded empty returns in new code |

Checked files: `pycopg/spatial.py`, `tests/test_spatial.py`, `tests/test_parity.py`, `docs/stability.md`, `docs/api-reference.md`. Zero debt markers. `_VALID_MAKE_VALID_METHODS` is a set (not frozenset) at line 1182 — this is intentional (the plan specified `frozenset/set`) and has no security or correctness impact since it is only used in a membership check.

---

### Human Verification Required

None. All success criteria are verifiable programmatically via code inspection and DB-free test execution.

---

## Gaps Summary

No gaps. All 5 must-have truths are VERIFIED, all required artifacts exist and are substantive and wired, all 6 REQUIREMENTS IDs are satisfied, no debt markers, no stubs.

The DB-backed live integration tests (mixed-SRID raise, `into="gdf"` GeoDataFrame, bowtie make_valid, simplify preserve_topology, make_valid structure) were reported green by the executor (91-test targeted subset confirmed green). These tests are present in `tests/test_spatial.py::TestIntegration` and are skipped when no DB is available — the DB-free SQL-shape and injection layers are the authoritative correctness signal per the D-08 two-layer test strategy.

---

_Verified: 2026-06-29T12:00:00Z_
_Verifier: Claude (gsd-verifier)_
