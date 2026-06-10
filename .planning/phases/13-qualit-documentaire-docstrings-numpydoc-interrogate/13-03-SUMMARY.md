---
phase: 13-qualit-documentaire-docstrings-numpydoc-interrogate
plan: "03"
subsystem: documentation
tags: [numpydoc, docstrings, interrogate, sphinx, napoleon, database]

requires:
  - phase: 13-01
    provides: interrogate tooling, Sphinx -W guard, napoleon_numpy_docstring config
  - phase: 13-02
    provides: ExtensionNotAvailable/DatabaseExists exceptions at 7 raise sites in database.py

provides:
  - numpydoc shallow docstrings in database.py (Database class — all ~77 public docstrings)
  - Raises sections for TimescaleDB/PostGIS extension methods and create() documenting ExtensionNotAvailable/DatabaseExists
  - All Example:/Examples: sections deleted per D-06

affects: [13-04, 13-05, 13-06, sphinx-docs]

tech-stack:
  added: []
  patterns:
    - "numpydoc shallow format: Parameters/Returns/Raises/Yields with 10/7/6/6-dash underlines"
    - "optional params: ', optional' type suffix + ', by default <value>' in description"
    - "class-level Attributes section uses 10-dash underline (same as Parameters)"
    - "All Example:/Examples: blocks deleted per D-06"

key-files:
  created: []
  modified:
    - pycopg/database.py

key-decisions:
  - "D-06 applied: all Example:/Examples: sections deleted (class body + all methods)"
  - "Raises sections added to from_geodataframe, create_hypertable, enable_compression, add_compression_policy, add_retention_policy, list_hypertables, hypertable_info documenting ExtensionNotAvailable"
  - "Database class-level Attributes: section converted to numpydoc format (10-dash underline)"

patterns-established:
  - "Sphinx build -W exit 0 after database.py migration — zero warnings from this module"

requirements-completed: [DOC-06]

duration: 15min
completed: "2026-06-10"
---

# Phase 13 Plan 03: database.py Docstring Migration Summary

**All ~77 Google-style docstrings in database.py converted to numpydoc shallow format — Parameters/Returns/Raises with exact dash counts, all Examples deleted, Raises sections added to 8 extension-gating methods, zero Sphinx warnings, 156 tests green**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-06-10T12:00:00Z
- **Completed:** 2026-06-10T12:15:00Z
- **Tasks:** 2 (migrated as single atomic pass)
- **Files modified:** 1

## Accomplishments

- All Google-style `Args:`, `Returns:`, `Raises:` labels replaced with numpydoc `Parameters / ----------`, `Returns / -------`, `Raises / ------` sections throughout database.py
- All `Example:` and `Examples:` sections removed per D-06 (class body + every method)
- `Raises` sections added to 8 extension-gating methods (`from_geodataframe`, `create_hypertable`, `enable_compression`, `add_compression_policy`, `add_retention_policy`, `list_hypertables`, `hypertable_info`) documenting `ExtensionNotAvailable` and `DatabaseExists`
- `Yields` context managers (`connect`, `cursor`, `session`, `stream`) converted to numpydoc `Yields / ------` (6 dashes)
- `interrogate pycopg --fail-under 95` passes (exit 0)
- Zero Sphinx warnings from database.py (0 warnings total in full build)
- 100 unit tests + 56 integration tests pass (156 total)

## Task Commits

1. **Task 1 + Task 2: Migrate all database.py docstrings to numpydoc** - `56afc19` (docs)

## Files Created/Modified

- `/home/loc/workspace/pycopg/pycopg/database.py` — Migrated 77 docstrings (Database class body, __init__, create, create_from_env, connect, cursor, transaction, session, in_session, execute, execute_many, insert_many, upsert_many, stream, notify, insert_batch, copy_insert, fetch_one, fetch_val, create_database, drop_database, database_exists, list_databases, create_extension, drop_extension, list_extensions, has_extension, create_schema, drop_schema, list_schemas, schema_exists, list_tables, table_exists, list_columns, columns_with_types, drop_table, truncate_table, table_info, row_count, add_primary_key, add_foreign_key, add_unique_constraint, create_index, drop_index, list_indexes, list_constraints, from_dataframe, to_dataframe, from_geodataframe, to_geodataframe, create_spatial_index, list_geometry_columns, create_hypertable, enable_compression, add_compression_policy, add_retention_policy, list_hypertables, hypertable_info, size, table_size, table_sizes, vacuum, analyze, explain, create_role, drop_role, role_exists, list_roles, alter_role, grant_role, revoke_role, grant, revoke, list_role_members, list_role_grants, pg_dump, pg_restore, copy_to_csv, copy_from_csv)

## Decisions Made

- `Raises` sections added to extension-gating methods (from_geodataframe, all TimescaleDB methods) since Plan 02 already raised these exceptions at these sites — documenting in numpydoc is the correct D-07 migration
- `Yields` sections use 6-dash underline (consistent with base.py/pool.py established in Plan 05)
- Task 1 and Task 2 executed as a single atomic pass and committed together — the split was organizational, not a logical gate

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## Known Stubs

None.

## Threat Flags

None — docstring-only reformatting introduces no new trust boundaries.

## Self-Check

Files exist:
- `/home/loc/workspace/pycopg/pycopg/database.py` — FOUND

Commits exist:
- `56afc19` — FOUND

Verification:
- `grep -cE "^\s*(Args|Returns|Raises|Example|Examples):" pycopg/database.py` = 0 — PASSED
- `grep -c "Parameters" pycopg/database.py` = 72 — PASSED (numpydoc sections present)
- `interrogate pycopg --fail-under 95 --quiet` exit 0 — PASSED
- Sphinx build: 0 warnings total, exit 0 — PASSED
- `uv run pytest tests/test_database.py tests/test_database_integration.py -x -o addopts="" -q` = 156 passed — PASSED

## Self-Check: PASSED

## Next Phase Readiness

- database.py is fully numpydoc shallow format
- Plans 13-04 (exceptions.py + __init__.py) and 13-05 (5 grouped modules) are already complete
- Plan 13-06 (final verification + coverage gate) is ready to run

---
*Phase: 13-qualit-documentaire-docstrings-numpydoc-interrogate*
*Completed: 2026-06-10*
