---
phase: 52-spatial-finish
verified: 2026-07-05T00:00:00Z
status: passed
score: 5/5 success criteria verified (6/6 requirement IDs SATISFIED)
overrides_applied: 0
---

# Phase 52: Spatial Finish Verification Report

**Phase Goal:** `db.spatial.*` gains fixed-precision overlay control and completes its measurement/validity/predicate helper families, with the existing overlay default path staying byte-identical.
**Verified:** 2026-07-05
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (Roadmap Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Keyword-only `gridSize=` on `union`/`difference`/`intersection`; `None` path byte-identical | ✓ VERIFIED | `_build_binary_geom_sql` (spatial.py:1793-1835) branches `if grid_size is None: expr = f"{op_func}(t.{geom}, t.{other_geom})"; params=[]` else appends `%s` 3rd arg + `[grid_size]`. Pre-existing exact-string tests `test_union_emits_st_union`/`test_difference_emits_st_difference`/`test_intersection_emits_st_intersection` (tests/test_spatial.py:963,1006,1051) assert the unchanged 2-arg SQL + empty params — left untouched as the regression guard (confirmed by diffing pre-phase-52 spatial.py: identical SQL strings). New tests `test_{union,difference,intersection}_grid_size_appends_third_arg` prove the 3-arg form. `gridSize` present on sync (spatial.py:5261-5609) and async (9091-9448) accessors with identical kw-only signature. |
| 2 | `db.spatial.length` computes length of linear geometries alongside `area`/`perimeter` | ✓ VERIFIED | `build_length_sql` (spatial.py:1132) emits `ST_Length(t.{geom}{cast}) AS length`, `unit="m"` → `::geography` cast, reuses `_validate_unit`. Accessor `length` on both `SpatialAccessor` (4476) and `AsyncSpatialAccessor` (8291), rows-only via `_SCALAR_HELPERS`. |
| 3 | `db.spatial.envelope` (per-row bbox) + `db.spatial.point_on_surface` (guaranteed-inside point), complementing `centroid` | ✓ VERIFIED | `build_envelope_sql` (2216) → `ST_Envelope(t.{geom}) AS envelope`; `build_point_on_surface_sql` (2270) → `ST_PointOnSurface(t.{geom}) AS point_on_surface`, both geometry-returning (NOT in `_SCALAR_HELPERS`), full `@overload` triplet, present on both accessor classes (sync 5845/5945, async 9690/9794). |
| 4 | `db.spatial.is_valid` + `is_valid_reason`, complementing `make_valid` | ✓ VERIFIED | `build_is_valid_sql` (1196) → `ST_IsValid(...) AS is_valid` (boolean); `build_is_valid_reason_sql` (1250) → `ST_IsValidReason(...) AS is_valid_reason` (text). Both registered in `_SCALAR_HELPERS` (2769-2781) → `into="gdf"` raises `ValueError` via `_check_into`. Present on both accessor classes (sync 4544/4606, async 8362/8427). |
| 5 | `overlaps`/`touches`/`crosses`/`disjoint` DE-9IM predicates, completing `contains`/`intersects`/`within`/`dwithin` | ✓ VERIFIED | `build_overlaps_sql`/`build_touches_sql`/`build_crosses_sql`/`build_disjoint_sql` (spatial.py:367,449,531,613) mechanically mirror `build_intersects_sql`: same 4 input forms via `_resolve_geometry`, same `EXISTS`+`_REF_SENTINEL` handling for `ref=`, same `into="rows"/"gdf"` `@overload` triplet. `disjoint` docstring carries both the `ref=` EXISTS-quantifier footgun (D-07) and the non-indexable performance note pointing to `NOT ST_Intersects`/`filter=` (D-08). All 4 present on both accessor classes (sync 3357-3838, async 7148-7638). |

**Score:** 5/5 success criteria verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `pycopg/spatial.py` — `_build_binary_geom_sql` + 3 overlay builders | `grid_size` threading, byte-identical `None` path | ✓ VERIFIED | Confirmed by direct read + diff against pre-phase-52 revision |
| `pycopg/spatial.py` — `build_length_sql`/`build_is_valid_sql`/`build_is_valid_reason_sql` | Scalar measurement/validity builders | ✓ VERIFIED | All 3 present, `validate_identifiers` line-1, registered in `_SCALAR_HELPERS` |
| `pycopg/spatial.py` — `build_envelope_sql`/`build_point_on_surface_sql` | Geometry-returning builders | ✓ VERIFIED | Present, `validate_identifiers` line-1, `@overload` triplets |
| `pycopg/spatial.py` — `build_overlaps_sql`/`build_touches_sql`/`build_crosses_sql`/`build_disjoint_sql` | DE-9IM predicate builders | ✓ VERIFIED | All 4 present, mirror `build_intersects_sql` mechanically |
| `SpatialAccessor` (sync, ~2847) + `AsyncSpatialAccessor` (async, ~6624) | All 9 new methods on both classes | ✓ VERIFIED | Grepped both classes: `length`/`is_valid`/`is_valid_reason`/`envelope`/`point_on_surface`/`overlaps`/`touches`/`crosses`/`disjoint` all present sync+async with matching overload counts |
| `tests/test_spatial.py` | Unit + routing + injection + live tests | ✓ VERIFIED | 443 tests, all pass (`PGDATABASE=pycopg_test3`) |
| `tests/test_parity.py::test_spatial_finish_surface` | Named frozenset asserting 9 methods on both classes | ✓ VERIFIED | Present at line 328, passes |
| `docs/spatial.md` | 6 helper families documented, disjoint footgun/perf note | ✓ VERIFIED | Sections present at lines 272-399, includes both D-07/D-08 disjoint warnings verbatim |
| `docs/api-reference.md` | 9 methods in Spatial Helpers table + scalar-rows-only list updated | ✓ VERIFIED | Rows present lines 293-313; scalar-only list at line 277 includes `length`/`is_valid`/`is_valid_reason` |
| `.planning/REQUIREMENTS.md` | SPAT-F01..F06 all Complete | ✓ VERIFIED | Checkboxes + traceability table both show Complete for all 6 IDs |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `union`/`difference`/`intersection` accessors | `_build_binary_geom_sql` | `grid_size=grid_size` forwarding through `build_*_sql` | ✓ WIRED | Confirmed at spatial.py:1899-1911, 1976-1988, 2053-2065 (builders) and accessor call sites (`grid_size=gridSize`) |
| `length`/`is_valid`/`is_valid_reason` | `_check_into` via `_SCALAR_HELPERS` | frozenset membership | ✓ WIRED | `_SCALAR_HELPERS` gains exactly the 3 names; `_check_into` (2793) rejects `into="gdf"` for members |
| `overlaps`/`touches`/`crosses`/`disjoint` builders | `_resolve_geometry` + `_REF_SENTINEL` | reused verbatim | ✓ WIRED | All 4 builders call `_resolve_geometry(point=, wkt=, geojson=, ref=, srid=)` and branch on `fragment == _REF_SENTINEL` identically to `build_intersects_sql` |
| `envelope`/`point_on_surface` accessors | `self._run(sql, params, into, alias)` | gdf routing passes result alias as geometry column | ✓ WIRED | Confirmed via `_GDF_CALLS` test fixture entries `("envelope", {}, "envelope")`, `("point_on_surface", {}, "point_on_surface")` and passing `TestAccessorRouting` parametrized tests |

### Behavioral Spot-Checks / Test Execution

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Spatial unit+integration suite | `PGDATABASE=pycopg_test3 uv run pytest tests/test_spatial.py -q -o addopts=""` | 443 passed | ✓ PASS |
| Parity suite (incl. `test_spatial_finish_surface`, `test_accessor_parameter_kind_parity`) | `PGDATABASE=pycopg_test3 uv run pytest tests/test_parity.py -q -o addopts=""` | 41 passed | ✓ PASS |
| Full project suite + coverage | `PGDATABASE=pycopg_test3 uv run pytest` | 2149 passed, 2 skipped, 96.78% cov (≥95% gate) | ✓ PASS |
| mypy --strict | `uv run mypy pycopg` | Success: no issues found in 18 source files | ✓ PASS |
| Zero new deps | `git diff --stat uv.lock` | empty (no diff) | ✓ PASS |
| Byte-identical default-overlay SQL (D-03, the subtlest criterion) | Diffed pre-phase-52 `spatial.py` (`git show 26b8457~1`) against current `_build_binary_geom_sql`/`build_union_sql`/`build_difference_sql`/`build_intersection_sql` None-path output; re-ran the 3 pre-existing exact-string tests unmodified | SQL strings identical, params `[]` unchanged | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|---|---|---|---|---|
| SPAT-F01 | 52-01 | `gridSize=` fixed-precision overlay, byte-identical default | ✓ SATISFIED | `_build_binary_geom_sql` + 3 builders + 6 accessors (sync+async), tests pass |
| SPAT-F02 | 52-02 | `db.spatial.length` | ✓ SATISFIED | `build_length_sql` + accessors, tests pass |
| SPAT-F03 | 52-03 | `db.spatial.envelope` | ✓ SATISFIED | `build_envelope_sql` + accessors, tests pass |
| SPAT-F04 | 52-03 | `db.spatial.point_on_surface` | ✓ SATISFIED | `build_point_on_surface_sql` + accessors, tests pass |
| SPAT-F05 | 52-02 | `is_valid` + `is_valid_reason` | ✓ SATISFIED | Both builders + accessors, `_SCALAR_HELPERS` updated |
| SPAT-F06 | 52-04, 52-05 | `overlaps`/`touches`/`crosses`/`disjoint` | ✓ SATISFIED | All 4 builders + accessors (split across 2 plans), tests pass |

No orphaned requirements found — REQUIREMENTS.md traceability table (lines 71-76) maps all 6 IDs to Phase 52 as Complete, matching the 6 IDs declared across the 6 plans' frontmatter.

### Anti-Patterns Found

| File | Line(s) | Pattern | Severity | Impact |
|------|---------|---------|----------|--------|
| `pycopg/spatial.py` | 24 occurrences across sync (5261-5609) + async (9091-9448) `gridSize` parameter declarations | Ruff `N803` (pep8-naming: "argument name should be lowercase") — `gridSize` is camelCase | ⚠️ Warning (non-blocking) | `uv run ruff check pycopg tests` (the lint command documented in `CLAUDE.md`) now fails with 24 errors. Confirmed via `git worktree` diff that the pre-phase-52 tree (`26b8457~1`) was 100% ruff-clean — this is a genuine regression introduced by this phase, not pre-existing debt. It is **not** caught by CI (`.github/workflows/tests.yml` does not invoke ruff) and is **not** one of the 5 formal release gates tracked for this milestone (coverage/mypy/interrogate/Sphinx/uv.lock), so it does not block phase acceptance, but it was not caught or mentioned by any plan/summary/review artifact (52-01..06 SUMMARYs and 52-REVIEW.md are silent on it) despite `gridSize` being a deliberate D-01 naming choice (mirrors PostGIS's own `ST_Union(a, b, gridSize)` argument name). Recommend fixing before v1.2.0 release with either a targeted `# noqa: N803` on each declaration, a `pyproject.toml` `[tool.ruff.lint.per-file-ignores]` entry, or documenting an accepted exception — a decision for the release phase (P54), not this verifier. |

No `TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER` markers, no stub returns, no empty handlers found in any file modified by this phase.

### Human Verification Required

None. This phase is purely backend/API additive (SQL builders + accessor methods); all behaviors are DB-verifiable and were verified via the automated test suite (443 spatial + 41 parity + full 2149-test suite, all passing against `PGDATABASE=pycopg_test3`).

### Gaps Summary

No gaps against the 5 roadmap success criteria or the 6 requirement IDs (SPAT-F01..F06) — all are independently verified against the actual codebase (not SUMMARY claims): builders exist, are substantive (real SQL generation with `validate_identifiers` line-1), are wired into both `SpatialAccessor` and `AsyncSpatialAccessor` with full sync/async parity, and are covered by a comprehensive test suite that passes end-to-end (443 spatial-specific tests, 41 parity tests, 2149 full-suite tests, mypy --strict 0 errors, coverage 96.78% ≥95%, zero `uv.lock` diff). The subtlest criterion — D-03 byte-identical default overlay SQL — was independently re-verified by diffing the pre-phase-52 builder source against the current implementation, not merely trusting the SUMMARY's claim.

One non-blocking quality finding surfaced independently of any plan/summary/review artifact: the new `gridSize` camelCase parameter name introduces 24 `ruff N803` lint violations (0 → 24), a genuine regression in a documented (if non-CI-gated) project convention. This does not affect functionality, security, or any of the 5 success criteria, so it does not block phase acceptance, but is flagged for follow-up (e.g., during the P54 Release phase) since no prior artifact in this phase acknowledged it.

---

_Verified: 2026-07-05_
_Verifier: Claude (gsd-verifier)_
