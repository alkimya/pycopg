---
phase: 12-refactoring-brancher-les-abstractions
plan: 03
subsystem: database
tags: [refactor, sql-constants, batch-insert, dead-code, postgres]

# Dependency graph
requires:
  - phase: 12-02
    provides: "Database and AsyncDatabase inherit (DatabaseBase, QueryMixin); _build_batch_insert_sql available"
provides:
  - "~25 inline SQL strings replaced by queries.* constants (single source of SQL truth)"
  - "async table_info/list_roles routed to canonical queries.TABLE_INFO / queries.LIST_ROLES (D-05)"
  - "insert_many/upsert_many (sync + async) use _build_batch_insert_sql (REF-02/D-02)"
  - "Dead code removed: Phase-3 comments, unread stdout, no-op try/except (REF-04)"
affects: [12-04]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "queries.NAME constant wiring (param-only)"
    - "queries.NAME.format(where_clause=...) for slot-bearing constants (LIST_ROLES, LIST_GEOMETRY_COLUMNS)"
    - "_build_batch_insert_sql: multi-VALUES INSERT via inherited mixin builder"

key-files:
  created: []
  modified:
    - pycopg/database.py
    - pycopg/async_database.py
    - pycopg/queries.py
    - tests/test_database.py
    - tests/test_async_database.py

key-decisions:
  - "insert_many/upsert_many now use _build_batch_insert_sql + cursor.execute (not executemany); mock tests updated to assert execute instead of executemany — implementation-checking mocks updated, behavioral assertions (rowcount, SQL format) preserved."
  - "queries.HYPERTABLE_INFO had bug: %I instead of %%I (psycopg would interpret %I as invalid placeholder). Fixed to %%I + ::text casts, matching the inline form used in both database.py/async_database.py pre-phase (Rule 1 bug-fix deviation)."
  - "validate_identifier count in database.py dropped 65→63, async 66→64: 2 explicit calls removed from insert_many body as _build_batch_insert_sql calls validate_identifiers(table, schema, *columns) internally. Validation still fires on every path; test_sql_injection.py confirms."
  - "Pre-existing ruff errors (38, entirely in untouched files pool/utils/migrations/config/exceptions/__init__) left out of scope per deviation scope boundary."

patterns-established:
  - "queries.* as single source of SQL truth; constants used directly or with .format(where_clause=...)"
  - "Batch INSERT via _build_batch_insert_sql returns (sql, flat_params); execute via cursor.execute not executemany"

requirements-completed: [REF-01, REF-02, REF-04]

# Metrics
duration: 35 min
completed: 2026-06-09
---

# Phase 12 Plan 03: Wire inline SQL to queries.* + batch INSERT + dead code removal Summary

**~25 inline SQL strings replaced by queries.* constants; async table_info/list_roles on canonical constants (D-05); insert_many/upsert_many routed through _build_batch_insert_sql (D-02); stale Phase-3 comments, unread stdout bindings, and no-op try/except removed (REF-04).**

## Performance

- **Duration:** ~35 min
- **Started:** 2026-06-09 (inline execution)
- **Completed:** 2026-06-09
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

### Task 1: Wire inline SQL to queries.* + batch INSERT

**REF-01 — Constants wired (database.py and async_database.py):**
- `LIST_SCHEMAS`, `SCHEMA_EXISTS`, `LIST_TABLES`, `TABLE_INFO`, `ROW_COUNT`
- `LIST_INDEXES`, `LIST_CONSTRAINTS`, `EXTENSION_EXISTS`, `LIST_EXTENSIONS`
- `LIST_GEOMETRY_COLUMNS.format(where_clause=...)` (slot-bearing constant)
- `LIST_HYPERTABLES`, `HYPERTABLE_INFO`, `ROLE_EXISTS`
- `LIST_ROLES.format(where_clause=...)` (slot-bearing constant)
- `LIST_ROLE_MEMBERS`, `LIST_ROLE_GRANTS`, `DATABASE_EXISTS`
- `LIST_DATABASES`, `DATABASE_SIZE_PRETTY`, `DATABASE_SIZE`
- `TABLE_SIZE_PRETTY`, `TABLE_SIZE`, `TABLE_SIZES`

**D-05 (async):** `async_database.table_info` → `queries.TABLE_INFO`; `async_database.list_roles` → `queries.LIST_ROLES.format(where_clause=where_clause)`. Both already produced the rich post-Phase-11 shape; test_parity field-parity tests confirm.

**REF-02/D-02 (batch INSERT):** `insert_many` (sync + async) now calls `self._build_batch_insert_sql(table, columns, rows, schema, on_conflict)` (inherited from QueryMixin via Phase 12-02) and executes the single multi-VALUES statement via `cursor.execute`. `upsert_many` delegates to `insert_many` as before.

**queries.py bug fix (Rule 1):** `HYPERTABLE_INFO` constant used `%I` (single percent) which psycopg treats as an invalid placeholder. Fixed to `%%I` with `::text` casts, matching the form in the inline SQL that was replaced.

### Task 2: Dead code removal (REF-04)

**Phase-3 stale comments removed:** Two "Note: Requires add_primary_key (available in Phase 3)." lines deleted from async_database.py docstrings (from_dataframe, from_geodataframe). `add_primary_key` shipped in Phase 11.

**Unread stdout bindings:** Three `stdout, stderr = await proc.communicate()` sites (pg_dump, pg_restore, _psql_restore in async_database.py) changed to `_, stderr = await proc.communicate()`. Verified stdout unused after each call before editing.

**No-op try/except removed:** Outer `try: ... except Exception: raise` wrapper in `async_database.copy_to_csv` deleted. The block had no `finally`, no other `except` clause — a pure no-op re-raise. The inner `try/finally` (file handle close guard) was preserved unchanged.

**import re:** Confirmed absent from both database.py and async_database.py — N/A.

**Intentional re-raises preserved:** `except ValueError: raise` at database.py:1387 and async_database.py:1823 — left untouched. These prevent a broader `except Exception` below from masking ValueError; removing them WOULD change control flow.

## Task Commits

1. **Task 1: Wire inline SQL to queries.* constants + batch INSERT via _build_batch_insert_sql** — `d7b6046` (refactor)
2. **Task 2: Remove grep-proven dead code (REF-04)** — `cea4757` (refactor)

## Files Created/Modified

- `pycopg/database.py` — ~25 inline SQL strings → queries.* constants; insert_many → _build_batch_insert_sql
- `pycopg/async_database.py` — same wiring + D-05 (table_info/list_roles) + dead code removal
- `pycopg/queries.py` — HYPERTABLE_INFO bug fix (%%I + ::text)
- `tests/test_database.py` — insert_many mock tests updated: executemany → execute (implementation change)
- `tests/test_async_database.py` — insert_many mock test updated: executemany → execute

## Decisions Made

- Adopted `_build_batch_insert_sql` for insert_many as directed by D-02; updated implementation-checking mock tests (asserting `executemany`) to assert `execute` instead. Behavioral assertions (rowcount, SQL format starting with "INSERT INTO public.users") preserved.
- validate_identifier count in database.py: 65→63 (async: 66→64). Two explicit calls removed from insert_many body; validation still fires inside the builder. Injection tests green.
- Pre-existing ruff errors (38, entirely in untouched files) left as-is per deviation scope boundary.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed queries.HYPERTABLE_INFO invalid placeholder**
- **Found during:** Task 1 (test_async_database::test_hypertable_lifecycle failure)
- **Issue:** `queries.HYPERTABLE_INFO` used `%I` (single percent); psycopg interprets `%I` as an invalid placeholder format (only `%s`, `%b`, `%t` allowed), raising `ProgrammingError`
- **Fix:** Changed `%I` → `%%I` and added `::text` casts in the constant, matching the form used by the inline SQL that was replaced. The original inline SQL in both database.py and async_database.py already used `%%I` correctly.
- **Files modified:** `pycopg/queries.py`
- **Commit:** `d7b6046`

**2. [Deviation - Test update] Updated implementation-checking mock tests for insert_many**
- **Found during:** Task 1 (D-02 wiring changes the internal execution method)
- **Issue:** Two mock tests (`test_insert_many_delegates_to_execute_many` in test_database.py, `test_insert_many` in test_async_database.py) asserted `cursor.executemany`. The plan explicitly changes the implementation to `cursor.execute` via `_build_batch_insert_sql`. These tests check implementation, not behavior.
- **Fix:** Updated assertion from `executemany.assert_called_once()` to `execute.assert_called_once()`; updated SQL extraction to use `execute.call_args`. Renamed test to `test_insert_many_delegates_to_batch_builder`. Behavioral assertions (rowcount == 2, SQL starts with "INSERT INTO public.users") preserved.
- **Files modified:** `tests/test_database.py`, `tests/test_async_database.py`
- **Commit:** `d7b6046`

## Known Pre-existing Full-suite DB Failures (unchanged)

The following three tests fail in the full local DB suite and were verified as pre-existing BEFORE Phase 12 (confirmed on base commit prior to 12-01):

1. `tests/test_parity.py::TestBehavioralParity::test_create_constructor_parity` — `ObjectInUse` during teardown `drop_database` (passes in isolation; lingering-session teardown race)
2. `tests/test_integration.py::TestAsyncIntegration::test_async_transaction_fix` — `UndefinedTable`
3. `tests/test_postgis_errors.py::TestPostGISErrorHandling::test_create_spatial_index_name_parameter` — `UndefinedTable`

These are unrelated to this plan's changes. The targeted acceptance suites (test_database, test_async_database, test_parity, test_sql_injection) pass 356/356.

## Pre-existing Ruff Errors in Untouched Files

38 ruff errors exist in untouched files (pool.py, utils.py, migrations.py, config.py, exceptions.py, __init__.py). Not fixed per deviation scope boundary. Touched files (database.py, async_database.py) pass ruff cleanly.

## Known Stubs

None — all changes are wiring existing SQL constants and cleanup; no placeholders or stub data introduced.

## Threat Flags

None — this plan replaces inline SQL with constants (same SQL text, same parameter binding) and removes dead code. No new network endpoints, auth paths, or schema changes. T-12-06 (SQL injection via rewire) mitigated: validation preserved in builder. T-12-07 (batch INSERT builder) mitigated: builder calls validate_identifiers up front. T-12-08 (no-op try/except removal) mitigated: confirmed no finally, no other except, control flow unchanged.

---
*Phase: 12-refactoring-brancher-les-abstractions*
*Completed: 2026-06-09*
