# Getting Started

## Installation

### Basic Installation

```bash
pip install pycopg
```

### With Optional Dependencies

```bash
# .env file support (python-dotenv)
pip install pycopg[dotenv]

# PostGIS/GeoPandas support
pip install pycopg[geo]

# All optional dependencies
pip install pycopg[all]

# Development dependencies
pip install pycopg[dev]
```

## Quick Start

### Connecting to a Database

There are three ways to connect:

#### From Environment Variables

```python
from pycopg import Database

# Reads DATABASE_URL or individual DB_* / PG* variables
db = Database.from_env()
```

#### From URL

```python
db = Database.from_url("postgresql://user:pass@localhost:5432/mydb")
```

#### From Config Object

```python
from pycopg import Database, Config

config = Config(
    host="localhost",
    port=5432,
    database="mydb",
    user="postgres",
    password="secret"
)
db = Database(config)
```

#### Create a New Database

Create a new database and connect to it in one step:

```python
# With explicit credentials
db = Database.create("myapp", user="admin", password="secret")

# Using credentials from .env
db = Database.create_from_env("myapp")

# With options
db = Database.create(
    "myapp",
    owner="appuser",           # Set owner
    template="template1",      # Template database
    if_not_exists=True,        # Don't error if exists
)
```

### Basic Operations

```python
# Explore database
schemas = db.list_schemas()       # ['public', 'app', ...]
tables = db.list_tables()         # ['users', 'orders', ...]
columns = db.table_info("users")  # Column details
size = db.size()                  # '256 MB'

# Execute queries
users = db.execute("SELECT * FROM users WHERE active = %s", [True])

# Fetch single row
user = db.fetch_one("SELECT * FROM users WHERE id = %s", [1])

# Fetch single value
count = db.fetch_val("SELECT COUNT(*) FROM users")

# Insert data
db.execute(
    "INSERT INTO users (name, email) VALUES (%s, %s)",
    ["Alice", "alice@example.com"]
)

# Batch insert
db.execute_many(
    "INSERT INTO users (name) VALUES (%s)",
    [("Alice",), ("Bob",), ("Charlie",)]
)
```

### Using Context Managers

```python
# Connection context manager
with db.connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM users")
        rows = cur.fetchall()

# Cursor context manager (returns dict rows)
with db.cursor() as cur:
    cur.execute("SELECT * FROM users WHERE id = %s", [1])
    user = cur.fetchone()  # Returns dict
```

### Closing Connections

```python
# Explicit close
db.close()

# Or use as context manager
with Database.from_env() as db:
    users = db.execute("SELECT * FROM users")
# Automatically closed
```

## Next Steps

- {doc}`configuration` - Learn about all configuration options
- {doc}`database` - Explore the full Database API
- {doc}`async-database` - Use async/await with AsyncDatabase
- {doc}`connection-pooling` - Connection pooling for production
