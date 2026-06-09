---
phase: 12-refactoring-brancher-les-abstractions
plan: 02
subsystem: database
tags: [refactor, inheritance, mixin, postgres, dead-code]

# Dependency graph
requires:
  - phase: 12-01
    provides: "module-level pure builders in base.py (base.py in its final shape)"
provides:
  - "Database and AsyncDatabase inherit (DatabaseBase, QueryMixin)"
  - "Single source of factories (from_env/from_url) + __repr__ on DatabaseBase"
  - "queries.py with orphan *_SIMPLE constants removed"
affects: [12-03, 12-04]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Inheritance collapse onto DatabaseBase socle (cls(...) preserves subclass)"

key-files:
  created: []
  modified:
    - pycopg/database.py
    - pycopg/async_database.py
    - pycopg/queries.py

key-decisions:
  - "Concrete from_env/from_url/__repr__ deleted from both subclasses; inherited from DatabaseBase. cls(...) resolution returns the correct subclass, behavior unchanged (D-01/D-06)."
  - "Pre-existing ruff errors (38, all in untouched files pool/utils/migrations/config/exceptions/__init__) left as-is per deviation scope boundary."

patterns-established:
  - "Inheritance collapse: class X(DatabaseBase, QueryMixin), __init__ calls super().__init__(config) then sets engine attrs"

requirements-completed: [REF-02, REF-04]

# Metrics
duration: 18 min
completed: 2026-06-09
---

# Phase 12 Plan 02: Adopt base.py inheritance + delete dead constants Summary

**Database and AsyncDatabase collapsed onto (DatabaseBase, QueryMixin) — duplicated from_env/from_url/__repr__ deleted (now inherited), orphan *_SIMPLE SQL constants removed; net -73 lines, behavior preserved.**

## Performance

- **Duration:** 18 min
- **Started:** 2026-06-09 (inline execution)
- **Completed:** 2026-06-09
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- `class Database(DatabaseBase, QueryMixin)` and `class AsyncDatabase(DatabaseBase, QueryMixin)` — both now inherit the socle.
- Deleted the byte-identical concrete `from_env`/`from_url`/`__repr__` from both subclasses; they are now inherited. `cls(...)` resolution in the base factories returns the correct subclass; the base `__repr__` uses `self.__class__.__name__` so reprs are unchanged.
- Both `__init__` now call `super().__init__(config)` then set subclass-specific engine attrs. `async_engine` property and async `create` classmethod kept untouched.
- Removed `TABLE_INFO_SIMPLE` and `LIST_ROLES_SIMPLE` from `queries.py` (grep-proven dead; Phase-11 already routed async to the canonical rich-shape constants). Canonical `TABLE_INFO`/`LIST_ROLES` untouched.

## Task Commits

Each task was committed atomically:

1. **Task 1: Collapse Database + AsyncDatabase onto (DatabaseBase, QueryMixin)** - `404ebbb` (refactor)
2. **Task 2: Remove orphan *_SIMPLE constants from queries.py** - `4ab39d6` (refactor)

## Files Created/Modified
- `pycopg/database.py` - inherit (DatabaseBase, QueryMixin); delete concrete factories/__repr__; super().__init__(config)
- `pycopg/async_database.py` - same collapse; async_engine property + create classmethod preserved
- `pycopg/queries.py` - removed two orphan *_SIMPLE constants + their comments

## Decisions Made
- Concrete factories/repr deleted (not re-pointed) — inheritance now sole source. Factory smoke test confirms `Database.from_url(...)` → `Database(...)` repr and `AsyncDatabase.from_url(...)` → `AsyncDatabase(...)` repr (cls resolution intact).
- Pre-existing ruff errors (38, entirely in untouched files) NOT auto-fixed — out of plan scope (deviation scope boundary). Touched files (database.py, async_database.py, queries.py) all pass ruff cleanly.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

**Pre-existing (NOT caused by this plan) — flaky/environment DB test failures.** Three full-suite tests fail in this local DB environment and were verified to fail identically on the pre-12-02 base commit (`9ceca24`):
- `tests/test_parity.py::TestBehavioralParity::test_create_constructor_parity` — `ObjectInUse` during teardown `drop_database` (passes in isolation; lingering-session teardown race).
- `tests/test_integration.py::TestAsyncIntegration::test_async_transaction_fix` — `UndefinedTable`.
- `tests/test_postgis_errors.py::TestPostGISErrorHandling::test_create_spatial_index_name_parameter` — `UndefinedTable`.

These are isolation-/state-sensitive DB tests unrelated to the inheritance collapse or constant deletion (my changes touch only `from_env`/`from_url`/`__repr__`/`__init__` and two dead SQL constants — none of which these tests exercise). The targeted plan suites (`test_base`, `test_config`, `test_database`, `test_async_database`, `test_parity`) pass 352/352. Flagged for Phase 12-04 (coverage ratchet runs the full suite) and the phase verifier.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Subclasses inherit QueryMixin, so `_build_batch_insert_sql` is available for 12-03's batch INSERT wiring.
- base.py + queries.py are in final shape; 12-03 can wire inline SQL → `queries.*` and the batch builder.
- Pre-existing full-suite DB failures (3) should be triaged before/within 12-04's "measure then flip" coverage step.

---
*Phase: 12-refactoring-brancher-les-abstractions*
*Completed: 2026-06-09*
