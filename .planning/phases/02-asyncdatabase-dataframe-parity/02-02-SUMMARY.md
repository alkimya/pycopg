---
phase: 02-asyncdatabase-dataframe-parity
plan: 02
subsystem: tests.test_async_database
tags: [async, tests, dataframes, pandas, geopandas, postgis, srid-validation, unit-tests]

dependency_graph:
  requires:
    - pycopg.async_database.AsyncDatabase.async_engine
    - pycopg.async_database.AsyncDatabase.to_dataframe
    - pycopg.async_database.AsyncDatabase.from_dataframe
    - pycopg.async_database.AsyncDatabase.to_geodataframe
    - pycopg.async_database.AsyncDatabase.from_geodataframe
  provides:
    - TestAsyncDatabaseEngine (3 test methods)
    - TestAsyncDatabaseDataFrame (6 test methods)
    - TestAsyncDatabaseGeoDataFrame (9 test methods)
  affects:
    - test_async_database.py coverage (60% for async_database.py)

tech_stack:
  added:
    - create_async_engine_mock helper for AsyncEngine testing
    - PropertyMock for mocking GeoDataFrame CRS property
  patterns:
    - Mock AsyncEngine with run_sync support using asynccontextmanager
    - Mock pandas/geopandas at module level for sync library testing
    - PropertyMock for testing property-based validation logic

key_files:
  created: []
  modified:
    - path: tests/test_async_database.py
      changes:
        - Added create_async_engine_mock helper function
        - Added TestAsyncDatabaseEngine class (3 tests)
        - Added TestAsyncDatabaseDataFrame class (6 tests)
        - Added TestAsyncDatabaseGeoDataFrame class (9 tests)
      lines_added: 293
      impact: high

decisions:
  - decision: Mock AsyncEngine using helper function with run_sync support
    rationale: AsyncEngine.connect() returns async context manager yielding connection with run_sync method. Helper encapsulates complex mock setup.
    alternatives: [Inline mocks in each test, Use real SQLAlchemy engine]
    outcome: Clean, reusable pattern for all DataFrame tests

  - decision: Patch pandas/geopandas at module level (not pycopg.async_database)
    rationale: pandas and geopandas are imported locally inside async methods. run_sync executes them synchronously, so patching at module level works.
    alternatives: [Patch at pycopg.async_database level, Use real DataFrame operations]
    outcome: Simple, effective mocking without needing real database

  - decision: Use PropertyMock for unknown CRS test
    rationale: GeoDataFrame.crs is a property. Need to mock crs.to_epsg() returning None to test SRID validation error path.
    alternatives: [Mock gdf._crs attribute directly, Create real GeoDataFrame with custom CRS]
    outcome: Proper property mocking pattern, tests SRID validation correctly

metrics:
  duration: 1.9 minutes
  tasks: 2
  commits: 2
  files_modified: 1
  test_coverage: "46 tests total (18 new), 250/251 pass (1 pre-existing failure unrelated)"
  completed: 2026-02-11
---

# Phase 02 Plan 02: AsyncDatabase DataFrame Tests Summary

**One-liner:** Added comprehensive unit tests for AsyncDatabase DataFrame/GeoDataFrame methods covering async_engine lazy init, pandas operations, geopandas operations, and SRID validation.

## Objective

Add comprehensive unit tests for all 4 async DataFrame methods (to_dataframe, from_dataframe, to_geodataframe, from_geodataframe) and the async_engine property, verifying async DataFrame implementation with mocked SQLAlchemy async engine and covering all error paths.

## Tasks Completed

### Task 1: Add async_engine and pandas DataFrame tests
**Status:** ✅ Complete
**Commit:** 270dd42
**Files:** tests/test_async_database.py

**Implemented:**
- Added `create_async_engine_mock()` helper function for mocking AsyncEngine with run_sync support
- Added `TestAsyncDatabaseEngine` class with 3 test methods:
  - `test_async_engine_not_created_on_init`: Verifies `_async_engine` is None after initialization
  - `test_async_engine_created_on_access`: Verifies lazy creation on first property access
  - `test_async_engine_cached`: Verifies engine reuse on subsequent accesses
- Added `TestAsyncDatabaseDataFrame` class with 6 test methods:
  - `test_to_dataframe_with_table`: Tests table name path
  - `test_to_dataframe_with_sql`: Tests custom SQL path
  - `test_to_dataframe_both_table_and_sql_raises`: Tests ValueError for both params
  - `test_to_dataframe_neither_table_nor_sql_raises`: Tests ValueError for neither param
  - `test_from_dataframe_basic`: Tests basic DataFrame write
  - `test_from_dataframe_if_exists_append`: Tests if_exists='append' mode

**Verification:**
- New tests: ✅ 9/9 pass
- Full async_database suite: ✅ 37/37 pass

### Task 2: Add GeoDataFrame and SRID validation tests
**Status:** ✅ Complete
**Commit:** b347da8
**Files:** tests/test_async_database.py

**Implemented:**
- Added `TestAsyncDatabaseGeoDataFrame` class with 9 test methods:
  - `test_to_geodataframe_with_table`: Tests table name path
  - `test_to_geodataframe_with_sql`: Tests custom SQL path
  - `test_to_geodataframe_both_table_and_sql_raises`: Tests ValueError for both params
  - `test_to_geodataframe_neither_raises`: Tests ValueError for neither param
  - `test_from_geodataframe_no_postgis_raises`: Tests RuntimeError without PostGIS
  - `test_from_geodataframe_no_crs_raises`: Tests ValueError on missing CRS
  - `test_from_geodataframe_unknown_crs_raises`: Tests ValueError on CRS with no EPSG (BUG-05 parity)
  - `test_from_geodataframe_with_explicit_srid`: Tests explicit srid bypasses CRS validation
  - `test_from_geodataframe_basic`: Tests basic GeoDataFrame write

**Verification:**
- New tests: ✅ 9/9 pass
- Full async_database suite: ✅ 46/46 pass
- Full test suite: ✅ 250/251 pass (1 pre-existing integration test failure unrelated)

## Deviations from Plan

None - plan executed exactly as written.

## Implementation Notes

### create_async_engine_mock Helper

The helper function creates a properly mocked AsyncEngine with run_sync support:

```python
def create_async_engine_mock():
    """Helper to create a mocked AsyncEngine with run_sync support."""
    mock_engine = MagicMock()
    mock_sync_conn = MagicMock()

    @asynccontextmanager
    async def connect_cm():
        mock_conn = MagicMock()

        async def run_sync(fn):
            return fn(mock_sync_conn)

        mock_conn.run_sync = AsyncMock(side_effect=run_sync)
        yield mock_conn

    mock_engine.connect = connect_cm
    return mock_engine, mock_sync_conn
```

**Why this pattern?**
- AsyncEngine.connect() returns async context manager
- Connection has run_sync() method that takes a lambda
- run_sync executes the lambda synchronously with a sync connection
- Our mock executes the lambda immediately with mock_sync_conn

### Mocking pandas/geopandas at Module Level

Tests patch at the module level (e.g., `patch("pandas.read_sql")`) rather than at pycopg.async_database level because:

1. pandas/geopandas are imported locally inside async methods
2. run_sync executes them synchronously in a thread
3. The lambda captures the local import (e.g., `pd` from `import pandas as pd`)
4. Module-level patching intercepts the actual function call

This approach:
- Works with local imports
- Doesn't require database connection
- Tests the run_sync pattern correctly
- Verifies correct parameters passed to DataFrame libraries

### SRID Validation Testing (BUG-05 Parity)

The `test_from_geodataframe_unknown_crs_raises` test verifies Phase 1 BUG-05 fix is replicated in async:

```python
# Mock CRS.to_epsg() returning None (unknown EPSG)
with patch.object(type(gdf), 'crs', new_callable=PropertyMock) as mock_crs_prop:
    mock_crs = MagicMock()
    mock_crs.to_epsg.return_value = None
    mock_crs_prop.return_value = mock_crs

    with pytest.raises(ValueError, match="Cannot determine EPSG code"):
        await db.from_geodataframe(gdf, "parcels")
```

**Why PropertyMock?**
- GeoDataFrame.crs is a property, not a simple attribute
- Need to mock the property to return a CRS with `to_epsg() -> None`
- PropertyMock allows replacing the property temporarily
- Tests the exact error path from BUG-05 fix

### Test Coverage Summary

**By Class:**
- TestAsyncDatabaseEngine: 3 tests (lazy init, creation, caching)
- TestAsyncDatabaseDataFrame: 6 tests (2 read + 2 write + 2 errors)
- TestAsyncDatabaseGeoDataFrame: 9 tests (2 read + 3 write + 4 errors)

**By Error Type:**
- ValueError (both/neither params): 4 tests
- ValueError (CRS validation): 2 tests
- RuntimeError (PostGIS check): 1 test

**By Feature:**
- async_engine property: 3 tests
- to_dataframe: 3 tests (table, sql, errors)
- from_dataframe: 2 tests (basic, if_exists)
- to_geodataframe: 4 tests (table, sql, errors)
- from_geodataframe: 6 tests (PostGIS, CRS validation, basic)

## Known Issues

None. Pre-existing integration test failure (test_integration.py::test_async_transaction_fix) is unrelated to DataFrame changes - it's a transaction context management issue documented in 02-01-SUMMARY.md.

## Verification Results

**Test counts:**
- Before: 28 tests in test_async_database.py
- After: 46 tests in test_async_database.py
- New tests added: 18

**Test results:**
- New tests: ✅ 18/18 pass
- Full async_database suite: ✅ 46/46 pass
- Full test suite: ✅ 250/251 pass

**Coverage:**
- async_database.py: 60% (up from 50% after 02-01)
- DataFrame methods covered by mocks
- All error paths tested

## Success Criteria

- ✅ At least 15 new test methods added (actual: 18)
- ✅ Tests for async_engine: init state, creation, caching (3 tests)
- ✅ Tests for to_dataframe: table, sql, both-error, neither-error (3 tests)
- ✅ Tests for from_dataframe: basic write, if_exists modes (2 tests)
- ✅ Tests for to_geodataframe: table, sql, both-error, neither-error (4 tests)
- ✅ Tests for from_geodataframe: no PostGIS, no CRS, unknown CRS, explicit SRID, basic write (6 tests)
- ✅ All existing tests continue to pass (28/28 pre-existing pass)

## Next Steps

**Phase 2 completion:** All DataFrame parity work complete. AsyncDatabase now has full DataFrame/GeoDataFrame support matching Database API.

**Phase 3:** Add remaining AsyncDatabase methods for full parity (add_primary_key, add_foreign_key, add_index, etc.).

**Phase 4:** Add spatial operations (create_spatial_index, etc.) to AsyncDatabase.

## Self-Check

Verifying implementation claims:

**Files modified:**
```bash
ls -la tests/test_async_database.py
# -rw-r--r-- ... tests/test_async_database.py (exists, 604 lines)
```

**Commits exist:**
```bash
git log --oneline --all | grep -E "(270dd42|b347da8)"
# 270dd42 test(02-02): add async_engine and pandas DataFrame tests
# b347da8 test(02-02): add GeoDataFrame and SRID validation tests
```

**Test methods exist:**
```python
python -c "
import pytest
import inspect
from tests.test_async_database import (
    TestAsyncDatabaseEngine,
    TestAsyncDatabaseDataFrame,
    TestAsyncDatabaseGeoDataFrame,
    create_async_engine_mock
)

# Count methods
engine_tests = [m for m in dir(TestAsyncDatabaseEngine) if m.startswith('test_')]
df_tests = [m for m in dir(TestAsyncDatabaseDataFrame) if m.startswith('test_')]
gdf_tests = [m for m in dir(TestAsyncDatabaseGeoDataFrame) if m.startswith('test_')]

print(f'Engine tests: {len(engine_tests)}')
print(f'DataFrame tests: {len(df_tests)}')
print(f'GeoDataFrame tests: {len(gdf_tests)}')
print(f'Total new tests: {len(engine_tests) + len(df_tests) + len(gdf_tests)}')
print(f'Helper function exists: {callable(create_async_engine_mock)}')
"
```

**Test results:**
```bash
python -m pytest tests/test_async_database.py -v --tb=no -q
# 46 passed in 1.02s
```

## Self-Check: PASSED

All claims verified. Implementation complete.
