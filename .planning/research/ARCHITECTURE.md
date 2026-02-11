# Architecture Research

**Domain:** Python Database Library (PostgreSQL wrapper)
**Researched:** 2026-02-11
**Confidence:** HIGH

## Standard Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     User-Facing API Layer                    │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────┐                    ┌──────────────┐       │
│  │   Database   │                    │AsyncDatabase │       │
│  │  (sync, 2299 │                    │ (async, 768  │       │
│  │    lines)    │                    │    lines)    │       │
│  └──────┬───────┘                    └──────┬───────┘       │
│         │                                   │               │
├─────────┴───────────────────────────────────┴───────────────┤
│                     Shared Base Layer                        │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │ DatabaseBase │  │ QueryMixin   │  │SessionMixin  │       │
│  │ (factory     │  │ (SQL build)  │  │ (conn reuse) │       │
│  │  methods)    │  │              │  │              │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
├─────────────────────────────────────────────────────────────┤
│                   Connection Layer                           │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────┐                    ┌──────────────┐       │
│  │   psycopg    │                    │  SQLAlchemy  │       │
│  │ (DDL/admin)  │                    │ (DataFrame)  │       │
│  └──────┬───────┘                    └──────┬───────┘       │
│         │                                   │               │
├─────────┴───────────────────────────────────┴───────────────┤
│                      PostgreSQL                              │
└─────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| Database | Sync API for all PostgreSQL operations | Class with 82 public methods, uses psycopg.Connection |
| AsyncDatabase | Async API subset of Database methods | Class with 39 methods (needs ~60% more), uses psycopg.AsyncConnection |
| DatabaseBase | Factory methods, config, repr | Abstract base class with classmethod constructors |
| QueryMixin | SQL generation, validation utilities | Static methods for building INSERT, query validation |
| SessionMixin | Connection reuse for batch operations | Context manager managing _session_conn lifecycle |
| Config | Connection params, URL parsing | Dataclass with from_env, from_url, connect_params |
| Pool | Connection pooling (future) | psycopg.ConnectionPool wrapper |

## Recommended Project Structure

Current structure is appropriate for the library:

```
pycopg/
├── __init__.py           # Public API exports
├── config.py            # Configuration and connection params
├── base.py              # Shared base classes and mixins (194 lines)
├── database.py          # Sync implementation (2299 lines)
├── async_database.py    # Async implementation (768 lines)
├── pool.py              # Connection pooling (future)
├── migrations.py        # Schema migrations
├── queries.py           # SQL query templates
├── utils.py             # Validation, helpers
└── exceptions.py        # Custom exceptions

tests/
├── conftest.py          # Fixtures (db_config, mock connections)
├── setup_test_db.py     # Real database setup script
├── test_database.py     # Sync tests
├── test_async_database.py  # Async tests
├── test_integration.py  # Real database integration tests
├── test_migrations.py   # Migration tests
├── test_config.py       # Config tests
└── test_utils.py        # Utility tests
```

### Structure Rationale

- **Monolithic database.py/async_database.py:** Keep current structure. Splitting into modules adds complexity without benefit at this scale.
- **Shared base.py:** Extract common logic (factory methods, SQL building) but NOT implementation.
- **Separate test files:** Sync vs async tests require different fixtures and decorators.
- **Real DB tests:** Integration tests use `pycopg_test` database, unit tests use mocks.

## Async/Sync Parity Patterns

### Pattern 1: Parallel Implementations (RECOMMENDED)

**What:** Separate Database and AsyncDatabase classes with duplicated method implementations.

**When to use:** When sync and async have fundamentally different control flow (context managers, connection handling, transactions).

**Trade-offs:**
- **Pro:** Clean, readable, type-safe. Each class optimized for its paradigm.
- **Pro:** No abstraction overhead. Direct calls to psycopg.Connection vs AsyncConnection.
- **Pro:** Easy to maintain. Changes in one don't break the other.
- **Con:** Code duplication (~60% of Database methods need async equivalents).
- **Con:** Feature parity requires discipline (easy to add to one and forget the other).

**Example:**
```python
# Sync (database.py)
class Database:
    def execute(self, sql: str, params=None) -> list[dict]:
        with self.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall() if cur.description else []

# Async (async_database.py)
class AsyncDatabase:
    async def execute(self, sql: str, params=None) -> list[dict]:
        async with self.cursor() as cur:
            await cur.execute(sql, params)
            return await cur.fetchall() if cur.description else []
```

**Current status:** pycopg uses this pattern. Database has 82 methods, AsyncDatabase has 39. Need to add ~43 methods.

**Recommendation:** Continue with parallel implementations. The duplication is worth the clarity and type safety.

### Pattern 2: Shared Base with Abstract Methods (NOT RECOMMENDED)

**What:** DatabaseBase defines abstract methods, Database/AsyncDatabase implement them.

**Trade-offs:**
- **Pro:** Forces parity (both must implement all abstract methods).
- **Con:** Cannot share implementation between sync/async (fundamentally different).
- **Con:** Type checkers struggle with abstract async methods.
- **Con:** Adds complexity without reducing code.

**Verdict:** Do not use. The current DatabaseBase is fine for factory methods and config, but don't make operational methods abstract.

### Pattern 3: Code Generation (CONSIDERED)

**What:** Generate AsyncDatabase from Database using AST transformation or templates.

**Trade-offs:**
- **Pro:** Perfect parity guaranteed.
- **Pro:** Changes in one automatically propagate.
- **Con:** Debugging generated code is harder.
- **Con:** Adds build complexity.
- **Con:** Special cases (sync-only methods like engine) need handling.

**Verdict:** Overkill for this library. Manual duplication with testing is simpler.

### Pattern 4: Shared Logic with Mixins (PARTIAL USE)

**What:** Extract common logic (SQL building, validation) to mixins. Implementation stays separate.

**Trade-offs:**
- **Pro:** DRY for business logic (SQL generation, validation).
- **Pro:** Single source of truth for query templates.
- **Con:** Only works for logic without I/O.

**Example:**
```python
# base.py
class QueryMixin:
    @staticmethod
    def _build_insert_sql(table, columns, schema="public", on_conflict=None):
        # Shared SQL building logic
        validate_identifiers(table, schema, *columns)
        cols_str = ", ".join(columns)
        placeholders = ", ".join(["%s"] * len(columns))
        conflict = f" ON CONFLICT {on_conflict}" if on_conflict else ""
        return f"INSERT INTO {schema}.{table} ({cols_str}) VALUES ({placeholders}){conflict}"

# database.py
class Database(QueryMixin):
    def insert_batch(self, table, rows, schema="public", on_conflict=None):
        sql = self._build_insert_sql(table, list(rows[0].keys()), schema, on_conflict)
        # Sync execution
        with self.cursor() as cur:
            cur.execute(sql, values)

# async_database.py
class AsyncDatabase(QueryMixin):
    async def insert_batch(self, table, rows, schema="public", on_conflict=None):
        sql = self._build_insert_sql(table, list(rows[0].keys()), schema, on_conflict)
        # Async execution
        async with self.cursor() as cur:
            await cur.execute(sql, values)
```

**Current status:** pycopg already uses this for SQL building. Good pattern.

**Recommendation:** Expand QueryMixin to cover more SQL generation logic when adding AsyncDatabase methods.

## Retry/Backoff Integration

### Current State

No retry logic currently exists. Connections fail immediately on network errors, connection limits, transient failures.

### Recommended Architecture

**Layered approach:** Retry at connection level, not method level.

```
┌─────────────────────────────────────────────────────────────┐
│                  Database / AsyncDatabase                    │
│         (business logic, unaware of retries)                 │
└────────────┬────────────────────────────────────────────────┘
             │
┌────────────▼────────────────────────────────────────────────┐
│              Retry Wrapper (Decorator/Context)               │
│   - Retry config (max_retries, backoff strategy)            │
│   - Error classification (retriable vs fatal)                │
│   - Backoff calculation (exponential, jitter)                │
└────────────┬────────────────────────────────────────────────┘
             │
┌────────────▼────────────────────────────────────────────────┐
│              psycopg Connection / AsyncConnection            │
│               (unchanged, no retry awareness)                │
└─────────────────────────────────────────────────────────────┘
```

### Pattern: Connection-Level Retry Decorator

**Implementation approach:**

```python
# pycopg/retry.py (new file)
from functools import wraps
from typing import Type, Callable
import time
import random
import psycopg

class RetryConfig:
    """Configuration for retry behavior."""
    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 0.1,  # seconds
        max_delay: float = 10.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter

    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt using exponential backoff."""
        delay = min(self.base_delay * (self.exponential_base ** attempt), self.max_delay)
        if self.jitter:
            delay *= (0.5 + random.random())  # 50-150% of calculated delay
        return delay

# Errors that are retriable (transient failures)
RETRIABLE_ERRORS = (
    psycopg.OperationalError,  # Connection lost, timeout
    psycopg.errors.ConnectionException,  # Connection refused
    psycopg.errors.AdminShutdown,  # Server restart
    psycopg.errors.CannotConnectNow,  # Server starting up
    psycopg.errors.CrashShutdown,  # Server crash
)

# Errors that are NOT retriable (permanent failures)
FATAL_ERRORS = (
    psycopg.errors.InvalidPassword,  # Bad credentials
    psycopg.errors.InvalidAuthorizationSpecification,  # Auth failure
    psycopg.errors.SyntaxError,  # SQL syntax error
    psycopg.errors.UndefinedTable,  # Table doesn't exist
)

def with_retry(config: RetryConfig):
    """Decorator for sync functions with retry logic."""
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(config.max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except RETRIABLE_ERRORS as e:
                    last_exception = e
                    if attempt < config.max_retries:
                        delay = config.calculate_delay(attempt)
                        time.sleep(delay)
                    # Last attempt, will raise
                except FATAL_ERRORS:
                    raise  # Don't retry fatal errors

            # All retries exhausted
            raise last_exception
        return wrapper
    return decorator

def with_async_retry(config: RetryConfig):
    """Decorator for async functions with retry logic."""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            import asyncio
            last_exception = None
            for attempt in range(config.max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except RETRIABLE_ERRORS as e:
                    last_exception = e
                    if attempt < config.max_retries:
                        delay = config.calculate_delay(attempt)
                        await asyncio.sleep(delay)
                except FATAL_ERRORS:
                    raise
            raise last_exception
        return wrapper
    return decorator
```

**Integration into Database:**

```python
# pycopg/database.py
from pycopg.retry import with_retry, RetryConfig

class Database:
    def __init__(self, config: Config, retry_config: Optional[RetryConfig] = None):
        self.config = config
        self.retry_config = retry_config or RetryConfig()  # Default retry config
        self._engine = None
        self._session_conn = None

    def _connect_with_retry(self, autocommit=False):
        """Internal method with retry logic."""
        @with_retry(self.retry_config)
        def _connect():
            return psycopg.connect(**self.config.connect_params(), autocommit=autocommit)
        return _connect()

    @contextmanager
    def connect(self, autocommit=False):
        """Context manager for connection with automatic retry."""
        conn = self._connect_with_retry(autocommit)
        try:
            yield conn
        finally:
            conn.close()
```

**Benefits:**
- Retry logic centralized in one place
- Database/AsyncDatabase methods unchanged
- User can configure retry behavior: `Database(config, retry_config=RetryConfig(max_retries=5))`
- Or disable: `Database(config, retry_config=RetryConfig(max_retries=0))`

**Alternative: Connection Pool with Retry (Future)**

```python
# pycopg/pool.py
from psycopg_pool import ConnectionPool
from pycopg.retry import RetryConfig

class RetryPool:
    """Connection pool with retry logic."""
    def __init__(self, config: Config, retry_config: RetryConfig, pool_config: PoolConfig):
        self.retry_config = retry_config
        self._pool = ConnectionPool(
            conninfo=config.url,
            min_size=pool_config.min_size,
            max_size=pool_config.max_size,
        )

    @contextmanager
    def connection(self):
        """Get connection from pool with retry on acquisition."""
        @with_retry(self.retry_config)
        def _get_conn():
            return self._pool.connection()

        with _get_conn() as conn:
            yield conn
```

## Test Organization

### Current Test Structure

```
tests/
├── conftest.py              # Fixtures (db_config, mocks)
├── setup_test_db.py         # Creates pycopg_test database
├── test_database.py         # Unit tests (mocked)
├── test_async_database.py   # Unit tests (mocked)
├── test_integration.py      # Real DB tests
└── test_*.py                # Other unit tests
```

### Recommended Test Architecture

**Three-tier test strategy:**

```
┌─────────────────────────────────────────────────────────────┐
│                    Unit Tests (Fast)                         │
│  - Mock psycopg connections                                  │
│  - Test business logic, validation, SQL generation           │
│  - No database required                                      │
│  - Run on every commit (~1-2 seconds)                        │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│              Integration Tests (Real DB)                     │
│  - Use pycopg_test database                                  │
│  - Test actual PostgreSQL operations                         │
│  - Verify data persistence, transactions, constraints        │
│  - Run before PR merge (~10-30 seconds)                      │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│         Extension Tests (PostGIS, TimescaleDB)               │
│  - Test PostGIS geometry operations                          │
│  - Test TimescaleDB hypertables                              │
│  - Optional: skip if extensions not available                │
│  - Run before release (~30-60 seconds)                       │
└─────────────────────────────────────────────────────────────┘
```

### Pattern: Fixture-Based Database Setup

**conftest.py design:**

```python
# tests/conftest.py
import os
import pytest
from pycopg import Config, Database, AsyncDatabase

# --- Config Fixtures ---

@pytest.fixture
def db_config():
    """Real database config for integration tests."""
    return Config(
        host=os.getenv("PGHOST", "localhost"),
        port=int(os.getenv("PGPORT", "5432")),
        database="pycopg_test",
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD", "postgres"),
    )

@pytest.fixture
def mock_config():
    """Mock config for unit tests."""
    return Config(
        host="localhost",
        port=5432,
        database="testdb",
        user="testuser",
        password="testpass",
    )

# --- Database Fixtures ---

@pytest.fixture
def db(db_config):
    """Real sync database for integration tests."""
    db = Database(db_config)
    yield db
    # Cleanup if needed

@pytest.fixture
async def async_db(db_config):
    """Real async database for integration tests."""
    db = AsyncDatabase(db_config)
    yield db
    # Cleanup if needed

# --- Table Fixtures ---

@pytest.fixture
def test_table(db):
    """Create and cleanup a test table."""
    table_name = "test_users"
    db.execute(f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE,
            active BOOLEAN DEFAULT true
        )
    """)
    yield table_name
    db.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")

@pytest.fixture
async def async_test_table(async_db):
    """Create and cleanup a test table for async tests."""
    table_name = "async_test_users"
    await async_db.execute(f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL
        )
    """)
    yield table_name
    await async_db.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")

# --- Transaction Fixtures (Test Isolation) ---

@pytest.fixture
def isolated_db(db_config):
    """Database with transaction rollback for test isolation."""
    db = Database(db_config)

    # Start transaction
    conn = db._connect_with_retry()
    conn.autocommit = False
    old_conn = db._session_conn
    db._session_conn = conn

    yield db

    # Rollback everything
    conn.rollback()
    conn.close()
    db._session_conn = old_conn

# --- Mock Fixtures ---

@pytest.fixture
def mock_connection():
    """Mocked psycopg connection for unit tests."""
    from unittest.mock import MagicMock
    conn = MagicMock()
    cursor = MagicMock()
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = cursor
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    return conn, cursor
```

### Test File Organization

**tests/test_database.py (Unit Tests - Mocked):**
```python
import pytest
from unittest.mock import patch, MagicMock
from pycopg import Database

class TestDatabaseMethods:
    """Unit tests with mocked connections."""

    @patch("pycopg.database.psycopg")
    def test_execute_select(self, mock_psycopg, mock_config):
        """Test execute with SELECT returns results."""
        # Setup mock
        mock_conn, mock_cursor = create_mock_connection()
        mock_cursor.description = [("id",), ("name",)]
        mock_cursor.fetchall.return_value = [{"id": 1, "name": "Alice"}]
        mock_psycopg.connect.return_value = mock_conn

        # Test
        db = Database(mock_config)
        result = db.execute("SELECT * FROM users")

        # Verify
        assert len(result) == 1
        assert result[0]["name"] == "Alice"
        mock_cursor.execute.assert_called_once()
```

**tests/test_integration.py (Integration Tests - Real DB):**
```python
import pytest
from pycopg import Database

@pytest.mark.integration
class TestDatabaseIntegration:
    """Integration tests with real PostgreSQL."""

    def test_create_and_query_table(self, db, test_table):
        """Test table creation and querying."""
        # Insert data
        db.execute(
            f"INSERT INTO {test_table} (name, email) VALUES (%s, %s)",
            ["Alice", "alice@example.com"]
        )

        # Query
        results = db.execute(f"SELECT * FROM {test_table}")
        assert len(results) == 1
        assert results[0]["name"] == "Alice"

    def test_transaction_rollback(self, db, test_table):
        """Test transaction rollback."""
        try:
            with db.transaction() as conn:
                conn.execute(f"INSERT INTO {test_table} (name) VALUES ('Bob')")
                raise ValueError("Intentional error")
        except ValueError:
            pass

        # Should be rolled back
        results = db.execute(f"SELECT * FROM {test_table}")
        assert len(results) == 0
```

**pytest.ini configuration:**
```ini
[pytest]
markers =
    integration: marks tests as integration tests (require database)
    postgis: marks tests as requiring PostGIS extension
    timescaledb: marks tests as requiring TimescaleDB extension
    slow: marks tests as slow running

# Run only fast unit tests by default
addopts = -v -m "not integration and not slow"

# Async test support
asyncio_mode = auto
```

**Running tests:**
```bash
# Fast unit tests (default)
pytest

# All tests including integration
pytest -m ""

# Only integration tests
pytest -m integration

# Skip extension tests
pytest -m "not postgis and not timescaledb"
```

### Pattern: Test Database Isolation

**Problem:** Parallel tests interfering with each other.

**Solution 1: Transaction Rollback (Fast)**
```python
@pytest.fixture
def isolated_db(db_config):
    """Each test runs in a transaction that's rolled back."""
    db = Database(db_config)
    with db.transaction() as conn:
        db._temp_conn = conn
        yield db
        # Transaction automatically rolled back on exit
```

**Solution 2: Unique Table Names (Parallel-Safe)**
```python
import uuid

@pytest.fixture
def unique_table(db):
    """Create table with unique name for parallel testing."""
    table_name = f"test_{uuid.uuid4().hex[:8]}"
    db.execute(f"CREATE TABLE {table_name} (id SERIAL, data TEXT)")
    yield table_name
    db.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")
```

**Solution 3: Database-Per-Test (Slow but Isolated)**
```python
@pytest.fixture
def isolated_database():
    """Create temporary database for test."""
    db_name = f"test_{uuid.uuid4().hex[:8]}"
    admin_db = Database.from_env()
    admin_db.create_database(db_name)

    test_db = Database(Config(database=db_name, ...))
    yield test_db

    test_db.close()
    admin_db.drop_database(db_name)
```

**Recommendation:** Use transaction rollback for most tests, unique tables for tests that need DDL.

## Data Flow

### Sync Request Flow

```
User Call: db.execute("SELECT * FROM users WHERE active = %s", [True])
    ↓
Database.execute()
    ↓
db.cursor() context manager
    ↓
psycopg.connect(**config.connect_params())  [with retry if configured]
    ↓
cursor.execute(sql, params)
    ↓
PostgreSQL query execution
    ↓
cursor.fetchall() → list[dict]
    ↓
conn.commit()
    ↓
conn.close()
    ↓
Return results to user
```

### Async Request Flow

```
User Call: await db.execute("SELECT * FROM users WHERE active = %s", [True])
    ↓
AsyncDatabase.execute()
    ↓
db.cursor() async context manager
    ↓
await psycopg.AsyncConnection.connect(...)  [with async retry if configured]
    ↓
await cursor.execute(sql, params)
    ↓
PostgreSQL query execution
    ↓
await cursor.fetchall() → list[dict]
    ↓
await conn.commit()
    ↓
await conn.close()
    ↓
Return results to user
```

### Session Mode Flow (Connection Reuse)

```
User: with db.session() as session:
    ↓
Database.session() context manager
    ↓
self._session_conn = psycopg.connect(...)  [single connection]
    ↓
session.execute(...)  ┐
session.execute(...)  ├─ All reuse _session_conn
session.insert_batch()┘
    ↓
conn.commit()  [on session exit]
    ↓
conn.close()
    ↓
self._session_conn = None
```

**Key insight:** Session mode is critical for performance. Batch operations should encourage/require session mode.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| Single developer | Current architecture perfect. Direct connections, no pooling. |
| Small team, low traffic | Add connection pooling (psycopg_pool), keep monolithic. |
| High traffic, connection limits | Implement RetryPool, add read replicas, query result caching. |
| Very high traffic | Split to connection pooler service (PgBouncer), add monitoring. |

### Scaling Priorities

1. **First bottleneck:** Connection exhaustion (too many clients)
   - **Fix:** Add connection pooling via psycopg_pool
   - **When:** More than ~100 concurrent connections

2. **Second bottleneck:** Query performance
   - **Fix:** Add query caching layer, read replicas
   - **When:** Specific queries taking >100ms consistently

3. **Third bottleneck:** Write contention
   - **Fix:** Batch operations, COPY instead of INSERT
   - **When:** Bulk imports slow down

**Note:** pycopg is a library, not a service. Users handle their own scaling. Library should provide tools (pooling, batching, COPY) not enforce them.

## Build Order and Dependencies

### Phase 1: Foundation (Current State)
**Status:** COMPLETE
- Config, Database (sync), basic operations
- psycopg integration, context managers
- Session mode, transactions

### Phase 2: AsyncDatabase Parity (Next)
**Depends on:** Phase 1
**Goal:** AsyncDatabase has same features as Database

**Method-by-method approach:**
1. Audit Database methods (82 total)
2. Check AsyncDatabase (39 implemented)
3. Missing: ~43 methods
4. Add by category:
   - **DDL:** create_table, drop_table, alter_table, create_index, drop_index
   - **DQL:** table_info, list_columns, columns_with_types, list_indexes
   - **Schema:** create_schema, drop_schema
   - **Extensions:** create_extension, drop_extension
   - **PostGIS:** create_spatial_index, list_geometry_columns
   - **TimescaleDB:** create_hypertable, list_hypertables
   - **Admin:** create_role, drop_role, grant, revoke
   - **Stats:** table_sizes, index_sizes

**Pattern:** For each sync method:
```python
# 1. Copy signature, add async
def list_tables(self, schema: str = "public") -> list[str]:
    ↓
async def list_tables(self, schema: str = "public") -> list[str]:

# 2. Extract SQL from sync version (move to queries.py if not there)
SQL_LIST_TABLES = "SELECT tablename FROM pg_tables WHERE schemaname = %s"

# 3. Replace cursor → async with cursor
with self.cursor() as cur:
    ↓
async with self.cursor() as cur:

# 4. Add await to all I/O
cur.execute(sql, params)
    ↓
await cur.execute(sql, params)

cur.fetchall()
    ↓
await cur.fetchall()
```

### Phase 3: Retry/Backoff (Future)
**Depends on:** Phase 2 (AsyncDatabase parity)
**Goal:** Production-ready error handling

**Components:**
1. Create pycopg/retry.py with RetryConfig, with_retry, with_async_retry
2. Add retry_config parameter to Database.__init__ and AsyncDatabase.__init__
3. Wrap connection creation in _connect_with_retry() and _async_connect_with_retry()
4. Document error classification (retriable vs fatal)
5. Add tests for retry behavior

**Dependencies:**
- Database parity complete (so both get retry at once)
- Error catalog documented (what's retriable?)
- Backoff strategy decided (exponential with jitter)

### Phase 4: Connection Pooling (Future)
**Depends on:** Phase 3 (Retry)
**Goal:** High-performance connection reuse

**Components:**
1. Create pycopg/pool.py with Pool class
2. Wrap psycopg_pool.ConnectionPool and AsyncConnectionPool
3. Integrate with RetryConfig
4. Add pool configuration (min_size, max_size, timeout)
5. Update Database/AsyncDatabase to optionally use pool

**Why after Retry:** Pool needs retry for connection acquisition failures.

## Anti-Patterns

### Anti-Pattern 1: Shared Implementation with Runtime Dispatch

**What people do:** Single class with `is_async` flag and runtime checks.
```python
# BAD
class Database:
    def __init__(self, config, is_async=False):
        self.is_async = is_async

    def execute(self, sql):
        if self.is_async:
            return self._async_execute(sql)
        else:
            return self._sync_execute(sql)
```

**Why it's wrong:**
- Type checkers can't infer return type (sync vs awaitable)
- IDE autocomplete broken
- Runtime overhead on every call
- Easy to forget `await` (silent bugs)

**Do this instead:** Separate Database and AsyncDatabase classes.

### Anti-Pattern 2: Method-Level Retry

**What people do:** Add retry logic to each method.
```python
# BAD
def execute(self, sql):
    for attempt in range(3):
        try:
            with self.cursor() as cur:
                return cur.execute(sql)
        except OperationalError:
            time.sleep(1)
```

**Why it's wrong:**
- Duplicated retry logic across methods
- Hard to configure (retry count hardcoded)
- Can't distinguish retriable vs fatal errors
- Transaction retries need special handling

**Do this instead:** Retry at connection level with configurable RetryConfig.

### Anti-Pattern 3: Mocking Real Database in Integration Tests

**What people do:** Use unittest.mock for integration tests.
```python
# BAD
@patch("psycopg.connect")
def test_integration_create_table(mock_connect):
    mock_cursor = MagicMock()
    # ... complex mock setup
    db.create_table("users", ...)
```

**Why it's wrong:**
- Not testing actual PostgreSQL behavior
- Mocks diverge from reality (constraint violations, type handling)
- False confidence (tests pass, real DB fails)

**Do this instead:** Use real `pycopg_test` database for integration tests. Use mocks only for unit tests.

### Anti-Pattern 4: Nested Sessions

**What people do:** Call session() inside session().
```python
# BAD
with db.session() as s1:
    with db.session() as s2:  # Error!
        s2.execute(...)
```

**Why it's wrong:**
- Connection leak (s1 connection abandoned)
- Confusing transaction semantics
- Not actually reusing connection

**Do this instead:** Check for existing session and raise error (already implemented).

### Anti-Pattern 5: Forgetting to Copy Changes to Both Sync and Async

**What people do:** Add feature to Database, forget AsyncDatabase.
```python
# database.py
def cool_new_feature(self): ...

# async_database.py - MISSING!
```

**Why it's wrong:**
- Feature parity breaks
- Users confused (works in sync, not async)
- Hard to track what's missing

**Do this instead:**
- Checklist when adding methods: "Did I add async version?"
- Test coverage comparison (sync vs async method count)
- CI check: `assert len(Database.__dict__) == len(AsyncDatabase.__dict__) + EXPECTED_DIFF`

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| PostgreSQL | psycopg.Connection | Direct connection, supports all PostgreSQL versions 12+ |
| PostGIS | ST_* functions via execute() | Optional, detected via list_extensions() |
| TimescaleDB | create_hypertable, time_bucket | Optional, detected via list_extensions() |
| SQLAlchemy | engine property (lazy init) | Used only for DataFrame operations (to_dataframe, from_dataframe) |
| pandas | engine.read_sql, df.to_sql | Optional dependency, import guarded |
| geopandas | gpd.read_postgis | Optional dependency, import guarded |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Database ↔ Config | Direct attribute access | Config is immutable after creation |
| Database ↔ psycopg | Context managers | Connection lifecycle managed by with blocks |
| Database ↔ SQLAlchemy | engine property | Lazy initialization, only created when needed |
| QueryMixin ↔ Database | Static method calls | Stateless SQL generation |
| SessionMixin ↔ Database | _session_conn attribute | State stored in instance variable |
| Database ↔ AsyncDatabase | No communication | Completely independent |

## Sources

**Confidence level: HIGH** - Based on direct codebase analysis and established Python async patterns.

**Primary sources:**
- pycopg codebase analysis (database.py: 2299 lines, async_database.py: 768 lines, base.py: 194 lines)
- psycopg 3 documentation (official PostgreSQL adapter patterns)
- Python asyncio patterns (context managers, async/await semantics)
- pytest async testing patterns (pytest-asyncio, fixtures)

**Patterns validated by:**
- HTTPX library (parallel sync/async implementations)
- aiohttp vs requests (separate async/sync libraries)
- SQLAlchemy 2.0 (separate async extension)
- encode/databases (async-first database library)

**Limitations:**
- No access to web search or external docs during research
- Retry/backoff patterns based on training data (standard exponential backoff with jitter)
- Test isolation patterns based on common pytest practices

---
*Architecture research for: pycopg v0.2.0 - PostgreSQL/PostGIS/TimescaleDB Python library*
*Researched: 2026-02-11*
