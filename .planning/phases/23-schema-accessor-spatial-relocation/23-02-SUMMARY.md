---
phase: 23-schema-accessor-spatial-relocation
plan: "02"
subsystem: schema-accessor
tags: [accessor, schema, wiring, deprecated-alias, lazy-property, v0.6.0]
dependency_graph:
  requires:
    - pycopg.schema.SchemaAccessor (plan 01)
    - pycopg.schema.AsyncSchemaAccessor (plan 01)
  provides:
    - Database._schema cache field + lazy schema property
    - AsyncDatabase._schema cache field + lazy schema property
    - 27 @deprecated_alias("schema.<m>") stubs on Database
    - 27 @deprecated_alias("schema.<m>") stubs on AsyncDatabase
    - pycopg.SchemaAccessor (top-level export)
    - pycopg.AsyncSchemaAccessor (top-level export)
  affects:
    - pycopg/database.py
    - pycopg/async_database.py
    - pycopg/__init__.py
tech_stack:
  added: []
  patterns:
    - lazy-cached accessor property (mirrors _timescale/_admin pattern)
    - @deprecated_alias stub (generic *args/**kwargs, one-line docstring)
    - TYPE_CHECKING guard for circular-import avoidance
    - unused-import cleanup after method body removal
key_files:
  created: []
  modified:
    - pycopg/database.py
    - pycopg/async_database.py
    - pycopg/__init__.py
decisions:
  - D-04 applied: validate_extension_name + validate_index_method removed from database.py/async_database.py imports (now only used in schema.py)
  - Sync+async stubs committed together (Pitfall 5 discipline: TestAsyncParity safe)
  - from_dataframe/from_geodataframe call-sites NOT rewritten (plan 03 owns those atomically per D-05)
  - Pre-existing ruff N818 errors in exceptions.py are out-of-scope (pre-existing, unrelated)
metrics:
  duration_seconds: 480
  completed: "2026-06-17"
  tasks_total: 2
  tasks_completed: 2
  files_created: 0
  files_modified: 3
---

# Phase 23 Plan 02: Schema Accessor Wiring Summary

**One-liner:** Wired `SchemaAccessor`/`AsyncSchemaAccessor` into `Database`/`AsyncDatabase` via `_schema` cache field, lazy `schema` property, and 27 `@deprecated_alias` stubs each; exported both classes from `pycopg.__all__`.

## What Was Built

### Task 1: Cache field + lazy property + 27 deprecated_alias stubs (both files, same commit)

**`pycopg/database.py`:**

- Added `self._schema: SchemaAccessor | None = None` to `Database.__init__` alongside the existing `_timescale`/`_admin`/... cache fields
- Added `SchemaAccessor` to `TYPE_CHECKING` import block
- Added lazy `@property def schema(self) -> SchemaAccessor:` after the `backup` property (same idiom as `timescale`/`admin`/`backup`)
- Replaced 27 flat schema method bodies with `@deprecated_alias("schema.<m>")` stubs (one-line docstrings, generic `*args, **kwargs`)
- Removed now-unused `validate_extension_name` and `validate_index_method` imports (they now live in `schema.py`)

**`pycopg/async_database.py`:**

- Added `self._schema: AsyncSchemaAccessor | None = None` to `AsyncDatabase.__init__`
- Added `AsyncSchemaAccessor` to `TYPE_CHECKING` import block
- Added lazy `@property def schema(self) -> AsyncSchemaAccessor:` after the `backup` property
- Replaced 27 flat async schema method bodies with `@deprecated_alias("schema.<m>") async def` stubs
- Removed now-unused `validate_extension_name` and `validate_index_method` imports

Both files committed in the same commit (Pitfall 5 discipline — `TestAsyncParity` never sees a half-migrated surface).

### Task 2: Export SchemaAccessor + AsyncSchemaAccessor from `pycopg/__init__.py`

- Added `from pycopg.schema import AsyncSchemaAccessor, SchemaAccessor` to the import block
- Added `"SchemaAccessor"` and `"AsyncSchemaAccessor"` to `__all__` under a `# Schema` comment block, placed after the `# Backup` group

## Commits

| Task | Description | Commit |
|------|-------------|--------|
| Task 1 | Wire SchemaAccessor into Database/AsyncDatabase (cache field + property + 27 stubs each) | fb92832 |
| Task 2 | Export SchemaAccessor + AsyncSchemaAccessor from pycopg.__all__ | e62fcde |

## Verification Results

| Check | Result |
|-------|--------|
| `grep -c '@deprecated_alias("schema\.' pycopg/database.py` == 27 | PASS |
| `grep -c '@deprecated_alias("schema\.' pycopg/async_database.py` == 27 | PASS |
| `grep -c '_schema' pycopg/database.py` >= 2 (actual: 14) | PASS |
| `grep -c '_schema' pycopg/async_database.py` >= 2 (actual: 14) | PASS |
| `grep -c 'def schema' pycopg/database.py` >= 1 (actual: 2 including schema_exists stub) | PASS |
| `grep -c 'def schema' pycopg/async_database.py` >= 1 (actual: 2) | PASS |
| `grep -nE 'self\.config\.with_database' pycopg/database.py` == 0 | PASS |
| `grep -nE 'self\.config\.with_database' pycopg/async_database.py` == 0 | PASS |
| Sync stub warns and delegates (MagicMock verify) | PASS |
| `from pycopg import SchemaAccessor, AsyncSchemaAccessor` succeeds | PASS |
| Both in `pycopg.__all__` | PASS |
| `grep -c 'from pycopg.schema import' pycopg/__init__.py` == 1 | PASS |
| `grep -c '"SchemaAccessor"' pycopg/__init__.py` == 1 | PASS |
| `grep -c '"AsyncSchemaAccessor"' pycopg/__init__.py` == 1 | PASS |
| `uv run ruff check pycopg/database.py pycopg/async_database.py pycopg/__init__.py pycopg/schema.py` | PASS |
| `uv run pytest tests/test_parity.py -x -q -o addopts=""` (22 passed) | PASS |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed unused imports after method body deletion**
- **Found during:** Task 1 (ruff check)
- **Issue:** After replacing 27 schema method bodies with thin stubs, `validate_extension_name` and `validate_index_method` became unused in both `database.py` and `async_database.py` (they are now only used inside `schema.py`)
- **Fix:** Removed both imports from each file's `from pycopg.utils import ...` block
- **Files modified:** `pycopg/database.py`, `pycopg/async_database.py`
- **Commit:** fb92832 (included in the same Task 1 commit)

**2. [Deviation - Plan verify command] Config parameter name mismatch**
- **Found during:** Running Task 1 verification command from plan
- **Issue:** Plan's verify command used `Config(host='h', dbname='d', ...)` but `Config.__init__` uses `database=` not `dbname=`
- **Fix:** Used correct parameter name `database='d'` in the verification
- **Impact:** None — plan's verify intent verified correctly with corrected syntax

## Known Stubs

The 27 `@deprecated_alias` stubs in `database.py` and `async_database.py` are intentional thin stubs (by design, per D-03/D-09). Each delegates to `self.schema.<m>` which is the real implementation in `schema.py`.

Internal callers `from_dataframe` (line ~1027 db, ~1089 async_db) and `from_geodataframe` (lines ~1108 db, ~1159 async_db) still call the deprecated flat aliases (`self.add_primary_key`, `self.has_extension`, `self.create_spatial_index`). These are D-05 call-site rewrites owned atomically by plan 03.

The `-W error::DeprecationWarning` gate is deliberately held by plan 03 — as documented in the plan objective.

## Threat Flags

None. This plan is pure wiring (cache field + lazy property + thin delegating stubs + export). It adds no new SQL, no new user-input paths. The stubs forward `*args, **kwargs` to the accessor bodies which retain all `validate_*` guards (T-23-02 mitigated as designed).

## Self-Check: PASSED

- [x] `pycopg/database.py` modified with 27 stubs, `_schema` field, lazy property: VERIFIED
- [x] `pycopg/async_database.py` modified with 27 stubs, `_schema` field, lazy property: VERIFIED
- [x] `pycopg/__init__.py` exports SchemaAccessor + AsyncSchemaAccessor: VERIFIED
- [x] Commit fb92832 exists: FOUND
- [x] Commit e62fcde exists: FOUND
- [x] 27 stubs in database.py: VERIFIED (grep count = 27)
- [x] 27 stubs in async_database.py: VERIFIED (grep count = 27)
- [x] Moved bodies deleted (self.config.with_database gone): VERIFIED (0 matches)
- [x] Sync stub warns + delegates: VERIFIED (python verify prints 'sync stub OK')
- [x] Ruff clean (plan files): VERIFIED
- [x] TestAsyncParity passes (22/22): VERIFIED
