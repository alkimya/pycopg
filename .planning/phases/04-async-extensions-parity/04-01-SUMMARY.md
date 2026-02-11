---
phase: 04-async-extensions-parity
plan: 01
subsystem: async-database
tags: [roles, privileges, async, parity]
related_work:
  - ASYNC-15: Async role lifecycle
  - ASYNC-16: Async privilege management
  - ASYNC-17: Async role membership
  - ASYNC-18: Async role inspection
dependency_graph:
  requires: [async_database.role_exists, async_database.list_roles]
  provides: [async_role_management, async_privilege_management, async_role_inspection]
  affects: []
tech_stack:
  added: []
  patterns: [parameterized-passwords, autocommit-ddl, async-await]
key_files:
  created: []
  modified:
    - pycopg/async_database.py: +335 lines (9 new async methods, enhanced list_roles)
    - tests/test_async_database.py: +521 lines (35 new tests)
decisions: []
metrics:
  duration_minutes: 2.81
  tasks_completed: 2
  tests_added: 35
  methods_added: 9
  completed_date: 2026-02-11
---

# Phase 04 Plan 01: Async Role & Privilege Management Summary

**One-liner:** Full sync/async parity for PostgreSQL role lifecycle, privilege grants/revokes, and role inspection using parameterized passwords and autocommit DDL.

## What Was Done

### Task 1: Add Async Role Management Methods to AsyncDatabase
Added 9 async methods to `AsyncDatabase` class for complete PostgreSQL role and privilege management:

**Role lifecycle (3 methods):**
- `async def create_role()` — Create users/roles with options (login, superuser, createdb, etc.)
  - Uses parameterized query via `cursor(autocommit=True)` when password is set
  - Supports `if_not_exists`, `in_roles`, `valid_until`, `connection_limit`
- `async def drop_role()` — Drop roles with IF EXISTS support
- `async def alter_role()` — Modify role attributes or rename
  - Uses parameterized query for password changes
  - Supports all boolean attributes (login, superuser, createdb, createrole)

**Privilege management (4 methods):**
- `async def grant()` — Grant privileges on tables, schemas, databases, sequences, functions
  - Handles ALL TABLES/SEQUENCES/FUNCTIONS patterns
  - Supports `with_grant_option`
- `async def revoke()` — Revoke privileges with cascade support
- `async def grant_role()` — Grant role membership with admin option
- `async def revoke_role()` — Revoke role membership

**Role inspection (2 methods):**
- `async def list_role_members()` — List members of a role (returns list[str])
- `async def list_role_grants()` — List privileges granted to a role (returns list[dict])

**Also enhanced:**
- `async def list_roles()` — Added missing fields (`replication`, `connection_limit`, `valid_until`) for full parity with sync version

### Task 2: Add Comprehensive Unit Tests
Added 3 test classes with 35 total tests covering all methods and edge cases:

**TestAsyncDatabaseRoles (15 tests):**
- `create_role`: basic, with password, if_not_exists, options, in_roles, nologin, noinherit, valid_until
- `drop_role`: basic, no if_exists
- `alter_role`: rename, password, attributes, connection_limit, valid_until

**TestAsyncDatabasePrivileges (16 tests):**
- `grant`: table, schema, database, all tables/sequences/functions, with_grant_option, list privileges
- `revoke`: table, schema, cascade, all tables, list privileges
- `grant_role`: basic, with_admin
- `revoke_role`: basic

**TestAsyncDatabaseRoleInspection (4 tests):**
- `list_role_members`: basic, empty
- `list_role_grants`: basic, empty

All tests verify:
- Correct SQL generation
- `autocommit=True` usage for DDL/privilege operations
- Parameterized password handling via cursor context manager
- Proper parameter passing

## Deviations from Plan

None — plan executed exactly as written.

## Test Results

**Before:**
- 83 tests passing

**After:**
- 118 tests passing (+35 new)
- All existing tests remain green
- Coverage: 76% for `async_database.py` (up from 32%)

**Test execution:**
```bash
$ python -m pytest tests/test_async_database.py::TestAsyncDatabaseRoles -v
15 passed

$ python -m pytest tests/test_async_database.py::TestAsyncDatabasePrivileges -v
16 passed

$ python -m pytest tests/test_async_database.py::TestAsyncDatabaseRoleInspection -v
4 passed
```

## Integration Points

**Dependencies:**
- Uses existing `role_exists()` for if_not_exists checks
- Uses existing `execute()` and `cursor()` for DDL execution
- Uses existing `validate_identifier()` and `validate_identifiers()` for SQL injection protection

**Provides:**
- Full role lifecycle management in async context
- Complete privilege grant/revoke operations
- Role membership introspection
- Foundation for async user/permission management in applications

**Patterns established:**
- Parameterized passwords via `cursor(autocommit=True)` — secure and async-safe
- Autocommit for all DDL/privilege operations — immediate execution, no transactions
- Direct `execute()` for inspection queries — transactional context not needed

## Verification

✅ All 9 methods exist in `AsyncDatabase`
✅ `create_role` and `alter_role` use parameterized queries for passwords
✅ All DDL/privilege methods pass `autocommit=True`
✅ Role inspection methods use standard `execute()` (no autocommit)
✅ 35 new unit tests pass
✅ All existing tests remain green
✅ No import errors
✅ Full sync/async API parity achieved

## Performance Notes

- **Execution time:** 2.81 minutes
- **Test suite:** 118 tests in 1.36s
- **Lines added:** 856 total (335 implementation + 521 tests)

## Key Implementation Details

### Parameterized Password Security
Both `create_role` and `alter_role` use parameterized queries when handling passwords to prevent SQL injection:

```python
async with self.cursor(autocommit=True) as cur:
    await cur.execute(f"CREATE ROLE {name} WITH {options_str}", [password])
```

### Autocommit for DDL
All role/privilege DDL operations use `autocommit=True` to ensure immediate execution outside of transaction blocks:

```python
await self.execute(f"GRANT {privileges} ON {object_type} {schema}.{on} TO {to}", autocommit=True)
```

### In-Roles Membership
`create_role()` with `in_roles` parameter automatically grants membership after role creation:

```python
if in_roles:
    for role in in_roles:
        await self.grant_role(role, name)
```

## Files Modified

| File | Changes | Purpose |
|------|---------|---------|
| `pycopg/async_database.py` | +335 lines | 9 new async methods + enhanced list_roles |
| `tests/test_async_database.py` | +521 lines | 35 comprehensive unit tests |

## Commits

| Hash | Message | Files |
|------|---------|-------|
| `d519a2a` | feat(04-01): add async role management, privilege, and inspection methods | pycopg/async_database.py |
| `cc89c5a` | test(04-01): add comprehensive tests for async role/privilege/inspection methods | tests/test_async_database.py |

## Self-Check: PASSED

✅ All claimed files exist:
```bash
$ [ -f "pycopg/async_database.py" ] && echo "FOUND: pycopg/async_database.py"
FOUND: pycopg/async_database.py

$ [ -f "tests/test_async_database.py" ] && echo "FOUND: tests/test_async_database.py"
FOUND: tests/test_async_database.py
```

✅ All claimed commits exist:
```bash
$ git log --oneline --all | grep -q "d519a2a" && echo "FOUND: d519a2a"
FOUND: d519a2a

$ git log --oneline --all | grep -q "cc89c5a" && echo "FOUND: cc89c5a"
FOUND: cc89c5a
```

✅ Methods verified in Python:
```python
>>> from pycopg import AsyncDatabase
>>> db = AsyncDatabase.__new__(AsyncDatabase)
>>> [m for m in dir(db) if m in ['create_role', 'drop_role', 'alter_role',
...  'grant', 'revoke', 'grant_role', 'revoke_role',
...  'list_role_members', 'list_role_grants']]
['create_role', 'drop_role', 'alter_role', 'grant', 'revoke',
 'grant_role', 'revoke_role', 'list_role_members', 'list_role_grants']
```
