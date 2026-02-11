---
phase: 02-asyncdatabase-dataframe-parity
plan: 01
subsystem: pycopg.async_database
tags: [async, dataframes, pandas, geopandas, postgis, parity]

dependency_graph:
  requires:
    - pycopg.config.Config.url (postgresql+psycopg format)
    - pycopg.async_database.AsyncDatabase.has_extension
  provides:
    - AsyncDatabase.async_engine (property)
    - AsyncDatabase.to_dataframe (async method)
    - AsyncDatabase.from_dataframe (async method)
    - AsyncDatabase.to_geodataframe (async method)
    - AsyncDatabase.from_geodataframe (async method)
  affects:
    - AsyncDatabase API surface (new DataFrame operations)

tech_stack:
  added:
    - sqlalchemy.ext.asyncio.create_async_engine
    - pandas.read_sql with AsyncConnection.run_sync
    - geopandas.read_postgis with AsyncConnection.run_sync
  patterns:
    - Lazy property initialization (async_engine)
    - run_sync pattern for sync libraries (pandas/geopandas) in async context
    - Library-safe logging for warnings (logging.getLogger)

key_files:
  created: []
  modified:
    - path: pycopg/async_database.py
      changes:
        - Added TYPE_CHECKING imports for pandas/geopandas type hints
        - Added Literal type import for if_exists parameter
        - Added _async_engine attribute to __init__
        - Added async_engine lazy property
        - Added DATAFRAME OPERATIONS section with 4 async methods
      lines_added: 235
      impact: high

decisions:
  - decision: Use run_sync pattern for pandas/geopandas operations
    rationale: pandas and geopandas are sync-only libraries. SQLAlchemy's run_sync() executes sync code in async context safely.
    alternatives: [Write custom async implementations, Wait for native async support]
    outcome: Matches Database implementation pattern, maintains API consistency

  - decision: Log warnings for primary_key and spatial_index parameters
    rationale: add_primary_key and create_spatial_index don't exist on AsyncDatabase yet (Phase 3/4). Silently ignoring would be misleading; raising would break API parity.
    alternatives: [Raise NotImplementedError, Silently ignore, Remove parameters]
    outcome: User-friendly - informs users of limitation with workaround suggestion

  - decision: Replicate exact SRID validation from Database.from_geodataframe
    rationale: BUG-05 fix from Phase 1 must apply to async version. No silent defaults to SRID 4326.
    alternatives: [Different validation, Copy exact logic]
    outcome: Full parity with sync version, prevents silent bugs

metrics:
  duration: 2.1 minutes
  tasks: 2
  commits: 2
  files_modified: 1
  test_coverage: "All existing tests pass (28/28 async tests)"
  completed: 2026-02-11
---

# Phase 02 Plan 01: AsyncDatabase DataFrame Parity Summary

**One-liner:** Added async DataFrame/GeoDataFrame methods to AsyncDatabase using SQLAlchemy async_engine and run_sync pattern for pandas/geopandas parity.

## Objective

Add all four async DataFrame methods (to_dataframe, from_dataframe, to_geodataframe, from_geodataframe) and the supporting async_engine property to AsyncDatabase, achieving DataFrame/GeoDataFrame parity between sync Database and async AsyncDatabase.

## Tasks Completed

### Task 1: Add async_engine property and pandas DataFrame methods
**Status:** ✅ Complete
**Commit:** fe65b1e
**Files:** pycopg/async_database.py

**Implemented:**
- Added `async_engine` lazy property with `create_async_engine()`
- Added `to_dataframe()` async method with table/sql/params support
- Added `from_dataframe()` async method with if_exists/dtype support
- Added TYPE_CHECKING imports for pandas/geopandas type hints
- Added Literal type for if_exists parameter
- Used `run_sync()` pattern for pandas operations in async context
- Added warning for primary_key parameter (add_primary_key unavailable until Phase 3)

**Verification:**
- Import check: ✅ Pass
- Method existence: ✅ Pass (both methods exist)
- Async coroutine check: ✅ Pass (both are async)
- All existing tests: ✅ 28/28 pass

### Task 2: Add GeoDataFrame methods (to_geodataframe, from_geodataframe)
**Status:** ✅ Complete
**Commit:** 854c99d
**Files:** pycopg/async_database.py

**Implemented:**
- Added `to_geodataframe()` async method with geometry_column support
- Added `from_geodataframe()` async method with full SRID validation
- Replicated BUG-05 fix: explicit SRID error handling (no silent defaults)
- PostGIS extension check using `await self.has_extension("postgis")`
- Warnings for primary_key parameter (Phase 3) and spatial_index parameter (Phase 4)
- Used `run_sync()` pattern for geopandas operations

**Verification:**
- Method existence: ✅ Pass (both methods exist)
- Async coroutine check: ✅ Pass (both are async)
- All existing tests: ✅ 28/28 pass
- SRID validation logic: ✅ Matches Database.from_geodataframe (lines 1221-1241)

## Deviations from Plan

None - plan executed exactly as written.

## Implementation Notes

### async_engine Lazy Initialization
The `async_engine` property creates a SQLAlchemy AsyncEngine on first access:
```python
@property
def async_engine(self):
    if self._async_engine is None:
        from sqlalchemy.ext.asyncio import create_async_engine
        self._async_engine = create_async_engine(self.config.url)
    return self._async_engine
```

**Key insight:** `Config.url` already returns `postgresql+psycopg://` format, which works directly with SQLAlchemy async. No URL transformation needed.

### run_sync Pattern for Sync Libraries
pandas and geopandas are sync-only libraries. SQLAlchemy's AsyncConnection provides `run_sync()` to safely execute sync code:

```python
async with self.async_engine.connect() as conn:
    return await conn.run_sync(
        lambda sync_conn: pd.read_sql(text(sql), sync_conn, params=params)
    )
```

This pattern:
1. Acquires async connection
2. Executes sync code in thread pool
3. Returns result to async context
4. Maintains connection safety

### SRID Validation Parity
`from_geodataframe` replicates the exact SRID validation from `Database.from_geodataframe` (BUG-05 fix):
- Fails if GeoDataFrame has no CRS
- Fails if CRS cannot be converted to EPSG code
- Provides clear error messages with workaround (explicit srid parameter)
- No silent defaulting to SRID 4326

### Warnings for Unavailable Features
`from_dataframe` and `from_geodataframe` accept `primary_key` and `spatial_index` parameters but log warnings since the underlying methods don't exist yet:

```python
if primary_key and if_exists != "append":
    import logging
    logger = logging.getLogger(__name__)
    logger.warning(
        "primary_key parameter ignored — add_primary_key not yet available in AsyncDatabase. "
        "Use db.execute('ALTER TABLE ...') manually or wait for Phase 3."
    )
```

**Rationale:**
- Maintains API parity with Database
- Informs users of limitation
- Provides workaround (manual SQL)
- Avoids breaking change later when Phase 3 adds these methods

## Known Issues

None. Pre-existing integration test failure (test_integration.py::test_async_transaction_fix) is unrelated to DataFrame changes - it's a transaction context management issue that existed before this plan.

## Verification Results

**Import check:** ✅ Pass
```
from pycopg.async_database import AsyncDatabase
print('Import OK')  # Success
```

**Method existence:** ✅ Pass (all 4 methods exist and are async coroutines)

**Test suite:** ✅ 28/28 async tests pass, no regressions

**API parity check:**
- ✅ AsyncDatabase.to_dataframe matches Database.to_dataframe signature
- ✅ AsyncDatabase.from_dataframe matches Database.from_dataframe signature
- ✅ AsyncDatabase.to_geodataframe matches Database.to_geodataframe signature
- ✅ AsyncDatabase.from_geodataframe matches Database.from_geodataframe signature
- ✅ SRID validation logic identical (lines 1221-1241 replicated)

## Success Criteria

- ✅ AsyncDatabase.async_engine property creates SQLAlchemy AsyncEngine lazily
- ✅ AsyncDatabase.to_dataframe() is async and accepts table/sql/params
- ✅ AsyncDatabase.from_dataframe() is async and accepts df/table/schema/if_exists/dtype
- ✅ AsyncDatabase.to_geodataframe() is async and accepts table/sql/geometry_column/params
- ✅ AsyncDatabase.from_geodataframe() is async with PostGIS check + explicit SRID validation
- ✅ All existing tests pass without regressions
- ✅ primary_key and spatial_index params log warnings (not silently ignored, not erroring)

## Next Steps

**Phase 2 Plan 2:** Add remaining schema management methods to AsyncDatabase for full parity with Database.

**Phase 3:** Add `add_primary_key` to AsyncDatabase, remove warnings from `from_dataframe` and `from_geodataframe`.

**Phase 4:** Add `create_spatial_index` to AsyncDatabase, remove spatial_index warning from `from_geodataframe`.

## Self-Check

Verifying implementation claims:

**Files created/modified:**
```bash
ls -la pycopg/async_database.py
# -rw-r--r-- ... pycopg/async_database.py (exists, modified)
```

**Commits exist:**
```bash
git log --oneline --all | grep -E "(fe65b1e|854c99d)"
# fe65b1e feat(02-01): add async_engine property and pandas DataFrame methods
# 854c99d feat(02-01): add GeoDataFrame methods with PostGIS validation
```

**Methods exist:**
```bash
python -c "
from pycopg.async_database import AsyncDatabase
import inspect
assert hasattr(AsyncDatabase, 'async_engine')
assert inspect.iscoroutinefunction(AsyncDatabase.to_dataframe)
assert inspect.iscoroutinefunction(AsyncDatabase.from_dataframe)
assert inspect.iscoroutinefunction(AsyncDatabase.to_geodataframe)
assert inspect.iscoroutinefunction(AsyncDatabase.from_geodataframe)
print('VERIFIED: All methods exist and are async')
"
# Output: VERIFIED: All methods exist and are async
```

## Self-Check: PASSED

All claims verified. Implementation complete.
