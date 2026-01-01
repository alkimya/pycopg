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

Execute SQL for multiple parameter sets.

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

### Schemas

```python
# List schemas
schemas = db.list_schemas()
# ['public', 'app', 'audit']

# Check if schema exists
if db.schema_exists("app"):
    print("Schema exists")

# Create schema
db.create_schema("new_schema")
db.create_schema("new_schema", owner="appuser")

# Drop schema
db.drop_schema("old_schema")
db.drop_schema("old_schema", cascade=True)  # Drop all objects
```

### Tables

```python
# List tables
tables = db.list_tables("public")
# ['users', 'orders', 'products']

# Check if table exists
if db.table_exists("users"):
    print("Table exists")

# Get column info
columns = db.table_info("users")
# [{'column_name': 'id', 'data_type': 'integer', 'is_nullable': 'NO', ...}, ...]

# Get row count (approximate, fast)
count = db.row_count("users")

# Drop table
db.drop_table("old_table")
db.drop_table("old_table", cascade=True)

# Truncate table
db.truncate_table("logs")
db.truncate_table("logs", cascade=True)
```

### Extensions

```python
# List installed extensions
extensions = db.list_extensions()
# [{'extname': 'plpgsql', 'extversion': '1.0', 'nspname': 'pg_catalog'}, ...]

# Check if extension is installed
if db.has_extension("postgis"):
    print("PostGIS is installed")

# Create extension
db.create_extension("uuid-ossp")
db.create_extension("postgis", schema="extensions")

# Drop extension
db.drop_extension("old_extension")
db.drop_extension("old_extension", cascade=True)
```

## Size & Statistics

```python
# Database size
size = db.size()           # '256 MB'
size_bytes = db.size(pretty=False)  # 268435456

# Table size
size = db.table_size("users")  # '1.2 MB'

# All table sizes
sizes = db.table_sizes("public", limit=10)
# [{'table_name': 'orders', 'total_size': '500 MB', 'data_size': '400 MB', 'index_size': '100 MB'}, ...]
```

## Indexes & Constraints

### Indexes

```python
# Create index
db.create_index("users", "email")
db.create_index("users", "email", unique=True)
db.create_index("products", ["category", "price"])
db.create_index("documents", "content", method="gin")

# List indexes
indexes = db.list_indexes("users")

# Drop index
db.drop_index("idx_users_email")
```

### Constraints

```python
# Primary key
db.add_primary_key("users", "id")
db.add_primary_key("order_items", ["order_id", "product_id"])

# Foreign key
db.add_foreign_key("orders", "user_id", "users", "id")
db.add_foreign_key("orders", "user_id", "users", "id", on_delete="CASCADE")

# Unique constraint
db.add_unique_constraint("users", "email")
db.add_unique_constraint("products", ["category", "sku"])

# List constraints
constraints = db.list_constraints("users")
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
db.create_extension("postgis")

# Create spatial table
gdf = gpd.read_file("parcels.geojson")
db.from_geodataframe(gdf, "parcels", primary_key="id", spatial_index=True)

# Read spatial table
parcels = db.to_geodataframe("parcels")

# Read with spatial query
nearby = db.to_geodataframe(
    sql="SELECT * FROM parcels WHERE ST_DWithin(geometry, ST_Point(-122.4, 37.8)::geography, 1000)"
)
```

## Maintenance

```python
# Vacuum
db.vacuum("users")
db.vacuum("users", full=True)  # Full vacuum (locks table)
db.vacuum()  # Vacuum entire database

# Analyze (update statistics)
db.analyze("users")
db.analyze()  # Analyze entire database

# Query plan
plan = db.explain("SELECT * FROM users WHERE email = %s", ["test@example.com"])
print("\n".join(plan))

# With actual execution
plan = db.explain(
    "SELECT * FROM users WHERE email = %s",
    ["test@example.com"],
    analyze=True
)
```

## Database Administration

```python
# Create database
db.create_database("myapp")
db.create_database("myapp", owner="appuser")

# Drop database
db.drop_database("olddb")

# Check if database exists
if db.database_exists("myapp"):
    print("Database exists")

# List databases
databases = db.list_databases()
```
