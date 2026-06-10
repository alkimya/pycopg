---
phase: 13-qualit-documentaire-docstrings-numpydoc-interrogate
plan: "04"
subsystem: documentation
tags: [numpydoc, docstrings, interrogate, sphinx, napoleon, async_database]

requires:
  - phase: 13-01
    provides: interrogate tooling, Sphinx -W guard, napoleon_numpy_docstring config
  - phase: 13-02
    provides: ExtensionNotAvailable/DatabaseExists exceptions at raise sites in async_database.py

provides:
  - numpydoc shallow docstrings in async_database.py (AsyncDatabase class — all ~70 public docstrings)
  - Raises sections for TimescaleDB/PostGIS extension methods and create() documenting ExtensionNotAvailable/DatabaseExists
  - All Example:/Examples: sections deleted per D-06 (including class-level Example: block)

affects: [13-05, 13-06, sphinx-docs]

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
    - pycopg/async_database.py

key-decisions:
  - "D-06 applied: all Example:/Examples: sections deleted (class body + all methods)"
  - "Raises sections added to create_hypertable, enable_compression, add_compression_policy, add_retention_policy, list_hypertables, hypertable_info documenting ExtensionNotAvailable"
  - "Raises section added to create() documenting DatabaseExists"
  - "Raises section added to from_geodataframe documenting ExtensionNotAvailable"
  - "One-liner stubs expanded to full numpydoc (list_schemas, schema_exists, list_tables, table_exists, row_count, has_extension, role_exists, list_roles, list_extensions, size, table_size)"
  - "Task 1 and Task 2 executed as single atomic pass — split was organizational not a logical gate"

requirements-completed: [DOC-06]

duration: 14min
completed: "2026-06-10"
---

# Phase 13 Plan 04: async_database.py Docstring Migration Summary

**All ~70 Google-style docstrings in async_database.py converted to numpydoc shallow format — Parameters/Returns/Raises/Yields with exact dash counts, all Examples deleted, Raises sections added to 8 extension-gating methods, class-level Example: block removed, zero Sphinx warnings, 172 tests green**

## Performance

- **Duration:** ~14 min
- **Started:** 2026-06-10T12:19:28Z
- **Completed:** 2026-06-10T12:33:28Z
- **Tasks:** 2 (migrated as single atomic pass)
- **Files modified:** 1

## Accomplishments

- All Google-style `Args:`, `Returns:`, `Raises:` labels replaced with numpydoc `Parameters / ----------`, `Returns / -------`, `Raises / ------` sections throughout async_database.py
- Class-level `Example:` block (lines 64-80) deleted per D-06
- All `Example:` and `Examples:` sections in methods removed per D-06
- AsyncDatabase class docstring converted from Example-based to Attributes-based (matching database.py format)
- `Raises` sections added to 8 extension-gating methods (`create`, `from_geodataframe`, `create_hypertable`, `enable_compression`, `add_compression_policy`, `add_retention_policy`, `list_hypertables`, `hypertable_info`) documenting `ExtensionNotAvailable` and `DatabaseExists`
- One-liner docstrings expanded to full numpydoc format (11 methods total)
- `Yields` context managers (`connect`, `cursor`, `session`, `transaction`, `stream`, `listen`) converted to numpydoc `Yields / ------` (6 dashes)
- `interrogate pycopg --fail-under 95` passes (exit 0)
- Zero Sphinx warnings from async_database.py (0 warnings total in full build, exit 0)
- 172 async_database unit + integration tests pass

## Task Commits

1. **Task 1 + Task 2: Migrate all async_database.py docstrings to numpydoc** - `a0e843e` (docs)

## Files Created/Modified

- `/home/loc/workspace/pycopg/pycopg/async_database.py` — Migrated ~70 docstrings (AsyncDatabase class body, __init__, create, create_from_env, connect, cursor, session, transaction, in_session, execute, execute_many, insert_batch, copy_insert, fetch_one, fetch_val, list_schemas, schema_exists, create_schema, list_tables, table_exists, list_columns, columns_with_types, table_info, row_count, drop_schema, drop_table, truncate_table, add_primary_key, add_foreign_key, add_unique_constraint, create_index, drop_index, list_indexes, list_constraints, has_extension, create_extension, list_extensions, drop_extension, create_spatial_index, list_geometry_columns, create_hypertable, enable_compression, add_compression_policy, add_retention_policy, list_hypertables, hypertable_info, role_exists, list_roles, create_role, drop_role, alter_role, grant, revoke, grant_role, revoke_role, list_role_members, list_role_grants, size, table_size, table_sizes, to_dataframe, from_dataframe, to_geodataframe, from_geodataframe, insert_many, upsert_many, stream, create_database, drop_database, database_exists, list_databases, vacuum, analyze, explain, pg_dump, pg_restore, copy_to_csv, copy_from_csv, listen, notify)

## Decisions Made

- `Raises` sections added to extension-gating methods since Plan 02 already raised these exceptions at these sites — documenting in numpydoc is correct D-07 migration
- `Yields` sections use 6-dash underline (consistent with database.py established in Plan 03)
- Task 1 and Task 2 executed as a single atomic pass — committed together since they form one coherent transformation

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## Known Stubs

None.

## Threat Flags

None — docstring-only reformatting introduces no new trust boundaries.

## Self-Check

Files exist:
- `/home/loc/workspace/pycopg/pycopg/async_database.py` — FOUND

Commits exist:
- `a0e843e` — FOUND

Verification:
- `grep -cE "^\s*(Args|Returns|Raises|Example|Examples):" pycopg/async_database.py` = 0 — PASSED
- `grep -c "Parameters" pycopg/async_database.py` = 73 — PASSED (numpydoc sections present)
- `interrogate pycopg --fail-under 95 --quiet` exit 0 — PASSED
- Sphinx build: 0 warnings total, exit 0 — PASSED
- `uv run pytest tests/test_async_database.py -x -o addopts="" -q` = 172 passed — PASSED

## Self-Check: PASSED

## Next Phase Readiness

- async_database.py is fully numpydoc shallow format
- Plan 13-05 (5 grouped modules: base.py, config.py, utils.py, migrations.py, pool.py) is next
- Plan 13-06 (final verification + coverage gate) is the final plan

---
*Phase: 13-qualit-documentaire-docstrings-numpydoc-interrogate*
*Completed: 2026-06-10*
