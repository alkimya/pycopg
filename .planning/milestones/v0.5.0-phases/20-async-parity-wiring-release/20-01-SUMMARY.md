---
phase: 20-async-parity-wiring-release
plan: "01"
subsystem: etl
tags: [async, etl, accessor, property, exports]
dependency_graph:
  requires: [phases/19-sync-runner-query-surface]
  provides: [AsyncETLAccessor, async_db.etl, top-level ETL exports]
  affects: [pycopg/etl.py, pycopg/async_database.py, pycopg/__init__.py]
tech_stack:
  added: [asyncio.to_thread]
  patterns: [async-mirror, lazy-property, asynccontextmanager]
key_files:
  created: []
  modified:
    - pycopg/etl.py
    - pycopg/async_database.py
    - pycopg/__init__.py
decisions:
  - "AsyncETLAccessor appended at bottom of etl.py following AsyncSpatialAccessor/spatial.py one-file convention"
  - "Transform dispatch via asyncio.to_thread(step, df) — callable + arg form, not step(df) (SC-2, Pitfall 2)"
  - "Run-log writes use dedicated async with self._db.connect(autocommit=True) per call — isolates from load transaction"
  - "async_db.etl lazy property mirrors async_db.spatial pattern exactly (SC-3)"
  - "Four symbols exported: ETLAccessor, AsyncETLAccessor, RunResult, Pipeline added to pycopg.__all__"
metrics:
  duration: "352s (~6 minutes)"
  completed: "2026-06-15"
  tasks_completed: 2
  tasks_total: 2
  files_changed: 3
---

# Phase 20 Plan 01: AsyncETLAccessor + Property Wiring + Exports Summary

Async mirror of the locked sync `ETLAccessor` via `AsyncETLAccessor` class (in `pycopg/etl.py`), lazy `async_db.etl` property wired on `AsyncDatabase` following the `async_db.spatial` pattern exactly, and four ETL public symbols added to `pycopg.__all__`.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add AsyncETLAccessor class (async mirror of ETLAccessor) to pycopg/etl.py | 467a10f | pycopg/etl.py |
| 2 | Wire lazy async_db.etl property + add four top-level exports | 9a501bd | pycopg/async_database.py, pycopg/__init__.py |

## What Was Built

### Task 1: AsyncETLAccessor (pycopg/etl.py)

Added `import asyncio` (alphabetical, before `traceback`) and `from pycopg.async_database import AsyncDatabase` to the `TYPE_CHECKING` block. Appended `AsyncETLAccessor` class at the bottom of `pycopg/etl.py` after `ETLAccessor`.

All seven methods mirrored as `async def`:
- `init`, `_start_run`, `_end_run`, `_fetch_run_result` — dedicated `async with self._db.connect(autocommit=True)` per call
- `history`, `last_run` — same autocommit connection pattern, `await cur.fetchall()` / `await cur.fetchone()`
- `run` — full dry-run early fork + normal ETL path, with:
  - `await self._db.to_dataframe(...)`, `await self._db.table_exists(...)`, `await self._db.from_dataframe(...)`
  - Transform chain: `df = await asyncio.to_thread(step, df)` (SC-2 — callable + arg, not `step(df)`)
  - Atomic load: `async with self._db.session(): async with self._db.transaction() as conn: async with conn.cursor() as cur:`
  - `await self._end_run(...)` in both success and except paths

Pure module-level helpers (`_row_to_result`, `_is_sql_source`, `_build_insert_sql`, `_build_upsert_sql`, `build_truncate_sql`, `_step_label`, `build_init_sql`) reused byte-for-byte — no duplication.

Full numpydoc docstrings on class and every method.

### Task 2: Property wiring + exports

**`pycopg/async_database.py`:**
- Added `from pycopg.etl import AsyncETLAccessor` to `TYPE_CHECKING` block
- Added `self._etl: AsyncETLAccessor | None = None` to `AsyncDatabase.__init__` (after `self._spatial`)
- Added `etl` property immediately after `spatial` property — mirrors it exactly (lazy import + cache in `self._etl`)

**`pycopg/__init__.py`:**
- Added `from pycopg.etl import AsyncETLAccessor, ETLAccessor, Pipeline, RunResult` (alphabetical, after `from pycopg.exceptions import`)
- Added all four to `__all__` under new `# ETL` comment block after `# Spatial`

## Verification

All acceptance criteria passed:

```
# Task 1
grep -q "class AsyncETLAccessor" pycopg/etl.py          # PASS
grep -q "import asyncio" pycopg/etl.py                   # PASS
grep -q "asyncio.to_thread(step, df)" pycopg/etl.py      # PASS
grep -c "async with self._db.connect(autocommit=True)"   # 10 occurrences
# Structural parity check: OK (public methods match)
# All run/history/last_run/init are coroutine functions: OK
# ruff check pycopg/etl.py: All checks passed

# Task 2
from pycopg import ETLAccessor, AsyncETLAccessor, RunResult, Pipeline  # OK
all(s in pycopg.__all__ for s in ('ETLAccessor','AsyncETLAccessor','RunResult','Pipeline'))  # True
db.etl returns AsyncETLAccessor, db.etl is db.etl (cache OK)
# 2 pre-existing TestAsyncParity failures now GREEN
# 74/74 tests pass: uv run pytest tests/test_parity.py tests/test_etl_accessor.py -o addopts="" -x -q
# interrogate pycopg --fail-under 95: PASS
```

## Success Criteria

- [x] `await async_db.etl.run/history/last_run/run(dry_run=True)` exist and mirror sync (SC-1)
- [x] Transform callables dispatched via `asyncio.to_thread(step, df)` (SC-2)
- [x] `async_db.etl` is lazily-created `AsyncETLAccessor` mirroring `async_db.spatial` (SC-3)
- [x] ETL public symbols exported from `pycopg` top level
- [x] Two pre-existing `TestAsyncParity` failures now green (ETL-12/ETL-13)

## Deviations from Plan

None — plan executed exactly as written.

### Worktree Base Recovery (infrastructure)

The worktree was forked from commit `333e070` (stale `origin/HEAD`) instead of the dispatch base `b10a397` (local `main` HEAD). Since the worktree branch had zero commits ahead of the stale base, it was safe to `git reset --hard b10a397` before starting work. This is the documented recovery pattern for the Phase 18/20 recurring worktree-base-mismatch issue.

## Threat Surface Scan

No new security surface introduced. `AsyncETLAccessor` reuses the same SQL constants (`ETL_INSERT_RUN`, `ETL_UPDATE_RUN`, `ETL_LIST_RUNS`, `ETL_GET_LAST_RUN`, `ETL_GET_RUN`) and the same pure builders (`_build_insert_sql`, `_build_upsert_sql`, `build_truncate_sql`) with `validate_identifiers` guards. No new identifier-interpolation path. T-20-01 and T-20-02 dispositions: accepted (no new surface).

## Self-Check: PASSED

| Item | Status |
|------|--------|
| pycopg/etl.py exists | FOUND |
| pycopg/async_database.py exists | FOUND |
| pycopg/__init__.py exists | FOUND |
| commit 467a10f (Task 1) exists | FOUND |
| commit 9a501bd (Task 2) exists | FOUND |
