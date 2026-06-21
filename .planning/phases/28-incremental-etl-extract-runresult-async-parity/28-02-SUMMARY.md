---
phase: 28-incremental-etl-extract-runresult-async-parity
plan: 02
subsystem: database
tags: [postgresql, pandas, etl, watermark, incremental, async]

# Dependency graph
requires:
  - phase: 28-01
    provides: "RunResult.watermark_used/watermark_recorded; sync _do_extract helper; sync watermark capture block with pd.isna-before-is_float guard; _row_to_result NULL guard"
provides:
  - "AsyncETLAccessor._read_watermark (async mirror of sync; isolated autocommit connection)"
  - "AsyncETLAccessor._end_run gains watermark: dict | None = None param, forks to ETL_UPDATE_RUN_WATERMARK + Jsonb"
  - "AsyncETLAccessor._do_extract() shared async filtered-extract helper (watermark-aware, D-A2a)"
  - "AsyncETLAccessor.run() filtered extract via _read_watermark + _do_extract + verbatim capture block"
  - "AsyncETLAccessor.run() incremental dry_run with watermark_used/watermark_recorded (ETL-INC-09)"
  - "Async success path encodes + records watermark via _end_run(watermark=wm_env); failed/empty pass none"
  - "12 async incremental integration tests in TestAsyncRunResultSurface (ETL-INC-03/04/07/08/09/11)"
  - "ETL-INC-11 closed: full sync/async parity on incremental watermark surface"
affects:
  - "28-03: docs plan references both sync and async surfaces now fully implemented"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Async _do_extract shared helper: single awaitable extract path for both dry_run and real path (D-A2a)"
    - "Verbatim capture block copied to async: pd.isna before is_float ordering preserved (WR-02)"
    - "Byte-for-byte ETLError message text in async (D-A3 strict parity)"
    - "dc_replace injects watermark_used on async success result (D-A1, not stored in DB)"

key-files:
  created: []
  modified:
    - "pycopg/etl.py"
    - "tests/test_etl_accessor.py"

key-decisions:
  - "D-A3 honored: async _do_extract and capture block are byte-for-byte mirrors of sync (only async with/await differ)"
  - "Async _do_extract as a method (mirrors sync choice) — avoids dry_run/real-path drift"
  - "ETLError message text for missing-column and float-dtype verified byte-for-byte equal in async guard tests (D-A3)"
  - "watermark_used injected via dc_replace on async success path (same pattern as sync — D-A1)"
  - "failed/empty-batch paths pass no watermark to _end_run (no-advance-on-failure invariant preserved)"

patterns-established:
  - "Async watermark reconciliation: same %s->:wm named bind as sync _do_extract"
  - "Async dry_run watermark capture: identical guard block to real path (pd.isna before is_float)"
  - "ETL-INC-04 guard text parity: async tests assert string equality to expected message, not just regex match"

requirements-completed: [ETL-INC-03, ETL-INC-04, ETL-INC-07, ETL-INC-08, ETL-INC-09, ETL-INC-11]

# Metrics
duration: 26min
completed: 2026-06-21
---

# Phase 28 Plan 02: Async ETL parity — _read_watermark, _do_extract, watermark capture + dry_run, 12 integration tests closing ETL-INC-11

**Full async incremental watermark surface ported 1:1 from sync: `_read_watermark` + `_do_extract` + verbatim capture block + `dry_run` watermark fields, closing ETL-INC-11 (sync/async parity); `test_accessor_parity` green and unmodified**

## Performance

- **Duration:** ~26 min
- **Started:** 2026-06-21T17:08:00Z
- **Completed:** 2026-06-21T17:34:19Z
- **Tasks:** 3 completed
- **Files modified:** 2

## Accomplishments

- Added `AsyncETLAccessor._read_watermark` — async mirror of sync (isolated autocommit connection, `ETL_GET_LAST_WATERMARK`, NULL→`_decode_watermark` guard identical to sync)
- Extended async `_end_run` with `watermark: dict | None = None` param — body forks to `ETL_UPDATE_RUN_WATERMARK` + `Jsonb(watermark)` on success path, `ETL_UPDATE_RUN` otherwise (exact sync structure)
- Added `AsyncETLAccessor._do_extract()` — shared awaitable filtered-extract helper (mirrors sync `_do_extract`): `%s`→`:wm` bind reconciliation, `extract_limit` as LIMIT subquery, non-incremental fallback
- Wired async `run()` dry_run fork: reads `await _read_watermark`, calls `await _do_extract`, captures `max(col)` with verbatim guard block (`pd.isna` before `is_float`), returns `RunResult` with `watermark_used`/`watermark_recorded`
- Wired async `run()` real path: reads `wm` before extract, `await _do_extract`, verbatim capture block, encodes and passes `watermark=wm_env` to `_end_run` on success only; `dc_replace` injects `watermark_used`
- 12 new async integration tests in `TestAsyncRunResultSurface` covering all 5 requirements + ETL-INC-11 parity; 3 ETL-INC-04 guard tests assert byte-for-byte message equality (D-A3)

## Task Commits

1. **Task 1: async _read_watermark + async _end_run(watermark=)** - `e88aedd` (feat)
2. **Task 2: async run() — filtered extract, watermark capture, incremental dry_run** - `6c99d26` (feat)
3. **Task 3: async integration tests mirroring sync + parity confirmation** - `6a6cfee` (test)

## Files Created/Modified

- `/home/loc/workspace/pycopg/pycopg/etl.py` — `AsyncETLAccessor._read_watermark` (new), `_end_run` extended with `watermark=` fork, `_do_extract` (new async helper), `run()` dry_run + real paths fully rewritten with watermark wiring
- `/home/loc/workspace/pycopg/tests/test_etl_accessor.py` — `async_etl_src` fixture (new), 12 new tests in `TestAsyncRunResultSurface`

## Decisions Made

- Async `_do_extract` as a method (matching sync choice) — avoids two-fork drift; body is `await self._db.to_dataframe(...)` vs sync `self._db.to_dataframe(...)`, only mechanical diff
- Verbatim capture block copied to async (not factored into a helper) — preserves the Phase-27 WR-02 fix visibly auditable in both places
- ETL-INC-04 guard text tested via exact string equality (not just regex match) in async tests — provides the byte-for-byte parity proof required by D-A3

## Deviations from Plan

None — plan executed exactly as written. The `%s`→`:wm` reconciliation, `pd.isna`-before-`is_float` ordering, and exact `ETLError` message text were all handled as specified.

## Issues Encountered

- `black` reformatted `etl.py` and `test_etl_accessor.py` once each after edits — auto-resolved with `uv run black` before commits. Pre-existing Python 3.15 target-version warning is non-blocking.

## Next Phase Readiness

- All 6 ETL-INC-* requirements on async side are closed; Plan 28-03 (docs) can now document the complete sync+async surface
- `test_accessor_parity` green and unmodified — structural parity is confirmed
- `interrogate pycopg` = 100%; coverage gate will be confirmed in full test run

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. All three STRIDE threats mitigated:
- T-28-A1: watermark VALUE reaches `to_dataframe` as `:wm` named bind (never interpolated)
- T-28-A2: identifiers validated by `_build_incremental_extract_sql` before any interpolation
- T-28-A3: watermark written via `Jsonb(watermark)` on dedicated autocommit connection, success path only

## Self-Check: PASSED

- `pycopg/etl.py` contains `async def _read_watermark` on `AsyncETLAccessor`: confirmed
- `pycopg/etl.py` contains `async def _do_extract` on `AsyncETLAccessor`: confirmed
- `async _end_run` has `watermark: dict | None = None` param: confirmed
- `tests/test_etl_accessor.py` contains `TestAsyncRunResultSurface` with async incremental tests: confirmed
- Commits `e88aedd`, `6c99d26`, `6a6cfee` exist in git log: confirmed
- 28 async tests pass (TestAsyncRunResultSurface): confirmed
- `test_accessor_parity` 7/7 green and test_parity.py unmodified: confirmed
- `interrogate pycopg` 100%: confirmed

---
*Phase: 28-incremental-etl-extract-runresult-async-parity*
*Completed: 2026-06-21*
