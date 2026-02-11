# AsyncDatabase Class

The `AsyncDatabase` class provides async/await support for all database operations.

## Connection

```python
from pycopg import AsyncDatabase

# From environment
db = AsyncDatabase.from_env()

# From URL
db = AsyncDatabase.from_url("postgresql://user:pass@localhost:5432/mydb")

# As async context manager
async with AsyncDatabase.from_env() as db:
    users = await db.execute("SELECT * FROM users")
```

## Query Execution

### execute()

```python
# SELECT queries
users = await db.execute("SELECT * FROM users WHERE active = %s", [True])
# [{'id': 1, 'name': 'Alice', 'active': True}, ...]

# INSERT/UPDATE/DELETE
await db.execute("INSERT INTO users (name) VALUES (%s)", ["Alice"])
await db.execute("UPDATE users SET active = %s WHERE id = %s", [False, 1])

# With autocommit
await db.execute("CREATE DATABASE newdb", autocommit=True)
```

### execute_many()

Execute SQL for multiple parameter sets. Uses `executemany()` internally for better performance.

```python
count = await db.execute_many(
    "INSERT INTO users (name, email) VALUES (%s, %s)",
    [
        ("Alice", "alice@example.com"),
        ("Bob", "bob@example.com"),
    ]
)
print(f"Inserted {count} rows")
```

### insert_batch()

High-performance batch insert using a single INSERT with multiple VALUES tuples.

```python
count = await db.insert_batch("users", [
    {"name": "Alice", "email": "alice@example.com"},
    {"name": "Bob", "email": "bob@example.com"},
])
print(f"Inserted {count} rows")

# With ON CONFLICT (upsert)
await db.insert_batch("users", rows, on_conflict="(email) DO UPDATE SET name = EXCLUDED.name")
```

### copy_insert()

Ultra-fast bulk insert using PostgreSQL's COPY protocol.

```python
rows = [{"name": f"User {i}", "email": f"user{i}@example.com"} for i in range(100000)]
count = await db.copy_insert("users", rows)
```

### fetch_one()

```python
user = await db.fetch_one("SELECT * FROM users WHERE id = %s", [1])
# {'id': 1, 'name': 'Alice', ...}

# Returns None if not found
missing = await db.fetch_one("SELECT * FROM users WHERE id = %s", [9999])
```

### fetch_val()

```python
count = await db.fetch_val("SELECT COUNT(*) FROM users")
# 42

name = await db.fetch_val("SELECT name FROM users WHERE id = %s", [1])
# 'Alice'
```

## Session Mode

Session mode keeps a single connection open for multiple operations, reducing connection overhead.

```python
# Without session: each operation opens/closes a connection
await db.execute("SELECT 1")  # Open, execute, close
await db.execute("SELECT 2")  # Open, execute, close

# With session: single connection for all operations
async with db.session() as session:
    await session.execute("SELECT 1")
    await session.execute("SELECT 2")
    await session.insert_batch("users", rows)
    # Connection closed automatically at end

# With autocommit mode
async with db.session(autocommit=True) as session:
    await session.execute("CREATE DATABASE newdb")

# Check if in session mode
if db.in_session:
    print("Currently in session mode")
```

> **Note:** Nested sessions are not supported and will raise a `RuntimeError`.

## Context Managers

### connect()

Async connection context manager.

```python
async with db.connect() as conn:
    result = await conn.execute("SELECT * FROM users")
    rows = await result.fetchall()

# With autocommit
async with db.connect(autocommit=True) as conn:
    await conn.execute("CREATE DATABASE newdb")
```

### cursor()

Async cursor context manager with dict rows.

```python
async with db.cursor() as cur:
    await cur.execute("SELECT * FROM users WHERE id = %s", [1])
    user = await cur.fetchone()  # Returns dict
    print(user['name'])
```

### transaction()

Transaction context manager with automatic commit/rollback.

```python
async with db.transaction() as conn:
    await conn.execute("INSERT INTO users (name) VALUES (%s)", ["Alice"])
    await conn.execute("UPDATE stats SET count = count + 1")
    # Commits automatically on success
    # Rolls back automatically on exception
```

## Streaming Results

For large result sets, use streaming to avoid loading everything into memory.

```python
async for row in db.stream("SELECT * FROM large_table", batch_size=1000):
    process(row)

# With parameters
async for row in db.stream(
    "SELECT * FROM events WHERE date > %s",
    params=["2024-01-01"],
    batch_size=5000
):
    process(row)
```

## Batch Operations

### insert_many()

Efficiently insert multiple rows.

```python
count = await db.insert_many("users", [
    {"name": "Alice", "email": "alice@example.com"},
    {"name": "Bob", "email": "bob@example.com"},
    {"name": "Charlie", "email": "charlie@example.com"},
])
print(f"Inserted {count} rows")

# With ON CONFLICT
await db.insert_many(
    "users",
    rows,
    on_conflict="(email) DO NOTHING"
)
```

### upsert_many()

Insert or update rows based on conflict columns.

```python
count = await db.upsert_many(
    "users",
    [
        {"id": 1, "name": "Alice Updated", "email": "alice@new.com"},
        {"id": 2, "name": "Bob Updated", "email": "bob@new.com"},
    ],
    conflict_columns=["id"],
    update_columns=["name", "email"]
)
```

## LISTEN/NOTIFY

PostgreSQL's pub/sub mechanism for real-time notifications.

### notify()

Send a notification.

```python
import json

# Simple notification
await db.notify("events", "user_created")

# JSON payload
await db.notify("events", json.dumps({
    "type": "user_created",
    "id": 1,
    "name": "Alice"
}))
```

### listen()

Listen for notifications.

```python
import json

async for payload in db.listen("events"):
    event = json.loads(payload)
    print(f"Received: {event}")

    if event["type"] == "user_created":
        await handle_user_created(event["id"])
```

## Schema Operations

All schema exploration methods are available asynchronously.

```python
# Schemas
schemas = await db.list_schemas()
exists = await db.schema_exists("app")
await db.create_schema("new_schema")

# Tables
tables = await db.list_tables("public")
exists = await db.table_exists("users")
info = await db.table_info("users")  # Column details
# Returns: column_name, data_type, is_nullable, column_default, etc.

# Lightweight column introspection
cols = await db.list_columns("users")
# ['id', 'name', 'email']

types = await db.columns_with_types("users")
# [('id', 'integer'), ('name', 'text')]

count = await db.row_count("users")

# Extensions
extensions = await db.list_extensions()
has_postgis = await db.has_extension("postgis")
await db.create_extension("uuid-ossp")

# Roles
roles = await db.list_roles()
exists = await db.role_exists("appuser")

# Size
size = await db.size()
table_size = await db.table_size("users")
```

## DataFrame Operations

AsyncDatabase supports pandas and geopandas operations using `run_sync` internally, since pandas/geopandas are synchronous libraries.

```python
import pandas as pd
import geopandas as gpd

# Read table to DataFrame
df = await db.to_dataframe("users")

# Write DataFrame to table
await db.from_dataframe(df, "users", if_exists="replace")

# Read spatial table to GeoDataFrame
gdf = await db.to_geodataframe("cities", geometry_column="location")

# Write GeoDataFrame to spatial table
await db.from_geodataframe(
    gdf,
    "cities",
    if_exists="replace",
    spatial_index=True  # Create spatial index automatically
)
```

> **Note:** DataFrame operations use `run_sync` internally to execute synchronous pandas/geopandas code in an async context. This is necessary because pandas and geopandas are not async-aware libraries.

## Admin Operations

Full administrative capabilities are available asynchronously.

```python
# Create table with columns
await db.create_table("products", {
    "id": "SERIAL PRIMARY KEY",
    "name": "TEXT NOT NULL",
    "price": "DECIMAL(10,2)"
})

# Drop table
await db.drop_table("old_table")

# Create index
await db.create_index("products", "name", unique=True)

# Drop index
await db.drop_index("products_name_idx")

# List indexes
indexes = await db.list_indexes("products")

# List constraints
constraints = await db.list_constraints("products")

# Drop schema with cascade
await db.drop_schema("old_schema", cascade=True)

# Get table sizes
sizes = await db.table_sizes("public")
# Returns list of dicts with table names and sizes
```

## Maintenance Operations

Database maintenance operations are fully async.

```python
# Vacuum table (with analyze)
await db.vacuum("large_table", analyze=True)

# Analyze table statistics
await db.analyze("products")

# Explain query plan
plan = await db.explain(
    "SELECT * FROM users WHERE created_at > %s",
    params=["2024-01-01"],
    analyze=True
)
for line in plan:
    print(line)
```

## Backup & Restore Operations

Backup operations use `asyncio.create_subprocess_exec` internally to run pg_dump/pg_restore asynchronously.

```python
# Dump database to file (custom format)
await db.pg_dump("backup.dump")

# Restore database from file
await db.pg_restore("backup.dump", clean=True)

# Export table to CSV
rows_exported = await db.copy_to_csv("users", "users.csv")

# Import table from CSV
rows_imported = await db.copy_from_csv("users", "users.csv")
```

> **Note:** pg_dump and pg_restore require the PostgreSQL client tools to be installed on the system.

## Database Lifecycle

Create and drop databases asynchronously.

```python
# Create new database
await db.create_database("analytics", owner="analyst")

# Drop database
await db.drop_database("old_db")
```

> **Note:** These operations require autocommit mode and appropriate privileges.

## Role Management

Full role and privilege management asynchronously.

```python
# Create role with password
await db.create_role("appuser", password="secret123", login=True)

# Drop role
await db.drop_role("old_user")

# Alter role password
await db.alter_role("appuser", password="newsecret")

# Grant table privileges
await db.grant("SELECT", "users", "appuser")
await db.grant("INSERT,UPDATE", "orders", "appuser")

# Revoke privileges
await db.revoke("DELETE", "users", "appuser")

# Grant role membership
await db.grant_role("admin", "appuser", with_admin=False)

# Revoke role membership
await db.revoke_role("admin", "appuser")

# List role members
members = await db.list_role_members("admin")

# List role grants
grants = await db.list_role_grants("appuser")
```

## PostGIS Operations

PostGIS spatial operations are available asynchronously.

```python
# Create spatial index
await db.create_spatial_index("cities", column="location")

# List geometry columns
geom_cols = await db.list_geometry_columns()
# Returns: table_name, column_name, srid, type
```

## TimescaleDB Operations

TimescaleDB hypertable and policy management asynchronously.

```python
# Create hypertable
await db.create_hypertable("metrics", "timestamp", chunk_time_interval="1 day")

# Enable compression
await db.enable_compression(
    "metrics",
    segment_by="device_id",
    order_by="timestamp DESC"
)

# Add compression policy
await db.add_compression_policy("metrics", compress_after="7 days")

# Add retention policy
await db.add_retention_policy("metrics", drop_after="90 days")

# List hypertables
hypertables = await db.list_hypertables()

# Get hypertable info
info = await db.hypertable_info("metrics")
```

## Complete Example

```python
import asyncio
import json
from pycopg import AsyncDatabase

async def main():
    # Connect
    db = AsyncDatabase.from_env()

    try:
        # Create table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id SERIAL PRIMARY KEY,
                type TEXT NOT NULL,
                data JSONB,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)

        # Insert data
        await db.insert_many("events", [
            {"type": "user.created", "data": {"name": "Alice"}},
            {"type": "user.updated", "data": {"name": "Alice B."}},
        ])

        # Query
        recent = await db.execute("""
            SELECT * FROM events
            WHERE created_at > NOW() - INTERVAL '1 hour'
            ORDER BY created_at DESC
            LIMIT 10
        """)

        for event in recent:
            print(f"{event['type']}: {event['data']}")

        # Stream large results
        async for row in db.stream("SELECT * FROM events", batch_size=100):
            process_event(row)

    finally:
        await db.close()

if __name__ == "__main__":
    asyncio.run(main())
```
