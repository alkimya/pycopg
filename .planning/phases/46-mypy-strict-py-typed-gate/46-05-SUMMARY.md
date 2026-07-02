---
phase: 46-mypy-strict-py-typed-gate
plan: 05
subsystem: typing
tags: [mypy, mypy-strict, typing, etl, pool, latent-bug, async]

# Dependency graph
requires:
  - phase: 46-mypy-strict-py-typed-gate
    plan: 01
    provides: "strict = true + warn_unreachable = true single source of truth (D-04)"
  - phase: 46-mypy-strict-py-typed-gate
    plan: 02
    provides: "10 foundation/leaf modules at 0 strict errors; D-03 pragmatic-Any + D-01 narrow-ignore precedents"
provides:
  - "etl.py at 0 mypy strict errors (46 -> 0) — steps [no-redef] root-caused and fixed as a duplicate mypy annotation across mutually-exclusive control-flow branches (not a runtime shadow bug); D-03 pragmatic-Any across builders/watermark codec; assert-for-exclusivity-narrowing reused for fetchone() INSERT/SELECT-by-known-id invariants; D-01 ignores for two genuine isinstance runtime guards mypy's warn_unreachable misreads"
  - "pool.py at 0 mypy strict errors (22 -> 0) — [unused-coroutine] root-caused (NOT at the plan's etl.py:2025 pointer; the real site is pool.py:574) and fixed: AsyncPooledDatabase.resize() was sync calling a psycopg_pool coroutine function without await, so resize silently never took effect; now async + awaited"
  - "package-wide mypy strict count 144 -> 76 (5 files -> 3 files)"
affects: [46-06, 46-07]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "steps [no-redef] fix: the two `steps: list = []` sites (dry_run early-return fork, normal-run path) live in the SAME method scope but on mutually-exclusive runtime branches (the dry_run fork always `return`s before the second assignment is ever reached) — never a real shadowing bug at runtime. Fixed by declaring `steps: list[Any]` once (at the first occurrence per method) and dropping the duplicate annotation at the second occurrence, reused identically across both ETLAccessor.run (sync) and AsyncETLAccessor.run (async)."
    - "assert-for-exclusivity-narrowing (46-03/46-04 precedent) applied to a NEW invariant class: fetchone() Optional-narrowing immediately after an INSERT ... RETURNING (_start_run) or a re-SELECT-by-just-written-run_id (_fetch_run_result) — both guaranteed non-None by the surrounding write/read protocol, not by an earlier branch check."
    - "D-01 ignore for a DIFFERENT unreachable-code shape than 46-02/46-03/46-04: not an unstubbed third-party edge, but mypy's warn_unreachable flagging two isinstance() runtime input-validation guards in Pipeline.__post_init__ as dead code because the frozen dataclass field's static annotation (tuple[str, ...]) doesn't reflect what untyped callers can pass at runtime — the guard is real defensive code (Rule 2 territory), not dead code."
    - "cast(\"list[dict[str, Any]]\", ...) for pandas' to_dict(orient=\"records\") Hashable-keyed stub vs. our always-str DataFrame columns — chosen over a bare # type: ignore[assignment] because black's line-wrapping repeatedly relocated the inline ignore comment onto an unrelated line across reformats, making the ignore silently drop; the named intermediate + cast() is stable under black."
  discovered:
    - "The plan's read_first pointer for [unused-coroutine] named etl.py; live investigation (uv run mypy pycopg/etl.py 2>&1 | grep unused-coroutine, then the full package mypy output) showed etl.py has ZERO unused-coroutine errors and etl.py's own asyncio.to_thread dispatch is correct throughout. The actual [unused-coroutine] is pool.py:574 (AsyncPooledDatabase.resize). Documented per the plan's own escape clause: 'If, after investigation, either turns out NOT to be a real bug [at the pointed location], document the evidence in SUMMARY.md.'"

key-files:
  created: []
  modified:
    - pycopg/etl.py
    - pycopg/pool.py
    - tests/test_pool.py

key-decisions:
  - "etl.py's steps [no-redef]: confirmed NOT a runtime shadowing bug via direct control-flow read (the dry_run branch's `return RunResult(...)` unconditionally exits before the normal-run branch's `steps` reassignment is reachable) — fixed as a pure type-annotation issue (annotate once, not twice), per the plan's own instruction to investigate before assuming a runtime defect."
  - "pool.py's [unused-coroutine] IS a real bug, confirmed by live introspection: `inspect.iscoroutinefunction(psycopg_pool.AsyncConnectionPool.resize)` returns True (v3+ async pool API), while `AsyncPooledDatabase.resize()` was `def` not `async def` and called `self._pool.resize(...)` with no await — the coroutine object was created and discarded, so pool resize silently never executed for the async pooled database. Fixed by making resize() async and awaiting the pool call, matching the already-correct check()/close() siblings in the same class."
  - "The existing tests/test_pool.py::TestAsyncPooledDatabase::test_resize test (a SYNC test using a plain MagicMock, not AsyncMock) never caught this because MagicMock.resize() also returns a MagicMock (not a real unawaited coroutine) that satisfies assert_called_once_with regardless of await. Moved the test into the async test class (TestAsyncPooledDatabaseAsync) with mock_pool.resize = AsyncMock() + await db.resize(...) + assert_awaited_once_with(...) so a regression here (a future contributor reverting resize to sync) fails the test immediately."
  - "_start_run/_fetch_run_result (sync + async, x2 methods) use assert row is not None rather than a defensive `if row is None: raise` — these are genuine runtime invariants (INSERT...RETURNING always yields one row; re-SELECT by a run_id this method itself just wrote/verified always finds it), matching the 46-03/46-04 assert-for-exclusivity-narrowing precedent rather than introducing new error-handling surface for an unreachable case."
  - "cast() chosen over inline # type: ignore[assignment] for the to_dict(orient=\"records\") Hashable-vs-str mismatch specifically because black's formatter kept relocating the inline ignore comment to a line where mypy no longer associated it with the assignment (producing an unused-ignore error on each reformat cycle) — the named-variable + cast() form is immune to this because it has no multi-line call chain for black to rewrap."

requirements-completed: []

# Metrics
duration: ~40min
completed: 2026-07-02
---

# Phase 46 Plan 05: etl.py + pool.py mypy Strict (Latent Bug Fixes) Summary

**Drove etl.py (46 errors) and pool.py (22 errors) to zero mypy strict errors via D-03 pragmatic-Any, root-caused and fixed the flagged `steps` `[no-redef]` as a duplicate-annotation-only issue (never a runtime bug), and found + fixed the REAL `[unused-coroutine]` bug at pool.py:574 (not etl.py as the plan pointer suggested) — `AsyncPooledDatabase.resize()` silently never resized the pool because it called an async psycopg_pool method without `await`.**

## Performance

- **Duration:** ~40 min
- **Completed:** 2026-07-02
- **Tasks:** 2 (each committed atomically)
- **Files modified:** 3 (`pycopg/etl.py`, `pycopg/pool.py`, `tests/test_pool.py`)

## Accomplishments

- **etl.py: 46 → 0 mypy strict errors.** `uv run mypy pycopg/etl.py` → `Success: no issues found in 1 source file`.
- **`[no-redef]` root-caused and fixed at BOTH occurrences** (sync `ETLAccessor.run` at the original lines ~1241/1339, async `AsyncETLAccessor.run` at ~1926/2025 — the plan's context flagged one instance but mypy's own baseline output showed the identical pattern duplicated in both the sync and async `run()` methods, 2 total, 4 physical sites). Traced the control flow directly: the `if dry_run:` early-return fork always executes a `return RunResult(...)` before the normal-run branch's `steps` reassignment is reachable — so the two `steps: list = []` statements are on mutually exclusive runtime paths and this was **never a live shadowing bug**. Fixed as a pure annotation issue: `steps: list[Any]` declared once (first occurrence), the duplicate annotation dropped from the second occurrence in the same scope.
- **`[unused-coroutine]` investigated at the plan's pointer (etl.py) and found ABSENT** — `uv run mypy pycopg/etl.py 2>&1 | grep unused-coroutine` returned nothing both before and after edits; etl.py's async `run()` already dispatches every transform step via `await asyncio.to_thread(step, df)` correctly (verified by direct read of both the dry_run and normal-run transform loops). The actual `[unused-coroutine]` — confirmed via the full baseline `uv run mypy pycopg/` — is **pool.py:574**, inside `AsyncPooledDatabase.resize()`.
- **pool.py: 22 → 0 mypy strict errors, including the real `[unused-coroutine]` bug fixed at the source.** `uv run mypy pycopg/pool.py` → `Success: no issues found in 1 source file`. Root cause confirmed live: `inspect.iscoroutinefunction(psycopg_pool.AsyncConnectionPool.resize)` → `True` (the async pool's `resize` is a coroutine function in the installed psycopg_pool version), but `AsyncPooledDatabase.resize()` was a plain `def` calling `self._pool.resize(min_size=..., max_size=...)` with **no `await`** — the coroutine object was constructed and immediately discarded by Python's garbage collector, so **the pool resize never actually executed** for any caller of the async pooled database's `resize()`. Fixed by making `resize()` `async def` and awaiting the pool call — now symmetric with the already-correct `check()`/`close()` methods in the same class.
- **Package-wide: `uv run mypy pycopg/` 144 → 76 errors, 5 → 3 files** — `pycopg/etl.py` and `pycopg/pool.py` no longer appear in the aggregate error list. Remaining 76 errors are entirely in `database.py`/`async_database.py`/`__init__.py`, explicitly out of scope for this plan and deferred to the phase's later plans per the roadmap's bottom-up ordering.
- **D-03 pragmatic-Any applied broadly**: etl.py builders (`_build_insert_sql`, `_build_upsert_sql`, `build_truncate_sql`, `build_init_sql`, `_build_incremental_extract_sql`) → `tuple[str, list[Any]]`; watermark codec (`_encode_watermark`/`_decode_watermark`) → `datetime | int | str` in/out; `_row_to_result`/`_end_run`/`_do_extract` params → `dict[str, Any]`/`datetime | int | str | None`; `Pipeline.transform` → `Callable[..., Any] | list[Callable[..., Any]] | None`. pool.py: `Params` alias (base.py D-03 precedent) reused for `execute`/`fetch_one`/`fetch_val` on both `PooledDatabase` and `AsyncPooledDatabase`; `Callable[..., Any]` for `reconnect_failed`/`check` constructor callbacks; `**kwargs: Any` on all four `from_env`/`from_url` classmethods; `dict[str, Any]` for `stats`/`health` returns; `TracebackType | None` typed on `__exit__`/`__aexit__` (no signature/behavior change — matches the frozen 1.0 contract).
- **New D-01 pattern (distinct from prior plans' unstubbed-third-party-edge ignores)**: two `isinstance()` runtime input-validation guards in `Pipeline.__post_init__` (rejecting a bare-string `conflict_columns`, normalizing a non-tuple iterable to a tuple) are flagged `[unreachable]` by `warn_unreachable` because the frozen dataclass field's *static* annotation (`tuple[str, ...]`) hides what an untyped/dynamically-constructed caller (e.g. a JSON-configured pipeline) can actually pass at runtime. These are genuine Rule-2-class defensive checks, not dead code — narrow `# type: ignore[unreachable]` with a one-line D-01 justification preserves both the guard and the strict-clean status.
- **Regression test added for the real bug**: `tests/test_pool.py::TestAsyncPooledDatabaseAsync::test_resize` (moved from the sync test class, now uses `AsyncMock` + `await db.resize(...)` + `assert_awaited_once_with(...)`) — the prior sync test with a plain `MagicMock` could never have caught the missing-`await` bug because `MagicMock().resize(...)` also "succeeds" without awaiting anything.
- **All validate_identifiers calls and the etl.py run-log autocommit-isolation seam verified untouched** — grep-diffed against the pre-plan state; only type annotations, the `steps` de-duplication, and the `resize()` sync→async fix touched runtime-adjacent code, and none altered SQL-builder identifier validation or the dedicated-autocommit-connection pattern in `_start_run`/`_end_run`/`init`.
- **Full verification green**: `-k etl` (253 passed), `-k pool` (55 passed, including the new async resize regression test), `test_parity.py` (37 passed), `test_pool_stress.py` (9 passed, live pool resize against a real DB) — all under `PGDATABASE=pycopg_test3` (both `pycopg_test`/`pycopg_test2` remain broken per current project state). `uv run ruff check pycopg tests` and `uv run black --check pycopg tests` both clean repo-wide. `uv run interrogate` → 100% on both files.

## Task Commits

1. **Task 1: etl.py steps no-redef fix + D-03 annotate to zero** — `480d42f` (feat)
2. **Task 2: pool.py unused-coroutine fix (resize async bug) + D-03 annotate to zero** — `0c07ada` (fix)

**Plan metadata:** (pending — final docs commit below)

## Files Created/Modified

- `pycopg/etl.py` — `from typing import TYPE_CHECKING, Any, cast` (added `Any`, `cast`); `steps` de-duplicated to a single `steps: list[Any]` declaration per method (sync + async `run()`); `Pipeline.transform` parameterized `Callable[..., Any]`; two `# type: ignore[unreachable]` (D-01, genuine runtime guards) in `__post_init__`; `dry_raw_watermark`/`raw_watermark` explicitly typed `datetime | int | str | None` (x4 sites); all builder functions and the watermark codec parameterized; `assert row is not None` added at 2 `fetchone()` call sites (x2 for sync+async = 4 total) backed by INSERT-RETURNING / re-SELECT-by-known-id invariants; `rows` materialization uses a named `records` intermediate + `cast("list[dict[str, Any]]", records)` (46 errors → 0)
- `pycopg/pool.py` — `from types import TracebackType` (new import); `Params` imported from `pycopg.base` (D-03 precedent reuse); **`AsyncPooledDatabase.resize()` changed from `def` to `async def` with `await self._pool.resize(...)`** (the real bug fix); `Callable[..., Any]`, `**kwargs: Any`, `Params`, `dict[str, Any]`, `Sequence[Sequence[Any]]`, `TracebackType | None` applied across both `PooledDatabase` and `AsyncPooledDatabase` (22 errors → 0, zero `# type: ignore` needed)
- `tests/test_pool.py` — removed the sync `TestAsyncPooledDatabase::test_resize` (masked-bug test); added `TestAsyncPooledDatabaseAsync::test_resize` with `AsyncMock` + `await` + `assert_awaited_once_with` as the resize-await regression guard

## Decisions Made

- **`steps` [no-redef] confirmed as annotation-only, not a runtime bug** — direct control-flow trace showed the dry_run branch's unconditional early `return` makes the two `steps` assignments mutually exclusive at runtime; documented rather than assumed, per the plan's explicit instruction to investigate before choosing a fix strategy.
- **`[unused-coroutine]` real bug found at pool.py:574, not etl.py:~2025 as the plan's context pointer suggested** — the plan's own escape clause ("If, after investigation, either turns out NOT to be a real bug [at the flagged location], document the evidence") was exercised for etl.py; the actual bug was chased down via the full-package `uv run mypy pycopg/` baseline and fixed at its real location (pool.py), preserving the plan's headline "fix the real bug" intent even though the file pointer in the plan text was inaccurate.
- **`resize()` fixed by making it `async def`, not by adding a sync wrapper or `asyncio.run()`** — `AsyncPooledDatabase` is an async-only class (every other public method — `open`/`execute`/`fetch_one`/`check`/`close` — is already `async def`); making `resize` async is the only change consistent with the class's existing API shape and requires no new sync/async bridging machinery.
- **Test moved to the async class, not made hybrid** — the old sync `test_resize` structurally could not detect a missing `await` (a `MagicMock` call succeeds with or without awaiting); the fix is a class move + `AsyncMock`, not a patch to the existing sync test.
- **`cast()` over inline `# type: ignore[assignment]` for the `to_dict(orient="records")` Hashable-vs-str mismatch** — black's formatter repeatedly relocated an inline ignore comment across the multi-line `.astype().where().to_dict()` chain onto a line mypy no longer associated with the assignment, causing an `unused-ignore` error on every reformat cycle; the named-variable + `cast()` form has no such chain for black to rewrap and was verified stable across two consecutive black runs (`1 file left unchanged`).
- **`assert row is not None` reused for two NEW invariant shapes** (INSERT...RETURNING single-row guarantee; re-SELECT-by-just-written-run_id) — extends the 46-03/46-04 assert-for-exclusivity-narrowing pattern to a different but equally-genuine runtime-invariant class (protocol guarantee rather than earlier-branch mutual exclusivity), rather than inventing a new narrowing idiom.

## Deviations from Plan

**1. [Rule 1 - Bug location correction] `[unused-coroutine]` fixed at pool.py:574, not etl.py as the plan text pointed to**
- **Found during:** Task 1 read_first investigation (etl.py)
- **Issue:** The plan's `<read_first>` and phase CONTEXT.md watch-item named etl.py as the location of the single `[unused-coroutine]` error. Direct `uv run mypy pycopg/etl.py 2>&1 | grep unused-coroutine` returned no matches, both at baseline and after all etl.py edits.
- **Fix:** Ran the full-package `uv run mypy pycopg/` baseline and located the actual occurrence at `pycopg/pool.py:574` (`AsyncPooledDatabase.resize`). Confirmed via `inspect.iscoroutinefunction` that `psycopg_pool.AsyncConnectionPool.resize` is genuinely async, then fixed `AsyncPooledDatabase.resize()` to be `async def` + `await`.
- **Files modified:** `pycopg/pool.py`, `tests/test_pool.py`
- **Commit:** `0c07ada`
- This is documented per the plan's own instruction ("If, after investigation, either turns out NOT to be a real bug, document the evidence in SUMMARY.md before choosing any suppression") — no suppression was needed for etl.py since there was nothing to suppress there; the real bug was found and fixed in Task 2's file instead of being silently missed.

No other deviations — both tasks' acceptance criteria (etl.py/pool.py → Success, no-redef/unused-coroutine gone and not silenced, tests green) were met within the existing task boundaries.

## Issues Encountered

- Both `pycopg_test` and `pycopg_test2` remain broken (TimescaleDB `.so` version drift, carried forward from 46-02/46-03/46-04) — verification ran against `pycopg_test3` per the current project operating instructions (superseding the plan's own `PGDATABASE=pycopg_test2` in its `<verify>` blocks, which is stale).
- `black` repeatedly relocated an inline `# type: ignore[assignment]` comment across reformats on the `to_dict(orient="records")` multi-line method chain (etl.py), producing an `unused-ignore` mypy error each time; resolved by refactoring to a named intermediate + `cast()`, which is immune to black's line-wrapping since it has no multi-line chain to rewrap. Verified stable across two consecutive `black` runs post-fix.
- `black` printed the same benign `Python 3.12 cannot parse code formatted for Python 3.15` safety-check warning seen in 46-03/46-04 (pre-existing local-Python-vs-black-target-version mismatch, unrelated to this plan) — each reformat completed correctly and was re-verified with a full mypy/ruff/pytest pass afterward.

## Next Phase Readiness

- Package-wide strict error count now **76** (down from 144 entering this plan), concentrated in exactly 3 files: `database.py` (~37), `async_database.py` (~38), `pycopg/__init__.py` (1 stray `no-untyped-def`).
- **FREEZE-05 is NOT yet complete** — this plan resolves 2 of the remaining 3 hotspot files; `database.py`, `async_database.py`, and `pycopg/__init__.py` still carry errors. Package-wide `uv run mypy pycopg/` must reach 0 across all of `pycopg/` before FREEZE-05 can be marked complete — deferred to the phase's final plan(s) (46-06/46-07 per the roadmap's bottom-up ordering: `database.py`/`async_database.py` are the last hotspot pair, explicitly the biggest remaining files at ~37-38 errors each).
- Both `database.py` and `async_database.py` errors include the same `[type-arg]`/`[return-value]`/`[misc]` (yield-type) shapes already resolved elsewhere in the package via D-03 — no new pattern discovery expected there, but `database.py:1732`/`async_database.py:1367` (`_read_postgis` overload mismatch on `TextClause`/`Connection`/`dict[Any, Any] | None`) looks like it may need a `cast()` or narrow ignore at the geopandas/SQLAlchemy boundary (an unstubbed-third-party-edge case, matching the original D-01 intent) — flagged for whichever plan picks up `database.py`.
- The `assert-for-exclusivity-narrowing` pattern now covers three distinct invariant shapes (46-03 branch-exclusivity, 46-04 same, 46-05 protocol-guarantee-after-write) — future plans hitting an `Optional`-narrowing-after-a-just-performed-write/read should reach for `assert` first before inventing a new idiom.
- No blockers for the next plan.

---
*Phase: 46-mypy-strict-py-typed-gate*
*Completed: 2026-07-02*

## Self-Check: PASSED

- FOUND: pycopg/etl.py
- FOUND: pycopg/pool.py
- FOUND: tests/test_pool.py
- FOUND: .planning/phases/46-mypy-strict-py-typed-gate/46-05-SUMMARY.md
- FOUND: 480d42f (Task 1 commit)
- FOUND: 0c07ada (Task 2 commit)
