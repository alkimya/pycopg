---
phase: 11-parit-sync-async-compl-te
plan: 05
subsystem: database
tags: [async, correctness, primary-key, engine-dispose, signatures, parity]

requires:
  - phase: 11-parit-sync-async-compl-te
    provides: "Plan 03 async add_primary_key (needed by C1); Plan 04 admin methods"
provides:
  - C1 fixed — async from_dataframe/from_geodataframe apply primary_key
  - C2 fixed — async close() disposes the async engine
  - PAR-07 — async create_extension(schema=)/create_schema(owner=) signatures aligned to sync
affects: [11-06 parity allow-list (KNOWN_SIGNATURE_MISMATCHES cleanup)]

tech-stack:
  added: []
  patterns:
    - "async close() disposes the lazily-created engine, mirroring sync close()"

key-files:
  created: []
  modified:
    - pycopg/async_database.py
    - tests/test_async_database.py

key-decisions:
  - "C1/PAR-04: replace warning-and-ignore with await self.add_primary_key(table, primary_key, schema) under the same if_exists != 'append' guard as sync"
  - "C2/PAR-05/D-05: close() disposes self._async_engine and nulls it; the is-not-None guard provides idempotence"
  - "PAR-07/D-07: async catches up to the richer sync signatures; table_info/list_roles already matched (verified, no change)"

patterns-established: []

requirements-completed: [PAR-04, PAR-05, PAR-07]

duration: 26min
completed: 2026-06-09
---

# Phase 11 / Plan 05: Async Correctness Fixes + Signature Alignment Summary

**The three async correctness bugs are closed — primary_key is actually applied in async DataFrame loads, close() disposes the engine — and the async signatures now match the richer sync contract.**

## Performance

- **Duration:** ~26 min
- **Completed:** 2026-06-09
- **Tasks:** 2 completed
- **Files modified:** 2

## Accomplishments
- **C1 (PAR-04):** async `from_dataframe` and `from_geodataframe` now call `await self.add_primary_key(table, primary_key, schema)` under the `if_exists != "append"` guard (mirroring sync), replacing the old log-and-ignore warning blocks. Removed the dead `import logging`/`logger.warning` code.
- **C2 (PAR-05/D-05):** async `close()` now disposes `self._async_engine` and resets it to `None` (was `pass`), releasing pooled connections; idempotent via the `is not None` guard.
- **PAR-07/D-07:** async `create_extension` now takes `schema=None` (+ `SCHEMA` clause, `validate_identifier(schema)`); async `create_schema` now takes `owner=None` (+ `AUTHORIZATION` clause, `validate_identifier(owner)`). Both match the sync signatures exactly. `table_info` and `list_roles` were already field-identical to sync — verified, no change.
- Added 11 tests (`TestAsyncDatabaseCorrectnessFixes`): C1 mock + real-DB PK, append-skips-PK, C2 dispose + no-engine idempotence, schema/owner clauses, signature parity, table_info/list_roles field parity.

## Task Commits

1. **Task 1+2: C1/C2 fixes + signature alignment + tests** — `abc70e8` (fix)
   _(Committed together — same file, one cohesive correctness/parity change set.)_

## Files Created/Modified
- `pycopg/async_database.py` — C1 in `from_dataframe`/`from_geodataframe`; C2 in `close()`; signatures of `create_extension`/`create_schema`.
- `tests/test_async_database.py` — `TestAsyncDatabaseCorrectnessFixes` (11 tests).

## Verification
- `tests/test_async_database.py`: 167 passed (11 new). ✓
- `test_parity.py::TestAsyncParity::test_method_signatures_match`: passed (create_extension/create_schema now match). ✓
- ruff + black: clean on changed files.

## Notes / Deviations
- No deviation from plan intent. `table_info`/`list_roles` required no edits — they already matched the sync field set; the plan anticipated this ("if any field differs, align it").
- No sync signature was reduced (D-07 honored).

## Self-Check: PASSED
