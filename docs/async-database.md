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
info = await db.table_info("users")
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
