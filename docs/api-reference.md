# API Reference

Complete API reference for all pycopg classes and methods.

## Config

Configuration for database connections.

```python
from pycopg import Config
```

### Constructor

```python
Config(
    host: str = "localhost",
    port: int = 5432,
    database: str = "postgres",
    user: str = "postgres",
    password: str = "",
    sslmode: Optional[str] = None,
    options: dict = {}
)
```

### Class Methods

| Method | Description |
|--------|-------------|
| `from_url(url)` | Create Config from PostgreSQL URL |
| `from_env(dotenv_path=None, *, load_dotenv_file=True)` | Create Config from environment variables |

#### from_env Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `dotenv_path` | `str`, `Path`, or `None` | `None` | Path to .env file |
| `load_dotenv_file` | `bool` | `True` | Whether to load .env file. Set `False` to use only existing env vars |

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `dsn` | `str` | psycopg-compatible DSN string |
| `url` | `str` | SQLAlchemy-compatible URL |

### Methods

| Method | Description |
|--------|-------------|
| `connect_params()` | Return dict for psycopg.connect() |
| `with_database(name)` | Create new Config with different database |

---

## Database

Synchronous database interface.

```python
from pycopg import Database
```

### Constructor

```python
Database(config: Config)
```

### Class Methods

| Method | Description |
|--------|-------------|
| `from_url(url)` | Create from PostgreSQL URL |
| `from_env(dotenv_path=None)` | Create from environment |
| `create(name, host, port, user, password, ...)` | Create a new database and connect to it |
| `create_from_env(name, ...)` | Create database using env credentials |

### Query Methods

| Method | Parameters | Returns | Description |
|--------|------------|---------|-------------|
| `execute` | `sql, params=None, autocommit=False` | `list[dict]` | Execute SQL, return results |
| `execute_many` | `sql, params_seq` | `int` | Execute for multiple params |
| `fetch_one` | `sql, params=None` | `Optional[dict]` | Fetch single row |
| `fetch_val` | `sql, params=None` | `Any` | Fetch single value |

### Context Managers

| Method | Parameters | Yields | Description |
|--------|------------|--------|-------------|
| `connect` | `autocommit=False` | `Connection` | Connection context |
| `cursor` | `autocommit=False` | `Cursor` | Cursor with dict rows |

### Schema Methods

| Method | Parameters | Returns |
|--------|------------|---------|
| `list_schemas` | - | `list[str]` |
| `schema_exists` | `name` | `bool` |
| `create_schema` | `name, if_not_exists=True, owner=None` | - |
| `drop_schema` | `name, if_exists=True, cascade=False` | - |

### Table Methods

| Method | Parameters | Returns |
|--------|------------|---------|
| `list_tables` | `schema="public"` | `list[str]` |
| `table_exists` | `name, schema="public"` | `bool` |
| `table_info` | `name, schema="public"` | `list[dict]` |
| `row_count` | `name, schema="public"` | `int` |
| `drop_table` | `name, schema="public", if_exists=True, cascade=False` | - |
| `truncate_table` | `name, schema="public", cascade=False` | - |

### Extension Methods

| Method | Parameters | Returns |
|--------|------------|---------|
| `list_extensions` | - | `list[dict]` |
| `has_extension` | `name` | `bool` |
| `create_extension` | `name, schema=None, if_not_exists=True` | - |
| `drop_extension` | `name, if_exists=True, cascade=False` | - |

### Index Methods

| Method | Parameters | Returns |
|--------|------------|---------|
| `create_index` | `table, columns, schema="public", name=None, unique=False, method="btree", if_not_exists=True` | - |
| `drop_index` | `name, schema="public", if_exists=True` | - |
| `list_indexes` | `table, schema="public"` | `list[dict]` |

### Constraint Methods

| Method | Parameters | Returns |
|--------|------------|---------|
| `add_primary_key` | `table, columns, schema="public", name=None` | - |
| `add_foreign_key` | `table, columns, ref_table, ref_columns, ...` | - |
| `add_unique_constraint` | `table, columns, schema="public", name=None` | - |
| `list_constraints` | `table, schema="public"` | `list[dict]` |

### DataFrame Methods

| Method | Parameters | Returns |
|--------|------------|---------|
| `from_dataframe` | `df, table, schema="public", if_exists="fail", primary_key=None, ...` | - |
| `to_dataframe` | `table=None, schema="public", sql=None, params=None` | `DataFrame` |
| `from_geodataframe` | `gdf, table, schema="public", ...` | - |
| `to_geodataframe` | `table=None, schema="public", sql=None, geometry_column="geometry", ...` | `GeoDataFrame` |

### PostGIS Methods

| Method | Parameters | Returns |
|--------|------------|---------|
| `create_spatial_index` | `table, column="geometry", schema="public", name=None` | - |
| `list_geometry_columns` | `schema=None` | `list[dict]` |

### TimescaleDB Methods

| Method | Parameters | Returns |
|--------|------------|---------|
| `create_hypertable` | `table, time_column, schema="public", chunk_time_interval="1 day", ...` | - |
| `enable_compression` | `table, segment_by=None, order_by=None, schema="public"` | - |
| `add_compression_policy` | `table, compress_after="7 days", schema="public"` | - |
| `add_retention_policy` | `table, drop_after, schema="public"` | - |
| `list_hypertables` | - | `list[dict]` |
| `hypertable_info` | `table, schema="public"` | `dict` |

### Role Methods

| Method | Parameters | Returns |
|--------|------------|---------|
| `create_role` | `name, password=None, login=True, superuser=False, ...` | - |
| `drop_role` | `name, if_exists=True` | - |
| `role_exists` | `name` | `bool` |
| `list_roles` | `include_system=False` | `list[dict]` |
| `alter_role` | `name, password=None, login=None, ...` | - |
| `grant_role` | `role, member, with_admin=False` | - |
| `revoke_role` | `role, member` | - |
| `grant` | `privileges, on, to, object_type="TABLE", schema="public", ...` | - |
| `revoke` | `privileges, on, from_role, object_type="TABLE", schema="public", ...` | - |
| `list_role_members` | `role` | `list[str]` |
| `list_role_grants` | `role` | `list[dict]` |

### Backup Methods

| Method | Parameters | Returns |
|--------|------------|---------|
| `pg_dump` | `output_file, format="custom", schema_only=False, ...` | - |
| `pg_restore` | `input_file, clean=False, if_exists=True, ...` | - |
| `copy_to_csv` | `table, output_file, schema="public", ...` | `int` |
| `copy_from_csv` | `table, input_file, schema="public", ...` | `int` |

### Database Admin Methods

| Method | Parameters | Returns |
|--------|------------|---------|
| `create_database` | `name, owner=None, template="template1"` | - |
| `drop_database` | `name, if_exists=True` | - |
| `database_exists` | `name` | `bool` |
| `list_databases` | - | `list[str]` |

### Size/Stats Methods

| Method | Parameters | Returns |
|--------|------------|---------|
| `size` | `pretty=True` | `str` or `int` |
| `table_size` | `table, schema="public", pretty=True` | `str` or `int` |
| `table_sizes` | `schema="public", limit=20` | `list[dict]` |

### Maintenance Methods

| Method | Parameters | Returns |
|--------|------------|---------|
| `vacuum` | `table=None, schema="public", analyze=True, full=False` | - |
| `analyze` | `table=None, schema="public"` | - |
| `explain` | `sql, params=None, analyze=False, format="text"` | `list[str]` |

---

## AsyncDatabase

Asynchronous database interface. Same methods as Database with async/await.

```python
from pycopg import AsyncDatabase
```

### Additional Async Methods

| Method | Parameters | Returns |
|--------|------------|---------|
| `stream` | `sql, params=None, batch_size=1000` | `AsyncIterator[dict]` |
| `insert_many` | `table, rows, schema="public", on_conflict=None` | `int` |
| `upsert_many` | `table, rows, conflict_columns, update_columns=None, ...` | `int` |
| `listen` | `channel` | `AsyncIterator[str]` |
| `notify` | `channel, payload=""` | - |

### Async Context Managers

| Method | Parameters | Yields |
|--------|------------|--------|
| `connect` | `autocommit=False` | `AsyncConnection` |
| `cursor` | `autocommit=False` | `AsyncCursor` |
| `transaction` | - | `AsyncConnection` |

---

## PooledDatabase

Synchronous connection pool.

```python
from pycopg import PooledDatabase
```

### Constructor

```python
PooledDatabase(
    config: Config,
    min_size: int = 2,
    max_size: int = 10,
    max_idle: float = 300.0,
    max_lifetime: float = 3600.0,
    timeout: float = 30.0,
    num_workers: int = 3,
)
```

### Methods

| Method | Parameters | Returns |
|--------|------------|---------|
| `connection` | - | `ContextManager[Connection]` |
| `execute` | `sql, params=None` | `list[dict]` |
| `execute_many` | `sql, params_seq` | `int` |
| `resize` | `min_size, max_size` | - |
| `check` | - | - |
| `wait` | `timeout=30.0` | - |
| `close` | - | - |

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `stats` | `dict` | Pool statistics |

---

## AsyncPooledDatabase

Asynchronous connection pool.

```python
from pycopg import AsyncPooledDatabase
```

### Constructor

Same as PooledDatabase.

### Methods

| Method | Parameters | Returns |
|--------|------------|---------|
| `open` | - | `Coroutine` |
| `connection` | - | `AsyncContextManager[AsyncConnection]` |
| `execute` | `sql, params=None` | `Coroutine[list[dict]]` |
| `execute_many` | `sql, params_seq` | `Coroutine[int]` |
| `fetch_one` | `sql, params=None` | `Coroutine[Optional[dict]]` |
| `fetch_val` | `sql, params=None` | `Coroutine[Any]` |
| `transaction` | - | `AsyncContextManager[AsyncConnection]` |
| `resize` | `min_size, max_size` | - |
| `check` | - | `Coroutine` |
| `close` | - | `Coroutine` |

---

## Migrator

SQL migration manager.

```python
from pycopg import Migrator
```

### Constructor

```python
Migrator(
    db: Database,
    migrations_dir: Union[str, Path],
    table: str = "schema_migrations",
)
```

### Methods

| Method | Parameters | Returns |
|--------|------------|---------|
| `status` | - | `dict` |
| `pending` | - | `list[Migration]` |
| `applied` | - | `list[dict]` |
| `migrate` | `target=None` | `list[Migration]` |
| `rollback` | `steps=1` | `list[dict]` |
| `create` | `name` | `Path` |

---

## Exceptions

```python
from pycopg import (
    PycopgError,        # Base exception
    ConnectionError,    # Connection failed
    ConfigurationError, # Bad config
    ExtensionNotAvailable,  # Missing extension
    TableNotFound,      # Table doesn't exist
    InvalidIdentifier,  # SQL injection attempt
    MigrationError,     # Migration failed
)
```
