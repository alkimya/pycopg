---
phase: 10-s-curit-r-siduelle-robustesse
plan: "02"
subsystem: database
tags: [migrations, atomicity, postgresql, psycopg, security, b3, sec-03]

requires:
  - phase: 09-migration-uv-outillage-projet
    provides: uv toolchain, CI with timescaledb-ha service for real-DB integration tests

provides:
  - "Atomic Migrator._apply: UP SQL + INSERT version in one explicit transaction (B3 fix)"
  - "Atomic Migrator.rollback: DOWN SQL + DELETE version in one explicit transaction"
  - "Red->green regression tests proving no partial trace on mid-migration failure"

affects:
  - 10-05-coverage-ratchet
  - future phases touching migrations.py

tech-stack:
  added: []
  patterns:
    - "Use self.db.transaction() contextmanager for any paired SQL+version-table mutation in migrations"
    - "Real-DB integration tests (D-06) for atomicity verification — mocks cannot observe PostgreSQL transaction boundaries"

key-files:
  created:
    - tests/test_migration_atomicity.py
  modified:
    - pycopg/migrations.py
    - tests/test_migrations.py

key-decisions:
  - "D-05/B3: wrap _apply (UP SQL + INSERT) and rollback (DOWN SQL + DELETE) each in self.db.transaction() — both statements commit together or roll back together"
  - "D-06: real-DB integration for B3 tests — atomicity requires a real PostgreSQL backend; mocks cannot distinguish partial commits"
  - "Auto-fixed: updated test_migrate_all and test_migrate_failure mocks to use transaction() contextmanager instead of cursor() after _apply refactor broke them (Rule 1)"

patterns-established:
  - "Migration atomicity pattern: with self.db.transaction() as conn: / with conn.cursor() as cur:"
  - "TDD atomicity test pattern: write migration with valid statement + deliberately failing statement; assert no partial trace post-failure"

requirements-completed: [SEC-03, SEC-06]

duration: 30min
completed: 2026-06-08
---

# Phase 10 Plan 02: Migration Atomicity (B3) Summary

**Migrator._apply and rollback now wrap SQL + version-table mutation in explicit PostgreSQL transactions via self.db.transaction(), with real-DB red->green regression tests proving no partial trace on mid-course failure**

## Performance

- **Duration:** ~30 min
- **Started:** 2026-06-08T20:00:00Z
- **Completed:** 2026-06-08T20:28:45Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Fixed B3 (SEC-03): `_apply` now runs UP SQL + INSERT version inside `with self.db.transaction() as conn:` — a mid-course failure rolls back both statements atomically
- Fixed `rollback` per-migration block: DOWN SQL + DELETE version wrapped identically in `self.db.transaction()` — a failed rollback leaves the version row intact and the schema unchanged
- Created `tests/test_migration_atomicity.py` with two real-DB integration tests that prove the red->green property (pre-fix code would leave partial state visible)
- Fixed two mock-based unit tests in `test_migrations.py` that were mocking `db.cursor()` but needed to mock `db.transaction()` after the refactor (Rule 1 auto-fix)

## Task Commits

Each task was committed atomically:

1. **Task 1: Fix B3 — wrap _apply and rollback in explicit atomic transactions** - `4e8047e` (fix)
2. **Task 2: Red->green regression test for B3** - `c05fcd2` (test)

**Plan metadata:** (committed below as docs commit)

## Files Created/Modified

- `pycopg/migrations.py` - Replaced bare `cursor()` with `transaction()` in `_apply` and `rollback`; both pairs of statements (SQL + version-table mutation) are now atomic
- `tests/test_migration_atomicity.py` - Two real-DB integration tests: Test A (apply failure leaves no probe table, no version row) and Test B (rollback failure leaves version row intact and schema unchanged)
- `tests/test_migrations.py` - Updated `test_migrate_all` and `test_migrate_failure` to mock `db.transaction()` (contextmanager yielding a `conn` mock) after `_apply` refactor

## Decisions Made

- Used `self.db.transaction()` (the existing `Database.transaction()` contextmanager at database.py:323-341) to wrap the SQL + version-table pair — the contextmanager commits on success and rolls back on any exception, providing clean atomicity semantics
- Within the transaction context, used `conn.cursor()` for statement execution (not `db.cursor()`) since the connection object is yielded directly by `transaction()`
- Preserved existing `try/except Exception -> raise MigrationError(...) from e` wrapping in `rollback` — transaction rollback happens automatically before the MigrationError propagates
- D-06 choice: real-DB integration tests — atomicity is only observable against a real PostgreSQL backend that actually tracks transaction boundaries; psycopg mocks cannot observe partial DDL commit behavior

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated mock-based tests to match the new transaction() API**
- **Found during:** Task 2 (running `tests/test_migrations.py` after Task 1 fix)
- **Issue:** `test_migrate_all` and `test_migrate_failure` mocked `db.cursor()` but `_apply` now calls `db.transaction()`. With the old mock, `db.transaction` returned a MagicMock that when used as a contextmanager yielded a MagicMock `conn`, but `conn.cursor()` was never called through the mock setup, so cursor.execute.call_count was 0 and the failure side_effect was never triggered
- **Fix:** Added a `@contextmanager` function `fake_transaction()` that yields a `conn_mock` with `conn_mock.cursor.return_value = cursor_mock` in both affected tests
- **Files modified:** `tests/test_migrations.py`
- **Verification:** All 37 unit tests in `test_migrations.py` pass after fix
- **Committed in:** `c05fcd2` (part of Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - Bug in existing mock tests)
**Impact on plan:** The mock update was required for correctness — the tests would have been silently passing with incorrect assertions (execute.call_count == 0 != 6) without the fix. No scope creep.

## Issues Encountered

- Worktree was forked off a stale base commit (phase 9 work) rather than `c89a718`. The HEAD assertion in the startup check caught this as a mismatch. Per the documented recovery in memory (worktree-wrong-base-recovery.md), the agent proceeded with execution since: (a) the worktree branch is in the correct `worktree-agent-*` namespace, (b) all source files are present in the worktree filesystem, and (c) the SUMMARY.md is committed to the worktree branch for the orchestrator to cherry-pick. The orchestrator must use cherry-pick of commits `4e8047e`, `c05fcd2`, and the docs commit onto main rather than a standard worktree merge (which would delete phase 10 planning files).
- PostgreSQL `postgres` user has password auth that fails in the local dev environment; tests run using Unix socket (`PGHOST=/var/run/postgresql`) with the `loc` user instead of the CI credentials. The `pycopg_test` database was created for local verification.

## Next Phase Readiness

- B3 (SEC-03) closed: migrations are now fully atomic
- `tests/test_migration_atomicity.py` provides regression coverage for the B3 fix
- Plans 10-03 (B5 subprocess) and 10-04 (B2 session/B1 pool) can proceed independently
- Plan 10-05 (coverage ratchet 70→80) will benefit from the new atomicity tests

## Known Stubs

None — all code is functional, no placeholder values or TODO items in delivered files.

## Threat Flags

None — no new network endpoints, auth paths, file access patterns, or schema changes introduced. The B3 fix closes threat T-10-03 (Tampering/Integrity) as specified in the plan's threat model.

## Self-Check: PASSED

- FOUND: pycopg/migrations.py (transaction() wrapping in _apply at line 233 and rollback at line 292)
- FOUND: tests/test_migration_atomicity.py (2 real-DB integration tests)
- FOUND: tests/test_migrations.py (mock updates for transaction() API)
- FOUND: .planning/phases/10-s-curit-r-siduelle-robustesse/10-02-SUMMARY.md
- Commits 4e8047e (fix) and c05fcd2 (test) confirmed in git log
- All 44 migration tests pass (test_migration_atomicity.py + test_migrations.py + test_migration_edge_cases.py)
