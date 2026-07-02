---
phase: 46-mypy-strict-py-typed-gate
plan: 06
subsystem: typing
tags: [mypy, mypy-strict, typing, database, async-database, kind-parity, freeze-05, gate-complete]

# Dependency graph
requires:
  - phase: 46-mypy-strict-py-typed-gate
    plan: 02
    provides: "10 foundation/leaf modules at 0 strict errors; D-03 pragmatic-Any + D-01 narrow-ignore precedents"
  - phase: 46-mypy-strict-py-typed-gate
    plan: 03
    provides: "spatial.py @overload + cast()-for-scalar-helper + assert-for-exclusivity-narrowing patterns"
  - phase: 46-mypy-strict-py-typed-gate
    plan: 04
    provides: "timescale.py + schema.py at 0 strict errors"
  - phase: 46-mypy-strict-py-typed-gate
    plan: 05
    provides: "etl.py + pool.py at 0 strict errors; package-wide 144 -> 76 (3 files remaining: database.py, async_database.py, __init__.py)"
provides:
  - "database.py at 0 mypy strict errors (38 -> 0) — the top-tier sync Database consumer, now checked against every already-typed accessor/foundation module"
  - "async_database.py at 0 mypy strict errors (37 -> 0) — mirrors every database.py annotation decision for DB-class KIND-parity"
  - "pycopg/__init__.py at 0 mypy strict errors (1 -> 0, gap-closure) — __getattr__(name: str) -> type annotated, deprecated-alias lookup narrowed via cast()"
  - "package-wide uv run mypy pycopg/ -> Success: no issues found in 18 source files (76 -> 0 errors, exit 0) — FREEZE-05 satisfied, whole pycopg/ package strict-clean"
  - "backup.py stale # type: ignore[call-overload] removed (Rule 1 side effect of database.py's cursor() typing making the row-dict type statically visible to a downstream caller)"
affects: [46-07]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "cursor()/AsyncCursor return-type precision closes downstream ignores: parameterizing Database.cursor() -> Iterator[psycopg.Cursor[dict[str, Any]]] (matching the dict_row row factory actually configured at runtime) made backup.py's compensating # type: ignore[call-overload] on `row['count']` newly UNUSED under warn_unused_ignores — a strict-mode side effect worth checking for whenever a shared connection/cursor factory gets its first precise generic parameterization."
    - "assert sql is not None reused for a NEW exclusivity shape: to_dataframe/to_geodataframe/AsyncDatabase mirrors all take `table: str | None` XOR `sql: str | None`, reject both-None/both-set via two `raise ValueError` guards, then unconditionally set `sql = f'SELECT * FROM ...'` inside `if table:` — mypy cannot see across the raise/assign control flow that sql is non-None by the time it reaches `text(sql)`, so a one-line `assert sql is not None` (with a comment citing the guard) closes 4 sites total (2 per class x 2 classes) identically to spatial.py/etl.py's prior exclusivity-narrowing precedent."
    - "cast() at genuinely-unstubbed third-party call-site edges, not at the public signature: from_dataframe's `dtype: dict[str, Any] | None` and to_geodataframe's `params: dict[str, Any] | None` keep pycopg's own precise public contract; the cast() (plus one narrow `# type: ignore[call-overload]` for geopandas' read_postgis(), which mypy cannot resolve to any single overload variant even after params narrowing) is applied only at the pandas .to_sql()/geopandas .read_postgis() call boundary, where the third-party stub's Mapping/dtype union is narrower than dict[str, Any] — this keeps pycopg's own typed surface honest while accepting the real precision gap at the unstubbed edge (D-01)."
  discovered:
    - "The plan's <read_first> flagged database.py:1732/async_database.py:1367 (_read_postgis overload mismatch) as the one anticipated D-01/cast() edge — investigation confirmed it, but TWO additional third-party edges of the identical shape existed and needed the same treatment: pandas.DataFrame.to_sql()'s dtype kwarg (Mapping[Hashable, precise-dtype-union], no arbitrary Any) hit the same 'our dict[str, Any] contract is wider than the stub' gap on both from_dataframe methods, discovered only once mypy's error list was re-run after the first read_postgis fix landed."

key-files:
  created: []
  modified:
    - pycopg/database.py
    - pycopg/async_database.py
    - pycopg/__init__.py
    - pycopg/backup.py

key-decisions:
  - "database.py Task 1 and async_database.py Task 2 committed as two SEPARATE atomic commits (unlike 46-03's combined commit) because the mirroring here was mechanical and non-interleaving: every sync fix has a 1:1 async counterpart at an analogous (not overlapping) line range, so each task's diff was independently reviewable and green before the next started — no shared-hunk conflict like spatial.py's overload-insertion + D-03 interleave."
  - "__init__.py:56 gap-closure folded into Task 2's commit rather than a separate Task 3: the plan's <files_modified> frontmatter only lists database.py/async_database.py, but the executor's mandatory objective explicitly requires __init__.py:56 to reach zero so the WHOLE package clears mypy strict (FREEZE-05 requires package-wide zero, not just the two named files) — committing it alongside async_database.py (both are small, single-purpose D-03/D-01 annotation fixes) avoided a near-empty third commit for one function."
  - "backup.py's newly-unused ignore removed in the SAME commit as async_database.py rather than deferred/flagged: this is a genuine Rule-1-adjacent consequence of database.py's Task-1 cursor() typing (not an out-of-scope discovery — CLAUDE.md forbids leaving uncommitted changes and warn_unused_ignores is part of the strict gate config from 46-01/D-04), so leaving it unfixed would re-break `uv run mypy pycopg/` immediately after this plan's own commits landed."
  - "getattr(exceptions, new_name) narrowed via cast('type', ...) rather than adding a # type: ignore[no-any-return]: every value in _DEPRECATED_PACKAGE_ALIASES is verified (by the exceptions.py module that owns the dict) to be a real *Error class name, so the dynamic getattr() is a genuinely-typed-but-statically-invisible lookup — the same D-03 pragmatic-Any-to-precise-cast idiom used throughout the phase, not a D-01 unstubbed-edge (stdlib getattr() IS fully stubbed; the imprecision is inherent to dynamic attribute access, not a stub gap)."

requirements-completed: [FREEZE-05]

# Metrics
duration: ~35min
completed: 2026-07-02
---

# Phase 46 Plan 06: database.py + async_database.py mypy Strict (+ __init__.py Gap-Closure) Summary

**Drove database.py (38 errors) and async_database.py (37 errors) — the last two hotspot files, both top-tier consumers importing every already-typed accessor and foundation module — to zero mypy strict errors via D-03 pragmatic generics and D-01 cast()/assert-narrowing at genuinely-unstubbed pandas/geopandas edges, then closed the sole remaining package-wide gap (`pycopg/__init__.py:56`) so `uv run mypy pycopg/` reports zero errors across the WHOLE package for the first time — FREEZE-05 is now satisfied and Phase 46's final plan (47-07, CI gate flip) is unblocked.**

## Performance

- **Duration:** ~35 min
- **Completed:** 2026-07-02
- **Tasks:** 2 (each committed atomically) + 1 mandatory gap-closure folded into Task 2
- **Files modified:** 4 (`pycopg/database.py`, `pycopg/async_database.py`, `pycopg/__init__.py`, `pycopg/backup.py`)

## Accomplishments

- **database.py: 38 → 0 mypy strict errors.** `uv run mypy pycopg/database.py` → `Success: no issues found in 1 source file`.
- **async_database.py: 37 → 0 mypy strict errors, mirroring every database.py decision.** `uv run mypy pycopg/async_database.py` → `Success: no issues found in 1 source file`.
- **`pycopg/__init__.py`: 1 → 0 mypy strict errors (gap-closure, not owned by any other plan).** `__getattr__(name: str)` annotated `-> type`; its `getattr(exceptions, new_name)` dynamic lookup narrowed via `cast("type", ...)` rather than `# type: ignore` (every alias value is a verified real class name — a D-03 pattern, not a D-01 unstubbed edge).
- **Package-wide: `uv run mypy pycopg/` → `Success: no issues found in 18 source files`.** Exit code 0, **zero errors across the entire `pycopg/` package** — down from 76 entering this plan (356 → 303 → 187 → 144 → 76 → **0** across the full phase). **FREEZE-05 is satisfied.**
- **D-03 pragmatic-`Any`/precise-generics applied at scale on both classes** (x2 for KIND-parity): `execute`/`fetch_one`/`fetch_all`/`insert_many`/`upsert_many`/`upsert`/`delete_where`/`update_where`/`exists`/`count`/`paginate`/`insert_batch`/`copy_insert` row-returning signatures parameterized `list[dict[str, Any]]`/`dict[str, Any] | None`; `execute_many`/`stream` params → `Sequence[Any]`; `cursor()`/async `cursor()` context managers parameterized `Iterator[psycopg.Cursor[dict[str, Any]]]`/`AsyncIterator[AsyncCursor[dict[str, Any]]]` (matching the `dict_row` row factory actually configured at connection time); loop-local `params: list[Any] = []` var-annotations added at 3 sites (`insert_batch`/`paginate` sync+async).
- **`__exit__`/`__aexit__` typed with `TracebackType | None`**, matching the `pool.py` (46-05) precedent exactly: `type[BaseException] | None`, `BaseException | None`, `TracebackType | None`.
- **`assert sql is not None` exclusivity-narrowing applied at 4 NEW sites** (`to_dataframe`, `to_geodataframe` x2 classes): all four methods take `table: str | None` XOR `sql: str | None`, reject both-None/both-set via `raise ValueError`, then set `sql = f"SELECT * FROM ..."` inside `if table:` — mypy cannot see across that control flow that `sql` is non-`None` by the time it reaches `text(sql)`, so the established spatial.py/etl.py exclusivity-narrowing idiom (a one-line `assert` with a comment) closes the gap.
- **3 genuinely-unstubbed third-party edges resolved via `cast()`** (D-01, x2 for sync+async = 6 call sites total): `from_dataframe`'s `dtype: dict[str, Any] | None` → `cast("dict[Hashable, Any] | None", dtype)` at the `pandas.DataFrame.to_sql()` call (pandas-stubs' `dtype` union is narrower than arbitrary `Any` values); `to_geodataframe`'s `gpd.read_postgis(...)` return value → `cast("gpd.GeoDataFrame", ...)` plus one narrow `# type: ignore[call-overload]` per class (geopandas-stubs' overloads key on the absent `chunksize` kwarg via a `params` union mypy cannot resolve against `dict[str, Any]` even after narrowing — the plan's own `<read_first>` anticipated this exact site). Both public signatures (`dtype`, `params`) keep pycopg's own precise `dict[str, Any]` contract; only the third-party call boundary is cast.
- **`_stream_df_copy`/`_async_stream_df_copy` module-level helper `cur` parameter typed** `psycopg.Cursor[Any]`/`psycopg.AsyncCursor[Any]` (previously untyped, the `[no-untyped-def]` at each file's line ~59).
- **Rule-1 side effect fixed in the SAME plan: `backup.py:316` stale `# type: ignore[call-overload]` removed.** Parameterizing `Database.cursor()` in Task 1 made `row["count"]`'s type statically visible as `dict[str, Any]` to `backup.py`'s `db.cursor()` caller for the first time, making its compensating ignore comment newly unused under `warn_unreachable`/`warn_unused_ignores` (D-04 config) — left unfixed, this would have immediately re-broken the just-achieved zero-error state. Confirmed via direct re-run of `uv run mypy pycopg/` after Task 1's commit.
- **No signature or runtime-behavior change anywhere** — every fix is annotation-only (types, `assert`, `cast()`) or a stale-ignore removal; `git diff --stat` confirms only type-adjacent lines touched. All `validate_identifiers`/`validate_identifier` calls verified byte-for-byte unchanged via direct read of every touched method.

## Task Commits

1. **Task 1: database.py annotate to zero strict errors** — `ab70d53` (feat)
2. **Task 2: async_database.py mirror + `__init__.py` gap-closure + backup.py stale-ignore cleanup** — `b8208bc` (feat)

**Plan metadata:** (pending — final docs commit below)

## Files Created/Modified

- `pycopg/database.py` — `from collections.abc import Hashable`, `from types import TracebackType`, `from typing import ..., cast` (new imports); `_stream_df_copy(cur: psycopg.Cursor[Any], ...)`; `cursor()` → `Iterator[psycopg.Cursor[dict[str, Any]]]`; 13 row-returning method signatures parameterized `dict[str, Any]`/`list[dict[str, Any]]`; `execute_many`/`stream` → `Sequence[Any]`; 3 `params`/loop-local `list[Any]` var-annotations; `__exit__` typed with `TracebackType | None`; 2 `assert sql is not None` (to_dataframe, to_geodataframe); `cast("dict[Hashable, Any] | None", dtype)` at `to_sql()`; `cast("gpd.GeoDataFrame", ...)` + `# type: ignore[call-overload]` at `read_postgis()` (38 errors → 0)
- `pycopg/async_database.py` — identical import additions plus `cast`/`Hashable`; `_async_stream_df_copy(cur: psycopg.AsyncCursor[Any], ...)`; `cursor()` → `AsyncIterator[AsyncCursor[dict[str, Any]]]`; the same 13-method row-typing mirror; `__aexit__` typed with `TracebackType | None`; 2 `assert sql is not None` (to_dataframe, to_geodataframe); same `cast()`/`# type: ignore[call-overload]` treatment at the async `run_sync` bridge call sites (37 errors → 0)
- `pycopg/__init__.py` — `from typing import cast` (new import); `__getattr__(name: str) -> type`; `getattr(exceptions, new_name)` → `cast("type", getattr(exceptions, new_name))` (1 error → 0)
- `pycopg/backup.py` — removed 1 stale `# type: ignore[call-overload]` on `int(row["count"])` (Rule 1, made unused by database.py's Task 1 `cursor()` typing)

## Decisions Made

- **Two separate atomic commits (Task 1, Task 2), not combined** — unlike 46-03's spatial.py (where `@overload` insertion and D-03 fixes interleaved in the same diff hunks), database.py's fixes and async_database.py's mirrored fixes sit at non-overlapping, 1:1-analogous line ranges across two different files — each task was independently green and reviewable before the next began.
- **`__init__.py` gap-closure folded into Task 2's commit, not a separate Task 3** — the plan's own `<files_modified>` frontmatter only names `database.py`/`async_database.py`, but the executor prompt's mandatory objective requires the WHOLE package to reach zero (FREEZE-05's actual bar), and the fix is a single small D-03 annotation — a standalone commit for one function was judged unnecessary ceremony.
- **backup.py's unused-ignore cleanup included in this plan** rather than deferred to 46-07 — leaving it would re-introduce a mypy error in the very state this plan is meant to leave the package in (zero errors), and CLAUDE.md's "leave NO uncommitted changes" + the strict gate's own `warn_unused_ignores` make this squarely in-scope Rule 1 territory, not an out-of-scope discovery.
- **`cast("type", ...)` over `# type: ignore[no-any-return]`** for `__getattr__`'s dynamic lookup — the imprecision is inherent to `getattr()` with a runtime string, not a third-party stub gap, so the D-03 (pragmatic-Any-to-precise-cast) idiom fits better than D-01 (unstubbed-edge ignore).

## Deviations from Plan

**1. [Rule 1 - Bug/staleness] `backup.py:316`'s `# type: ignore[call-overload]` became unused as a side effect of Task 1, and was removed in Task 2's commit.**
- **Found during:** Post-Task-1 full-package `uv run mypy pycopg/` re-run (routine check before starting Task 2).
- **Issue:** `Database.cursor()`'s new `Iterator[psycopg.Cursor[dict[str, Any]]]` return type (added in Task 1 to resolve database.py's own `[misc]` yield-type errors) made `backup.py`'s `db.cursor()` → `cur.fetchone()` → `row["count"]` chain statically typed for the first time; its 2026-06-xx compensating ignore comment (written when `cursor()` had no generic parameter) was now flagged `[unused-ignore]` by the phase's `warn_unused_ignores` config (D-04, 46-01).
- **Fix:** Removed the stale `# type: ignore[call-overload]` comment; verified `uv run mypy pycopg/backup.py` and the full package still report zero errors afterward.
- **Files modified:** `pycopg/backup.py`
- **Commit:** `b8208bc`
- Not flagged out-of-scope per the deviation rules' scope boundary — this is a change DIRECTLY caused by Task 1's edits to `database.py`, not a pre-existing unrelated issue.

**2. [Gap-closure, per executor mandate] `pycopg/__init__.py:56` fixed even though the plan's `<files_modified>` frontmatter only lists `database.py`/`async_database.py`.**
- **Found during:** Reading the executor prompt's explicit objective before starting Task 1.
- **Issue:** The 46-06-PLAN.md's own frontmatter and task list scope to the two named files, but FREEZE-05 (the phase requirement) and this execution's mandatory objective both require the WHOLE `pycopg/` package to reach zero strict errors — `__init__.py`'s single remaining `[no-untyped-def]` (carried forward, unowned, since 46-02/46-03's baseline measurements) would otherwise block that bar even after Tasks 1-2 succeeded.
- **Fix:** Annotated `__getattr__(name: str) -> type`, narrowed the dynamic `getattr()` return via `cast("type", ...)`.
- **Files modified:** `pycopg/__init__.py`
- **Commit:** `b8208bc`
- This was pre-authorized by the executor's own objective text ("ADDITIONALLY (gap-closure, mandatory)...") rather than an autonomous deviation-rule judgment call.

No other deviations — both tasks' acceptance criteria (database.py/async_database.py → Success; `Params` alias present; parity green; behavior tests green) were met within the existing task boundaries, and no architectural changes were needed.

## Issues Encountered

- None new. `pycopg_test`/`pycopg_test2` remain broken (carried-forward TimescaleDB `.so` version-drift infra issue from every prior 46-* plan) — all verification ran against `PGDATABASE=pycopg_test3` per current project operating instructions (this supersedes the plan's own `<verify>` blocks, which still reference `pycopg_test2`).
- `black` printed the same benign `Python 3.12 cannot parse code formatted for Python 3.15` safety-check warning seen in every prior 46-* plan (pre-existing local-Python-vs-black-target-version mismatch, unrelated to this plan) — reformatting completed correctly and was re-verified with a full mypy/ruff/pytest pass afterward (no reformat was actually needed on the second `black` invocation — files were already correctly formatted from the first pass after Task 1).

## Next Phase Readiness

- **Phase 46's core deliverable (FREEZE-05) is now COMPLETE**: `uv run mypy pycopg/` → `Success: no issues found in 18 source files`, exit code 0, zero errors package-wide. This was the last of the phase's `type-arg`/`no-untyped-def`/`return-value`/`misc` hotspots — all 356 errors measured at the 46-01 baseline are now resolved (356 → 303 → 187 → 144 → 76 → 0 across 46-02 through 46-06).
- **46-07 (the phase's final plan, per the roadmap) can now flip CI's `mypy --strict` step from `continue-on-error: true` to a blocking gate** — the package-wide zero-error state this plan establishes is the precondition that gate flip requires. No remaining hotspot files; no known latent type gaps.
- All D-01/D-02/D-03/D-04 decisions from `46-CONTEXT.md` held through to the final file pair: no TypedDicts introduced, no blanket ignores, `Params` alias reused (not reinvented) on every raw-SQL primitive, sync/async DB-class KIND-parity asserted green via `test_accessor_parameter_kind_parity` + `test_accessor_parity` (14/14) and the full `test_parity.py` (37/37).
- No blockers for 46-07.

---
*Phase: 46-mypy-strict-py-typed-gate*
*Completed: 2026-07-02*

## Self-Check: PASSED

- FOUND: pycopg/database.py
- FOUND: pycopg/async_database.py
- FOUND: pycopg/__init__.py
- FOUND: pycopg/backup.py
- FOUND: .planning/phases/46-mypy-strict-py-typed-gate/46-06-SUMMARY.md
- FOUND: ab70d53 (Task 1 commit)
- FOUND: b8208bc (Task 2 commit)
