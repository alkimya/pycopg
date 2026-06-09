---
phase: 11-parit-sync-async-compl-te
plan: 02
subsystem: database
tags: [sync, batch, streaming, notify, pg_notify, parity]

requires:
  - phase: 10-s-curit-r-siduelle-robustesse
    provides: validate_identifier / validate_identifiers helpers, sync cursor/execute primitives
provides:
  - Database.insert_many (sync mirror of async twin)
  - Database.upsert_many (sync mirror of async twin)
  - Database.stream (lazy sync generator mirror)
  - Database.notify (sync mirror; payload now via pg_notify)
  - Correctness fix: async notify now uses pg_notify (was broken NOTIFY ..., %s)
affects: [11-06 parity allow-list updates, sync↔async parity surface]

tech-stack:
  added: []
  patterns:
    - "Sync batch/stream/notify mirror the async twins using with self.cursor(...) / execute / execute_many"
    - "NOTIFY payloads sent via SELECT pg_notify(%s, %s) (parameterizable; raw NOTIFY cannot bind payload)"

key-files:
  created: []
  modified:
    - pycopg/database.py
    - pycopg/async_database.py
    - tests/test_database_integration.py

key-decisions:
  - "D-01: each new sync method is a mechanical mirror of its async twin"
  - "D-06: listen is NOT mirrored to Database — a blocking sync listener is an anti-pattern (async-only)"
  - "DEVIATION: NOTIFY {channel}, %s is invalid SQL (NOTIFY cannot bind the payload); switched both sync and async notify to SELECT pg_notify(%s, %s) to keep them in parity AND make them actually work"

patterns-established:
  - "Pattern: sync streaming uses with self.cursor() + fetchmany(batch_size) loop with yield from"

requirements-completed: [PAR-03]

duration: 25min
completed: 2026-06-09
---

# Phase 11 / Plan 02: Sync Batch/Stream/Notify Parity Summary

**The sync `Database` now has working `insert_many`, `upsert_many`, `stream`, and `notify` matching their async twins — and a latent NOTIFY-binding bug was fixed on both sides.**

## Performance

- **Duration:** ~25 min
- **Completed:** 2026-06-09
- **Tasks:** 2 completed
- **Files modified:** 3

## Accomplishments
- Added `Database.insert_many` and `Database.upsert_many` as mechanical mirrors (D-01) of the async twins — empty-rows guard, `validate_identifiers` reuse, `execute_many`/`insert_many` delegation.
- Added `Database.stream` as a lazy sync generator (`with self.cursor()` + `fetchmany(batch_size)` loop, `yield from`).
- Added `Database.notify`; deliberately did NOT add a sync `listen` (D-06).
- **Correctness fix (deviation):** discovered that `NOTIFY {channel}, %s` is invalid — PostgreSQL's `NOTIFY` is a utility statement and cannot bind the payload, raising `syntax error near "$1"`. The async twin had the same latent bug. Switched BOTH sync and async `notify` to `SELECT pg_notify(%s, %s)`, keeping the channel validated and the payload safely parameterized.
- Added 9 integration tests (`TestDatabaseBatchStreamNotify`) covering all four methods + the D-06 no-listen guarantee.

## Task Commits

Each task was committed atomically:

1. **Task 1: Sync insert_many + upsert_many** — `0fe430b` (feat)
2. **Task 2: Sync stream + notify (+ async notify pg_notify fix)** — `8f2babc` (feat)

## Files Created/Modified
- `pycopg/database.py` — added `insert_many`, `upsert_many`, `stream`, `notify`.
- `pycopg/async_database.py` — fixed async `notify` to use `pg_notify` (parity + correctness).
- `tests/test_database_integration.py` — new `TestDatabaseBatchStreamNotify` class (9 tests).

## Verification
- `tests/test_database_integration.py`: 41 passed (9 new). ✓
- async `notify` sanity-checked against real DB: works. ✓
- ruff: clean on changed files (UP028 fixed via `yield from`). ✓
- black: changed files conform. ✓
- `tests/test_parity.py`: 3 passed, 1 expected failure — `test_exception_lists_are_minimal` flags the 4 now-mirrored methods as needing removal from `ASYNC_ONLY_METHODS`. **This is expected** (plan §verification) and is resolved by Plan 11-06's allow-list update. No other regressions.

## Notes / Deviations
- **Deviation (notify → pg_notify):** changed from the literal plan instruction (`NOTIFY {channel}, %s`) because that statement is invalid SQL. Applied the fix to both sync and async to preserve parity and correctness. Documented in commit `8f2babc`.
- The two `tdd="true"` tasks were implemented test-first conceptually, but project `tdd_mode=false`, so no separate RED commits were required.

## Self-Check: PASSED
