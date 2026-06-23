# pycopg

High-level Python API for PostgreSQL/PostGIS/TimescaleDB built on [psycopg 3](https://www.psycopg.org/psycopg3/).

Simple, powerful, pythonic database operations with sync and async support.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Installation

```bash
# Basic installation
pip install pycopg

# With .env file support
pip install pycopg[dotenv]

# With PostGIS support
pip install pycopg[geo]

# Full installation (all optional dependencies)
pip install pycopg[all]
```

## Development

Contributors use [uv](https://docs.astral.sh/uv/) for project management.

```bash
# Clone and set up dev environment
git clone https://github.com/alkimya/pycopg.git
cd pycopg
uv sync --all-extras --dev

# Run tests
uv run pytest

# Lint
uv run ruff check pycopg tests

# Format
uv run black pycopg tests

# Build wheel + sdist
uv build
```

## Quick Start

```python
from pycopg import Database, Config

# Connect from environment variables
db = Database.from_env()

# Or with explicit config
db = Database(Config(
    host="localhost",
    port=5432,
    database="mydb",
    user="postgres",
    password="secret"
))

# Or from URL
db = Database.from_url("postgresql://user:pass@localhost:5432/mydb")

# Create a new database and connect to it
db = Database.create("myapp", user="admin", password="secret")

# Or create using credentials from .env
db = Database.create_from_env("myapp")
```

## Accessor Namespaces

pycopg organizes database operations into typed accessor namespaces:

| Accessor | Access | Methods |
| -------- | ------ | ------- |
| `db.schema.*` | DDL + introspection | `list_schemas`, `list_tables`, `table_info`, `create_index`, … (27 methods) |
| `db.admin.*` | Roles & permissions | `create_role`, `grant`, `revoke`, `list_roles`, … (11 methods) |
| `db.maint.*` | Maintenance | `size`, `vacuum`, `analyze`, `explain`, … (6 methods) |
| `db.backup.*` | Backup & restore | `pg_dump`, `pg_restore`, `copy_to_csv`, `copy_from_csv` (4 methods) |
| `db.timescale.*` | TimescaleDB | `create_hypertable`, `enable_compression`, `time_bucket`, `show_chunks`, … (15 methods) |
| `db.spatial.*` | PostGIS helpers | `contains`, `within`, `intersects`, `create_spatial_index`, … (13 methods) |
| `db.etl.*` | ETL pipelines | `run`, `history`, `last_run`, `init` (4 methods) |

All accessors expose an identical async surface on `AsyncDatabase` (e.g. `async_db.admin.*`).
Flat methods are deprecated as of v0.6.0; see [MIGRATION.md](MIGRATION.md).

## Core Features

### Database Exploration

```python
db.schema.list_schemas()           # ['public', 'app', ...]
db.schema.list_tables("public")    # ['users', 'orders', ...]
db.schema.table_info("users")      # Column details
db.schema.list_columns("users")    # ['id', 'name', 'email']
db.schema.columns_with_types("users") # [('id', 'integer'), ('name', 'text')]
db.maint.size()                    # '256 MB'
db.maint.table_sizes("public")     # Size of each table
```

### Query Execution

```python
# Select with parameters
users = db.execute("SELECT * FROM users WHERE active = %s", [True])

# Insert/Update
db.execute("INSERT INTO users (name, email) VALUES (%s, %s)", ["Alice", "alice@example.com"])

# Batch insert (optimized with executemany)
db.execute_many(
    "INSERT INTO users (name) VALUES (%s)",
    [("Alice",), ("Bob",), ("Charlie",)]
)

# High-performance batch insert (single INSERT with multiple VALUES)
db.insert_batch("users", [
    {"name": "Alice", "email": "alice@example.com"},
    {"name": "Bob", "email": "bob@example.com"},
    {"name": "Charlie", "email": "charlie@example.com"},
])

# Upsert with conflict handling
db.insert_batch("users", rows, on_conflict="(email) DO UPDATE SET name = EXCLUDED.name")

# Ultra-fast bulk insert using COPY protocol (10-100x faster for large datasets)
db.copy_insert("users", rows)
```

### Session Mode (Connection Reuse)

For multiple sequential operations, use session mode to reuse a single connection:

```python
# Without session: each operation opens/closes a connection
db.execute("SELECT 1")  # Open, execute, close
db.execute("SELECT 2")  # Open, execute, close

# With session: single connection for all operations (much faster)
with db.session() as session:
    session.execute("SELECT 1")
    session.execute("SELECT 2")
    session.insert_batch("users", rows)
    # Connection closed automatically at end

# Useful for batch operations
with db.session() as session:
    for table in tables:
        session.truncate_table(table)
        session.insert_batch(table, data[table])
```

### DataFrame Operations

```python
import pandas as pd

# Create table from DataFrame
df = pd.DataFrame({"name": ["Alice", "Bob"], "age": [30, 25]})
db.from_dataframe(df, "users", primary_key="id")

# Read table to DataFrame
users_df = db.to_dataframe("users")
users_df = db.to_dataframe(sql="SELECT * FROM users WHERE age > :min_age", params={"min_age": 25})
```

## Roles & Permissions

```python
# Create users
db.admin.create_role("appuser", password="secret123", login=True)
db.admin.create_role("admin", password="secret", superuser=True)

# Create group roles
db.admin.create_role("readonly", login=False)
db.admin.create_role("analyst", password="secret", in_roles=["readonly"])

# Grant privileges
db.admin.grant("SELECT", "users", "readonly")
db.admin.grant("ALL", "orders", "appuser")
db.admin.grant("SELECT", "ALL TABLES", "readonly", schema="public")
db.admin.grant("USAGE", "myschema", "appuser", object_type="SCHEMA")

# Revoke privileges
db.admin.revoke("INSERT", "users", "readonly")

# Role management
db.admin.grant_role("readonly", "analyst")
db.admin.alter_role("appuser", password="newpassword")
db.admin.list_roles()
db.admin.list_role_grants("appuser")
```

## Backup & Restore

```python
# Full backup (custom format - compressed)
db.backup.pg_dump("backup.dump")

# SQL format
db.backup.pg_dump("backup.sql", format="plain")

# Schema only
db.backup.pg_dump("schema.sql", format="plain", schema_only=True)

# Specific tables
db.backup.pg_dump("users.dump", tables=["users", "profiles"])

# Parallel backup (directory format)
db.backup.pg_dump("backup_dir", format="directory", jobs=4)

# Restore
db.backup.pg_restore("backup.dump")
db.backup.pg_restore("backup.dump", clean=True)  # Drop and recreate
db.backup.pg_restore("backup_dir", jobs=4)        # Parallel restore

# CSV export/import
db.backup.copy_to_csv("users", "users.csv")
db.backup.copy_from_csv("users", "users.csv")
```

## Async Support

```python
from pycopg import AsyncDatabase

db = AsyncDatabase.from_env()

# Basic queries
users = await db.execute("SELECT * FROM users")
user = await db.fetch_one("SELECT * FROM users WHERE id = %s", [1])
count = await db.fetch_val("SELECT COUNT(*) FROM users")

# Transactions
async with db.transaction() as conn:
    await conn.execute("INSERT INTO users (name) VALUES (%s)", ["Alice"])
    await conn.execute("UPDATE stats SET count = count + 1")
    # Auto-commits on success, rolls back on exception

# Streaming large results
async for row in db.stream("SELECT * FROM large_table", batch_size=1000):
    process(row)

# Batch operations
await db.insert_many("users", [
    {"name": "Alice", "email": "alice@example.com"},
    {"name": "Bob", "email": "bob@example.com"},
])

await db.upsert_many("users", rows, conflict_columns=["email"], update_columns=["name"])

# Pub/Sub with LISTEN/NOTIFY
await db.notify("events", '{"type": "user_created", "id": 1}')

async for payload in db.listen("events"):
    event = json.loads(payload)
    handle_event(event)
```

### Async DataFrame Operations

```python
import pandas as pd
import geopandas as gpd

# Read table to DataFrame
df = await db.to_dataframe("users")
df = await db.to_dataframe(sql="SELECT * FROM users WHERE age > :min", params={"min": 18})

# Insert from DataFrame
df = pd.DataFrame({"name": ["Alice", "Bob"], "age": [30, 25]})
await db.from_dataframe(df, "users_backup", primary_key="id")

# Spatial data
gdf = await db.to_geodataframe("parcels")
await db.from_geodataframe(gdf, "parcels_copy", spatial_index=True)
```

### Async Admin Operations

```python
# Maintenance
await db.maint.vacuum("users", analyze=True)
await db.maint.analyze("orders")

# Query analysis
plan = await db.maint.explain("SELECT * FROM users WHERE email = %s", ["test@example.com"])

# Indexes
await db.schema.create_index("users", "email", unique=True)
await db.schema.drop_index("idx_users_email")

# Tables
await db.schema.drop_table("temp_data")
```

### Async Backup Operations

```python
# Full backup
await db.backup.pg_dump("backup.dump")
await db.backup.pg_dump("backup.sql", format="plain")

# Restore
await db.backup.pg_restore("backup.dump")

# CSV export/import
await db.backup.copy_to_csv("users", "users.csv")
await db.backup.copy_from_csv("users", "users.csv")
```

### Async Role Management

```python
# Create roles
await db.admin.create_role("analyst", password="secret", login=True)
await db.admin.create_role("readonly", login=False)

# Grant/revoke privileges
await db.admin.grant("SELECT", "users", "readonly")
await db.admin.grant("ALL", "orders", "analyst")
await db.admin.revoke("INSERT", "users", "readonly")

# Role membership
await db.admin.grant_role("readonly", "analyst")
```

### Async PostGIS & TimescaleDB

```python
# PostGIS: Spatial indexes
await db.spatial.create_spatial_index("parcels", "geometry")

# TimescaleDB: Hypertables
await db.timescale.create_hypertable("events", "timestamp", chunk_time_interval="1 week")

# TimescaleDB: Compression
await db.timescale.enable_compression("events", segment_by="device_id", order_by="timestamp DESC")
await db.timescale.add_compression_policy("events", compress_after="30 days")

# TimescaleDB: Retention
await db.timescale.add_retention_policy("logs", drop_after="90 days")
```

## Connection Pooling

For high-performance applications with many concurrent requests:

```python
from pycopg import PooledDatabase, AsyncPooledDatabase

# Sync pool
db = PooledDatabase.from_env(
    min_size=5,      # Minimum connections
    max_size=20,     # Maximum connections
    max_idle=300,    # Close idle connections after 5 minutes
    timeout=30,      # Wait timeout for connection
)

# Use connections from pool
with db.connection() as conn:
    result = conn.execute("SELECT * FROM users")

# Or use simplified API (auto-manages connection)
users = db.execute("SELECT * FROM users WHERE active = %s", [True])

# Monitor pool stats
print(db.stats)
# {'pool_min': 5, 'pool_max': 20, 'pool_size': 8, 'pool_available': 5, ...}

# Resize pool dynamically
db.resize(min_size=10, max_size=50)

# Clean up
db.close()

# Async pool
async with AsyncPooledDatabase.from_env(min_size=5, max_size=20) as db:
    users = await db.execute("SELECT * FROM users")

    async with db.transaction() as conn:
        await conn.execute("INSERT INTO users (name) VALUES (%s)", ["Alice"])
```

## Resilience

pycopg includes automatic resilience features to handle transient failures and prevent runaway queries.

### Automatic Retry with Backoff

Connection failures are automatically retried with exponential backoff:

```python
from pycopg import Database, AsyncDatabase

# Retry automatically enabled on connect()
db = Database.from_env()
# On connection failure: retries 3 times with exponential backoff (1-10s)

# Same for async
db = AsyncDatabase.from_env()
# Automatically retries on OperationalError (connection failures only)
```

**Details:**

- 3 retry attempts (initial + 2 retries)
- Exponential backoff: 1s, 2.7s, 7.4s
- Only retries `OperationalError` (connection failures, not SQL errors)
- Applies to `connect()` method only (pools have built-in reconnection)

### Statement Timeout

Prevent runaway queries from consuming resources:

```python
from pycopg import Database, Config

# Configure timeout for all queries
config = Config.from_env()
config.statement_timeout = 30000  # 30 seconds (milliseconds)
db = Database(config)

# Queries exceeding 30s will be cancelled automatically

# Or with URL
db = Database.from_url(
    "postgresql://user:pass@localhost:5432/mydb",
    statement_timeout=30000
)
```

**Recommended values:**

- Web API endpoints: 5000-10000ms (5-10s)
- Background jobs: 60000-300000ms (1-5 minutes)
- Data warehousing: 600000+ (10+ minutes)

### Configurable Batch Size

Optimize memory usage and performance for bulk inserts:

```python
# Default batch size is 1000
db.insert_batch("users", large_dataset)

# For memory-constrained environments or very large rows
db.insert_batch("users", large_dataset, batch_size=500)

# For small rows and high performance
db.insert_batch("users", large_dataset, batch_size=5000)
```

**When to adjust:**

- Large rows (many columns, JSONB, TEXT): decrease to 100-500
- Small rows (few columns, simple types): increase to 2000-5000
- Memory errors: decrease batch size
- Performance tuning: benchmark different values

## Migrations

Simple SQL-based migrations using numbered files:

```text
migrations/
├── 001_create_users.sql
├── 002_add_email_index.sql
└── 003_create_orders.sql
```

```python
from pycopg import Database, Migrator

db = Database.from_env()
migrator = Migrator(db, "migrations/")

# Check status
status = migrator.status()
print(f"Applied: {status['applied_count']}, Pending: {status['pending_count']}")

# Run all pending migrations
applied = migrator.migrate()
for m in applied:
    print(f"Applied: {m}")

# Run up to specific version
migrator.migrate(target=5)

# Rollback last migration
migrator.rollback()

# Rollback last 3 migrations
migrator.rollback(steps=3)

# Create new migration
path = migrator.create("add_orders_table")
# Creates: migrations/004_add_orders_table.sql
```

Migration file format (with optional rollback):

```sql
-- Migration: create_users
-- Created: 2024-01-15

-- UP
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_users_email ON users(email);

-- DOWN
DROP TABLE users;
```

Migrations are tracked in `schema_migrations` table with version, name, and applied timestamp.

## PostGIS Support

```python
import geopandas as gpd

# Ensure PostGIS is installed
db.schema.create_extension("postgis")

# Create spatial table
gdf = gpd.read_file("parcels.geojson")
db.from_geodataframe(gdf, "parcels", spatial_index=True)

# Read spatial data
parcels = db.to_geodataframe("parcels")

# Spatial queries
db.execute("""
    SELECT * FROM parcels
    WHERE ST_Within(geometry, ST_MakeEnvelope(-122.5, 37.7, -122.3, 37.9, 4326))
""")
```

## TimescaleDB Support

```python
# Ensure TimescaleDB is installed
db.schema.create_extension("timescaledb")

# Create hypertable
db.timescale.create_hypertable("events", "timestamp", chunk_time_interval="1 week")

# Enable compression
db.timescale.enable_compression("events", segment_by="device_id", order_by="timestamp DESC")
db.timescale.add_compression_policy("events", compress_after="30 days")

# Data retention
db.timescale.add_retention_policy("logs", drop_after="90 days")

# Query hypertables
db.timescale.list_hypertables()
```

### v0.8.0 Highlights — new TimescaleDB methods

```python
# Time bucketing — returns a pandas DataFrame directly
df = db.timescale.time_bucket(
    "events", "time", "1 hour",
    aggregates="device_id, AVG(temperature) AS avg_temp",
    into="df",
)

# Chunk management — list and safely remove old chunks
old = db.timescale.show_chunks("events", older_than="30 days")
would_drop = db.timescale.drop_chunks("events", older_than="90 days", dry_run=True)
db.timescale.drop_chunks("events", older_than="90 days")  # irreversible

# Continuous aggregate lifecycle
db.timescale.create_continuous_aggregate(
    "hourly",
    select_sql="SELECT time_bucket('1 hour', time) AS bucket, device_id, AVG(temperature) AS avg_temp FROM events GROUP BY bucket, device_id",
)
db.timescale.add_continuous_aggregate_policy("hourly", start_offset="3 hours", end_offset="1 hour")
```

For the full advanced guide (chunk dimensions, gap filling, license notes) see the
[TimescaleDB documentation](docs/timescaledb.md) or the
[RTD timescaledb page](https://pycopg.readthedocs.io/en/latest/timescaledb.html).

## Schema & Table Management

```python
# Schemas
db.schema.create_schema("app")
db.schema.drop_schema("old_schema", cascade=True)

# Tables
db.schema.drop_table("users")
db.schema.truncate_table("logs")

# Indexes
db.schema.create_index("users", "email", unique=True)
db.schema.create_index("products", ["category", "price"])
db.schema.create_index("documents", "content", method="gin")

# Constraints
db.schema.add_primary_key("users", "id")
db.schema.add_foreign_key("orders", "user_id", "users", "id", on_delete="CASCADE")
db.schema.add_unique_constraint("users", "email")
```

## Database Administration

```python
# Create/drop databases
db.schema.create_database("myapp", owner="appuser")
db.schema.drop_database("olddb")
db.schema.database_exists("myapp")
db.schema.list_databases()

# Maintenance
db.maint.vacuum("users", analyze=True)
db.maint.analyze("users")

# Query analysis
plan = db.maint.explain("SELECT * FROM users WHERE email = %s", ["test@example.com"])
print("\n".join(plan))
```

## Environment Variables

pycopg reads configuration from environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | Full connection URL | - |
| `DB_HOST` / `PGHOST` | Database host | localhost |
| `DB_PORT` / `PGPORT` | Database port | 5432 |
| `DB_NAME` / `PGDATABASE` | Database name | postgres |
| `DB_USER` / `PGUSER` | Database user | postgres |
| `DB_PASSWORD` / `PGPASSWORD` | Database password | - |

## License

MIT License - Copyright (c) 2026 Loc Cosnier <loc.cosnier@pm.me>
