---
phase: 35-schema-introspection
plan: 01
subsystem: database
tags: [postgresql, pg_catalog, information_schema, introspection, schema, parity]

# Dependency graph
requires:
  - phase: 34-crud-ergonomics
    provides: validate_identifiers pattern, builder-pur + parity conventions established
provides:
  - PRIMARY_KEY and FOREIGN_KEYS pg_catalog SQL constants in queries.py (composite-safe, conkey/confkey ordered)
  - SEQUENCES and VIEWS information_schema SQL constants in queries.py (schema-scoped, matview-excluded)
  - primary_key(table, schema) -> dict|None on SchemaAccessor and AsyncSchemaAccessor
  - foreign_keys(table, schema) -> list[dict] (4-key shape) on SchemaAccessor and AsyncSchemaAccessor
  - sequences(schema) -> list[str] on SchemaAccessor and AsyncSchemaAccessor
  - views(schema) -> list[str] (regular views only) on SchemaAccessor and AsyncSchemaAccessor
  - Mock unit tests and live-DB integration tests for all four helpers
affects: [35-02-describe-PLAN, plan-02-schema-describe]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "pg_catalog conkey/confkey unnest-with-ordinality for composite PK/FK column ordering"
    - "information_schema.views naturally excludes materialized views (relkind != 'm')"
    - "validate_identifiers(table, schema) called first in every method; values always %s-bound"

key-files:
  created: []
  modified:
    - pycopg/queries.py
    - pycopg/schema.py
    - tests/test_database.py
    - tests/test_database_integration.py

key-decisions:
  - "PRIMARY_KEY/FOREIGN_KEYS use pg_catalog pg_constraint with unnest(conkey/confkey) WITH ORDINALITY for reliable composite-column key-order ordering (D-05)"
  - "VIEWS uses information_schema.views which naturally excludes materialized views (vs pg_catalog relkind filter) — simpler and equally correct (D-07)"
  - "foreign_keys entry has exactly 4 keys: constraint_name, columns, referenced_table, referenced_columns — on_delete/on_update/referenced_schema deferred per D-02"
  - "nonexistent table yields same result as empty table: primary_key -> None, foreign_keys -> [] (no pre-check, no new exception class)"

patterns-established:
  - "Introspection helper pattern: validate_identifiers first, execute(queries.CONSTANT, [schema, table]), reshape rows"
  - "Schema-level helpers (sequences, views) take only schema arg (no table); table-level helpers take table + schema"

requirements-completed: [INTRO-01, INTRO-02, INTRO-03, INTRO-04, INTRO-06]

# Metrics
duration: 6min
completed: 2026-06-25
---

# Phase 35 Plan 01: Schema Introspection Helpers Summary

**Four read-only introspection helpers (primary_key, foreign_keys, sequences, views) added to SchemaAccessor and AsyncSchemaAccessor using pg_catalog/information_schema with composite-safe conkey-order column arrays**

## Performance

- **Duration:** 6 min
- **Started:** 2026-06-25T08:29:08Z
- **Completed:** 2026-06-25T08:35:02Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments

- Added PRIMARY_KEY and FOREIGN_KEYS pg_catalog constants with unnest-with-ordinality for composite-safe column ordering; primary_key returns dict|None, foreign_keys returns list[dict] with exactly 4 keys
- Added SEQUENCES and VIEWS information_schema constants (schema-scoped, single %s); sequences returns list[str] including SERIAL-backed sequences; views returns list[str] excluding materialized views
- Added 8 mock unit tests (shape, composite, None/[] edge cases) and 9 live-DB integration tests (composite PK key-order, matview exclusion, nonexistent-table graceful handling) — all pass with PGDATABASE=pycopg_test2

## Task Commits

Each task was committed atomically:

1. **Task 1: PRIMARY_KEY + FOREIGN_KEYS constants and sync/async methods** - `218aba5` (feat)
2. **Task 2: SEQUENCES + VIEWS constants and sync/async methods** - `88aadf6` (feat)
3. **Task 3: Mock unit + live-DB integration tests** - `a145da6` (test)

## Files Created/Modified

- `pycopg/queries.py` - Added PRIMARY_KEY, FOREIGN_KEYS (pg_catalog, schema+table), SEQUENCES, VIEWS (information_schema, schema-only) constants
- `pycopg/schema.py` - Added primary_key, foreign_keys, sequences, views on SchemaAccessor (sync) and AsyncSchemaAccessor (async twins)
- `tests/test_database.py` - Added TestDatabaseIntrospectionHelpers with 9 mock-based unit tests
- `tests/test_database_integration.py` - Added TestIntrospectionHelpers with 9 live-DB integration tests

## Decisions Made

- Used pg_catalog (pg_constraint + unnest WITH ORDINALITY) for PK/FK rather than information_schema — gives reliable conkey-order column arrays including composites
- Used information_schema.views for VIEWS filter (not pg_catalog relkind='v') — naturally excludes materialized views and is simpler SQL
- No on_delete/on_update/referenced_schema in foreign_keys entries — deferred per D-02
- No new exception class — nonexistent tables return None/[] gracefully (consistent with list_indexes/list_constraints behavior)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- `uv run ruff check pycopg tests` has 35 pre-existing errors (N818, W291, F841, E722 in existing files not touched by this plan) — confirmed by reverting changes and re-running. New code (`pycopg/queries.py`, `pycopg/schema.py`) is ruff-clean.
- The default `pycopg_test` DB is broken (TimescaleDB 2.28.0 catalog mismatch); live-DB tests run with `PGDATABASE=pycopg_test2` per project convention.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- All four introspection helpers are ready; parity test_accessor_parity passes (7/7 accessor pairs green)
- Plan 02 (describe consolidation) can compose primary_key, foreign_keys, sequences, views as building blocks
- No blockers; no new dependencies

## Self-Check: PASSED

- `pycopg/queries.py` contains PRIMARY_KEY, FOREIGN_KEYS, SEQUENCES, VIEWS constants
- `pycopg/schema.py` contains def primary_key, def foreign_keys, def sequences, def views (sync) and async twins
- Commits 218aba5, 88aadf6, a145da6 all verified in git log
- 9 mock unit tests pass, 9 live-DB tests pass, test_accessor_parity (7 pairs) passes

---
*Phase: 35-schema-introspection*
*Completed: 2026-06-25*
