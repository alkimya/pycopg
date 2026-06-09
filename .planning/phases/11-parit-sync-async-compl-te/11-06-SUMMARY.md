---
phase: 11-parit-sync-async-compl-te
plan: 06
subsystem: testing
tags: [parity, integration, real-db, allow-lists, pytest-asyncio]

requires:
  - phase: 11-parit-sync-async-compl-te
    provides: "Plans 02-05 — all 13 mirrored methods, C1 fix, PAR-07 signatures"
provides:
  - Minimized parity allow-lists (SYNC_ONLY={engine}, ASYNC_ONLY={async_engine, listen}, no signature mismatches)
  - TestBehavioralParity — real-DB sync==async assertions for this phase's pairs (PAR-08, D-03)
  - Per-method edge-case tests for the new sync methods (test_database.py)
affects: [11-07 coverage ratchet, CI tests.yml parity job]

tech-stack:
  added: []
  patterns:
    - "Behavioral parity: run the same op on Database and AsyncDatabase against pycopg_test, assert identical results"

key-files:
  created: []
  modified:
    - tests/test_parity.py
    - tests/test_database.py
    - tests/test_async_database.py

key-decisions:
  - "D-03: assert RESULTS/fields/behavior for this phase's pairs only — introspection stays the full-surface guard"
  - "D-06: listen kept in ASYNC_ONLY_METHODS with an explanatory comment (no sync twin by design)"
  - "D-07: KNOWN_SIGNATURE_MISMATCHES emptied — create_schema/create_extension now align"

patterns-established:
  - "Pattern: _uniq(prefix) helper for collision-free temp table/schema/db names in parity tests"

requirements-completed: [PAR-08]

duration: 30min
completed: 2026-06-09
---

# Phase 11 / Plan 06: Behavioral Parity Tests + Minimal Allow-Lists Summary

**test_parity.py now verifies real-DB behavioral parity (sync == async) for every pair this phase touched, and the three allow-lists are minimal and accurate — `listen` is the sole documented async-only behavior.**

## Performance

- **Duration:** ~30 min
- **Completed:** 2026-06-09
- **Tasks:** 3 completed
- **Files modified:** 3

## Accomplishments
- **Task 1 — allow-lists:** `SYNC_ONLY_METHODS` reduced to `{engine}`; `ASYNC_ONLY_METHODS` to `{async_engine, listen}` (listen documented async-only, D-06); `KNOWN_SIGNATURE_MISMATCHES` emptied (create_schema/create_extension aligned, D-07). All 4 introspection tests pass.
- **Task 2 — behavioral parity:** added `TestBehavioralParity` (13 tests) running the same operation on `Database` and `AsyncDatabase` against `pycopg_test` and asserting identical results: insert_many/upsert_many/stream/notify (PAR-03), add_primary_key/truncate_table/database_exists/list_databases (PAR-01/02), C1 from_dataframe primary_key, PAR-07 table_info/list_roles field parity + create_schema owner, and D-02 create constructor parity.
- **Task 3 — per-method edge cases:** `TestDatabaseBatchStreamNotify` in test_database.py (empty returns 0, on-conflict clause, stream batching, notify→pg_notify, invalid channel, no sync listen); `create_from_env` delegation test in test_async_database.py. (The 9 async methods already had dedicated coverage from Plans 03/04/05.)

## Task Commits

1. **Task 1+2: allow-lists + behavioral parity** — `9e8e929` (test)
2. **Task 3: per-method edge tests** — `38820c9` (test, includes an I001 import-order fix in a Plan-05 test)

## Files Created/Modified
- `tests/test_parity.py` — minimized allow-lists; new `TestBehavioralParity` + `_uniq` helper; fixed 2 pre-existing F541.
- `tests/test_database.py` — `TestDatabaseBatchStreamNotify` (8 edge-case tests).
- `tests/test_async_database.py` — `create_from_env` delegation test; import-order fix.

## Verification
- `tests/test_parity.py`: 17 passed (4 introspection + 13 behavioral). ✓
- `tests/test_database.py tests/test_async_database.py`: 268 passed. ✓
- Combined parity+database+async: 285 passed. ✓
- ruff/black: test_parity.py fully clean; test_database.py/test_async_database.py have only pre-existing F841/I001 findings (Phase 12 cleanup) — no new issues from this plan.

## Notes / Deviations
- Task 3 was largely pre-satisfied: per-method async coverage was created incrementally in Plans 03-05. This plan added the missing sync edge cases and the create_from_env delegation test rather than duplicating existing real-DB tests (D-08 — no fragile redundancy).

## Self-Check: PASSED
