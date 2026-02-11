---
phase: 05-resilience-configuration
plan: 01
subsystem: core-resilience
tags: [resilience, retry, config, pool]
dependency_graph:
  requires: [config, database, async_database, pool]
  provides: [connection-retry, statement-timeout, configurable-batch-size, pool-reconnection]
  affects: [all-database-operations]
tech_stack:
  added: [tenacity>=9.0.0]
  patterns: [retry-decorator, exponential-backoff, config-driven-defaults]
key_files:
  created: []
  modified:
    - pyproject.toml
    - pycopg/config.py
    - pycopg/database.py
    - pycopg/async_database.py
    - pycopg/pool.py
decisions:
  - "Use tenacity library for retry/backoff (industry standard, well-tested)"
  - "Retry only on OperationalError (connection failures, not logic errors)"
  - "3 attempts with exponential backoff 1-10s (balance reliability vs latency)"
  - "Add logging at WARNING level for retries (operational visibility)"
  - "statement_timeout as Optional[int] in milliseconds (matches PostgreSQL convention)"
  - "default_batch_size defaults to 1000 (existing hardcoded value, now configurable)"
  - "Retry on Database/AsyncDatabase.connect() only, not on pools (pools have built-in reconnect_timeout)"
metrics:
  duration_minutes: 3.96
  tasks_completed: 2
  files_modified: 5
  commits: 2
  tests_passing: 254
  completed_date: 2026-02-11
---

# Phase 05 Plan 01: Resilience & Configuration Summary

**One-liner:** Connection retry with exponential backoff, statement_timeout enforcement, configurable batch sizes, and pool reconnection parameters for production-grade resilience.

## What Was Built

Added production-grade resilience features to pycopg:

1. **Connection Retry** - Automatic retry with exponential backoff for transient connection failures
2. **Statement Timeout** - PostgreSQL-level query timeout enforcement via connection options
3. **Configurable Batch Size** - Operational tuning of insert_batch() default batch sizes
4. **Pool Reconnection** - Resilience parameters for connection pool management

## Implementation Details

### Task 1: Config Extension & Tenacity Dependency

**Added to pyproject.toml:**
- `tenacity>=9.0.0` in core dependencies

**Extended Config dataclass:**
- `statement_timeout: Optional[int] = None` - milliseconds, None means disabled
- `default_batch_size: int = 1000` - default rows per batch

**Updated Config methods:**
- `connect_params()` - builds PostgreSQL options string: `-c statement_timeout=30000`
- `dsn` property - includes options string for pool connections
- `from_url()` - parses `?statement_timeout=5000` from URL query params
- `with_database()` - preserves new fields when switching databases

### Task 2: Retry Logic & Pool Resilience

**Database.py:**
- Added `_connect_with_retry()` method with tenacity decorator:
  - 3 attempts max (`stop_after_attempt(3)`)
  - Exponential backoff 1-10s (`wait_exponential(multiplier=1, min=1, max=10)`)
  - Only retry `OperationalError` (connection failures, not SQL errors)
  - Logs at WARNING level before retry attempts
- Updated `connect()` to use `_connect_with_retry()`
- Changed `insert_batch(batch_size)` from `int = 1000` to `Optional[int] = None`
- Fallback logic: `batch_size = self.config.default_batch_size` when None

**AsyncDatabase.py:**
- Added async `_connect_with_retry()` with same retry configuration
- Updated async `connect()` to use `_connect_with_retry()`
- Same `insert_batch()` signature and fallback logic

**Pool.py:**
- Added 3 new parameters to `PooledDatabase.__init__`:
  - `reconnect_timeout: float = 300.0` - seconds to retry reconnection
  - `reconnect_failed: Optional[Callable] = None` - callback on prolonged failure
  - `check: Optional[Callable] = None` - health check callback
- Pass through to `ConnectionPool()` constructor with default `check_connection`
- Same updates to `AsyncPooledDatabase` with `AsyncConnectionPool`

**Important design decision:** Retry added to direct Database/AsyncDatabase connections only. Pools already have built-in reconnection via `reconnect_timeout` parameter, so adding retry would be redundant and could interfere with pool management.

## Verification Results

All success criteria met:

✅ tenacity is a core dependency in pyproject.toml
✅ Config has statement_timeout (Optional[int], default None)
✅ Config has default_batch_size (int, default 1000)
✅ Config.connect_params() includes PostgreSQL options string when statement_timeout is set
✅ Config.from_url() parses statement_timeout from URL query params
✅ Database.connect() retries transient OperationalError 3 times with exponential backoff
✅ AsyncDatabase.connect() retries transient OperationalError 3 times with exponential backoff
✅ insert_batch() on both classes defaults to config.default_batch_size when batch_size is None
✅ PooledDatabase/AsyncPooledDatabase accept reconnect_timeout, reconnect_failed, check params
✅ 254/255 existing tests pass (1 pre-existing async transaction test failure, unrelated to changes)

## Deviations from Plan

None - plan executed exactly as written.

## Usage Examples

### Statement Timeout

```python
from pycopg import Database, Config

# Via Config constructor
config = Config(
    host="localhost",
    database="mydb",
    statement_timeout=30000  # 30 seconds
)
db = Database(config)

# Via URL
db = Database.from_url("postgresql://user:pass@host/db?statement_timeout=30000")

# All queries now have 30-second timeout enforced by PostgreSQL
```

### Connection Retry

```python
# Automatic retry on connection failures
db = Database.from_env()

# This will retry up to 3 times with exponential backoff if network is flaky
with db.connect() as conn:
    conn.execute("SELECT * FROM users")

# Logs (if retries happen):
# WARNING:pycopg.database:Retrying in 1.0 seconds (attempt 1 of 3)
# WARNING:pycopg.database:Retrying in 2.0 seconds (attempt 2 of 3)
```

### Configurable Batch Size

```python
# Set default batch size globally
config = Config(default_batch_size=500)
db = Database(config)

# Uses config default (500)
db.insert_batch("users", rows)

# Override per call
db.insert_batch("users", rows, batch_size=2000)
```

### Pool Reconnection

```python
from pycopg.pool import PooledDatabase

def on_reconnect_failed(pool):
    print(f"Pool {pool} failed to reconnect after timeout")

db = PooledDatabase.from_env(
    min_size=5,
    max_size=20,
    reconnect_timeout=600.0,  # Try reconnecting for 10 minutes
    reconnect_failed=on_reconnect_failed  # Alert on prolonged failure
)
```

## Self-Check: PASSED

**Files created/modified exist:**
- FOUND: pyproject.toml
- FOUND: pycopg/config.py
- FOUND: pycopg/database.py
- FOUND: pycopg/async_database.py
- FOUND: pycopg/pool.py

**Commits exist:**
- FOUND: 94527ba (Task 1 - Config & tenacity)
- FOUND: 19c4b91 (Task 2 - Retry & pool resilience)

**Functionality verified:**
- Config.connect_params() includes statement_timeout in options string ✓
- Config.from_url() parses statement_timeout from URL ✓
- Config.with_database() preserves new fields ✓
- Database._connect_with_retry has tenacity retry decorator ✓
- AsyncDatabase._connect_with_retry has tenacity retry decorator ✓
- PooledDatabase accepts reconnect_timeout, reconnect_failed, check ✓
- AsyncPooledDatabase accepts reconnect_timeout, reconnect_failed, check ✓
- insert_batch() defaults to config.default_batch_size ✓
