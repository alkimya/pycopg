# Architecture

**Analysis Date:** 2026-02-11

## Pattern Overview

**Overall:** Layered abstraction pattern with sync/async duality

**Key Characteristics:**
- Separation of concerns: configuration, database operations, connection management
- Dual sync/async implementations (Database and AsyncDatabase) with shared abstractions
- Mixin-based code reuse for query building and session management
- Centralized SQL query constants for maintainability
- Factory methods for connection creation from multiple sources (env, URL, direct)

## Layers

**Configuration Layer:**
- Purpose: Manage database connection parameters and credentials
- Location: `pycopg/config.py`
- Contains: Config dataclass for storing host, port, database, user, password, SSL settings
- Depends on: Standard library (os, urllib.parse), optional python-dotenv
- Used by: Database, AsyncDatabase, PooledDatabase, AsyncPooledDatabase

**Database Abstraction Layer:**
- Purpose: Provide high-level API for PostgreSQL/PostGIS/TimescaleDB operations
- Location: `pycopg/database.py` (sync), `pycopg/async_database.py` (async)
- Contains: Database and AsyncDatabase classes with schema queries, table operations, DataFrame integration, migrations support
- Depends on: Config, psycopg (sync driver), SQLAlchemy (for DataFrames), queries module
- Used by: End-user application code

**Connection Pool Layer:**
- Purpose: Manage efficient connection reuse for web applications and services
- Location: `pycopg/pool.py`
- Contains: PooledDatabase and AsyncPooledDatabase classes wrapping psycopg_pool
- Depends on: Config, psycopg_pool, psycopg
- Used by: High-concurrency applications

**Migration Layer:**
- Purpose: Provide simple numbered SQL migration system
- Location: `pycopg/migrations.py`
- Contains: Migration file parser and Migrator class for tracking/executing migrations
- Depends on: Database, exceptions, utils
- Used by: Database schema versioning

**Query Constants Layer:**
- Purpose: Centralize SQL query definitions for reuse and consistency
- Location: `pycopg/queries.py`
- Contains: SQL constants for schemas, tables, databases, extensions, indexes, constraints, roles, sizes, PostGIS, TimescaleDB
- Depends on: None
- Used by: Database and AsyncDatabase classes

**Utilities Layer:**
- Purpose: Shared validation and helper functions
- Location: `pycopg/utils.py`
- Contains: SQL identifier validation, interval validation, index method validation, literal quoting
- Depends on: exceptions
- Used by: Database, AsyncDatabase, migrations, base classes

**Exceptions Layer:**
- Purpose: Custom exception hierarchy for pycopg-specific errors
- Location: `pycopg/exceptions.py`
- Contains: PycopgError (base), ConnectionError, ConfigurationError, ExtensionNotAvailable, TableNotFound, InvalidIdentifier, MigrationError
- Depends on: None
- Used by: All layers for error handling

**Base Abstractions Layer:**
- Purpose: Shared base classes and mixins for sync/async database classes
- Location: `pycopg/base.py`
- Contains: DatabaseBase abstract class, QueryMixin (SQL building), SessionMixin (connection reuse)
- Depends on: Config, queries, utils
- Used by: Database and AsyncDatabase

## Data Flow

**Query Execution (Sync):**

1. User calls method on Database instance (e.g., `db.execute()`)
2. Database uses QueryMixin to build parameterized SQL if needed
3. Database._get_session_connection() checks if in session mode
4. Opens psycopg connection via context manager or uses session connection
5. Executes query through psycopg cursor with dict_row factory
6. Returns dict rows or processed results (DataFrame, count, etc.)
7. Commits transaction unless in autocommit mode
8. Connection closes (or remains open in session mode)

**Query Execution (Async):**

1. User awaits method on AsyncDatabase instance
2. AsyncDatabase uses same QueryMixin for SQL building
3. AsyncDatabase._session_conn checked for active session
4. Opens psycopg.AsyncConnection via async context manager
5. Executes query through async cursor with dict_row factory
6. Returns awaitable that yields results
7. Awaits commit unless in autocommit mode
8. Connection closes

**Connection Pool Flow:**

1. PooledDatabase/AsyncPooledDatabase initialized with min/max size
2. Pool creates and maintains background connections
3. User requests connection via .connection() or simplified API (.execute())
4. Pool provides connection from available pool or creates new
5. Operation completes
6. Connection returned to pool or closed based on TTL/idle timeout
7. Pool maintains health by recycling expired connections

**State Management:**

- **Session Mode**: Database instance tracks `_session_connection` (sync) or `_session_conn` (async)
  - When in session context, all operations reuse the same connection
  - Single connection significantly reduces overhead for batch operations
  - Connections committed/closed when exiting session context

- **Transaction Mode**: Tracked via psycopg.pq.TransactionStatus
  - Autocommit mode: no explicit commit needed
  - Normal mode: commit after each operation unless error
  - Transaction context: manual control over commit points

- **SQLAlchemy Engine Caching**: Database maintains `_engine` for DataFrame operations
  - Lazy-created on first DataFrame access
  - Reused for subsequent DataFrame operations
  - Separate from connection for pooling reasons

## Key Abstractions

**DatabaseBase:**
- Purpose: Shared interface for Database and AsyncDatabase
- Examples: `pycopg/base.py` lines 18-59
- Pattern: Abstract base class with factory methods (from_env, from_url)
- Not directly instantiated; provides contract for sync/async implementations

**QueryMixin:**
- Purpose: SQL generation for INSERT, SELECT, batch operations
- Examples: `pycopg/base.py` lines 62-173
- Pattern: Static methods for building parameterized SQL with safe identifier validation
- Used by: Both Database and AsyncDatabase classes

**SessionMixin:**
- Purpose: Connection reuse for batch operations
- Examples: `pycopg/base.py` lines 176-195
- Pattern: Context manager support with internal `_session_connection` tracking
- Used by: Database and AsyncDatabase for session() context manager

**Config Dataclass:**
- Purpose: Immutable connection parameters with factory methods
- Examples: `pycopg/config.py`
- Pattern: Dataclass with class methods for loading from env, URL, or direct params
- Properties: dsn (psycopg format), url (SQLAlchemy format), connect_params() dict

**Migration:**
- Purpose: Individual migration file representation
- Examples: `pycopg/migrations.py` lines 33-74
- Pattern: Parses numbered filename (001_name.sql), reads SQL on demand

**Migrator:**
- Purpose: Orchestrate migration execution and tracking
- Examples: `pycopg/migrations.py` lines 77+
- Pattern: Maintains migration table, runs pending migrations in order

## Entry Points

**Sync Database:**
- Location: `pycopg/database.py`
- Triggers: `db = Database.from_env()` or `Database(config)` or `Database.from_url()`
- Responsibilities: Execute queries, manage transactions, handle DataFrame operations, track schema metadata

**Async Database:**
- Location: `pycopg/async_database.py`
- Triggers: `db = AsyncDatabase.from_env()` or `AsyncDatabase(config)` or `AsyncDatabase.from_url()`
- Responsibilities: Same as Database but with async/await interface

**Pooled Database:**
- Location: `pycopg/pool.py`
- Triggers: `db = PooledDatabase.from_env()` or `PooledDatabase(config, min_size, max_size)`
- Responsibilities: Manage connection pool for concurrent access, lazy connection creation

**Module Entry:**
- Location: `pycopg/__init__.py`
- Exports: Database, AsyncDatabase, PooledDatabase, AsyncPooledDatabase, Config, Migrator, exceptions, utils
- Purpose: Public API surface

## Error Handling

**Strategy:** Custom exception hierarchy with specific error types for recovery logic

**Patterns:**

- **Identifier Validation**: All user-supplied identifiers (tables, columns, schemas) validated against regex before SQL generation
  - Raises InvalidIdentifier with specific message about valid characters
  - Prevents SQL injection for object names (not parameter values)
  - Location: `pycopg/utils.py` lines 21-67

- **Connection Errors**: psycopg exceptions wrapped/re-raised as ConnectionError
  - Allows separation of connection failures from query errors
  - Facilitates retry logic in applications

- **Migration Errors**: MigrationError raised for invalid migration files or execution failures
  - Invalid filename format caught during Migration.__init__
  - Execution errors include migration version in message for debugging

- **Configuration Errors**: ConfigurationError raised for missing/invalid env vars or URLs
  - Clear messages about which env vars are checked
  - Defaults provided for optional parameters

- **Extension Errors**: ExtensionNotAvailable raised when PostGIS/TimescaleDB methods called without extension
  - Checked on-demand, not at initialization
  - Allows graceful degradation

- **Table Errors**: TableNotFound raised when operations target non-existent tables
  - Checked before DDL operations when appropriate

## Cross-Cutting Concerns

**Logging:** Not implemented in core; relies on psycopg logging configuration
- Users enable via: logging.getLogger("psycopg").setLevel(DEBUG)
- SQL queries logged by psycopg if configured

**Validation:** Three-tiered approach
- Identifier validation: regex-based SQL injection prevention
- Interval validation: format checks for TimescaleDB operations
- Type validation: parameter passing to psycopg (no custom validation)

**Authentication:** Delegated to psycopg
- Config.from_env() loads credentials from environment
- Config.dsn and Config.url properties generate connection strings
- SSL mode supported via Config.sslmode parameter

**Connection Management:** Two strategies
- **Direct**: Each operation opens connection, executes, closes
- **Session**: User context manager maintains single connection for multiple ops
- **Pooled**: Background pool maintains min/max connections, recycles on TTL

**Transaction Control:** psycopg native
- Autocommit mode: no transaction wrapping
- Normal mode: implicit transaction per operation
- Explicit: user can call connection/transaction context managers
