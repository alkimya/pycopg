---
phase: 04-async-extensions-parity
plan: 02
subsystem: async-database
tags: [postgis, timescaledb, spatial-index, async-methods, extensions]
dependency_graph:
  requires:
    - "04-01 (async role management)"
    - "pycopg.utils.validate_interval"
  provides:
    - "AsyncDatabase.create_spatial_index"
    - "AsyncDatabase.list_geometry_columns"
    - "AsyncDatabase.create_hypertable"
    - "AsyncDatabase.enable_compression"
    - "AsyncDatabase.add_compression_policy"
    - "AsyncDatabase.add_retention_policy"
    - "AsyncDatabase.list_hypertables"
    - "AsyncDatabase.hypertable_info"
  affects:
    - "AsyncDatabase.from_geodataframe (now uses create_spatial_index)"
tech_stack:
  added: []
  patterns:
    - "async/await extension validation with RuntimeError"
    - "No extension validation for PostGIS methods (sync parity)"
key_files:
  created: []
  modified:
    - path: "pycopg/async_database.py"
      lines_added: 241
      lines_removed: 7
      description: "Added 8 PostGIS/TimescaleDB async methods + updated from_geodataframe"
    - path: "tests/test_async_database.py"
      lines_added: 281
      lines_removed: 0
      description: "Added 20 comprehensive tests for PostGIS and TimescaleDB methods"
decisions:
  - id: "ASYNC-19-20-21-22-23"
    summary: "Implement PostGIS and TimescaleDB async methods with exact sync parity"
    rationale: "Users expect same API surface in both sync and async"
    alternatives: []
  - id: "POSTGIS-NO-VALIDATION"
    summary: "PostGIS methods have no extension validation (matches sync Database)"
    rationale: "Consistency with sync implementation - PostGIS methods work without explicit validation"
    alternatives: []
  - id: "TIMESCALEDB-AWAIT-VALIDATION"
    summary: "TimescaleDB methods use await self.has_extension('timescaledb') with RuntimeError"
    rationale: "Async context requires await, maintains consistency with sync RuntimeError pattern"
    alternatives: []
  - id: "FROM-GEODATAFRAME-SPATIAL-INDEX"
    summary: "from_geodataframe now calls create_spatial_index instead of logging warning"
    rationale: "Fixes Phase 2 technical debt, makes from_geodataframe fully functional"
    alternatives: []
metrics:
  duration_minutes: 3.55
  tasks_completed: 2
  files_modified: 2
  tests_added: 20
  methods_added: 8
  completed_date: "2026-02-11"
---

# Phase 4 Plan 02: Async PostGIS and TimescaleDB Methods Summary

**One-liner:** Added 8 async PostGIS/TimescaleDB methods (create_spatial_index, list_geometry_columns, create_hypertable, enable_compression, add_compression_policy, add_retention_policy, list_hypertables, hypertable_info) with full sync parity and fixed from_geodataframe spatial indexing.

## Objectives Achieved

- [x] Added 8 async extension methods to AsyncDatabase matching sync Database signatures
- [x] All TimescaleDB methods validate extension with `await self.has_extension("timescaledb")` and raise RuntimeError
- [x] PostGIS methods have no extension validation (matches sync Database pattern)
- [x] Updated from_geodataframe to use create_spatial_index instead of logging warning
- [x] 20 comprehensive unit tests covering all methods, extension checks, and edge cases
- [x] All existing tests remain green (138/138 passing)

## Implementation Details

### Task 1: Add PostGIS and TimescaleDB Methods

**File:** `pycopg/async_database.py`

**Added imports:**
- `validate_interval` from `pycopg.utils`

**PostGIS methods (no extension validation):**
1. `async def create_spatial_index(table, column="geometry", schema="public", name=None)`
   - Creates GIST spatial index on geometry column
   - Auto-generates index name as `idx_{table}_{column}_gist` if not specified
   - No extension validation (matches sync)

2. `async def list_geometry_columns(schema=None)`
   - Queries `geometry_columns` view
   - Optional schema filter
   - Returns geometry column metadata (schema, table, column, dimensions, srid, type)

**TimescaleDB methods (all validate extension with await):**
3. `async def create_hypertable(table, time_column, schema="public", chunk_time_interval="1 day", if_not_exists=True, migrate_data=True)`
   - Converts table to TimescaleDB hypertable
   - Validates identifiers and interval
   - Extension check: `if not await self.has_extension("timescaledb"): raise RuntimeError`

4. `async def enable_compression(table, segment_by=None, order_by=None, schema="public")`
   - Enables compression on hypertable
   - Handles segment_by/order_by as str or list[str]
   - Validates each column name

5. `async def add_compression_policy(table, compress_after="7 days", schema="public")`
   - Adds automatic compression policy
   - Uses TimescaleDB's add_compression_policy function

6. `async def add_retention_policy(table, drop_after, schema="public")`
   - Adds automatic data retention policy
   - Uses TimescaleDB's add_retention_policy function

7. `async def list_hypertables()`
   - Queries `timescaledb_information.hypertables`
   - Returns hypertable metadata (schema, table, dimensions, chunks, compression)

8. `async def hypertable_info(table, schema="public")`
   - Queries hypertable_size and hypertable_detailed_size
   - Returns first result dict or empty dict

**Updated from_geodataframe:**
- Removed warning about create_spatial_index not being available
- Now calls `await self.create_spatial_index(table, geometry_column, schema)` when `spatial_index=True`
- Makes from_geodataframe fully functional, matching sync Database behavior

### Task 2: Add Unit Tests

**File:** `tests/test_async_database.py`

**New test classes:**

1. **TestAsyncDatabasePostGIS** (5 tests):
   - `test_create_spatial_index_basic` - Default index name generation
   - `test_create_spatial_index_custom_name` - Custom index name
   - `test_create_spatial_index_custom_schema` - Custom schema
   - `test_list_geometry_columns_all` - No schema filter
   - `test_list_geometry_columns_with_schema` - With schema filter

2. **TestAsyncDatabaseTimescaleDB** (14 tests):
   - `test_create_hypertable_basic` - Extension check + SQL generation
   - `test_create_hypertable_no_extension_raises` - RuntimeError on missing extension
   - `test_create_hypertable_custom_interval` - Custom chunk interval
   - `test_enable_compression_basic` - segment_by parameter
   - `test_enable_compression_with_order_by` - order_by parameter
   - `test_enable_compression_no_extension_raises` - RuntimeError
   - `test_add_compression_policy_basic` - Policy creation
   - `test_add_compression_policy_no_extension_raises` - RuntimeError
   - `test_add_retention_policy_basic` - Policy creation
   - `test_add_retention_policy_no_extension_raises` - RuntimeError
   - `test_list_hypertables_basic` - Query timescaledb_information
   - `test_list_hypertables_no_extension_raises` - RuntimeError
   - `test_hypertable_info_basic` - Size info retrieval
   - `test_hypertable_info_no_extension_raises` - RuntimeError

3. **Updated TestAsyncDatabaseGeoDataFrame:**
   - `test_from_geodataframe_with_spatial_index` - Verifies create_spatial_index is called
   - Fixed `test_from_geodataframe_basic` and `test_from_geodataframe_with_explicit_srid` to mock create_spatial_index

**Testing patterns:**
- Mock `db.has_extension = AsyncMock(return_value=True/False)` for extension checks
- Mock `db.execute = AsyncMock()` for SQL execution
- Verify SQL contains expected keywords and parameters
- Test both success paths and RuntimeError on missing extension

## Verification

All verification criteria met:

1. ✅ `python -c "from pycopg import AsyncDatabase"` - No import errors
2. ✅ `pytest tests/test_async_database.py -v` - All 138 tests pass (118 existing + 20 new)
3. ✅ All 8 methods exist: create_spatial_index, list_geometry_columns, create_hypertable, enable_compression, add_compression_policy, add_retention_policy, list_hypertables, hypertable_info
4. ✅ All TimescaleDB methods check `await self.has_extension("timescaledb")` and raise RuntimeError
5. ✅ PostGIS methods do NOT validate extension (matches sync Database)
6. ✅ from_geodataframe now calls create_spatial_index instead of logging warning

## Deviations from Plan

None - plan executed exactly as written.

## Success Criteria Met

- [x] AsyncDatabase has 8 new async PostGIS/TimescaleDB methods matching Database signatures
- [x] All TimescaleDB methods validate extension with `await self.has_extension("timescaledb")`
- [x] PostGIS methods have no extension validation (parity with sync Database)
- [x] from_geodataframe calls create_spatial_index when spatial_index=True
- [x] 20 unit tests covering all methods, extension checks, and edge cases pass
- [x] Existing tests remain green (138/138 passing)

## Self-Check

Verifying all claims:

### Created Files Check
No new files created (only modifications).

### Modified Files Check
```bash
[ -f "/home/loc/workspace/pycopg/pycopg/async_database.py" ] && echo "FOUND: pycopg/async_database.py" || echo "MISSING: pycopg/async_database.py"
[ -f "/home/loc/workspace/pycopg/tests/test_async_database.py" ] && echo "FOUND: tests/test_async_database.py" || echo "MISSING: tests/test_async_database.py"
```

### Commits Check
```bash
git log --oneline --all | grep -q "9aa5523" && echo "FOUND: 9aa5523 (Task 1)" || echo "MISSING: 9aa5523"
git log --oneline --all | grep -q "c6aeaf0" && echo "FOUND: c6aeaf0 (Task 2)" || echo "MISSING: c6aeaf0"
```

### Self-Check Results

All checks PASSED:
- ✅ FOUND: pycopg/async_database.py
- ✅ FOUND: tests/test_async_database.py
- ✅ FOUND: 9aa5523 (Task 1 commit)
- ✅ FOUND: c6aeaf0 (Task 2 commit)

## Self-Check: PASSED

## Next Steps

Continue to next plan in Phase 4 or move to Phase 5 according to ROADMAP.md.

## Notes

- **Technical debt resolved:** from_geodataframe spatial_index warning from Phase 2 is now fixed
- **Full parity achieved:** AsyncDatabase now has complete PostGIS and TimescaleDB support matching sync Database
- **Consistent patterns:** Extension validation follows established sync patterns (RuntimeError for TimescaleDB, no validation for PostGIS)
- **Test coverage:** 20 new tests provide comprehensive coverage of all methods and edge cases
