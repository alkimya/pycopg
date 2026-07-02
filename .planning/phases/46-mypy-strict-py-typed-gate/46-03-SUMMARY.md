---
phase: 46-mypy-strict-py-typed-gate
plan: 03
subsystem: typing
tags: [mypy, mypy-strict, typing, overload, kind-parity, spatial]

# Dependency graph
requires:
  - phase: 46-mypy-strict-py-typed-gate
    plan: 01
    provides: "strict = true + warn_unreachable = true single source of truth (D-04); 356-error/15-file baseline"
  - phase: 46-mypy-strict-py-typed-gate
    plan: 02
    provides: "10 foundation/leaf modules at 0 strict errors; package-wide 356 -> 303; D-03 pragmatic-Any + D-01 narrow-ignore precedents"
provides:
  - "spatial.py (the largest strict hotspot) at 0 mypy strict errors — package-wide 303 -> 187"
  - "96 @overload stubs (48 sync + 48 async, symmetric) giving downstream mypy --strict callers precise list[dict[str, Any]] / gpd.GeoDataFrame return types on all 16 polymorphic into= methods"
  - "D-03 pragmatic-Any applied to every module-level SQL builder + _run/_run_mvt/_arun_mvt/_to_named_binds helper"
affects: [46-04, 46-05, 46-06, 46-07]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "@overload triplet pattern for into= polymorphism: Literal[\"rows\"] = \"rows\" -> list[dict[str, Any]], Literal[\"gdf\"] (no default, required) -> gpd.GeoDataFrame, bare str (runtime-variable fallback) -> the union — real implementation keeps the union return and its own into: str = \"rows\" default. First use of @overload in the codebase; precedent for timescale.py (46-04+)."
    - "Scalar-helper narrowing via cast(): the 6 into=-bearing-but-scalar-only helpers (distance/area/perimeter/centroid/as_geojson/as_text) call the same self._run() as the polymorphic methods, so _run's static return type is always the union — even though _check_into() already raises ValueError for into=\"gdf\" on these at runtime. Rather than adding overloads to scalar helpers (explicitly excluded by the plan) or loosening their return type to the union, narrowed the single return site with cast(\"list[dict[str, Any]]\", self._run(...)) plus a one-line comment citing the runtime guarantee. Zero # type: ignore needed anywhere in the file."
    - "assert for exclusivity-checked Optional narrowing: _resolve_geometry's ref= branch is reached only when sum(x is not None for x in (point, wkt, geojson, ref)) == 1 and the first three were already ruled out — mypy cannot narrow ref: tuple[str, str] | None through that sum() check, so a one-line assert ref is not None (with a comment explaining why it's a static-only gap, not a runtime bug) resolved the sole non-overload/non-type-arg error in the file."
    - "D-03 mechanical parameterization at scale: geojson: dict -> dict[str, Any]; params: list -> list[Any] (builder signatures + _run_mvt/_arun_mvt/_to_named_binds); -> tuple[str, list] -> tuple[str, list[Any]]; bare list[dict] (return types + docstrings-adjacent code) -> list[dict[str, Any]] applied via targeted regex across ~30 builder functions and ~50 method signatures rather than hand-editing each of the 6199 lines individually."

key-files:
  created: []
  modified:
    - pycopg/spatial.py

key-decisions:
  - "Overload generation done programmatically, not by hand: wrote a one-off Python script (scratchpad, not committed) that parsed each polymorphic method's multi-line signature via paren-depth tracking, then emitted 3 @overload-decorated stub copies with only the into= line and return-type line varying. This was necessary at the 32-method (16 methods x 2 classes) scale to guarantee byte-for-byte parameter symmetry between the rows/gdf/fallback overloads and the real implementation — hand-transcription risk of a stray keyword or default was judged higher than the risk of a scripted transform, and the resulting diff was verified via full mypy + pytest + ruff/black passes before commit."
  - "Scalar helpers (distance/area/perimeter/centroid/as_geojson/as_text) got NO @overload, per the plan's explicit exclusion — their concrete list[dict[str, Any]] return type is correct and unambiguous (into=\"gdf\" always raises for them via _check_into), so an overload triplet would be redundant. The cast() at their single self._run() call site is the D-03-sanctioned way to reconcile their narrower static contract with _run's necessarily-wider union return, since _run is shared by both scalar and non-scalar callers and cannot itself be narrowed."
  - "No # type: ignore comments were needed anywhere in spatial.py — D-01's escape hatch was available but unnecessary; every error resolved via a real annotation (parameterized generic), a cast() backed by a runtime invariant (_check_into), or an assert backed by a runtime invariant (the sum()==1 exclusivity check). This keeps spatial.py's ignore count at zero, which is stronger than the plan's baseline expectation."

requirements-completed: [FREEZE-05]

# Metrics
duration: ~50min
completed: 2026-07-02
---

# Phase 46 Plan 03: Spatial.py mypy Strict (@overload + D-03) Summary

**Drove spatial.py — the largest strict hotspot (116 errors) — to zero via 96 symmetric `@overload` stubs (48 sync + 48 async) on all 16 polymorphic `into=` methods plus D-03 pragmatic-`Any` parameterization across every SQL builder and runner helper, with zero `# type: ignore` needed anywhere in the file.**

## Performance

- **Duration:** ~50 min
- **Completed:** 2026-07-02
- **Tasks:** 2 (combined into 1 commit — see Deviations)
- **Files modified:** 1 (pycopg/spatial.py; 1673 insertions / 147 deletions)

## Accomplishments

- **spatial.py: 116 -> 0 mypy strict errors.** Package-wide count dropped **303 -> 187** (`uv run mypy pycopg/` — spatial.py no longer appears in the aggregate error list at all).
- **96 `@overload` stubs added, 48 on `SpatialAccessor` + 48 on `AsyncSpatialAccessor` (perfectly symmetric)** — 3 stubs (`Literal["rows"]` -> `list[dict[str, Any]]`, `Literal["gdf"]` -> `gpd.GeoDataFrame`, bare `str` fallback -> the union) x 16 polymorphic methods x 2 classes: `contains, within, intersects, dwithin, nearest, buffer, transform, union, difference, intersection, simplify, convex_hull, make_valid, collect_geometries, union_aggregate, extent`. The real implementation of each method keeps its own `into: str = "rows"` default and the union return type — the overloads are purely the static complement.
- **`_check_into()` runtime validator is byte-for-byte unchanged** (verified via `git diff` — only its line number shifted, its body did not) — confirms D-02's "static complement, not replacement" contract.
- **D-03 pragmatic-`Any` applied across every module-level SQL builder** (`build_contains_sql`, `build_intersects_sql`, ... `build_extent_sql` — ~25 builders) and the shared runner helpers `_run`/`_run_mvt` (sync), `_run`/`_arun_mvt` (async), `_to_named_binds`: `geojson: dict` -> `dict[str, Any]`, `params: list` -> `list[Any]`, `-> tuple[str, list]` -> `tuple[str, list[Any]]`, bare `list[dict]` return annotations -> `list[dict[str, Any]]`.
- **6 scalar-only helpers narrowed via `cast()`, not overloaded** (per the plan's explicit exclusion): `distance`, `area`, `perimeter`, `centroid`, `as_geojson`, `as_text` (x2 classes = 12 sites) each call the same `self._run()`/`await self._run()` used by polymorphic methods, so `_run`'s static return type is the union even though `_check_into()` already raises `ValueError` for `into="gdf"` on these at runtime. Each of the 12 return sites was narrowed with `cast("list[dict[str, Any]]", self._run(...))` (or the `await` form) plus a one-line comment citing the runtime guarantee, rather than adding a redundant overload triplet or loosening the method's own return type.
- **One `assert` added in `_resolve_geometry`** (module-level pure builder, not a class method): the `ref=` branch is only reached when exactly one of `point`/`wkt`/`geojson`/`ref` is non-`None` (checked earlier via `sum(x is not None for x in (...)) == 1`) and the first three were already ruled out by prior `if` returns — mypy cannot narrow `ref: tuple[str, str] | None` through that `sum()` check, so `assert ref is not None` (with an explanatory comment) resolved the file's sole `[misc]` "None object is not iterable" error.
- **Zero `# type: ignore` comments needed anywhere in spatial.py.** D-01's escape hatch was available but every error was resolvable via a real annotation, a `cast()` backed by the `_check_into` runtime invariant, or an `assert` backed by the `sum()` exclusivity invariant — stronger than the plan's baseline expectation of "possible narrow ignores at geoalchemy2 edges" (spatial.py's `create_spatial_index`/`list_geometry_columns` don't touch geoalchemy2 directly; that edge lives elsewhere in the codebase, untouched by this plan).
- **KIND-parity and behavior verification, all green under `PGDATABASE=pycopg_test3`** (both `pycopg_test`/`pycopg_test2` remain broken per the carried-forward TimescaleDB `.so` version-drift infra issue): `test_accessor_parameter_kind_parity` + `test_accessor_parity` (14 tests), full `test_parity.py` (37/37), `-k spatial` selection (346 passed), full suite **1736 passed, 2 skipped**, coverage **96.38%** (ratchet >=95% held).
- `uv run ruff check pycopg tests` clean; `uv run black pycopg tests` reformatted spatial.py once (the overload triplets needed black's own line-wrapping pass) — re-verified mypy/ruff/tests all still green after the reformat. `uv run interrogate pycopg` -> 100% (overload stubs correctly excluded via the pre-configured `ignore-overloaded-functions = true`).

## Task Commits

Tasks 1 (`@overload` on both classes) and 2 (D-03 annotate remaining errors to zero) were committed together as a single atomic commit — see Deviations for why.

1. **Task 1 + Task 2 combined: `@overload` triplets + D-03 pragmatic-Any to zero strict errors** - `2edf7da` (feat)

**Plan metadata:** (pending — final docs commit below)

## Files Created/Modified

- `pycopg/spatial.py` — `from typing import TYPE_CHECKING, Any, Literal, cast, overload` (added `Any`, `Literal`, `cast`, `overload`); 96 new `@overload` stub signatures (48 `SpatialAccessor` + 48 `AsyncSpatialAccessor`); every module-level builder's `geojson`/`params`/return-tuple bare generics parameterized; `_run`/`_run_mvt`/`_arun_mvt`/`_to_named_binds` parameterized; 12 `cast("list[dict[str, Any]]", ...)` sites on the 6 scalar helpers x2 classes; 1 `assert ref is not None` in `_resolve_geometry` (116 errors -> 0)

## Decisions Made

- **Overload generation done programmatically, not by hand.** Wrote a one-off Python script (in the session scratchpad, not committed to the repo) that parsed each polymorphic method's multi-line signature via paren-depth tracking, then emitted 3 `@overload`-decorated stub copies with only the `into=` line and return-type line varying. At 32-method scale (16 methods x 2 classes) this guarantees byte-for-byte parameter symmetry between the rows/gdf/fallback overloads and the real implementation — the risk of a stray keyword or default drifting during hand-transcription was judged higher than the risk of a scripted transform, and the resulting diff was fully verified via mypy + pytest + ruff/black before committing.
- **Scalar helpers got no `@overload`, matching the plan's explicit exclusion.** `distance`/`area`/`perimeter`/`centroid`/`as_geojson`/`as_text` keep their existing concrete `list[dict[str, Any]]` return type (unambiguous — `into="gdf"` always raises for them via `_check_into`); a `cast()` at their single `_run()` call site reconciles the mismatch with `_run`'s necessarily-wider union return (shared with polymorphic callers), rather than adding a redundant overload triplet.
- **No `# type: ignore` used anywhere in spatial.py.** Every strict error resolved via a real annotation, a `cast()` backed by the `_check_into` runtime invariant, or an `assert` backed by the `sum()`-exclusivity runtime invariant — D-01's narrow-ignore escape hatch was available but not needed for this file.

## Deviations from Plan

**1. [Process] Tasks 1 and 2 committed as a single combined commit, not two atomic commits.**
- **Found during:** Post-implementation, preparing to stage/commit.
- **Issue:** The plan structures Task 1 (`@overload` triplets) and Task 2 (D-03 annotate remaining errors) as sequential, separately-committable tasks. In practice, `black`'s reformatting pass and the D-03 generic-parameterization edits landed on lines immediately adjacent to (and in several cases inside) the newly-inserted overload blocks throughout the same ~6200-line file — e.g. every scalar helper's `cast()` line sits directly below its (Task-1-untouched) implementation, and the builder-function `Any`/`list[Any]` fixes from Task 2 interleave with the accessor-class overload insertions from Task 1 in the same contiguous diff hunks. A clean `git add -p` split risked staging an intermediate state where overload stubs exist but their sibling implementation still has a bare-generic-parameter mypy error (or vice versa), which is not a meaningfully separable, independently-green commit boundary.
- **Resolution:** Committed both tasks together as one atomic, fully-verified commit (`2edf7da`), with the commit message explicitly documenting both tasks' distinct contributions and results. Both tasks' acceptance criteria (symmetric overload count; `_check_into` unchanged; KIND-parity green; zero strict errors; spatial + parity tests green) were independently verified as satisfied before the commit.
- **Files affected:** `pycopg/spatial.py` (the only file in scope).
- **Commit:** `2edf7da`

## Issues Encountered

- Both `pycopg_test` and `pycopg_test2` remain broken (TimescaleDB `.so` version drift, carried forward from 46-02) — all verification ran against the scratch `pycopg_test3` database per the project's current operating instructions. No new infra issues surfaced.
- `black` printed a benign `Python 3.12 cannot parse code formatted for Python 3.15` safety-check warning while reformatting (pre-existing local-Python-vs-black-target-version mismatch, unrelated to this plan's changes) — the reformat itself completed correctly and was re-verified with a full mypy/ruff/pytest pass afterward.

## Next Phase Readiness

- Package-wide strict error count now **187** (down from 303 entering this plan), concentrated in the 6 remaining files not yet touched: `etl.py` (~46, including 1 likely-real `[no-redef]`/`[assignment]` latent bug at `etl.py:2017/2025` flagged for a future plan), `database.py`/`async_database.py` (~42/41), `timescale.py` (~23), `pool.py` (~23), `schema.py` (~20), plus 1 stray `pycopg/__init__.py:56` `[no-untyped-def]`.
- **spatial.py is now the reference implementation for timescale.py's `@overload` pass (46-04+)**: timescale's `into=` polymorphism (`Literal["df"]` -> `pd.DataFrame`, `Literal["rows"]` -> `list[dict[str, Any]]`) follows the exact same rows/gdf-analog/fallback triplet pattern established here, including the same KIND-parity (sync `TimescaleAccessor` + async equivalent) and scalar-helper `cast()`-not-overload treatment if timescale.py has an analogous scalar/non-scalar split.
- `cast()`-for-scalar-helper and `assert`-for-exclusivity-narrowing are new D-03-adjacent patterns established in this plan; later plans hitting the same "shared runner returns a wider union than one specific caller's contract" shape should reuse `cast()` rather than loosening the caller's return type or duplicating the runner.
- No blockers for 46-04.

---
*Phase: 46-mypy-strict-py-typed-gate*
*Completed: 2026-07-02*

## Self-Check: PASSED

- FOUND: pycopg/spatial.py
- FOUND: .planning/phases/46-mypy-strict-py-typed-gate/46-03-SUMMARY.md
- FOUND: 2edf7da (Task 1+2 combined commit)
- FOUND: a807390 (SUMMARY.md commit)
