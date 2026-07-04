---
phase: 52-spatial-finish
plan: 05
subsystem: database
tags: [postgis, spatial, sql-builder, geometry, de-9im]

# Dependency graph
requires: ["52-04"]
provides:
  - "db.spatial.crosses (ST_Crosses) — DE-9IM predicate, sync+async, into=rows/gdf"
  - "db.spatial.disjoint (ST_Disjoint) — DE-9IM predicate, sync+async, into=rows/gdf, ref= EXISTS-quantifier footgun + non-indexable perf docstring"
  - "build_crosses_sql / build_disjoint_sql pure builders"
affects: [52-spatial-finish, spatial.py]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "DE-9IM predicate builder: mechanical copy of build_intersects_sql/build_overlaps_sql (4 input forms via _resolve_geometry, EXISTS subquery for ref= via _REF_SENTINEL, validate_identifiers first, has_where=True tail) — only the ST_* function name swapped"
    - "Predicate accessor: full @overload triplet (Literal['rows']->list[dict], Literal['gdf']->GeoDataFrame, str->union) mirroring intersects/overlaps/touches, born-clean (no where= shim, no DeprecationWarning block), _run(sql, params, into, geom) uses the table's own geometry column"
    - "disjoint stays mechanically uniform: ref= uses the SAME EXISTS(...) form as every other predicate (D-07) — NOT special-cased into NOT EXISTS"

key-files:
  created: []
  modified:
    - pycopg/spatial.py
    - tests/test_spatial.py
    - .planning/REQUIREMENTS.md

key-decisions:
  - "D-07 confirmed and implemented: disjoint(ref=...) keeps the uniform EXISTS(... ST_Disjoint ...) form; a dedicated test asserts 'NOT EXISTS' is absent from the emitted SQL"
  - "D-08 confirmed and implemented: disjoint docstring (builder + both accessors) cites the postgis.net 'does not use indexes' text verbatim and points to NOT ST_Intersects / filter= as the indexable alternative"
  - "Predicates NOT added to _SCALAR_HELPERS — they are row-filters (full row incl. geometry), gdf uses the table's own geom column, not a computed alias"
  - "SPAT-F06 marked Complete in REQUIREMENTS.md — this plan closes the requirement opened by 52-04 (overlaps/touches) with crosses/disjoint"

patterns-established:
  - "Born-clean DE-9IM predicate: no where= parameter, full @overload triplet, both SpatialAccessor and AsyncSpatialAccessor gain identical kw-only signatures; async mirror awaits self._check_postgis() first (parity with async overlaps/touches/intersects)"

requirements-completed: [SPAT-F06]

# Metrics
duration: ~11min
completed: 2026-07-04
---

# Phase 52 Plan 05: Crosses + Disjoint DE-9IM Predicates Summary

**Added `db.spatial.crosses` (ST_Crosses) and `db.spatial.disjoint` (ST_Disjoint) as mechanical copies of the shipped `intersects`/`overlaps`/`touches` predicates — same 4 input forms, same EXISTS subquery for `ref=`, same `into="rows"/"gdf"` overload triplet — completing part 2 of 2 of the `contains`/`intersects`/`overlaps`/`touches`/`within`/`dwithin` predicate family (SPAT-F06, now fully shipped). `disjoint` carries two mandatory docstring warnings: the `ref=` EXISTS-quantifier footgun (D-07, proven live) and the non-indexable performance note pointing to `NOT ST_Intersects` (D-08, cited verbatim from postgis.net).**

## Performance

- **Duration:** ~11 min
- **Started:** 2026-07-04
- **Completed:** 2026-07-04
- **Tasks:** 3
- **Files modified:** 3 (2 code/test files + REQUIREMENTS.md)

## Accomplishments

- Added `build_crosses_sql` and `build_disjoint_sql` pure module-level builders to `pycopg/spatial.py`, placed directly after `build_touches_sql` — mechanical copies with `validate_identifiers` first, `_resolve_geometry` reused verbatim for the 4 input forms, `_REF_SENTINEL` EXISTS-subquery handling reused verbatim, `has_where=True` tail. Only the ST_* function name differs (`ST_Crosses`/`ST_Disjoint` vs `ST_Overlaps`/`ST_Touches`/`ST_Intersects`). `build_disjoint_sql` keeps the SAME uniform `EXISTS(... ST_Disjoint ...)` form for `ref=` — no `NOT EXISTS` special-case (D-07) — and its docstring documents the `ref=` footgun plus the non-indexable perf note (D-08).
- Added `crosses` and `disjoint` accessor methods to both `SpatialAccessor` and `AsyncSpatialAccessor`, placed directly after the `touches` accessor in each class. Each carries the full 3-way `@overload` triplet (`Literal["rows"]` → `list[dict]`, `Literal["gdf"]` → `gpd.GeoDataFrame`, `str` → union), mirroring `overlaps`/`touches`' structure but **born-clean**: no `where=` parameter, no `DeprecationWarning` shim block. Both return `self._run(sql, params, into, geom)` — the predicate's own row geometry column, matching `intersects`/`overlaps`/`touches`'s `_GDF_CALLS` entry of `"geometry"`. Async mirrors call `await self._check_postgis()` first (parity with async `overlaps`/`touches`). The `disjoint` docstring on BOTH accessors (sync + async) has a `Warnings` section stating: "the `ref=` form means EXISTS a ref row disjoint from t... NOT disjoint from all reference rows" (D-07) and "`ST_Disjoint` does not use indexes [postgis.net/docs/ST_Disjoint.html: \"This function call does not use indexes\"]... use a negated `NOT ST_Intersects` predicate instead — e.g. via the `filter=` escape hatch" (D-08).
- Added `TestBuilders` exact-string tests for both builders covering all 4 input forms (point/wkt/geojson/ref-EXISTS) plus tail clauses (`columns=`/`filter=`/`order_by=`/`limit=`), and dedicated injection tests (invalid `table`/`schema`/`geom`/`columns` → `InvalidIdentifierError`, plus invalid `ref=` identifier). The `disjoint` ref= test additionally asserts `"NOT EXISTS" not in sql` to positively prove the uniform-EXISTS decision (D-07) at the string level. Extended `_HELPER_CALLS` with `("crosses", {"point": (1, 2)})` and `("disjoint", {"point": (1, 2)})`, and `_GDF_CALLS` with both mapped to `"geometry"` — auto-covering `TestAccessorRouting`'s parametrized sync/async rows+gdf tests. Added a new `TestIntegration` live-DB test (`test_disjoint_ref_existence_quantifier_footgun`) that proves the D-07 footgun with a real assertion, not just a description: a point that genuinely `ST_Intersects` one reference zone is still returned by `disjoint(ref=...)`, because a second, unrelated reference zone is disjoint from it (EXISTS, not ALL).

## Task Commits

Each task was committed atomically:

1. **Task 1: Add build_crosses_sql + build_disjoint_sql, mirroring build_intersects_sql (D-06)** - `847bb96` (feat)
2. **Task 2: Add crosses + disjoint accessors + disjoint footgun/perf docstrings, both classes (D-06/D-07/D-08)** - `154fada` (feat)
3. **Task 3: Tests — builder strings, rows+gdf routing, injection, live disjoint EXISTS footgun proof** - `8cf3d24` (test)

**Plan metadata:** (pending — this commit)

## Files Created/Modified

- `pycopg/spatial.py` - 2 new pure builders (`build_crosses_sql`/`build_disjoint_sql`), 2 new sync + 2 new async accessor methods (4 total), each with a full `@overload` triplet; `disjoint` docstrings (builder + both accessors) carry the D-07/D-08 warnings
- `tests/test_spatial.py` - 32 new `TestBuilders` tests (16 per predicate: 4 input forms + 4 injection variants + 2 tail-clause tests + 1 extra disjoint uniform-EXISTS assertion), `_HELPER_CALLS`/`_GDF_CALLS` +2 entries each, 1 new live `TestIntegration` test proving the D-07 EXISTS-quantifier footgun
- `.planning/REQUIREMENTS.md` - SPAT-F06 checkbox flipped to Complete (all 4 DE-9IM predicates now shipped across Plans 52-04/52-05); traceability row updated

## Decisions Made

- Followed 52-CONTEXT.md D-06/D-07/D-08 and 52-RESEARCH.md Pattern 5 exactly — `crosses`/`disjoint` mirror `build_intersects_sql`/`intersects` (and the just-shipped `overlaps`/`touches`) mechanically, including the `into=`/`@overload`/gdf support.
- `disjoint(ref=...)` was NOT special-cased into `NOT EXISTS(...)` — kept the family mechanically uniform per D-07, with the footgun documented (not code-guarded) and proven by a live test.
- Placed the new builders immediately after `build_touches_sql` and the new accessors immediately after the `touches` accessor in both classes (predicate-family grouping: `contains`→`intersects`→`overlaps`→`touches`→(now)`crosses`→`disjoint`→`within`→`dwithin`).
- Neither `crosses` nor `disjoint` was added to `_SCALAR_HELPERS` — they are row-filter predicates (matching `overlaps`/`touches`/`intersects`/`contains`/`dwithin`), not scalar-column helpers; `into="gdf"` is valid and uses the table's own geometry column (`geom` param), not a computed alias.
- Adjusted the D-08 docstring wording (builder + both accessors) mid-task so the literal substrings "does not use indexes" and "disjoint from all" appear verbatim, matching the plan's `verify` grep exactly (an initial draft used "does not use\nspatial indexes" wrapped across a line break and "disjoint from ALL" uppercase, which would not have matched a literal grep).
- This plan's frontmatter lists `requirements: [SPAT-F06]`; unlike Plan 52-04 (which had to revert a premature completion because it only shipped half the predicate family), this plan legitimately completes SPAT-F06 — `requirements.mark-complete SPAT-F06` was run and is correct as-is.

## Deviations from Plan

None — plan executed exactly as written. One in-flight self-correction: the initial `disjoint` docstring wording used line-wrapped/uppercase variants of the D-08 warning text that would not have satisfied the plan's literal `grep -n "does not use indexes\|disjoint from all"` verify command; reworded (still fully faithful to D-07/D-08's substance) before running the verify step, tracked above as a Decision rather than a Rule 1 bug since no test or behavior was broken — it was caught before the verify step ran, not after a test failure.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- SPAT-F06 fully complete (all 4 DE-9IM predicates: `overlaps`/`touches` from Plan 52-04, `crosses`/`disjoint` from this plan). Phase 52 (Spatial Finish) requirements SPAT-F01 through SPAT-F06 are now all shipped (Plans 52-01 through 52-05, 5 of 6 plans).
- Full suite green: 2148 passed, 2 skipped, coverage 96.78% (gate ≥95%); mypy --strict 0 errors/18 files; interrogate 100%; `git diff --stat uv.lock pyproject.toml` empty (zero new deps).
- Remaining Phase 52 work (if any 6th plan is a phase-closing/verification plan) can proceed — the spatial predicate family and all measurement/processing helpers (SPAT-F01..F06) are complete.

---
*Phase: 52-spatial-finish*
*Completed: 2026-07-04*

## Self-Check: PASSED

- FOUND: pycopg/spatial.py
- FOUND: tests/test_spatial.py
- FOUND: .planning/phases/52-spatial-finish/52-05-SUMMARY.md
- FOUND: commit 847bb96 (Task 1)
- FOUND: commit 154fada (Task 2)
- FOUND: commit 8cf3d24 (Task 3)
