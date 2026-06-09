---
phase: 11-parit-sync-async-compl-te
plan: 04
subsystem: database
tags: [async, admin, extensions, database, classmethod, constructor, parity]

requires:
  - phase: 11-parit-sync-async-compl-te
    provides: "Plan 03 — async constraint DDL (first part of the 9 missing async methods)"
provides:
  - AsyncDatabase.drop_extension
  - AsyncDatabase.database_exists
  - AsyncDatabase.list_databases
  - AsyncDatabase.create (async classmethod constructor)
  - AsyncDatabase.create_from_env (async classmethod constructor)
affects: [11-06 parity allow-list, async DB lifecycle]

tech-stack:
  added: []
  patterns:
    - "Async admin methods reconnect to postgres via config.with_database('postgres') + AsyncConnection.connect"
    - "Async alternative constructors are @classmethod async def returning a connected AsyncDatabase"

key-files:
  created: []
  modified:
    - pycopg/async_database.py
    - tests/test_async_database.py

key-decisions:
  - "D-02: create/create_from_env are async classmethods mirroring the sync constructors"
  - "database_exists opens its own admin read connection (no autocommit needed); list_databases uses the normal execute path"

patterns-established:
  - "Pattern: async constructors validate identifiers, check pg_database existence with %s, then CREATE DATABASE"

requirements-completed: [PAR-02]

duration: 24min
completed: 2026-06-09
---

# Phase 11 / Plan 04: Async Admin Methods + Constructors Summary

**AsyncDatabase now has drop_extension, database_exists, list_databases, and async create/create_from_env constructors — completing all 9 missing async methods (PAR-01 + PAR-02).**

## Performance

- **Duration:** ~24 min
- **Completed:** 2026-06-09
- **Tasks:** 2 completed
- **Files modified:** 2

## Accomplishments
- Added async `drop_extension` (mirrors sync, `autocommit=True`), `database_exists` (own admin read connection to `postgres`), and `list_databases` (non-template names, sorted).
- Added async `create` and `create_from_env` `@classmethod`s (D-02), mirroring the sync constructors: admin-connect to `postgres`, existence check via `%s`, `CREATE DATABASE`, return a connected `AsyncDatabase`.
- With Plan 03's four DDL methods, **all 9 PAR-01/PAR-02 async methods now exist** — `test_all_database_public_methods_exist_in_async` passes.
- Added 7 real-DB async tests (`TestAsyncDatabaseAdminIntegration`): exists true/false, list includes pycopg_test, drop_extension idempotency, classmethod check, signature parity vs sync, create-returns-connected, create-raises-on-existing.

## Task Commits

1. **Task 1+2: async admin methods + constructors + tests** — `e9dcfcc` (feat)
   _(Both tasks committed together — same file, cohesive change set.)_

## Files Created/Modified
- `pycopg/async_database.py` — `drop_extension` (EXTENSIONS), `database_exists`/`list_databases` (DATABASE ADMIN), `create`/`create_from_env` (near `from_env`).
- `tests/test_async_database.py` — `TestAsyncDatabaseAdminIntegration` (7 tests); added module-level `import inspect`.

## Verification
- `tests/test_async_database.py`: 156 passed (7 new). ✓
- `test_all_database_public_methods_exist_in_async`: passed. ✓
- async `create` signature matches sync `Database.create` (same names/order/defaults). ✓
- ruff: my new code clean (4 pre-existing F841/unused findings remain — Phase 12). black: changed files conform.

## Notes / Deviations
- None. The async `create_extension` still lacks the sync's `schema` param — that PAR-07 signature alignment is Plan 11-05's job, deliberately not touched here.
- `test_create_returns_connected_database` creates and drops a throwaway DB (`pycopg_tmp_create_xyz`) with cleanup in `finally`.

## Self-Check: PASSED
