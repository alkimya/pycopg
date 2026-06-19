# Database Class

The `Database` class is the main synchronous interface for pycopg.

## Connection

```python
from pycopg import Database, Config

# From environment
db = Database.from_env()

# From URL
db = Database.from_url("postgresql://user:pass@localhost:5432/mydb")

# From Config
db = Database(Config(host="localhost", database="mydb", user="postgres"))

# As context manager
with Database.from_env() as db:
    users = db.execute("SELECT * FROM users")
```

## Query Execution

### execute()

Execute SQL and return results as list of dicts.

```python
# SELECT queries
users = db.execute("SELECT * FROM users WHERE active = %s", [True])
# [{'id': 1, 'name': 'Alice', 'active': True}, ...]

# INSERT/UPDATE/DELETE (returns empty list)
db.execute("INSERT INTO users (name) VALUES (%s)", ["Alice"])
db.execute("UPDATE users SET active = %s WHERE id = %s", [False, 1])
```

### execute_many()

Execute SQL for multiple parameter sets. Uses `executemany()` internally for better performance.

```python
count = db.execute_many(
    "INSERT INTO users (name, email) VALUES (%s, %s)",
    [
        ("Alice", "alice@example.com"),
        ("Bob", "bob@example.com"),
        ("Charlie", "charlie@example.com"),
    ]
)
print(f"Inserted {count} rows")
```

### insert_batch()

High-performance batch insert using a single INSERT with multiple VALUES tuples.
Significantly faster than `execute_many()` for large inserts.

```python
# Basic batch insert
count = db.insert_batch("users", [
    {"name": "Alice", "email": "alice@example.com"},
    {"name": "Bob", "email": "bob@example.com"},
    {"name": "Charlie", "email": "charlie@example.com"},
])
print(f"Inserted {count} rows")

# With ON CONFLICT (upsert)
db.insert_batch("users", rows, on_conflict="(email) DO UPDATE SET name = EXCLUDED.name")

# With custom batch size (default 1000)
db.insert_batch("users", large_rows, batch_size=5000)
```

### copy_insert()

Ultra-fast bulk insert using PostgreSQL's COPY protocol. 10-100x faster than INSERT for large datasets.

```python
# Insert millions of rows efficiently
rows = [{"name": f"User {i}", "email": f"user{i}@example.com"} for i in range(1000000)]
count = db.copy_insert("users", rows)
print(f"Inserted {count} rows using COPY protocol")
```

### fetch_one()

Fetch a single row as dict.

```python
user = db.fetch_one("SELECT * FROM users WHERE id = %s", [1])
# {'id': 1, 'name': 'Alice', 'email': 'alice@example.com'}

# Returns None if no row found
missing = db.fetch_one("SELECT * FROM users WHERE id = %s", [9999])
# None
```

### fetch_val()

Fetch a single value.

```python
count = db.fetch_val("SELECT COUNT(*) FROM users")
# 42

name = db.fetch_val("SELECT name FROM users WHERE id = %s", [1])
# 'Alice'
```

## Session Mode

Session mode keeps a single connection open for multiple operations, significantly reducing connection overhead.

### session()

```python
# Without session: each operation opens/closes a connection
db.execute("SELECT 1")  # Open, execute, close
db.execute("SELECT 2")  # Open, execute, close

# With session: single connection for all operations
with db.session() as session:
    session.execute("SELECT 1")  # Reuse connection
    session.execute("SELECT 2")  # Reuse connection
    session.insert_batch("users", rows)
    # Connection closed automatically at end

# With autocommit mode
with db.session(autocommit=True) as session:
    session.execute("CREATE DATABASE newdb")

# Check if in session mode
if db.in_session:
    print("Currently in session mode")

# Useful for batch operations
with db.session() as session:
    for table in tables:
        session.schema.truncate_table(table)
        session.insert_batch(table, data[table])
```

> **Note:** Nested sessions are not supported and will raise a `RuntimeError`.

## Context Managers

### connect()

Low-level connection context manager.

```python
with db.connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM users")
        rows = cur.fetchall()
    conn.commit()

# With autocommit
with db.connect(autocommit=True) as conn:
    conn.execute("CREATE DATABASE newdb")
```

### cursor()

Cursor context manager with dict row factory.

```python
with db.cursor() as cur:
    cur.execute("SELECT * FROM users WHERE id = %s", [1])
    user = cur.fetchone()  # Returns dict
    print(user['name'])

# With autocommit
with db.cursor(autocommit=True) as cur:
    cur.execute("VACUUM ANALYZE users")
```

## Database Exploration

pycopg provides a `db.schema.*` (and `async_db.schema.*`) accessor namespace for DDL
and introspection, and `db.maint.*` for maintenance operations.

> **Note:** The flat `db.*` DDL and maintenance methods (e.g. `db.list_schemas`,
> `db.vacuum`) are deprecated as of v0.6.0 and will be removed in v0.7.0.
> Use `db.schema.*` and `db.maint.*` instead.
> See [MIGRATION.md](https://github.com/alkimya/pycopg/blob/main/MIGRATION.md) for the complete name mapping.

### Schemas

```python
# List schemas
schemas = db.schema.list_schemas()
# ['public', 'app', 'audit']

# Check if schema exists
if db.schema.schema_exists("app"):
    print("Schema exists")

# Create schema
db.schema.create_schema("new_schema")
db.schema.create_schema("new_schema", owner="appuser")

# Drop schema
db.schema.drop_schema("old_schema")
db.schema.drop_schema("old_schema", cascade=True)  # Drop all objects
```

### Tables

```python
# List tables
tables = db.schema.list_tables("public")
# ['users', 'orders', 'products']

# Check if table exists
if db.schema.table_exists("users"):
    print("Table exists")

# Get column info (detailed)
columns = db.schema.table_info("users")
for col in columns:
    print(f"{col['column_name']}: {col['data_type']} (nullable: {col['is_nullable']})")

# Get updated column names (lightweight)
names = db.schema.list_columns("users")
# ['id', 'name', 'email']

# Get column names with types (lightweight)
cols = db.schema.columns_with_types("users")
# [('id', 'integer'), ('name', 'text'), ('email', 'text')]

# Returns: column_name, data_type, is_nullable, column_default,
#          ordinal_position, character_maximum_length,
#          numeric_precision, numeric_scale

# Get row count (approximate, fast)
count = db.schema.row_count("users")

# Drop table
db.schema.drop_table("old_table")
db.schema.drop_table("old_table", cascade=True)

# Truncate table
db.schema.truncate_table("logs")
db.schema.truncate_table("logs", cascade=True)
```

### Extensions

```python
# List installed extensions
extensions = db.schema.list_extensions()
# [{'extname': 'plpgsql', 'extversion': '1.0', 'nspname': 'pg_catalog'}, ...]

# Check if extension is installed
if db.schema.has_extension("postgis"):
    print("PostGIS is installed")

# Create extension
db.schema.create_extension("uuid-ossp")
db.schema.create_extension("postgis", schema="extensions")

# Drop extension
db.schema.drop_extension("old_extension")
db.schema.drop_extension("old_extension", cascade=True)
```

## Size & Statistics

```python
# Database size
size = db.maint.size()           # '256 MB'
size_bytes = db.maint.size(pretty=False)  # 268435456

# Table size
size = db.maint.table_size("users")  # '1.2 MB'

# All table sizes
sizes = db.maint.table_sizes("public", limit=10)
# [{'table_name': 'orders', 'total_size': '500 MB', 'data_size': '400 MB', 'index_size': '100 MB'}, ...]
```

## Indexes & Constraints

### Indexes

```python
# Create index
db.schema.create_index("users", "email")
db.schema.create_index("users", "email", unique=True)
db.schema.create_index("products", ["category", "price"])
db.schema.create_index("documents", "content", method="gin")

# List indexes
indexes = db.schema.list_indexes("users")

# Drop index
db.schema.drop_index("idx_users_email")
```

### Constraints

```python
# Primary key
db.schema.add_primary_key("users", "id")
db.schema.add_primary_key("order_items", ["order_id", "product_id"])

# Foreign key
db.schema.add_foreign_key("orders", "user_id", "users", "id")
db.schema.add_foreign_key("orders", "user_id", "users", "id", on_delete="CASCADE")

# Unique constraint
db.schema.add_unique_constraint("users", "email")
db.schema.add_unique_constraint("products", ["category", "sku"])

# List constraints
constraints = db.schema.list_constraints("users")
```

## DataFrame Operations

### Pandas

```python
import pandas as pd

# Create table from DataFrame
df = pd.DataFrame({
    "name": ["Alice", "Bob"],
    "age": [30, 25]
})
db.from_dataframe(df, "users", primary_key="id")
db.from_dataframe(df, "users", if_exists="append")
db.from_dataframe(df, "users", if_exists="replace")

# Read table to DataFrame
users_df = db.to_dataframe("users")

# Read with SQL query
active_df = db.to_dataframe(
    sql="SELECT * FROM users WHERE age > :min_age",
    params={"min_age": 25}
)
```

### GeoPandas

```python
import geopandas as gpd

# Ensure PostGIS is installed
db.schema.create_extension("postgis")

# Create spatial table
gdf = gpd.read_file("parcels.geojson")
db.from_geodataframe(gdf, "parcels", primary_key="id", spatial_index=True)

# Read spatial table
parcels = db.to_geodataframe("parcels")

# Read with spatial query — use db.spatial.dwithin for cleaner syntax
nearby = db.spatial.dwithin(
    "parcels",
    point=(-122.4, 37.8),
    distance=1000,
    into="gdf",
)
```

## Maintenance

```python
# Vacuum
db.maint.vacuum("users")
db.maint.vacuum("users", full=True)  # Full vacuum (locks table)
db.maint.vacuum()  # Vacuum entire database

# Analyze (update statistics)
db.maint.analyze("users")
db.maint.analyze()  # Analyze entire database

# Query plan
plan = db.maint.explain("SELECT * FROM users WHERE email = %s", ["test@example.com"])
print("\n".join(plan))

# With actual execution
plan = db.maint.explain(
    "SELECT * FROM users WHERE email = %s",
    ["test@example.com"],
    analyze=True
)
```

## Database Administration

```python
# Create database
db.schema.create_database("myapp")
db.schema.create_database("myapp", owner="appuser")

# Drop database
db.schema.drop_database("olddb")

# Check if database exists
if db.schema.database_exists("myapp"):
    print("Database exists")

# List databases
databases = db.schema.list_databases()
```
