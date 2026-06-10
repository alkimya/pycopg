---
phase: 13-qualit-documentaire-docstrings-numpydoc-interrogate
plan: "02"
subsystem: exceptions
tags: [exceptions, pycopg-exceptions, type-safety, mypy, async]
dependency_graph:
  requires:
    - phase: 13-01
      provides: "DatabaseExists exception type + pycopg.exceptions foundation"
  provides:
    - "14 raise ExtensionNotAvailable sites: 7 in database.py + 7 in async_database.py"
    - "2 raise DatabaseExists sites: 1 in database.py + 1 in async_database.py"
    - "async_engine property annotated -> AsyncEngine via TYPE_CHECKING guard"
    - "Tests updated to assert new exception types (D-04)"
  affects:
    - pycopg/database.py
    - pycopg/async_database.py
    - tests/test_database_integration.py
    - tests/test_async_database.py
tech_stack:
  added: []
  patterns:
    - "TYPE_CHECKING guard for AsyncEngine annotation in async_database.py"
    - "Domain exception types raised at extension-check and DB-exists sites"
key_files:
  created: []
  modified:
    - pycopg/database.py (DatabaseExists + ExtensionNotAvailable imports + 7 raise conversions)
    - pycopg/async_database.py (same + async_engine annotation + _async_engine type)
    - tests/test_database_integration.py (ExtensionNotAvailable import + 1 assertion updated)
    - tests/test_async_database.py (ExtensionNotAvailable/DatabaseExists import + 7 assertions updated)
key_decisions:
  - "7 ExtensionNotAvailable raises in database.py (not 6): PostGIS from_geodataframe + 6 TimescaleDB methods — plan text had a typo ('6 sites') but the enumeration listed 7; research inventory confirmed 7 per file"
  - "Session-mode RuntimeError and subprocess RuntimeErrors left unchanged per D-01"
  - "AsyncEngine imported under TYPE_CHECKING to preserve lazy create_async_engine import inside method body (Pitfall 5)"
requirements-completed: [DOC-09, DOC-12]

# Metrics
duration: ~8min
completed: "2026-06-10"
---

# Phase 13 Plan 02: Domain Exception Conversion Summary

**14 RuntimeError/ValueError raises converted to ExtensionNotAvailable/DatabaseExists at inventoried domain sites; async_engine property annotated with AsyncEngine return type via TYPE_CHECKING guard.**

## Performance

- **Duration:** ~8 minutes
- **Started:** 2026-06-10T11:35:00Z
- **Completed:** 2026-06-10T11:43:00Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Added `from pycopg.exceptions import DatabaseExists, ExtensionNotAvailable` to both database.py and async_database.py (neither had any pycopg.exceptions import before)
- Converted all 7 extension-check sites in database.py (1 PostGIS + 6 TimescaleDB) from `RuntimeError` to `ExtensionNotAvailable`, messages preserved verbatim
- Converted 1 `ValueError("Database already exists")` in database.py to `DatabaseExists`
- Converted all 7 extension-check sites in async_database.py (same set of methods, same messages)
- Converted 1 `ValueError("Database already exists")` in async_database.py to `DatabaseExists`
- Annotated `async_engine` property with `-> AsyncEngine` and `self._async_engine: AsyncEngine | None = None`; `AsyncEngine` imported under `if TYPE_CHECKING:` (no runtime import, no circular import)
- Updated 1 test assertion in test_database_integration.py and 7 test assertions in test_async_database.py (D-04); all targeted tests pass (30 passed)

## Task Commits

Each task was committed atomically:

1. **Task 1: database.py domain exception conversion + test update** - `a155a1d` (fix)
2. **Task 2: async_database.py domain exception conversion + async_engine annotation + test update** - `f3c5e58` (fix)

**Plan metadata:** (docs commit — see below)

## Files Created/Modified

- `/home/loc/workspace/pycopg/pycopg/database.py` — Added `from pycopg.exceptions import DatabaseExists, ExtensionNotAvailable`; 7 raise site conversions (lines ~167, ~1370, ~1524, ~1560, ~1607, ~1638, ~1657, ~1675)
- `/home/loc/workspace/pycopg/pycopg/async_database.py` — Same import added; AsyncEngine TYPE_CHECKING guard added; async_engine annotated; _async_engine typed; 7 raise site conversions (lines ~160, ~1077, ~1113, ~1160, ~1191, ~1210, ~1228, ~1805)
- `/home/loc/workspace/pycopg/tests/test_database_integration.py` — Added exceptions import; line ~869 assertion updated to ExtensionNotAvailable
- `/home/loc/workspace/pycopg/tests/test_async_database.py` — Added ExtensionNotAvailable/DatabaseExists to exceptions import; 7 assertions updated

## Decisions Made

- Plan acceptance criteria said `grep -c "raise ExtensionNotAvailable" pycopg/database.py` = 6, but the plan's own enumeration listed 7 methods (from_geodataframe + 6 TimescaleDB) and the research inventory explicitly said "Total: 14 sites — 7 in database.py, 7 in async_database.py." Implemented 7 per file (14 total) as specified by the research inventory — this is a plan text typo, not a deviation.
- Session-mode `RuntimeError("Already in session mode")` and subprocess `RuntimeError("pg_dump/pg_restore/psql ... failed")` explicitly preserved (D-01).
- CRS/SRID `ValueError`s and API-misuse `ValueError`s explicitly preserved (D-01).

## Deviations from Plan

None - plan executed exactly as written (the count discrepancy in acceptance criteria vs inventory was a plan text typo; research inventory used as the authoritative source).

## Known Stubs

None — no stub values or placeholder data introduced in this plan.

## Threat Flags

None — exception message text is preserved verbatim; only Python types change (T-13-02-01 accepted). No new network endpoints, auth paths, or schema changes.

## Self-Check

### Self-Check: PASSED

- FOUND: /home/loc/workspace/pycopg/.planning/phases/13-qualit-documentaire-docstrings-numpydoc-interrogate/13-02-SUMMARY.md
- FOUND commit a155a1d (Task 1: database.py conversion)
- FOUND commit f3c5e58 (Task 2: async_database.py conversion + async_engine annotation)
- VERIFIED: `grep -c "raise ExtensionNotAvailable" pycopg/database.py` = 7
- VERIFIED: `grep -c "raise ExtensionNotAvailable" pycopg/async_database.py` = 7
- VERIFIED: `grep -c "raise DatabaseExists" pycopg/database.py` = 1
- VERIFIED: `grep -c "raise DatabaseExists" pycopg/async_database.py` = 1
- VERIFIED: `grep -c "def async_engine(self) -> AsyncEngine" pycopg/async_database.py` = 1
- VERIFIED: `uv run python -c "import pycopg.async_database"` raises no import error
- VERIFIED: 30 targeted tests passed (0 failures)
