---
phase: 35-schema-introspection
plan: 02
subsystem: database
tags: [postgresql, pg_catalog, information_schema, introspection, schema, parity, describe]

# Dependency graph
requires:
  - phase: 35-01
    provides: primary_key, foreign_keys, sequences, views helpers on both accessors
provides:
  - describe(table, schema) -> dict on SchemaAccessor (sync) and AsyncSchemaAccessor (async)
  - Flat 4-key composition dict: columns/primary_key/foreign_keys/indexes
  - Live-DB composition-equality tests (anti-drift guarantee D-04)
  - Missing-table empty/None graceful behavior (D-06)
  - test_schema_v090_surface named frozenset test in test_parity.py
affects: [35-CONTEXT-D04, 35-CONTEXT-D06]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "describe composes four standalone helpers (table_info/primary_key/foreign_keys/list_indexes) — no new SQL, no new queries.py constant (D-04)"
    - "Async describe awaits each composed helper identically"
    - "Missing table: composed helpers each return empty/None so describe returns all-empty/None flat dict (D-06)"
    - "Mock test patches each helper with patch.object to assert call args and exact return shapes"

key-files:
  created: []
  modified:
    - pycopg/schema.py
    - tests/test_database.py
    - tests/test_database_integration.py
    - tests/test_parity.py

key-decisions:
  - "describe composes (not re-queries) the four standalone helpers — guarantees sub-shapes can never drift from the standalone methods (D-04)"
  - "No validate_identifiers call in describe itself — each composed helper already guards its own inputs"
  - "Missing table returns all-empty/None dict with no existence pre-check and no new exception class (D-06)"
  - "Mock unit test uses patch.object per helper rather than shared fetchall mock to avoid cross-helper row shape conflicts"

requirements-completed: [INTRO-05, INTRO-06]

# Metrics
duration: 8min
completed: 2026-06-25
---

# Phase 35 Plan 02: describe Consolidation Helper Summary

**Sync and async describe method added to SchemaAccessor / AsyncSchemaAccessor composing table_info/primary_key/foreign_keys/list_indexes into one guaranteed-consistent flat dict with no new SQL**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-06-25T08:40:00Z
- **Completed:** 2026-06-25T08:48:00Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Added `describe(table, schema="public") -> dict` to `SchemaAccessor` (sync) composing the four standalone helpers: `table_info`, `primary_key`, `foreign_keys`, `list_indexes` — exact 4-key flat dict, no new SQL, no new queries.py constant
- Added `async describe(...)` to `AsyncSchemaAccessor` awaiting all four helpers identically; `test_accessor_parity` passes (7 pairs x bidirectional parity)
- Added live-DB tests in `TestIntrospectionHelpers`: composition-equality (each sub-value == standalone helper output), missing-table all-empty/None dict
- Added mock unit test in `TestDatabaseIntrospectionHelpers` using `patch.object` per helper to assert call args and exact composition
- Added `test_schema_v090_surface` to `test_parity.py`: frozenset `{primary_key, foreign_keys, sequences, views, describe}` asserted as subset of both classes' public members

## Task Commits

Each task was committed atomically:

1. **Task 1: Add describe composition helper to both classes** - `964c6f5` (feat)
2. **Task 2: Tests for describe (composition equality + missing-table) and optional v090 named-surface test** - `a2df075` (test)

## Files Created/Modified

- `pycopg/schema.py` - Added `def describe` (sync) on SchemaAccessor + `async def describe` on AsyncSchemaAccessor (lines ~777, ~1558)
- `tests/test_database.py` - Added `test_describe_composes_four_helpers` mock unit test to `TestDatabaseIntrospectionHelpers`
- `tests/test_database_integration.py` - Added `test_describe_keys_and_composition_equality` and `test_describe_missing_table_returns_empty` to `TestIntrospectionHelpers`
- `tests/test_parity.py` - Added `test_schema_v090_surface` named frozenset test

## Decisions Made

- Composed four standalone helpers (no new SQL) so sub-shapes can never drift — D-04 compliance
- Numpydoc shallow docstring on both methods (no Examples section, matching existing schema.py style)
- Mock test uses `patch.object` per helper (not shared `_make_db` fetchall) to avoid row-shape conflicts across helpers
- No `validate_identifiers` in `describe` itself — composed helpers guard their own inputs

## Deviations from Plan

**1. [Rule 1 - Bug] Fixed mock test design to use patch.object per helper**
- **Found during:** Task 2
- **Issue:** Initial mock test used `_make_db` which sets a single `fetchall` return value shared across all execute calls; `primary_key` tried to access `constraint_name` on column-info rows → KeyError
- **Fix:** Rewrote mock test to `patch.object` each of the four composed helpers individually, asserting both call args and exact return shapes
- **Files modified:** `tests/test_database.py`
- **Commit:** `a2df075`

## Threat Surface Scan

No new threat surface introduced. `describe` is pure read-only composition of already-mitigated helpers; identifier validation is provided by each composed helper (T-35-03/T-35-04 — both accepted/mitigated in plan threat model).

## Known Stubs

None — `describe` returns live data from composed helpers; no placeholder values.

## Self-Check: PASSED

- `pycopg/schema.py` contains `def describe` (line 777) and `async def describe` (line 1558) — verified via grep
- Both bodies reference all four helpers: `self.table_info`, `self.primary_key`, `self.foreign_keys`, `self.list_indexes`
- No DESCRIBE constant in queries.py
- Commits 964c6f5, a2df075 verified in git log
- `PGDATABASE=pycopg_test2 uv run pytest tests/test_database_integration.py -o addopts="" -q -k describe` — 2 passed
- `uv run pytest tests/test_parity.py -o addopts="" -q -k "accessor_parity or v090"` — 8 passed
- `uv run pytest tests/test_database.py -o addopts="" -q -k describe` — 1 passed
- `uv run ruff check pycopg/schema.py` — clean (0 errors)

---
*Phase: 35-schema-introspection*
*Completed: 2026-06-25*
