---
phase: 46-mypy-strict-py-typed-gate
plan: 04
subsystem: typing
tags: [mypy, mypy-strict, typing, overload, kind-parity, timescale, schema]

# Dependency graph
requires:
  - phase: 46-mypy-strict-py-typed-gate
    plan: 01
    provides: "strict = true + warn_unreachable = true single source of truth (D-04)"
  - phase: 46-mypy-strict-py-typed-gate
    plan: 02
    provides: "10 foundation/leaf modules at 0 strict errors; D-03 pragmatic-Any + D-01 narrow-ignore precedents"
provides:
  - "timescale.py at 0 mypy strict errors (23 -> 0) — 12 @overload stubs (6 sync + 6 async, symmetric) on time_bucket/time_bucket_gapfill giving downstream mypy --strict callers precise pd.DataFrame / list[dict[str, Any]] return types"
  - "schema.py at 0 mypy strict errors (20 -> 0) via D-03 pragmatic-Any on every introspection accessor return type, both classes"
  - "package-wide mypy strict count 187 -> 144 (7 files -> 5 files)"
affects: [46-05, 46-06, 46-07]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "@overload triplet pattern reused verbatim from 46-03/spatial.py for timescale's df/rows polymorphism: Literal[\"df\"] = \"df\" -> pd.DataFrame, Literal[\"rows\"] (no default, required) -> list[dict[str, Any]], bare str fallback -> the union — the real implementation keeps its own into: str = \"df\" default and the union return."
    - "assert for exclusivity-checked Optional narrowing (second use after 46-03's _resolve_geometry precedent): add_dimension's number_partitions/chunk_interval are proven not-None by an earlier construction-time mutual-exclusivity check (raises ValueError before reaching the hash/range branch), but that check lives in a separate if/elif block mypy cannot correlate with the later if partition_type == \"hash\" branch — one-line assert ... is not None with an explanatory comment resolved both [arg-type] errors (sync + async) without touching runtime behavior."
    - "D-03 mechanical parameterization at schema.py's smaller scale (20 errors, all [type-arg], no @overload needed — schema has no into= polymorphism): list[dict] -> list[dict[str, Any]] on list_extensions/table_info/list_indexes/list_constraints/foreign_keys; dict | None -> dict[str, Any] | None on primary_key; dict -> dict[str, Any] on describe and the foreign_keys grouping locals (result/seen/entry)."

key-files:
  created: []
  modified:
    - pycopg/timescale.py
    - pycopg/schema.py

key-decisions:
  - "Both tasks committed separately (unlike 46-03's combined commit) — timescale.py and schema.py are two independent files with no interleaved diff hunks, so each task's acceptance criteria (23->0 for timescale with KIND-parity; 20->0 for schema) could be verified and committed atomically without the staging-split risk that forced 46-03's combination."
  - "add_dimension's number_partitions/chunk_interval narrowing used assert, not cast() — these are plain Optional[int]/Optional[str] locals reached through a real runtime invariant (the construction-time mutual-exclusivity ValueError block), which is exactly the assert-for-exclusivity-narrowing pattern 46-03 established for _resolve_geometry's ref= branch, not the cast()-for-wider-shared-return pattern used for spatial's scalar helpers."
  - "_run's pd.DataFrame | list[dict[str, Any]] union return type kept as the implementation's own annotation (not narrowed) on both classes — mirrors 46-03's spatial.py _run pattern where the shared runner intentionally keeps the wider union since it's called by both overloaded and (here, none) non-overloaded callers."

requirements-completed: []

# Metrics
duration: ~25min
completed: 2026-07-02
---

# Phase 46 Plan 04: timescale.py + schema.py mypy Strict (@overload + D-03) Summary

**Drove timescale.py (23 errors) to zero via 12 symmetric `@overload` stubs (6 sync + 6 async) on `time_bucket`/`time_bucket_gapfill` plus two `assert`-narrowed `add_dimension` branches, and schema.py (20 errors) to zero via pure D-03 pragmatic-`Any` parameterization of every introspection accessor — package-wide strict count now 187 → 144 (7 → 5 files).**

## Performance

- **Duration:** ~25 min
- **Completed:** 2026-07-02
- **Tasks:** 2 (each committed atomically)
- **Files modified:** 2 (`pycopg/timescale.py`, `pycopg/schema.py`)

## Accomplishments

- **timescale.py: 23 → 0 mypy strict errors.** `uv run mypy pycopg/timescale.py` → `Success: no issues found in 1 source file`.
- **12 `@overload` stubs added, 6 on `TimescaleAccessor` + 6 on `AsyncTimescaleAccessor` (perfectly symmetric)** — 3 stubs per method (`Literal["df"] = "df"` → `pd.DataFrame`, `Literal["rows"]` → `list[dict[str, Any]]`, bare `str` fallback → the union) × 2 methods (`time_bucket`, `time_bucket_gapfill`) × 2 classes. Verified via `awk` split at the `AsyncTimescaleAccessor` class boundary: 6 `@overload` before, 6 after; `Literal["df"]` and `Literal["rows"]` each appear 4 times (2 methods × 2 classes).
- **`_check_into()` runtime validator byte-for-byte unchanged** (only its surrounding line numbers shifted) — confirms D-02's "static complement, not replacement" contract, same as 46-03's spatial.py finding.
- **D-03 pragmatic-`Any` applied to the remaining timescale.py surface**: `_build_chunk_bound_fragments`/`_to_named_binds`/`_build_time_bucket_sql`/`_build_time_bucket_gapfill_sql` params/return generics; `list_hypertables`/`hypertable_info` dict returns (both classes); `_run` params/return (both classes).
- **Two `assert ... is not None` narrows added in `add_dimension`** (sync at ~line 850, async mirror at ~line 1897) for `number_partitions` (hash branch) and `chunk_interval` (range branch) — each backed by the existing construction-time mutual-exclusivity `ValueError` check higher in the same method, which mypy cannot see across an unrelated `if partition_type == "hash":` re-test. Resolved the file's only 2 `[arg-type]` error pairs (×2 for sync+async = 4 total).
- **schema.py: 20 → 0 mypy strict errors.** `uv run mypy pycopg/schema.py` → `Success: no issues found in 1 source file`. No `@overload` needed — schema.py has no `into=` polymorphism.
- **Every bare `list[dict]`/`dict`/`dict | None` generic parameterized to `Any`-args** across both `SchemaAccessor` and `AsyncSchemaAccessor`: `list_extensions`, `table_info`, `list_indexes`, `list_constraints`, `primary_key` (→ `dict[str, Any] | None`), `foreign_keys` (incl. its `result`/`seen`/`entry` grouping locals), `describe` (→ `dict[str, Any]`).
- **Package-wide: `uv run mypy pycopg/` 187 → 144 errors, 7 → 5 files** — `pycopg/timescale.py` and `pycopg/schema.py` no longer appear in the aggregate error list.
- **KIND-parity and behavior verification, all green under `PGDATABASE=pycopg_test3`**: `test_accessor_parameter_kind_parity` (7 tests) passed after Task 1; full `test_parity.py` (37/37) passed after both tasks; `-k timescale` (130/130) and `-k schema` (89/89) both passed; full suite **1736 passed, 2 skipped**, coverage **96.43%** (ratchet ≥95% held).
- `uv run ruff check pycopg tests` clean throughout. `uv run black pycopg tests` reformatted `schema.py` once (the widened `list[dict[str, Any]]` return-type signatures pushed several lines over the wrap threshold) — re-verified mypy/ruff/tests all still green after the reformat. `timescale.py` needed no reformatting. `uv run interrogate` → 100% on both files (overload stubs correctly excluded via the pre-configured `ignore-overloaded-functions = true`).

## Task Commits

1. **Task 1: timescale.py `@overload` triplets + D-03 to zero** — `5b7bd47` (feat)
2. **Task 2: schema.py D-03 annotate to zero** — `7a2af90` (feat)

**Plan metadata:** (pending — final docs commit below)

## Files Created/Modified

- `pycopg/timescale.py` — `from typing import TYPE_CHECKING, Any, Literal, overload` (added `Any`, `Literal`, `overload`); 12 new `@overload` stub signatures (6 `TimescaleAccessor` + 6 `AsyncTimescaleAccessor`) on `time_bucket`/`time_bucket_gapfill`; 2 `assert ... is not None` narrows in `add_dimension` (sync + async); every module-level builder's `params`/return-tuple bare generics parameterized; `_run` (both classes), `list_hypertables`, `hypertable_info` (both classes) parameterized (23 errors → 0)
- `pycopg/schema.py` — `from typing import TYPE_CHECKING, Any` (added `Any`); `list_extensions`, `table_info`, `list_indexes`, `list_constraints`, `primary_key`, `foreign_keys` (+ locals), `describe` parameterized on both `SchemaAccessor` and `AsyncSchemaAccessor` (20 errors → 0); reformatted by `black` after the D-03 edits pushed some signatures over the line-length threshold

## Decisions Made

- **Tasks committed separately, not combined** (contrast with 46-03). `timescale.py` and `schema.py` are two independent files with no interleaved diff hunks between the two tasks, so each task's own acceptance criteria (23→0 + KIND-parity for timescale; 20→0 + schema/parity tests for schema) could be verified and committed atomically without the staging-split risk 46-03 hit within a single 6200-line file.
- **`assert`, not `cast()`, for `add_dimension`'s Optional narrowing.** `number_partitions`/`chunk_interval` are plain `int | None`/`str | None` locals whose non-`None`-ness is proven by a real runtime invariant (the construction-time mutual-exclusivity `ValueError` block earlier in the same method) — this is the assert-for-exclusivity-narrowing pattern 46-03 established for `_resolve_geometry`'s `ref=` branch, not the cast()-for-wider-shared-return pattern used for spatial's scalar helpers (there is no shared wider-return-type caller here).
- **`_run`'s union return type (`pd.DataFrame | list[dict[str, Any]]`) kept as-is on both classes**, not narrowed — mirrors 46-03's `spatial.py` `_run`, which intentionally stays wide since `_check_into` is the runtime authority and the `@overload` stubs are the static complement at the call sites, not at the shared runner.

## Deviations from Plan

None — plan executed exactly as written. Both tasks' acceptance criteria were met without needing Rule 1-4 deviations beyond the two `assert` narrows, which were anticipated by the plan's own read_first pointer to `_check_into` interplay and are a direct reuse of 46-03's established pattern (not a new architectural decision).

## Issues Encountered

- Both `pycopg_test` and `pycopg_test2` remain broken (TimescaleDB `.so` version drift, carried forward from 46-02/46-03) — all verification ran against the scratch `pycopg_test3` database per the project's current operating instructions. No new infra issues surfaced.
- `black` printed the same benign `Python 3.12 cannot parse code formatted for Python 3.15` safety-check warning seen in 46-03 (pre-existing local-Python-vs-black-target-version mismatch, unrelated to this plan) — the reformat itself completed correctly and was re-verified with a full mypy/ruff/pytest pass afterward.

## Next Phase Readiness

- Package-wide strict error count now **144** (down from 187 entering this plan), concentrated in the remaining files: `etl.py` (~46, including 1 likely-real `[no-redef]`/`[assignment]` latent bug at `etl.py:2017/2025` flagged since 46-03 for a future plan), `database.py`/`async_database.py` (~42/41), `pool.py` (~23), plus 1 stray `pycopg/__init__.py:56` `[no-untyped-def]`.
- **FREEZE-05 is NOT yet complete** — this plan resolves 2 of the remaining 5 hotspot files; `etl.py`, `database.py`, `async_database.py`, `pool.py`, and `pycopg/__init__.py` still carry errors. Package-wide `uv run mypy pycopg/` must reach 0 across all of `pycopg/` (all 7 phase plans) before FREEZE-05 can be marked complete — deferred to later plans in this phase (46-05..46-07 per the roadmap).
- `assert`-for-exclusivity-narrowing (established 46-03, reused here) and the `@overload` triplet pattern are now proven across two independent files (spatial.py, timescale.py) with zero drift — later plans hitting Optional-narrowing-across-branches or `into=`-style polymorphism should reuse both without re-deriving.
- No blockers for 46-05.

---
*Phase: 46-mypy-strict-py-typed-gate*
*Completed: 2026-07-02*

## Self-Check: PASSED

- FOUND: pycopg/timescale.py
- FOUND: pycopg/schema.py
- FOUND: .planning/phases/46-mypy-strict-py-typed-gate/46-04-SUMMARY.md
- FOUND: 5b7bd47 (Task 1 commit)
- FOUND: 7a2af90 (Task 2 commit)
