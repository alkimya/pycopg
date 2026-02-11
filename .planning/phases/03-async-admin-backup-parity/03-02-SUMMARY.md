---
phase: 03-async-admin-backup-parity
plan: 02
subsystem: async-database
tags: [async, maintenance, backup, csv, parity]
dependency_graph:
  requires:
    - 03-01 (DDL/Admin/Stats methods)
  provides:
    - async vacuum, analyze, explain
    - async pg_dump, pg_restore via subprocess
    - async copy_to_csv, copy_from_csv via COPY protocol
  affects:
    - AsyncDatabase (7 new methods)
    - test_async_database.py (23 new tests)
tech_stack:
  added:
    - asyncio.create_subprocess_exec (for pg_dump/pg_restore/psql)
    - asyncio.to_thread (for blocking file I/O)
  patterns:
    - autocommit=True for VACUUM/ANALYZE (cannot run in transactions)
    - subprocess.PIPE for stdout/stderr capture
    - async COPY protocol via psycopg cur.copy()
    - file I/O delegation to thread pool
key_files:
  created: []
  modified:
    - pycopg/async_database.py
    - tests/test_async_database.py
decisions:
  - Use asyncio.create_subprocess_exec (not shell) for security
  - Use asyncio.to_thread for all file I/O to avoid blocking event loop
  - Replicate Database method signatures exactly for parity
  - Pass autocommit=True to execute() for VACUUM/ANALYZE
metrics:
  duration_minutes: 3.55
  tasks_completed: 2
  files_modified: 2
  methods_added: 7
  tests_added: 23
  completed_date: 2026-02-11
---

# Phase 03 Plan 02: Async Maintenance, Backup, and CSV Methods Summary

**One-liner:** Async maintenance (vacuum/analyze/explain), backup/restore (pg_dump/pg_restore via subprocess), and bulk CSV operations (COPY protocol) with proper autocommit handling and non-blocking file I/O.

## Objective

Add 7 async methods to AsyncDatabase for maintenance, backup/restore, and CSV operations. Complete async parity for ASYNC-14 (maintenance), ASYNC-05/06 (backup/restore), and ASYNC-07/08 (CSV bulk operations).

## Work Completed

### Task 1: Add 7 Async Methods to AsyncDatabase

**Commit:** 57fedb2

**Methods added:**

1. **vacuum()** — Database maintenance with autocommit
2. **analyze()** — Update query planner statistics with autocommit
3. **explain()** — Get query execution plan (no autocommit needed)
4. **pg_dump()** — Backup database using async subprocess
5. **pg_restore()** — Restore database, delegates to _psql_restore for .sql files
6. **_psql_restore()** — Private helper for plain SQL restore via psql subprocess
7. **copy_to_csv()** — Export table to CSV via async COPY TO STDOUT
8. **copy_from_csv()** — Import CSV to table via async COPY FROM STDIN

**Key implementation details:**

- VACUUM and ANALYZE use `autocommit=True` because they cannot run inside transactions
- pg_dump/pg_restore/psql use `asyncio.create_subprocess_exec()` (NOT shell) for security
- PGPASSWORD passed via environment dict
- CSV methods use `asyncio.to_thread()` for all file operations to avoid blocking
- All type hints match Database signatures exactly
- Added imports: `asyncio` and `os` at module level

**Files modified:** `pycopg/async_database.py` (+423 lines)

### Task 2: Add Unit Tests

**Commit:** 0253b10

**Test classes added:**

1. **TestAsyncDatabaseMaintenance** — 8 tests covering vacuum, analyze, explain
   - test_vacuum_basic, test_vacuum_full_table, test_vacuum_no_analyze
   - test_analyze_basic, test_analyze_table
   - test_explain_basic, test_explain_analyze, test_explain_json_format

2. **TestAsyncDatabaseBackup** — 9 tests covering pg_dump, pg_restore, _psql_restore
   - test_pg_dump_basic, test_pg_dump_plain_format, test_pg_dump_failure, test_pg_dump_with_tables
   - test_pg_restore_basic, test_pg_restore_clean, test_pg_restore_sql_file, test_pg_restore_failure
   - test_psql_restore

3. **TestAsyncDatabaseCSV** — 6 tests covering copy_to_csv, copy_from_csv
   - test_copy_to_csv_basic, test_copy_to_csv_with_columns, test_copy_to_csv_validates_identifiers
   - test_copy_from_csv_basic, test_copy_from_csv_with_columns, test_copy_from_csv_validates_identifiers

**Testing patterns:**

- Mock `asyncio.create_subprocess_exec` for subprocess tests
- Mock `asyncio.to_thread` for file I/O tests
- Verify autocommit=True passed for vacuum/analyze
- Verify PGPASSWORD in environment
- Verify COPY TO STDOUT / FROM STDIN SQL construction
- Verify InvalidIdentifier raised for malicious input

**Test results:** All 83 async database tests pass (60 existing + 23 new)

**Files modified:** `tests/test_async_database.py` (+463 lines)

## Deviations from Plan

None — plan executed exactly as written.

## Verification Results

All verification steps passed:

1. ✓ All 7 methods exist and are async coroutines (including _psql_restore)
2. ✓ All 83 async database tests pass
3. ✓ No regressions in full test suite (287 of 288 tests pass, 1 pre-existing failure unrelated to this work)
4. ✓ Phase 3 parity check: All 16 Phase 3 methods present on AsyncDatabase

## Phase 3 Completion Status

**Plan 01:** ✓ Complete (DDL/Admin/Stats methods)
**Plan 02:** ✓ Complete (Maintenance/Backup/CSV methods)

**Total Phase 3 methods:** 16 of 16 (100%)
- DDL: drop_table, create_index, drop_index, list_indexes, list_constraints, drop_schema
- Admin: table_sizes, create_database, drop_database
- Maintenance: vacuum, analyze, explain
- Backup/Restore: pg_dump, pg_restore
- CSV: copy_to_csv, copy_from_csv

**AsyncDatabase now has full parity with Database for all Phase 3 operations.**

## Technical Insights

### Autocommit Requirement

VACUUM and ANALYZE cannot run inside a transaction block. The implementation correctly passes `autocommit=True` to `self.execute()` to handle this PostgreSQL constraint.

### Subprocess Security

Using `asyncio.create_subprocess_exec(*cmd, ...)` instead of `create_subprocess_shell()` prevents shell injection attacks. Command arguments are passed as list elements, not a shell string.

### Non-Blocking File I/O

CSV methods use `asyncio.to_thread()` to delegate all file operations (open, read, write, close, mkdir) to the thread pool. This prevents blocking the async event loop during disk I/O.

### COPY Protocol

The async COPY protocol via `cur.copy()` is significantly more complex than the sync version:
- Must iterate asynchronously over data chunks
- File operations must be delegated to threads
- Error handling requires try/finally for resource cleanup

### Test Mocking Complexity

Testing async subprocess and file I/O required careful mocking:
- Mock process with `communicate()` AsyncMock
- Mock `to_thread` to bypass thread delegation in tests
- Track call counts for repeated `to_thread` calls (open, read×N, close)

## Self-Check: PASSED

**Files created/modified verification:**

✓ pycopg/async_database.py exists and modified
✓ tests/test_async_database.py exists and modified

**Commits verification:**

✓ Commit 57fedb2 exists (feat: add async maintenance, backup, and CSV methods)
✓ Commit 0253b10 exists (test: add unit tests for new methods)

**Method verification:**

```python
# All 7 methods present and async
vacuum: async=True
analyze: async=True
explain: async=True
pg_dump: async=True
pg_restore: async=True
_psql_restore: async=True
copy_to_csv: async=True
copy_from_csv: async=True
```

**Phase 3 parity verification:**

```
ALL 16 PHASE 3 METHODS PRESENT
```

All claims verified successfully.
