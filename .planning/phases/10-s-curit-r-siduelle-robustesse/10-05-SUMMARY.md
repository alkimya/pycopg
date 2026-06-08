---
phase: 10-s-curit-r-siduelle-robustesse
plan: "05"
subsystem: coverage-ratchet
tags: [coverage, tdd, d-07, sec-06, pool, database, ratchet]
dependency_graph:
  requires: [10-01, 10-02, 10-03, 10-04]
  provides:
    - "cov-fail-under raised from 70 to 80 (D-07 ratchet)"
    - "pool.py at 100% coverage (async methods fully tested)"
    - "database.py coverage raised from 57% to 68% (targeted mock tests)"
    - "TOTAL local coverage: 80.71% with full green suite"
  affects:
    - pyproject.toml
    - tests/test_pool.py
    - tests/test_database.py
tech_stack:
  added: []
  patterns:
    - "AsyncMock with __aenter__/__aexit__ for async context manager testing"
    - "execute() mock injection pattern for admin-method branch coverage"
    - "contextmanager fake_cursor for cursor()-based methods (alter_role, create_role)"
key_files:
  created: []
  modified:
    - tests/test_pool.py
    - tests/test_database.py
    - pyproject.toml
decisions:
  - "D-07 gate flip: local suite measures 80.71% >= 80 so --cov-fail-under flipped to 80 exactly as planned"
  - "Coverage raised by targeted mock tests only; zero production refactoring (Phase 12)"
  - "pool.py async methods (execute/execute_many/fetch_one/fetch_val/transaction/connection) covered with AsyncMock pattern"
  - "database.py grant/revoke/role-admin branches covered by mocking self.execute() and self.cursor()"
metrics:
  duration: "~15 minutes"
  completed: "2026-06-08T22:25:00Z"
  tasks_completed: 2
  tasks_total: 2
  files_changed: 3
  files_created: 0
requirements: [SEC-06]
---

# Phase 10 Plan 05: Coverage Ratchet 70 -> 80 (D-07) Summary

**One-liner:** Raised coverage ratchet from 70 to 80 by adding 35 targeted mock tests for async pool methods and database admin branches; local suite reports 80.71% TOTAL, gate passed, ratchet locked at 80.

---

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add targeted coverage-fill tests to reach >= 80 | 6df6d99 | `tests/test_pool.py`, `tests/test_database.py` |
| 2 | Flip --cov-fail-under from 70 to 80 (ratchet) | 97dc9d1 | `pyproject.toml` |

---

## Coverage Measurement

### Baseline (before this plan)
- TOTAL: 75.47%
- pool.py: 76% (27 missed lines in AsyncPooledDatabase)
- database.py: 57% (292 missed lines)
- migrations.py: 100%
- async_database.py: 81%

### After Plan 05
- TOTAL: **80.71%** (357 missed, 1494 covered out of 1851 statements)
- pool.py: **100%** (all 27 async method lines now covered)
- database.py: **68%** (222 missed lines, down from 292 — 70 newly covered)
- migrations.py: 100% (unchanged)
- async_database.py: 81% (unchanged — PostGIS/Timescale code not locally coverable)

**Gate result:** `Required test coverage of 80% reached. Total coverage: 80.71%`
**Suite result:** 574 passed, 2 skipped, 6 deselected — 0 failures.
**Gate threshold:** `--cov-fail-under=80` — green. Ratchet locked.

---

## What Was Built

### Task 1: Coverage-fill tests (35 new tests across 2 files)

**tests/test_pool.py — class `TestAsyncPooledDatabaseMethods` (8 tests):**

All use `@patch("pycopg.pool.AsyncConnectionPool")` + `AsyncMock` for cursor/connection context managers. Cover pool.py lines 337–395 completely:

| Test | Covers | Behavior asserted |
|------|--------|-------------------|
| `test_connection_context_manager` | line 337-338 | yields mock_conn from pool.connection() |
| `test_execute_returns_rows_when_description` | lines 350-355 | fetchall rows returned, commit awaited |
| `test_execute_returns_empty_when_no_description` | lines 350-355 | empty list returned, commit awaited |
| `test_execute_many_returns_total_rows` | lines 359-366 | 3 executions, rowcount summed, commit |
| `test_fetch_one_returns_single_row` | lines 370-373 | fetchone value returned |
| `test_fetch_val_returns_first_column_value` | lines 375-380 | first dict value extracted |
| `test_fetch_val_returns_none_when_no_row` | lines 375-380 | None returned on empty fetch |
| `test_transaction_context_manager_yields_conn` | lines 393-395 | conn yielded, transaction() called |

**tests/test_database.py — class `TestDatabaseGrantRevoke` (13 tests):**

Inject `db.execute = MagicMock(return_value=[])` directly on the Database instance to mock away real DB calls and assert SQL string contents:

- `grant()` with list privileges (joined), SCHEMA branch, DATABASE branch, ALL TABLES branch, default TABLE branch, WITH GRANT OPTION
- `revoke()` with list privileges, SCHEMA branch, DATABASE branch, ALL TABLES branch, CASCADE flag
- `list_role_members()` — returns `["alice", "bob"]` from mocked execute
- `list_databases()` — returns `["mydb", "testdb"]` from mocked execute

**tests/test_database.py — class `TestDatabaseRoleAdminBranches` (12 tests):**

Mix of `execute = MagicMock(return_value=[])` and `fake_cursor` contextmanager (for `cursor()`-based methods):

- `create_role()`: if_not_exists early-return, NOLOGIN branch, SUPERUSER/CREATEDB/CREATEROLE flags, NOINHERIT/REPLICATION/CONNECTION LIMIT options, password path via cursor()
- `drop_role()`: if_exists=False path (no IF EXISTS in SQL)
- `alter_role()`: rename_to path, password via cursor(), login/superuser/createdb/createrole options via cursor(), connection_limit option
- `grant_role()`: WITH ADMIN OPTION flag in SQL
- `revoke_role()`: correct REVOKE SQL emitted

**tests/test_database.py — class `TestDatabaseCursorTransactionSessionPaths` (2 tests):**

Set `db._session_conn = mock_conn` directly to exercise session-active code paths:

- `test_cursor_session_inerror_triggers_rollback`: sets `mock_conn.info.transaction_status = TransactionStatus.INERROR`, asserts `rollback()` called once and `commit()` not called (line 319)
- `test_transaction_reuses_session_connection`: verifies `transaction()` yields `_session_conn` directly and does NOT call `psycopg.connect()` (lines 342-343)

### Task 2: Gate flip (pyproject.toml)

Changed line 88: `--cov-fail-under=70` → `--cov-fail-under=80`

Verification:
- `grep -c "cov-fail-under=70" pyproject.toml` = 0
- `grep -q "cov-fail-under=80" pyproject.toml` succeeds
- Full suite exits 0 under new 80 gate

---

## Deviations from Plan

None — plan executed exactly as written.

The gate discipline was satisfied:
- Task 1 measured 80.71% BEFORE Task 2 flipped the threshold
- Task 2 flipped to 80 ONLY after the measured value crossed 80
- No fragile tests written; no production code touched

---

## Known Stubs

None — all tests assert observable behavior (return values, SQL content, call counts). No instantiation-only tests.

---

## Threat Model Coverage

| Threat ID | Status |
|-----------|--------|
| T-10-06 (Repudiation — false coverage gate) | Mitigated: gate flipped only after measured >= 80 with green suite |
| T-10-06-FT (Tampering — fragile tests) | Mitigated: every test asserts return value / exception / SQL content; no ordering/timing dependencies |

---

## Remaining Uncovered Code (database.py: 222 missed lines)

The remaining 222 missed lines in database.py are in regions that cannot be covered locally without PostGIS/TimescaleDB extensions or without complex admin setup:

- Lines 169-208, 242-244: `Database.create()` / `create_from_env()` — requires real admin psycopg.connect to postgres DB (complex fixture)
- Lines 555-573: `copy_insert()` — PostgreSQL COPY protocol
- Lines 626-635, 647-659, 670-674: `create_database()`, `drop_database()`, `database_exists()` — require psycopg.connect to postgres DB with autocommit
- Lines 1261-1298, 1323-1334: PostGIS `from_geodataframe()`, `to_geodataframe()` — require PostGIS extension
- Lines 1413-1580: TimescaleDB hypertable/compression/retention methods — require TimescaleDB extension
- Lines 2333-2418: More PostGIS spatial methods — require PostGIS extension

These are deferred to Phase 12 (refactoring) or Phase 14 (spatial helpers) where proper test fixtures can be established.

---

## Self-Check

| Check | Result |
|-------|--------|
| `tests/test_pool.py` modified | FOUND |
| `tests/test_database.py` modified | FOUND |
| `pyproject.toml` has `--cov-fail-under=80` | FOUND |
| `pyproject.toml` has NO `--cov-fail-under=70` | VERIFIED (grep -c returns 0) |
| commit 6df6d99 (Task 1 tests) | FOUND |
| commit 97dc9d1 (Task 2 gate flip) | FOUND |
| Full suite passes under 80 gate (574 passed, 80.71%) | VERIFIED |

## Self-Check: PASSED
