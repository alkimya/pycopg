---
phase: 52-spatial-finish
plan: 04
subsystem: database
tags: [postgis, spatial, sql-builder, geometry, de-9im]

# Dependency graph
requires: []
provides:
  - "db.spatial.overlaps (ST_Overlaps) — DE-9IM predicate, sync+async, into=rows/gdf"
  - "db.spatial.touches (ST_Touches) — DE-9IM predicate, sync+async, into=rows/gdf"
  - "build_overlaps_sql / build_touches_sql pure builders"
affects: [52-spatial-finish, spatial.py]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "DE-9IM predicate builder: mechanical copy of build_intersects_sql (4 input forms via _resolve_geometry, EXISTS subquery for ref= via _REF_SENTINEL, validate_identifiers first, has_where=True tail) — only the ST_* function name swapped"
    - "Predicate accessor: full @overload triplet (Literal['rows']->list[dict], Literal['gdf']->GeoDataFrame, str->union) mirroring intersects, born-clean (no where= shim, no DeprecationWarning block), _run(sql, params, into, geom) uses the table's own geometry column"

key-files:
  created: []
  modified:
    - pycopg/spatial.py
    - tests/test_spatial.py

key-decisions:
  - "D-06 (amended): overlaps/touches carry the same into=rows/gdf @overload triplet as the shipped intersects/contains/dwithin — the original CONTEXT.md '(no into=)' parenthetical was a factual error, corrected during plan-phase"
  - "Predicates are NOT added to _SCALAR_HELPERS — they are row-filters (full row incl. geometry), gdf uses the table's own geom column, not a computed alias"

patterns-established:
  - "Born-clean DE-9IM predicate: no where= parameter, full @overload triplet, both SpatialAccessor and AsyncSpatialAccessor gain identical kw-only signatures; async mirror is a 1:1 await mirror (no _check_postgis at builder level — check happens in the accessor)"

requirements-completed: [SPAT-F06]

# Metrics
duration: ~20min
completed: 2026-07-04
---

# Phase 52 Plan 04: Overlaps + Touches DE-9IM Predicates Summary

**Added `db.spatial.overlaps` (ST_Overlaps) and `db.spatial.touches` (ST_Touches) as mechanical copies of the shipped `intersects` predicate — same 4 input forms (point/wkt/geojson/ref), same EXISTS subquery for `ref=`, same `into="rows"/"gdf"` overload triplet (amended D-06) — completing part 1 of 2 of the `contains`/`intersects`/`overlaps`/`touches`/`within`/`dwithin` predicate family (SPAT-F06).**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-07-04
- **Completed:** 2026-07-04
- **Tasks:** 3
- **Files modified:** 2

## Accomplishments

- Added `build_overlaps_sql` and `build_touches_sql` pure module-level builders to `pycopg/spatial.py`, placed directly after `build_intersects_sql` — mechanical copies with `validate_identifiers` first, `_resolve_geometry` reused verbatim for the 4 input forms, `_REF_SENTINEL` EXISTS-subquery handling reused verbatim, `has_where=True` tail. Only the ST_* function name differs (`ST_Overlaps`/`ST_Touches` vs `ST_Intersects`).
- Added `overlaps` and `touches` accessor methods to both `SpatialAccessor` and `AsyncSpatialAccessor`, placed directly after the `intersects` accessor in each class. Each carries the full 3-way `@overload` triplet (`Literal["rows"]` → `list[dict]`, `Literal["gdf"]` → `gpd.GeoDataFrame`, `str` → union), mirroring `intersects`' structure but **born-clean**: no `where=` parameter, no `DeprecationWarning` shim block (unlike `intersects`, which still carries the pre-1.0 `where=`→`filter=` shim). Both return `self._run(sql, params, into, geom)` — the predicate's own row geometry column, matching `intersects`/`contains`/`dwithin`'s `_GDF_CALLS` entry of `"geometry"`. Async mirrors call `await self._check_postgis()` first (parity with async `intersects`/`envelope`/`convex_hull`).
- Added `TestBuilders` exact-string tests for both builders covering all 4 input forms (point/wkt/geojson/ref-EXISTS) plus tail clauses (`columns=`/`filter=`/`order_by=`/`limit=`), and dedicated injection tests (invalid `table`/`schema`/`geom`/`columns` → `InvalidIdentifierError`, plus invalid `ref=` identifier). Extended `_HELPER_CALLS` with `("overlaps", {"point": (1, 2)})` and `("touches", {"point": (1, 2)})`, and `_GDF_CALLS` with both mapped to `"geometry"` — so `TestAccessorRouting`'s parametrized sync/async rows+gdf tests auto-cover the new predicates (30 new/auto-covering tests total for overlaps+touches, verified via `-k "overlaps or touches"`).

## Task Commits

Each task was committed atomically:

1. **Task 1: Add build_overlaps_sql + build_touches_sql, mirroring build_intersects_sql (D-06)** - `a0add9b` (feat)
2. **Task 2: Add overlaps + touches accessors with @overload triplets + into=rows/gdf, both classes** - `1600620` (feat)
3. **Task 3: Tests — builder strings (4 input forms), rows+gdf routing, injection** - `507cc27` (test)

**Plan metadata:** (pending — this commit)

## Files Created/Modified

- `pycopg/spatial.py` - 2 new pure builders (`build_overlaps_sql`/`build_touches_sql`), 2 new sync + 2 new async accessor methods (4 total) each with a full `@overload` triplet
- `tests/test_spatial.py` - 30 new `TestBuilders` tests (15 per predicate: 4 input forms + 4 injection variants + tail clauses), `_HELPER_CALLS`/`_GDF_CALLS` +2 entries each (auto-extending `TestAccessorRouting`'s parametrized sync/async rows+gdf coverage)

## Decisions Made

- Followed 52-CONTEXT.md amended D-06 and 52-RESEARCH.md Pattern 5 exactly — `overlaps`/`touches` mirror `build_intersects_sql`/`intersects` mechanically, including the `into=`/`@overload`/gdf support (the research-flagged and user-confirmed correction to the original CONTEXT.md "(no into=)" text).
- Placed the new builders immediately after `build_intersects_sql` and the new accessors immediately after the `intersects` accessor in both classes (predicate-family grouping, matching `contains`→`intersects`→(now)`overlaps`→`touches`→`within`→`dwithin` ordering).
- Neither `overlaps` nor `touches` was added to `_SCALAR_HELPERS` — they are row-filter predicates (matching `contains`/`intersects`/`dwithin`), not scalar-column helpers; `into="gdf"` is valid and uses the table's own geometry column (`geom` param), not a computed alias.
- Split the single-file diff into 3 precise commits via targeted `git apply --cached` on individual diff hunks (builders hunk isolated from the two accessor-class hunks), since both tasks touched the same file with no overlapping regions.

## Deviations from Plan

**1. [Process correction] REQUIREMENTS.md `SPAT-F06` checkbox reverted from premature "Complete"**

- **Found during:** state-update step (after `requirements.mark-complete`)
- **Issue:** This plan's frontmatter lists `requirements: [SPAT-F06]`, but SPAT-F06 covers all four DE-9IM predicates (`overlaps`/`touches`/`crosses`/`disjoint`); this plan (52-04) only ships `overlaps`/`touches` — `crosses`/`disjoint` are Plan 52-05's scope. Running `requirements.mark-complete SPAT-F06` per the standard protocol flipped the checkbox to `[x]`/"Complete" even though half the requirement is unimplemented.
- **Fix:** Manually reverted `.planning/REQUIREMENTS.md` SPAT-F06 checkbox to `[ ]` and traceability status to "In Progress (overlaps/touches done, Plan 52-04; crosses/disjoint pending, Plan 52-05)", with a note in the requirement description. Plan 52-05 will legitimately flip it to Complete once `crosses`/`disjoint` ship.
- **Files modified:** `.planning/REQUIREMENTS.md`
- **Commit:** folded into this plan's final metadata commit

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- SPAT-F06 part 1 of 2 complete (overlaps/touches). Remaining SPAT-F06 work (crosses/disjoint DE-9IM predicates) is plan 52-05/52-06 — an independent, mechanically identical addition to `pycopg/spatial.py`, following the exact same pattern established here.
- Full suite green: 2117 passed, 2 skipped, coverage 96.74% (gate ≥95%); mypy --strict 0 errors/18 files; interrogate 100%; `git diff --stat uv.lock pyproject.toml` empty (zero new deps).

---
*Phase: 52-spatial-finish*
*Completed: 2026-07-04*

## Self-Check: PASSED

- FOUND: pycopg/spatial.py
- FOUND: tests/test_spatial.py
- FOUND: .planning/phases/52-spatial-finish/52-04-SUMMARY.md
- FOUND: commit a0add9b (Task 1)
- FOUND: commit 1600620 (Task 2)
- FOUND: commit 507cc27 (Task 3)
