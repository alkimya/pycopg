# Connection Pooling

Connection pooling improves performance by reusing database connections instead of creating new ones for each request.

## When to Use Pooling

Use connection pooling when:
- Building web applications with many concurrent requests
- Running background workers that need frequent database access
- Any application where connection overhead is significant

## Sync Pool: PooledDatabase

```python
from pycopg import PooledDatabase

# Create pool
db = PooledDatabase.from_env(
    min_size=5,        # Minimum connections to keep open
    max_size=20,       # Maximum connections allowed
    max_idle=300.0,    # Close idle connections after 5 minutes
    max_lifetime=3600.0,  # Close connections after 1 hour
    timeout=30.0,      # Wait timeout for getting a connection
)

# Use connections from pool
with db.connection() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM users")
        users = cur.fetchall()
    conn.commit()

# Or use simplified API
users = db.execute("SELECT * FROM users WHERE active = %s", [True])
count = db.execute_many("INSERT INTO users (name) VALUES (%s)", [("Alice",), ("Bob",)])

# Clean up
db.close()
```

### Context Manager

```python
from pycopg import PooledDatabase

with PooledDatabase.from_env(min_size=5, max_size=20) as db:
    users = db.execute("SELECT * FROM users")
    # Pool automatically closed on exit
```

### Pool Statistics

```python
stats = db.stats
# {
#     'pool_min': 5,
#     'pool_max': 20,
#     'pool_size': 8,
#     'pool_available': 5,
#     'requests_waiting': 0,
#     'requests_num': 1234,
# }
```

### Dynamic Resizing

```python
# Resize pool based on load
db.resize(min_size=10, max_size=50)

# Check pool health
db.check()

# Wait for pool to be ready
db.wait(timeout=30.0)
```

## Async Pool: AsyncPooledDatabase

```python
from pycopg import AsyncPooledDatabase

# Create pool
db = AsyncPooledDatabase.from_env(
    min_size=5,
    max_size=20,
    max_idle=300.0,
    max_lifetime=3600.0,
    timeout=30.0,
)

# Open pool (required before use)
await db.open()

# Use connections
async with db.connection() as conn:
    async with conn.cursor() as cur:
        await cur.execute("SELECT * FROM users")
        users = await cur.fetchall()

# Simplified API
users = await db.execute("SELECT * FROM users")
user = await db.fetch_one("SELECT * FROM users WHERE id = %s", [1])
count = await db.fetch_val("SELECT COUNT(*) FROM users")

# Transactions
async with db.transaction() as conn:
    await conn.execute("INSERT INTO users (name) VALUES (%s)", ["Alice"])
    await conn.execute("UPDATE stats SET count = count + 1")

# Close pool
await db.close()
```

### Async Context Manager

```python
async with AsyncPooledDatabase.from_env(min_size=5, max_size=20) as db:
    users = await db.execute("SELECT * FROM users")
    # Pool automatically opened and closed
```

## Pool Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `min_size` | 2 | Minimum connections to maintain |
| `max_size` | 10 | Maximum connections allowed |
| `max_idle` | 300.0 | Close idle connections after N seconds |
| `max_lifetime` | 3600.0 | Close connections after N seconds |
| `timeout` | 30.0 | Wait timeout for getting a connection |
| `num_workers` | 3 | Background workers for pool management |

## Best Practices

### 1. Size Your Pool Appropriately

```python
# For a web app with 4 workers, each handling 10 concurrent requests
# max_size = workers * concurrent_per_worker = 4 * 10 = 40
db = PooledDatabase.from_env(min_size=10, max_size=40)
```

### 2. Use Connection Context Managers

```python
# Good: Connection returned to pool quickly
with db.connection() as conn:
    result = conn.execute("SELECT * FROM users")
    # Process result here

# Bad: Connection held longer than needed
conn = db.connection().__enter__()
result = conn.execute("SELECT * FROM users")
# ... other work ...
conn.close()  # May forget to close
```

### 3. Handle Pool Exhaustion

```python
from psycopg_pool import PoolTimeout

try:
    with db.connection() as conn:
        result = conn.execute("SELECT * FROM users")
except PoolTimeout:
    # Pool is exhausted, all connections in use
    logger.warning("Database pool exhausted")
    raise ServiceUnavailable("Database busy")
```

### 4. Monitor Pool Health

```python
import logging

def log_pool_stats(db):
    stats = db.stats
    logging.info(
        f"Pool: {stats['pool_size']}/{stats['pool_max']} "
        f"available={stats['pool_available']} "
        f"waiting={stats['requests_waiting']}"
    )
```

## FastAPI Integration

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from pycopg import AsyncPooledDatabase

db: AsyncPooledDatabase = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global db
    db = AsyncPooledDatabase.from_env(min_size=5, max_size=20)
    await db.open()
    yield
    await db.close()

app = FastAPI(lifespan=lifespan)

async def get_db():
    return db

@app.get("/users")
async def list_users(db: AsyncPooledDatabase = Depends(get_db)):
    return await db.execute("SELECT * FROM users")

@app.get("/users/{user_id}")
async def get_user(user_id: int, db: AsyncPooledDatabase = Depends(get_db)):
    return await db.fetch_one("SELECT * FROM users WHERE id = %s", [user_id])
```

## Flask Integration

```python
from flask import Flask, g
from pycopg import PooledDatabase

app = Flask(__name__)

# Create pool at startup
pool = PooledDatabase.from_env(min_size=5, max_size=20)

def get_db():
    if 'db' not in g:
        g.db = pool
    return g.db

@app.route('/users')
def list_users():
    db = get_db()
    users = db.execute("SELECT * FROM users")
    return {'users': users}

@app.teardown_appcontext
def close_db(e=None):
    # Connections automatically returned to pool
    pass

# Close pool on shutdown
import atexit
atexit.register(pool.close)
```
