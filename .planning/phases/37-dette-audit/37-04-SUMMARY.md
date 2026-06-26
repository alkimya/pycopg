---
phase: 37-dette-audit
plan: "04"
subsystem: schema-accessor, timescale, crud-ergonomics
tags: [debt, audit, TableNotFound, raise-site, WR-01, docstring, tdd]
dependency_graph:
  requires: ["37-02"]
  provides: ["DEBT-05-raise-site", "DEBT-03a-fixes"]
  affects: ["pycopg.schema", "pycopg.timescale", "pycopg.database", "pycopg.async_database"]
tech_stack:
  added: []
  patterns:
    - "table_exists guard before DDL (existence check after validate_identifiers, before SQL)"
    - "case-insensitive guard via select_sql.lower()"
    - "TDD RED/GREEN cycle for TableNotFound raise site"
key_files:
  created: []
  modified:
    - "pycopg/schema.py"
    - "pycopg/timescale.py"
    - "pycopg/database.py"
    - "pycopg/async_database.py"
    - "tests/test_database_integration.py"
    - "tests/test_async_database.py"
decisions:
  - "DEBT-05: truncate_table chosen as the TableNotFound raise site (not table_info/describe — those keep empty-return contract per Pitfall 2)"
  - "Test names use snake_case only (N802): test_truncate_table_missing_raises_table_not_found, not raises_TableNotFound"
  - "validate_identifiers runs BEFORE table_exists guard (builder-pur invariant preserved)"
  - "DEBT-03b closures (WR-03, %-in-structural-SQL, IN-03) NOT fixed here — Plan 05 records them in 37-DECISIONS.md"
metrics:
  duration_minutes: 7
  completed_date: "2026-06-26"
  task_count: 2
  file_count: 6
---

# Phase 37 Plan 04: DEBT-05 TableNotFound Raise Site + DEBT-03a Advisory Fixes Summary

**One-liner:** TableNotFound now has a real internal raise site in `truncate_table` (sync + async TDD), WR-01 guard is case-insensitive, upsert docstrings document the ValueError, sequences test asserts the specific name, and import uuid is de-duplicated.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 (RED) | Failing tests for truncate_table TableNotFound | af504a6 | tests/test_database_integration.py, tests/test_async_database.py |
| 1 (GREEN) | TableNotFound raise site in truncate_table sync + async | feccd2b | pycopg/schema.py, tests/test_database_integration.py, tests/test_async_database.py |
| 2 | DEBT-03a advisory fixes: WR-01, upsert docstring Raises, sequences assertion, import uuid de-dup | 11d60de | pycopg/timescale.py, pycopg/database.py, pycopg/async_database.py, tests/test_async_database.py |

## What Was Built

### Task 1: TableNotFound raise site (DEBT-05) — TDD

**RED phase (af504a6):**
- `tests/test_database_integration.py`: imported `TableNotFound`; added `test_truncate_table_missing_raises_table_not_found` (sync) generating a UUID-based missing table name and asserting `pytest.raises(TableNotFound)`.
- `tests/test_async_database.py`: imported `TableNotFound`; added async twin. Both failed with `psycopg.errors.UndefinedTable` (correct RED state).

**GREEN phase (feccd2b):**
- `pycopg/schema.py`: added `from pycopg.exceptions import TableNotFound` import.
- `SchemaAccessor.truncate_table`: after `validate_identifiers(name, schema)`, guard `if not self.table_exists(name, schema): raise TableNotFound(f"Table '{schema}.{name}' does not exist.")`, then the TRUNCATE DDL. Added `Raises` section to docstring.
- `AsyncSchemaAccessor.truncate_table`: mirror with `await self.table_exists(name, schema)`. Added `Raises` section to docstring.
- Order invariant: `validate_identifiers` → `table_exists` guard → `TRUNCATE`. Invalid identifiers still raise `InvalidIdentifier`, not `TableNotFound`.
- Regression: `test_describe_missing_table_returns_empty` (line 1287) still passes — `describe`/`table_info` empty-return contract untouched.

### Task 2: DEBT-03a Advisory Fixes

**(a) WR-01 case-insensitive time_bucket guard:**
- `pycopg/timescale.py` line 969 (sync) and 1946 (async): `if "time_bucket(" not in select_sql:` → `if "time_bucket(" not in select_sql.lower():`
- Now accepts `Time_Bucket(`/`TIME_BUCKET(` etc. Guard still rejects SQL with no time_bucket call.

**(b) upsert Raises docstrings:**
- `pycopg/database.py` `Database.upsert`: added `Raises` section after `Returns` documenting `ValueError` when `update_columns` resolves to empty.
- `pycopg/async_database.py` `AsyncDatabase.upsert`: symmetric `Raises` section added.
- Docstring-only; no behavior change.

**(c) test_sequences_async specific-name assertion:**
- `tests/test_async_database.py`: replaced `assert len(seqs) >= 1` with `assert f"{t}_id_seq" in seqs` — guarantees the expected sequence is present, not merely "at least one."

**(d) import uuid de-duplication:**
- Added single top-level `import uuid` at line 4 of `tests/test_async_database.py`.
- Removed 9 inline `import uuid` statements from `_t()`/`_tname()` helpers and test methods: `TestAsyncDatabaseConstraintsIntegration._tname`, `test_from_dataframe_with_primary_key_constraint`, `test_table_info_fields_match_sync`, `TestAsyncDatabaseBulkAndSizeCoverage._t`, `TestAsyncDatabaseCRUDErgonomics._t`, `test_upsert_async`, `test_delete_where_async`, `TestAsyncDatabaseReadHelpers._t`, `TestAsyncSchemaIntrospection._t`, and `test_truncate_table_missing_raises_table_not_found`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] N802 test function names contain CamelCase (ruff)**
- **Found during:** Task 1 GREEN phase — ruff returned N802 error
- **Issue:** `test_truncate_table_missing_raises_TableNotFound` violates N802 (function names must be lowercase); `TableNotFound` is CamelCase.
- **Fix:** Renamed to `test_truncate_table_missing_raises_table_not_found` in both test files.
- **Files modified:** tests/test_database_integration.py, tests/test_async_database.py
- **Commit:** feccd2b

**2. [Rule 1 - Bug] I001 import block unsorted in test_async_database.py**
- **Found during:** Task 1 GREEN phase — ruff --fix applied
- **Issue:** Adding `TableNotFound` to the end of the from-import triggered I001.
- **Fix:** `uv run ruff check tests/test_async_database.py --fix` reformatted into sorted multi-line block.
- **Commit:** feccd2b

## Verification Results

| Check | Result |
|-------|--------|
| `PGDATABASE=pycopg_test2 pytest -k truncate -o addopts=""` | 2 passed (sync raise + cascade) |
| `PGDATABASE=pycopg_test2 pytest TestAsyncSchemaIntrospection::test_truncate... -o addopts=""` | 1 passed (async raise) |
| `pytest -k describe_missing_table -o addopts=""` | 1 passed (regression contract untouched) |
| `pytest tests/test_timescale.py -k time_bucket -x -o addopts=""` | 9 passed (1 pre-existing TSDB UndefinedFile error) |
| `PGDATABASE=pycopg_test2 pytest TestAsyncSchemaIntrospection::test_sequences_async -o addopts=""` | 1 passed (specific name asserted) |
| `PGDATABASE=pycopg_test2 pytest tests/test_parity.py -x -o addopts=""` | 26 passed |
| `uv run ruff check pycopg tests` | All checks passed |
| `uv run interrogate -f 95 pycopg/database.py` | PASSED (100%) |

## Known Stubs

None.

## Threat Flags

None — no new network endpoints, auth paths, file access patterns, or schema changes beyond what the plan's threat model covers. The `truncate_table` message names only `f"{schema}.{name}"` (caller-supplied, already validated by `validate_identifiers`). No DB internals leak.

## TDD Gate Compliance

- RED gate commit: af504a6 (`test(37-04): add failing tests...`) — both tests failed with UndefinedTable
- GREEN gate commit: feccd2b (`feat(37-04): add TableNotFound raise site...`) — all 3 targeted tests pass

## Self-Check: PASSED
