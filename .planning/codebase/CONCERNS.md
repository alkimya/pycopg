# Codebase Concerns

**Analysis Date:** 2026-02-11

## Tech Debt

**Missing DataFrame methods in AsyncDatabase:**
- Issue: The async version lacks `to_dataframe()`, `from_dataframe()`, `to_geodataframe()`, and `from_geodataframe()` methods that exist in sync Database
- Files: `pycopg/async_database.py` vs `pycopg/database.py` (lines 1105-1262)
- Impact: Users cannot use async context with DataFrame operations, limiting use in async pipelines
- Fix approach: Implement async versions of DataFrame methods in AsyncDatabase, or clearly document this as a deliberate limitation with workarounds

**Missing backup/restore in AsyncDatabase:**
- Issue: Methods `pg_dump()`, `pg_restore()`, `copy_to_csv()`, `copy_from_csv()` only exist in sync Database
- Files: `pycopg/database.py` (lines 1976-2285), not in `pycopg/async_database.py`
- Impact: Async users cannot perform backups/restores without switching to sync code
- Fix approach: Add async wrappers or document that these operations must use sync interface

**Missing extensive admin methods in AsyncDatabase:**
- Issue: Role management, privilege management, extensions, and constraint operations have limited coverage in async version
- Files: `pycopg/database.py` (lines 1607-1933 for roles/privileges, 640-695 for extensions), minimal in `pycopg/async_database.py`
- Impact: AsyncDatabase is significantly less featured than Database, creating inconsistent API
- Fix approach: Complete feature parity or publish comparison matrix in documentation

## Known Bugs

**Session mode transaction handling potential issue:**
- Issue: In `database.py` line 281-282, cursor is committed if `transaction_status == IDLE`. However, session mode may have implicit transactions that aren't detected
- Files: `pycopg/database.py` (lines 278-288) and `pycopg/async_database.py` (lines 118-128)
- Trigger: When using cursor within session but not in explicit transaction context
- Workaround: Use explicit `with db.transaction()` instead of relying on implicit commit in session mode

**Migration file parsing is silent on errors:**
- Issue: In `migrations.py` line 152, `except MigrationError: continue` silently skips invalid migration files without logging
- Files: `pycopg/migrations.py` (lines 145-154)
- Trigger: User creates a SQL file that doesn't match pattern (e.g., "001-create_users.sql" with dash instead of underscore)
- Workaround: Check migration directory listing directly; no indication file was skipped
- Fix approach: Log skipped files at debug level or raise warning

## Security Considerations

**SQL Identifier validation could be bypassed with quoted identifiers:**
- Risk: PostgreSQL allows quoted identifiers with special characters (e.g., `"table!name"`) which pass through current validation in `utils.py` line 44
- Files: `pycopg/utils.py` (lines 21-49), used throughout `database.py` and `async_database.py`
- Current mitigation: Regex pattern `_IDENTIFIER_PATTERN` rejects non-alphanumeric (except underscore), so quoted identifiers cannot be injected
- Recommendations: Document this design choice; consider adding separate `quote_identifier()` function for applications needing special characters

**Password exposed in URL/DSN generation:**
- Risk: Config's `url` property (line 193) and `dsn` property (line 177) include plaintext passwords
- Files: `pycopg/config.py` (lines 156-177, 180-196)
- Current mitigation: Passwords only visible to code that directly accesses these properties; typically not logged
- Recommendations: Add warning in docstrings about not logging or printing connection strings; consider mask_password parameter

**Subprocess password handling in pg_dump/pg_restore:**
- Risk: Password passed via environment variable `PGPASSWORD` to subprocess in `database.py` lines 2057-2058
- Files: `pycopg/database.py` (lines 2017-2061, 2105-2156, 2158-2175)
- Current mitigation: Merged into subprocess environment, not visible in process arguments; standard PostgreSQL approach
- Recommendations: Document security implications; consider warning if password is empty or weak

## Performance Bottlenecks

**Large Database class is monolithic:**
- Problem: `database.py` is 2,299 lines covering DDL, DML, admin, backup, spatial, timescale - difficult to navigate and test
- Files: `pycopg/database.py`
- Cause: Everything is in one class rather than split into mixins or separate classes
- Improvement path: Refactor using composition or multiple classes (AdminDatabase, BackupDatabase, SpatialDatabase, etc.) - requires major restructuring

**Missing connection pooling defaults guidance:**
- Problem: Pool sizes (min=2, max=10) may be too small for production or too large for development
- Files: `pycopg/pool.py` (lines 46-74, 248-280)
- Cause: Generic defaults don't account for workload characteristics
- Improvement path: Add pool sizing guidelines in documentation; consider workload profiling helper

**No query timeout configuration:**
- Problem: Long-running queries can hang indefinitely; no statement timeout support exposed
- Files: All execute methods (database.py, async_database.py, pool.py)
- Cause: psycopg timeout is per-connection, not per-query; would require connection pool modification
- Improvement path: Add `statement_timeout` parameter to Config; set via `SET statement_timeout` at connection creation

**Insert batch size hardcoded to 1000:**
- Problem: Optimal batch size depends on row size and network latency; 1000 may cause memory issues for large rows
- Files: `pycopg/database.py` line 414, `pycopg/async_database.py` line 265
- Cause: Default chosen without guidance for tuning
- Improvement path: Add documentation with tuning examples; consider auto-detecting based on average row size

## Fragile Areas

**Migrations directory state assumptions:**
- Files: `pycopg/migrations.py`
- Why fragile:
  - `_get_migrations()` (line 145) silently skips invalid files instead of warning
  - No atomic rollback - if rollback fails halfway, database is inconsistent
  - Manual migration file deletion causes version sequence gaps without detection
- Safe modification: Validate all migration files exist before starting migrate/rollback; fail fast on gaps
- Test coverage: `tests/test_migrations.py` (467 lines) covers basic flow but not edge cases like:
  - Interrupted rollback recovery
  - Version number collisions
  - Missing migration files for applied versions

**Session mode connection lifetime:**
- Files: `pycopg/database.py` lines 310-353, `pycopg/async_database.py` lines 131-174
- Why fragile:
  - `_session_conn` is set to None only on successful exit
  - If exception occurs during cleanup (line 352), `_session_conn` stays alive, leaking connection on retry
  - No context reentry protection beyond RuntimeError at line 341
- Safe modification: Use try/finally to guarantee cleanup; add timeout for idle session connections
- Test coverage: `tests/test_database.py` has session tests but not exception-during-cleanup scenario

**TimescaleDB operations without extension check:**
- Files: `pycopg/database.py` lines 1314-1437
- Why fragile:
  - `create_hypertable()` checks for extension (line 1338) but intermediate functions like `enable_compression()` (line 1354) assume it exists
  - If user calls compression before hypertable creation, error is cryptic
- Safe modification: Add pre-condition assertions for all timescaledb functions
- Test coverage: Tests assume extension is available; no test for missing extension graceful handling

**GeoDataFrame SRID inference:**
- Files: `pycopg/database.py` lines 1208-1213
- Why fragile:
  - If `gdf.crs.to_epsg()` fails (line 1211), defaults to WGS84 (4326) silently
  - Spatial data with wrong SRID can cause subtle bugs in analysis
- Safe modification: Raise error if SRID cannot be determined and not explicitly provided; never silently default
- Test coverage: No test coverage for SRID edge cases (invalid CRS, missing CRS)

## Scaling Limits

**Connection pool max_size not adaptive:**
- Current capacity: Fixed at initialization (default 10)
- Limit: Workload spikes cause connection timeout; pool cannot grow beyond max
- Scaling path: Implement dynamic pool sizing based on queue depth; expose `resize()` method usage in load handling examples

**Large CSV imports via copy_from_csv:**
- Current capacity: File read in 8KB chunks (line 2281) - fine, but entire file buffered in cursor
- Limit: Multi-GB CSV files may cause memory issues; no streaming with backpressure
- Scaling path: Implement CSV streaming with error handling; consider chunking CSV files before import

**No query result streaming:**
- Current capacity: `fetchall()` returns entire result set in memory
- Limit: SELECT * on 100M+ row tables crashes with OOM
- Scaling path: Add cursor iteration support; implement streaming API for large result sets

## Dependencies at Risk

**sqlalchemy>=2.0.0 is heavyweight for DataFrame-only users:**
- Risk: Large dependency footprint (38 packages) for users who only need to_dataframe()
- Impact: Increases installation time and security surface area
- Alternative: Make SQLAlchemy optional for core operations; only require for DataFrame methods

**pandas>=2.0.0 is large dependency:**
- Risk: Adds 600MB to environment; users may want sync-only without pandas
- Impact: Forces inclusion even for users not using DataFrame methods
- Alternative: Move pandas/geopandas to optional extras completely; raise helpful error if used without install

**geopandas and geoalchemy2 may have conflicting PostGIS versions:**
- Risk: Different PostGIS versions installed locally vs in database can cause mismatch errors
- Impact: Subtle spatial data corruption if SRID or geometry format mismatches
- Alternative: Add version compatibility matrix in documentation; implement version checking at runtime

## Missing Critical Features

**No retry/backoff for transient connection errors:**
- Problem: Single connection failure causes entire operation to fail
- Blocks: Building resilient applications; requires users to implement retry logic
- Solution path: Add `retry_policy` parameter to Database; implement exponential backoff for transient errors

**No query result caching:**
- Problem: Repeated identical queries hit database each time
- Blocks: Optimization for frequently repeated queries; read-only workloads
- Solution path: Add optional query cache with TTL; consider redis backend

**No named parameters support:**
- Problem: Only positional %s placeholders supported; Python dict unpacking not intuitive
- Blocks: Converting from SQLAlchemy ORM with named parameters
- Solution path: Implement named parameter support using :name syntax; convert to positional %s internally

**No computed column or virtual column support:**
- Problem: Cannot create stored expressions in database
- Blocks: Advanced schema design patterns
- Solution path: Add helper methods for computed column creation; document usage patterns

## Test Coverage Gaps

**AsyncDatabase feature parity gaps:**
- What's not tested: DataFrame methods (`from_dataframe`, etc.), backup methods, full role/privilege APIs
- Files: `pycopg/async_database.py` (entire backup/DataFrame/role sections are untested)
- Risk: Methods that fail due to refactoring go unnoticed
- Priority: High - async is incomplete; document what's not implemented or add feature parity

**Migration rollback edge cases:**
- What's not tested:
  - Rollback when migration file is deleted after apply
  - Rollback when DOWN section has syntax error
  - Rollback of first migration in sequence
- Files: `tests/test_migrations.py` (467 lines, but rollback tests are minimal)
- Risk: Silent data inconsistency; users cannot recover from failed migrations
- Priority: High - migrations are critical path

**Session mode with exceptions:**
- What's not tested:
  - Exception in execute() during session mode
  - Exception in cleanup (close) handler
  - Nested session attempt
  - Session timeout/disconnect
- Files: `tests/test_database.py` (1023 lines, session tests exist but don't cover exceptions)
- Risk: Connection leaks; confusing error messages
- Priority: Medium - impacts reliability

**Pool stress testing:**
- What's not tested:
  - Pool exhaustion (all connections in use)
  - Rapid connect/disconnect cycling
  - Connection timeout behavior
  - Recovery from broken connections
- Files: `tests/test_pool.py` (413 lines, but no stress scenarios)
- Risk: Production failures under load; timeouts instead of proper queueing
- Priority: Medium - important for production use

**Spatial operations without PostGIS:**
- What's not tested:
  - Calling spatial methods when extension not installed
  - SRID inference failure
  - Geometry column with unusual types
- Files: `pycopg/database.py` has spatial methods (lines 1268-1308), no error case tests
- Risk: Cryptic errors; silent data loss from SRID mismatch
- Priority: Medium - data integrity concern

---

*Concerns audit: 2026-02-11*
