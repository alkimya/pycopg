---
phase: 11-parit-sync-async-compl-te
plan: 03
subsystem: database
tags: [async, ddl, constraints, primary-key, foreign-key, unique, truncate, parity]

requires:
  - phase: 11-parit-sync-async-compl-te
    provides: "Plan 01 — async_engine on async driver (first touch of async_database.py)"
provides:
  - AsyncDatabase.add_primary_key (mirror of sync twin)
  - AsyncDatabase.add_foreign_key (mirror, with valid_actions ON DELETE/UPDATE check)
  - AsyncDatabase.add_unique_constraint (mirror)
  - AsyncDatabase.truncate_table (mirror)
affects: [11-05 C1 (needs async add_primary_key), 11-06 parity allow-list]

tech-stack:
  added: []
  patterns:
    - "Async DDL methods mirror sync twins line-for-line, swapping self.execute -> await self.execute"

key-files:
  created: []
  modified:
    - pycopg/async_database.py
    - tests/test_async_database.py

key-decisions:
  - "D-01: mechanical mirror of each sync twin; identical validate_* wiring and valid_actions allow-set"
  - "Ordering: async add_primary_key created here so Plan 05 C1 (async from_dataframe primary_key) can call it"

patterns-established:
  - "Pattern: new async DDL grouped under a CONSTRAINTS & INDEXES section in async_database.py"

requirements-completed: [PAR-01]

duration: 22min
completed: 2026-06-09
---

# Phase 11 / Plan 03: Async Constraint/Admin DDL Parity Summary

**AsyncDatabase now has working add_primary_key, add_foreign_key, add_unique_constraint, and truncate_table — closing the PAR-01 constraint-DDL gap and unblocking the C1 fix in Plan 05.**

## Performance

- **Duration:** ~22 min
- **Completed:** 2026-06-09
- **Tasks:** 2 completed
- **Files modified:** 2

## Accomplishments
- Mirrored 4 sync constraint/admin DDL methods into `AsyncDatabase` (D-01), each swapping `self.execute(...)` for `await self.execute(...)` with identical `validate_identifiers`/`validate_identifier` wiring.
- `add_foreign_key` carries the same `valid_actions` allow-set (`NO ACTION/RESTRICT/CASCADE/SET NULL/SET DEFAULT`), raising `ValueError` for bad `on_delete`/`on_update` before any SQL.
- `add_primary_key` now exists on the async side, satisfying the ordering constraint for Plan 05's C1.
- Added 6 real-DB async integration tests (`TestAsyncDatabaseConstraintsIntegration`) including signature-parity, cascade-on-delete, unique-rejects-duplicate, and invalid-action-raises.

## Task Commits

1. **Task 1+2: async PK/FK/unique/truncate mirrors + tests** — `a932587` (feat)
   _(Both tasks committed together — same file, cohesive change set.)_

## Files Created/Modified
- `pycopg/async_database.py` — added `truncate_table` + CONSTRAINTS & INDEXES section with `add_primary_key`, `add_foreign_key`, `add_unique_constraint`.
- `tests/test_async_database.py` — new `TestAsyncDatabaseConstraintsIntegration` (6 tests); fixed stale `test_async_engine_created_on_access` assertion (see below).

## Verification
- `tests/test_async_database.py`: 149 passed (6 new). ✓
- `test_parity.py::TestAsyncParity::test_all_database_public_methods_exist_in_async`: passed (the 4 methods now exist). ✓
- ruff: my new code clean (4 pre-existing F841/unused-import findings remain — Phase 12 cleanup, not this plan; my engine-test fix actually removed 2). black: changed files conform.

## Notes / Deviations
- **Cross-plan regression fix (from Plan 01):** the post-merge full-suite run surfaced `test_async_engine_created_on_access` failing because Plan 01 correctly rewired `async_engine` to `config.async_url`, but this unit test still asserted `config.url`. Updated the assertion to expect `config.async_url` (the PAR-06 behavior). This was a stale test, not a code defect — Plan 01's own verify only ran `test_config.py` and missed it.

## Self-Check: PASSED
