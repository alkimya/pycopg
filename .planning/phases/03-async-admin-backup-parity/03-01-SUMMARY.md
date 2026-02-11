---
phase: 03-async-admin-backup-parity
plan: 01
subsystem: async-database
status: complete
completed: 2026-02-11
tags:
  - async-database
  - ddl-operations
  - database-admin
  - index-management
  - storage-stats

dependencies:
  requires:
    - phase-02-plan-02 (AsyncDatabase DataFrame tests)
  provides:
    - async-drop-table
    - async-create-index
    - async-drop-index
    - async-list-indexes
    - async-list-constraints
    - async-drop-schema
    - async-table-sizes
    - async-create-database
    - async-drop-database
  affects:
    - pycopg/async_database.py
    - tests/test_async_database.py

tech_stack:
  added: []
  patterns:
    - admin-connection-with-autocommit
    - pg-terminate-backend-before-drop
    - percent-escaping-for-format-in-queries

key_files:
  created: []
  modified:
    - path: pycopg/async_database.py
      changes: "Added 9 async DDL/admin/stats methods with docstrings and examples"
      loc_delta: +228
    - path: tests/test_async_database.py
      changes: "Added TestAsyncDatabaseDDL (10 tests) and TestAsyncDatabaseAdmin (4 tests)"
      loc_delta: +265

decisions: []

metrics:
  duration_minutes: 3.7
  tasks_completed: 2
  files_modified: 2
  tests_added: 14
  test_pass_rate: "100% (60/60 async_database tests)"
---

# Phase 03 Plan 01: AsyncDatabase DDL/Admin/Stats Methods Summary

9 async methods for DDL operations, database administration, and storage statistics with full test coverage.

## What Was Built

Added 9 new async methods to AsyncDatabase for DDL operations, database lifecycle management, and storage stats:

**DDL Methods (7):**
- `drop_schema()` - Drop schema with cascade support
- `drop_table()` - Drop table with cascade support
- `create_index()` - Create indexes (btree, hash, gist, gin, etc.) with unique constraint support
- `drop_index()` - Drop indexes by name
- `list_indexes()` - List all indexes on a table with type and definition
- `list_constraints()` - List all constraints on a table
- `table_sizes()` - Get table sizes sorted by total size (includes data + index sizes)

**Database Admin Methods (2):**
- `create_database()` - Create database using admin connection to postgres DB with autocommit
- `drop_database()` - Drop database after terminating existing connections using pg_terminate_backend

All methods match their Database counterparts exactly in signature, behavior, and SQL generation.

## Implementation Details

### Key Patterns

**1. Import Addition**
Added `validate_index_method` to imports for index validation.

**2. DDL Methods Placement**
Added 7 DDL methods after `row_count()` and before EXTENSIONS section, following the same organization pattern as Database.

**3. Stats Method Placement**
Added `table_sizes()` in SIZE & STATS section after `table_size()`.

**4. Admin Methods Placement**
Created new DATABASE ADMINISTRATION section before LISTEN/NOTIFY for `create_database()` and `drop_database()`.

**5. Admin Connection Pattern**
```python
admin_config = self.config.with_database("postgres")
async with await psycopg.AsyncConnection.connect(**admin_config.connect_params(), autocommit=True) as conn:
    async with conn.cursor() as cur:
        await cur.execute(...)
```

**6. Connection Termination Pattern**
`drop_database()` terminates existing connections first using:
```python
await cur.execute("""
    SELECT pg_terminate_backend(pg_stat_activity.pid)
    FROM pg_stat_activity
    WHERE pg_stat_activity.datname = %s
    AND pid <> pg_backend_pid()
""", [name])
```

**7. Percent Escaping**
`table_sizes()` uses `%%I` in SQL string to escape percent signs for psycopg's format() handling.

### Test Coverage

**TestAsyncDatabaseDDL (10 tests):**
- `test_drop_table_basic` - Default parameters with IF EXISTS
- `test_drop_table_cascade` - CASCADE option verification
- `test_create_index_basic` - Single column btree index
- `test_create_index_unique_multi_column` - UNIQUE constraint with multiple columns
- `test_drop_index_basic` - Drop index with IF EXISTS
- `test_list_indexes` - Return index metadata (name, type, def)
- `test_list_constraints` - Return constraint metadata
- `test_drop_schema_basic` - Schema drop with IF EXISTS
- `test_drop_schema_cascade` - Schema CASCADE option
- `test_table_sizes` - Return sorted table size info

**TestAsyncDatabaseAdmin (4 tests):**
- `test_create_database` - Admin connection with autocommit and template
- `test_create_database_with_owner` - OWNER clause verification
- `test_drop_database` - Connection termination + drop verification
- `test_drop_database_if_not_exists` - if_exists=False behavior

All tests use AsyncMock for execute patching and asynccontextmanager pattern for admin connection mocking.

## Verification Results

1. All 9 methods present on AsyncDatabase: PASS
2. All methods are async coroutines: PASS
3. AsyncDatabase test suite: 60/60 tests pass (46 existing + 14 new)
4. Full test suite: 264/265 pass (1 pre-existing integration test failure unrelated to changes)

## Deviations from Plan

None - plan executed exactly as written.

## Task Commits

| Task | Description | Commit | Files | LOC |
|------|-------------|--------|-------|-----|
| 1 | Add 9 DDL/admin/stats async methods | d9a7ac3 | pycopg/async_database.py | +228 |
| 2 | Add unit tests for all methods | 4492905 | tests/test_async_database.py | +265 |

## Impacts

**AsyncDatabase capabilities:**
- DDL operations now available async (drop table/schema, index management)
- Database lifecycle management async (create/drop databases)
- Storage statistics async (table_sizes for monitoring)

**Async parity progress:**
- ASYNC-09 (drop_table): Complete
- ASYNC-10 (create_index, drop_index): Complete
- ASYNC-11 (list_indexes, list_constraints): Partial (covered 2 of 3 items)
- ASYNC-12 (drop_schema): Complete
- ASYNC-13 (table_sizes): Complete
- ASYNC-24 (drop_database, create_database): Partial (covered 2 of 3 items)
- ASYNC-25 (database admin): Complete

**Next steps:**
Remaining async parity items for Phase 03 Plan 02:
- VACUUM operations (async)
- ANALYZE operations (async)
- pg_dump/pg_restore integration (async)
- Backup/restore workflow (async)

## Self-Check

Verifying all created methods and commits exist:

```bash
# Check methods exist
python -c "from pycopg.async_database import AsyncDatabase; import inspect; methods = ['drop_table','create_index','drop_index','list_indexes','list_constraints','drop_schema','table_sizes','create_database','drop_database']; missing = [m for m in methods if not hasattr(AsyncDatabase, m)]; print('PASS' if not missing else f'FAIL: {missing}')"
```
**Result:** PASS - All 9 methods present

```bash
# Check commits exist
git log --oneline --all | grep -E "(d9a7ac3|4492905)"
```
**Result:** PASS
- d9a7ac3 feat(03-01): add 9 DDL/admin/stats async methods to AsyncDatabase
- 4492905 test(03-01): add unit tests for DDL/admin/stats methods

```bash
# Check test execution
python -m pytest tests/test_async_database.py -q
```
**Result:** PASS - 60 tests passed

## Self-Check: PASSED

All methods created, all commits present, all tests passing.
