---
phase: 23
plan: "04"
subsystem: schema-accessor-alias-tests
tags: [testing, deprecation, schema-accessor, parity, migration]
dependency_graph:
  requires: ["23-01", "23-02", "23-03"]
  provides: [schema-alias-tests, parity-schema-pair, flat-call-migration, phase-gate]
  affects: [test_schema_aliases.py, test_parity.py, test_database.py, test_async_database.py, test_database_integration.py, test_integration.py, test_sql_injection.py, test_postgis_errors.py, test_spatial.py, timescale.py, etl.py]
tech_stack:
  added: []
  patterns: [DB-free MagicMock alias test pattern, _FakeSyncSchema/AsyncSchema stub pattern]
key_files:
  created:
    - tests/test_schema_aliases.py
  modified:
    - tests/test_parity.py
    - tests/test_database.py
    - tests/test_async_database.py
    - tests/test_database_integration.py
    - tests/test_integration.py
    - tests/test_sql_injection.py
    - tests/test_postgis_errors.py
    - tests/test_spatial.py
    - pycopg/timescale.py
    - pycopg/etl.py
decisions:
  - D-01 validated: exactly 27 schema methods in SchemaAccessor/AsyncSchemaAccessor
  - Rule 1 auto-fix: timescale.py + etl.py internal deprecated alias calls rewritten to accessor paths
  - _FakeSyncDb/_FakeAsyncDb/_RecordingSyncDb/_RecordingAsyncDb mocks extended with .schema stub attribute
metrics:
  duration: 45min
  completed: "2026-06-18"
---

# Phase 23 Plan 04: Schema Alias Tests & Full-Suite Gate Summary

**One-liner:** 54 DB-free MagicMock schema alias tests + parity pair registration + complete flat-call migration across 8 test files + -W error gate green at 1030 unit tests.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Create test_schema_aliases.py (27 sync + 27 async) | 9c03255 | tests/test_schema_aliases.py (206 lines) |
| 2 | Append SchemaAccessor pair to ACCESSOR_PAIRS | 1e3d46b | tests/test_parity.py |
| 3 | Migrate all flat schema/spatial call-sites | 0386655 | 10 files (8 test + 2 production) |
| 4 | Phase gates: full suite, -W error, count validation | (verification) | — |

## Verification Results

### Full Suite (uv run pytest)
- **3 failed** (all pre-existing flaky DB integration tests from STATE.md):
  - `test_async_transaction_fix` — UndefinedTable fixture isolation bug
  - `test_create_spatial_index_name_parameter` — PostGIS DB state race
  - `test_create_hypertable_requires_extension` — pre-existing integration env issue
- **1108 passed, 2 skipped**
- **Coverage: 95.61%** (gate: 94%) — PASSED

### -W error::DeprecationWarning Gate
- **1030 passed** (unit + mock tests, excluding known pre-existing flaky integration tests)
- psycopg_pool's own DeprecationWarning in pool stress/commit tests is third-party noise (pre-existing)
- All pycopg flat-alias call-sites: fully migrated

### D-01 Method Count Validation
- `SchemaAccessor`: 27 public methods — PASSED
- `AsyncSchemaAccessor`: 27 public methods — PASSED
- `SpatialAccessor`: includes `create_spatial_index` + `list_geometry_columns` — PASSED
- Total flat names covered: 29 (27 schema + 2 spatial)

### ACCESSOR_PAIRS Registry
- All 7 pairs registered including `(SchemaAccessor, AsyncSchemaAccessor)`
- `test_accessor_parity`: 24 passed — PASSED

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Internal deprecated alias calls in pycopg/timescale.py**
- **Found during:** Task 3 (-W error gate run)
- **Issue:** 12 occurrences of `self._db.has_extension(...)` inside `TimescaleAccessor`/`AsyncTimescaleAccessor` triggered DeprecationWarning under -W error (was fixed in prior session before compaction)
- **Fix:** Replaced all 12 with `self._db.schema.has_extension(...)`
- **Files modified:** `pycopg/timescale.py`
- **Commit:** 0386655

**2. [Rule 1 - Bug] Internal deprecated alias calls in pycopg/etl.py**
- **Found during:** Task 4 gate run
- **Issue:** 2 occurrences of `self._db.table_exists(...)` in `ETLRunner.run()` triggered DeprecationWarning under -W error
- **Fix:** Replaced with `self._db.schema.table_exists(...)`
- **Files modified:** `pycopg/etl.py`
- **Commit:** 0386655

**3. [Rule 1 - Bug] test_spatial.py mock stubs missing .schema attribute**
- **Found during:** Task 4 gate run
- **Issue:** `_FakeSyncDb`, `_FakeAsyncDb`, `_RecordingSyncDb`, `_RecordingAsyncDb` had no `.schema` attribute; `SpatialAccessor.__init__` / `AsyncSpatialAccessor._check_postgis` calls `db.schema.has_extension("postgis")` (changed in plan 03)
- **Fix:** Added `_FakeSyncSchema`, `_FakeAsyncSchema`, `_SyncSchemaStub`, `_AsyncSchemaStub` inner stubs; wired `.schema` into all four mock DB classes
- **Files modified:** `tests/test_spatial.py`
- **Commit:** 0386655

**4. [Rule 1 - Bug] test_postgis_errors.py flat spatial calls**
- **Found during:** Task 3 migration pass
- **Issue:** 4 `db.create_spatial_index()` + 2 `db.list_geometry_columns()` calls in integration test file
- **Fix:** Migrated to `db.spatial.create_spatial_index()` / `db.spatial.list_geometry_columns()`
- **Files modified:** `tests/test_postgis_errors.py`
- **Commit:** 0386655

## Known Stubs

None — all schema accessor methods are fully implemented with real SQL; test stubs are mock-injected DB-free test patterns, not production stubs.

## Threat Flags

None — this plan adds alias tests and migrates internal call-sites; no new network endpoints, auth paths, or schema changes at trust boundaries.

## Self-Check: PASSED

- `tests/test_schema_aliases.py` exists: FOUND
- Commits 9c03255, 1e3d46b, 0386655: FOUND in git log
- Coverage 95.61% >= 94%: PASSED
- 27 SchemaAccessor methods: VALIDATED
- 1030 unit tests green under -W error: PASSED
