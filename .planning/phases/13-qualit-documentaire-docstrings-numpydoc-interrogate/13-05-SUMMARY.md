---
phase: 13-qualit-documentaire-docstrings-numpydoc-interrogate
plan: "05"
subsystem: documentation
tags: [numpydoc, docstrings, interrogate, sphinx, napoleon]

requires:
  - phase: 13-01
    provides: interrogate tooling, Sphinx -W guard, napoleon_numpy_docstring config

provides:
  - numpydoc shallow docstrings in base.py (DatabaseBase, QueryMixin, build_pg_dump_cmd, build_pg_restore_cmd, build_role_options)
  - numpydoc shallow docstrings in config.py (Config.from_url, from_env, dsn, url, async_url, connect_params, with_database)
  - numpydoc shallow docstrings in utils.py (all 10 validation/utility functions)
  - numpydoc shallow docstrings in migrations.py (Migration, Migrator — all public methods)
  - numpydoc shallow docstrings in pool.py (PooledDatabase, AsyncPooledDatabase — all public methods)

affects: [13-06, sphinx-docs, any future doc builds]

tech-stack:
  added: []
  patterns:
    - "numpydoc shallow format: Parameters/Returns/Raises with 10/7/6-dash underlines, 4-space param descriptions"
    - "optional params: ', optional' type suffix + ', by default <value>' in description"
    - "Yields sections use 6-dash underline (same as Raises)"
    - "class-level and method-level Example:/Examples: blocks deleted per D-06"

key-files:
  created: []
  modified:
    - pycopg/base.py
    - pycopg/config.py
    - pycopg/utils.py
    - pycopg/migrations.py
    - pycopg/pool.py

key-decisions:
  - "D-06 applied: all Example:/Examples: sections deleted, including module-level docstring example block in migrations.py"
  - "Yields sections formatted as 'Yields / ------' (6 dashes) matching Raises convention"
  - "Pre-existing Sphinx warnings in database.py / async_database.py (22 total) are out of scope — zero warnings from the 5 plan modules"

patterns-established:
  - "Numpydoc shallow: Parameters(10) / Returns(7) / Raises(6) / Yields(6) dashes"
  - "**kwargs documented as '**kwargs' entry without type, no default"
  - "Optional params: 'type, optional\\n    Description, by default value.'"

requirements-completed: [DOC-06]

duration: 7min
completed: "2026-06-10"
---

# Phase 13 Plan 05: Base, Config, Utils, Migrations, Pool Docstring Migration Summary

**Numpydoc shallow format applied to all ~42 Google-style docstrings across 5 grouped modules (base.py, config.py, utils.py, migrations.py, pool.py) — no Examples sections, interrogate >= 95, zero Sphinx warnings from these modules**

## Performance

- **Duration:** ~7 min
- **Started:** 2026-06-10T11:50:00Z
- **Completed:** 2026-06-10T11:57:00Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- All Google-style `Args:`, `Returns:`, `Raises:` labels replaced with numpydoc `Parameters / ----------`, `Returns / -------`, `Raises / ------` sections across 5 modules
- All `Example:`, `Examples:` sections removed per D-06 (including class-body examples in `Config`, `Migrator`, `PooledDatabase`, `AsyncPooledDatabase` and the module-level example block in `migrations.py`)
- `interrogate pycopg --fail-under 95` passes (exit 0)
- Zero Sphinx warnings from the 5 plan modules; pre-existing 22 warnings in database.py/async_database.py are out of scope for this plan
- Targeted tests for migrations, config, and pool all pass (79 + 38 tests green)

## Task Commits

1. **Task 1: Migrate base.py, config.py, utils.py** - `1881f72` (docs)
2. **Task 2: Migrate migrations.py + pool.py + whole-package verification** - `159d006` (docs)

## Files Created/Modified

- `/home/loc/workspace/pycopg/pycopg/base.py` - Migrated 9 docstrings (DatabaseBase.__init__, from_env, from_url; QueryMixin._build_insert_sql, _build_batch_insert_sql, _build_select_sql; build_pg_dump_cmd, build_pg_restore_cmd, build_role_options)
- `/home/loc/workspace/pycopg/pycopg/config.py` - Migrated 7 docstrings (Config class body Examples removed; from_url, from_env, dsn, url, async_url, connect_params, with_database)
- `/home/loc/workspace/pycopg/pycopg/utils.py` - Migrated 10 docstrings (validate_identifier, validate_identifiers, validate_interval, validate_extension_name, validate_timestamp, validate_privileges, validate_object_type, validate_csv_option, validate_index_method, quote_literal)
- `/home/loc/workspace/pycopg/pycopg/migrations.py` - Migrated 11 docstrings (Migration.__init__, _parse_filename; Migrator class body + __init__, pending, applied, migrate, _apply, rollback, _extract_section, status, create); module-level Example block removed
- `/home/loc/workspace/pycopg/pycopg/pool.py` - Migrated 13 docstrings (PooledDatabase class body + __init__, from_env, from_url, connection, execute, execute_many, stats, resize, wait; AsyncPooledDatabase class body + __init__, connection, execute, transaction)

## Decisions Made

- `Yields:` sections in context managers converted to numpydoc `Yields / ------` (6 dashes, same as `Raises`) — numpydoc uses same dash count as `Raises` for `Yields`
- Module-level docstring example block in `migrations.py` deleted (D-06 applies to all `Example:` / `Examples:` occurrences including module-level ones)
- Pre-existing Sphinx warnings (22 total in database.py + async_database.py from Plans 13-03/04) are out of scope; zero warnings from these 5 plan modules

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Sphinx `uv run pip install ...` failed (no pip module in uv venv); used `uv run python -m pip` as fallback — pip not available, but docs/requirements.txt were already installed from Plan 13-01 so Sphinx build succeeded directly.

## Known Stubs

None.

## Threat Flags

None - docstring-only reformatting introduces no new trust boundaries.

## Self-Check

Files exist:
- `/home/loc/workspace/pycopg/pycopg/base.py` — FOUND
- `/home/loc/workspace/pycopg/pycopg/config.py` — FOUND
- `/home/loc/workspace/pycopg/pycopg/utils.py` — FOUND
- `/home/loc/workspace/pycopg/pycopg/migrations.py` — FOUND
- `/home/loc/workspace/pycopg/pycopg/pool.py` — FOUND

Commits exist:
- `1881f72` — FOUND
- `159d006` — FOUND

Verification:
- `grep -cE "^\s*(Args|Returns|Raises|Example|Examples):"` = 0 for all 5 files — PASSED
- `interrogate pycopg --fail-under 95 --quiet` exit 0 — PASSED
- Sphinx build: 0 warnings from plan's 5 modules — PASSED
- Targeted tests: 79 + 38 passed — PASSED

## Self-Check: PASSED

## Next Phase Readiness

- All 5 grouped modules are in numpydoc shallow format
- Plan 13-05 completes the D-06/D-07 migration for the "rest" group
- Plans 13-03 (database.py + async_database.py) and 13-04 (exceptions.py + __init__.py) plus this plan 13-05 together cover the whole package
- Phase 13 Plan 06 (final verification + coverage gate) is ready to run

---
*Phase: 13-qualit-documentaire-docstrings-numpydoc-interrogate*
*Completed: 2026-06-10*
