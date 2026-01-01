# pycopg

High-level Python API for PostgreSQL/PostGIS/TimescaleDB.

Simple, powerful, pythonic database operations with sync and async support.

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

## Core Features

### Database Exploration

```python
db.list_schemas()           # ['public', 'app', ...]
db.list_tables("public")    # ['users', 'orders', ...]
db.table_info("users")      # Column details
db.size()                   # '256 MB'
db.table_sizes("public")    # Size of each table
```

### Query Execution

```python
# Select with parameters
users = db.execute("SELECT * FROM users WHERE active = %s", [True])

# Insert/Update
db.execute("INSERT INTO users (name, email) VALUES (%s, %s)", ["Alice", "alice@example.com"])

# Batch insert
db.execute_many(
    "INSERT INTO users (name) VALUES (%s)",
    [("Alice",), ("Bob",), ("Charlie",)]
)
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
db.create_role("appuser", password="secret123", login=True)
db.create_role("admin", password="secret", superuser=True)

# Create group roles
db.create_role("readonly", login=False)
db.create_role("analyst", password="secret", in_roles=["readonly"])

# Grant privileges
db.grant("SELECT", "users", "readonly")
db.grant("ALL", "orders", "appuser")
db.grant("SELECT", "ALL TABLES", "readonly", schema="public")
db.grant("USAGE", "myschema", "appuser", object_type="SCHEMA")

# Revoke privileges
db.revoke("INSERT", "users", "readonly")

# Role management
db.grant_role("readonly", "analyst")
db.alter_role("appuser", password="newpassword")
db.list_roles()
db.list_role_grants("appuser")
```

## Backup & Restore

```python
# Full backup (custom format - compressed)
db.pg_dump("backup.dump")

# SQL format
db.pg_dump("backup.sql", format="plain")

# Schema only
db.pg_dump("schema.sql", format="plain", schema_only=True)

# Specific tables
db.pg_dump("users.dump", tables=["users", "profiles"])

# Parallel backup (directory format)
db.pg_dump("backup_dir", format="directory", jobs=4)

# Restore
db.pg_restore("backup.dump")
db.pg_restore("backup.dump", clean=True)  # Drop and recreate
db.pg_restore("backup_dir", jobs=4)       # Parallel restore

# CSV export/import
db.copy_to_csv("users", "users.csv")
db.copy_from_csv("users", "users.csv")
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
db.create_extension("postgis")

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
db.create_extension("timescaledb")

# Create hypertable
db.create_hypertable("events", "timestamp", chunk_time_interval="1 week")

# Enable compression
db.enable_compression("events", segment_by="device_id", order_by="timestamp DESC")
db.add_compression_policy("events", compress_after="30 days")

# Data retention
db.add_retention_policy("logs", drop_after="90 days")

# Query hypertables
db.list_hypertables()
```

## Schema & Table Management

```python
# Schemas
db.create_schema("app")
db.drop_schema("old_schema", cascade=True)

# Tables
db.drop_table("users")
db.truncate_table("logs")

# Indexes
db.create_index("users", "email", unique=True)
db.create_index("products", ["category", "price"])
db.create_index("documents", "content", method="gin")

# Constraints
db.add_primary_key("users", "id")
db.add_foreign_key("orders", "user_id", "users", "id", on_delete="CASCADE")
db.add_unique_constraint("users", "email")
```

## Database Administration

```python
# Create/drop databases
db.create_database("myapp", owner="appuser")
db.drop_database("olddb")
db.database_exists("myapp")
db.list_databases()

# Maintenance
db.vacuum("users", analyze=True)
db.analyze("users")

# Query analysis
plan = db.explain("SELECT * FROM users WHERE email = %s", ["test@example.com"])
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
