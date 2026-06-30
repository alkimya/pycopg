---
phase: 45-api-completeness-gaps-structured-logging
plan: "02"
subsystem: core
tags: [transaction, savepoint, isolation-level, sync-async-parity, tdd]
dependency_graph:
  requires: [45-01]
  provides: [TXN-01, TXN-02]
  affects: [pycopg/database.py, pycopg/async_database.py]
tech_stack:
  added: []
  patterns:
    - "IsolationLevel enum accepted on transaction()/session() kw-only params"
    - "savepoint() delegates to psycopg native conn.transaction(savepoint_name=) — never string-interpolates"
    - "_num_transactions guard in cursor() prevents commit() inside psycopg txn block"
key_files:
  modified:
    - pycopg/database.py
    - pycopg/async_database.py
  created:
    - tests/test_transaction_isolation.py
    - tests/test_savepoints.py
decisions:
  - "D-03 honored: transaction(isolation_level=) inside active session raises RuntimeError (fail-closed)"
  - "D-04 enforced: all new params keyword-only; autocommit stays positional in session()"
  - "D-02 honored: two savepoint surfaces — standalone savepoint() + transaction(savepoint_name=)"
  - "T-45-03 mitigated: savepoint name routed only through psycopg native API, never interpolated"
  - "cursor() _num_transactions guard: skip explicit commit when inside a psycopg conn.transaction() block (deviation Rule 1 — bug in existing code revealed by savepoint integration)"
metrics:
  duration: "46 min"
  completed: "2026-06-30T18:23:10Z"
  tasks_completed: 2
  files_changed: 4
---

# Phase 45 Plan 02: Transaction Control (isolation + savepoints) Summary

Transaction isolation control and savepoint surface added to `Database` and `AsyncDatabase` with full sync/async parity (TXN-01 + TXN-02).

## What Was Built

### Task 1 — isolation_level + savepoint_name on transaction()/session() (commit 7a89bb5)

Extended `transaction()` on both `Database` and `AsyncDatabase`:
- New kw-only params: `isolation_level: IsolationLevel | None = None`, `savepoint_name: str | None = None`
- Outside a session: sets `conn.isolation_level = isolation_level` on the fresh per-call connection before `conn.transaction(savepoint_name=...)`
- Inside an active session with `isolation_level is not None`: raises `RuntimeError` (D-03 fail-closed, T-45-04 mitigated)
- `savepoint_name` passed through to psycopg's native API on both branches

Extended `session()` on both classes:
- New kw-only param: `isolation_level: IsolationLevel | None = None`
- `autocommit` remains positional (no breaking change, D-04)
- Sets `conn.isolation_level` immediately after `connect()`, before any transaction

Added `IsolationLevel` import from psycopg in both files.

`tests/test_transaction_isolation.py`: 8 unit tests (sync + async), all mock-based (no live DB).

### Task 2 — savepoint() standalone context manager (commit 4ee78a3)

Added `savepoint(*, name: str | None = None)` on both `Database` and `AsyncDatabase`:
- Guard: raises `RuntimeError("db.savepoint() requires an active db.session() ...")` if `_session_conn is None`
- Delegates to `conn.transaction(savepoint_name=name)` / `async with conn.transaction(savepoint_name=name)` — psycopg safely quotes the savepoint identifier; no SQL interpolation (T-45-03)
- `name=None` lets psycopg auto-generate the name

`tests/test_savepoints.py`: 7 tests (2 guard + 5 integration):
- `test_savepoint_requires_session` / `test_async_savepoint_requires_session` — guard (no live DB)
- `test_savepoint_named_partial_rollback` — named savepoint partial rollback, outer session survives
- `test_savepoint_autoname` — auto-named savepoint partial rollback
- `test_transaction_savepoint_name_kwarg` — second savepoint surface via `transaction(savepoint_name="sp2")`
- `test_async_savepoint_named_partial_rollback` / `test_async_savepoint_autoname` — async mirrors

## Commits

| Task | Hash | Message |
|------|------|---------|
| Task 1 | 7a89bb5 | feat(45-02): add isolation_level/savepoint_name to transaction() and session() (sync+async) |
| Task 2 | 4ee78a3 | feat(45-02): add savepoint() context manager (sync+async) + fix cursor auto-commit in txn blocks |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] cursor() auto-commit called inside psycopg transaction() block**

- **Found during:** Task 2 integration tests
- **Issue:** `Database.cursor()` and `AsyncDatabase.cursor()` check `TransactionStatus.INTRANS` and call `conn.commit()`. Inside a `savepoint()` or `transaction(savepoint_name=)` block, psycopg's `conn.transaction()` context manager is active (`_num_transactions > 0`), and explicit `commit()` raises `ProgrammingError: Explicit commit() forbidden within a Transaction context`.
- **Fix:** Added `try: in_txn_block = conn._num_transactions > 0; except TypeError: in_txn_block = False` guard in the session cursor branch of both `Database.cursor()` and `AsyncDatabase.cursor()`. When inside a psycopg transaction block, skip the explicit commit/rollback — the outer CM handles it. `TypeError` fallback handles `MagicMock` in existing unit tests.
- **Files modified:** `pycopg/database.py`, `pycopg/async_database.py`
- **Commit:** 4ee78a3

**2. [Rule 3 - Blocker] TEMP TABLE ON COMMIT DELETE ROWS deleted rows mid-test**

- **Found during:** Task 2 integration tests (first design)
- **Issue:** Test initially used `CREATE TEMP TABLE ... ON COMMIT DELETE ROWS`. The cursor auto-commit commits after each `INSERT`, triggering `ON COMMIT DELETE ROWS` which deleted all rows. The SELECT at the end returned `[]`.
- **Fix:** Changed integration tests to use regular tables (uniquely named, `DROP TABLE IF EXISTS` in `finally`). Default `ON COMMIT PRESERVE ROWS` semantics; no data deleted on cursor-level commits.
- **Files modified:** `tests/test_savepoints.py`
- **Commit:** 4ee78a3

## Threat Surface Scan

All new caller-tainted values are routed safely:
- `savepoint(name=)` and `transaction(savepoint_name=)` pass the name only to psycopg's native `conn.transaction(savepoint_name=...)` — no string interpolation into SQL (T-45-03 mitigated as planned)
- `isolation_level=` accepts a psycopg `IsolationLevel` enum value — psycopg handles the protocol (T-45-04 mitigated via RuntimeError guard in session)
- `session()` `finally` block unchanged — T-45-05 accept (no new leak path)

No new threat surface beyond the registered T-45-03/04/05 threats.

## Gates

| Gate | Result |
|------|--------|
| `uv run pytest tests/test_transaction_isolation.py -x -q -o addopts=""` | 8 passed |
| `PGDATABASE=pycopg_test2 uv run pytest tests/test_savepoints.py -x -q -o addopts=""` | 7 passed |
| `PGDATABASE=pycopg_test2 uv run pytest tests/test_parity.py -x -q -o addopts=""` | 37 passed |
| `PGDATABASE=pycopg_test2 uv run pytest` (full suite) | 1715 passed, 2 skipped; 96.19% (gate ≥95%) |
| `uv run ruff check pycopg tests` | clean |
| `uv run black --check pycopg tests` | clean |
| `uv run interrogate -f 95 pycopg` | 100% (gate ≥95%) |

## Self-Check: PASSED

- [x] `tests/test_transaction_isolation.py` exists
- [x] `tests/test_savepoints.py` exists
- [x] Commit 7a89bb5 exists (Task 1)
- [x] Commit 4ee78a3 exists (Task 2)
- [x] Full suite 1715 passed, 96.19% coverage
