# Configuration

## Config Class

The `Config` class manages database connection settings.

```python
from pycopg import Config

config = Config(
    host="localhost",      # Database host
    port=5432,             # Database port
    database="mydb",       # Database name
    user="postgres",       # Username
    password="secret",     # Password
    sslmode="require",     # SSL mode (optional)
    options={}             # Additional options
)
```

## Connection Methods

### From URL

```python
config = Config.from_url("postgresql://user:pass@localhost:5432/mydb")

# Also supports:
# - postgresql+asyncpg://...
# - postgres://...
# - postgresql://...?sslmode=require
```

### From Environment Variables

```python
# With python-dotenv (optional)
config = Config.from_env()

# From specific .env file
config = Config.from_env("/path/to/.env")
```

## Environment Variables

pycopg reads configuration from environment variables in this order:

1. `DATABASE_URL` - Full connection URL (takes precedence)
2. Individual variables:

| Variable | Alternative | Default | Description |
|----------|-------------|---------|-------------|
| `DB_HOST` | `PGHOST` | localhost | Database host |
| `DB_PORT` | `PGPORT` | 5432 | Database port |
| `DB_NAME` | `PGDATABASE` | postgres | Database name |
| `DB_USER` | `PGUSER` | postgres | Username |
| `DB_PASSWORD` | `PGPASSWORD` | (empty) | Password |
| `DB_SSLMODE` | `PGSSLMODE` | (none) | SSL mode |

## Using .env Files

If you have `python-dotenv` installed (`pip install pycopg[dotenv]`), the `Config.from_env()` method will automatically load variables from a `.env` file:

```bash
# .env
DATABASE_URL=postgresql://user:pass@localhost:5432/mydb

# Or individual variables
DB_HOST=localhost
DB_PORT=5432
DB_NAME=mydb
DB_USER=postgres
DB_PASSWORD=secret
```

```python
from pycopg import Config

# Loads from .env in current directory or parents
config = Config.from_env()

# Or from a specific file
config = Config.from_env("/path/to/.env")
```

## Config Properties

```python
config = Config.from_env()

# DSN string for psycopg
print(config.dsn)
# 'host=localhost port=5432 dbname=mydb user=postgres password=secret'

# SQLAlchemy URL
print(config.url)
# 'postgresql+psycopg://postgres:secret@localhost:5432/mydb'

# Connection parameters dict
print(config.connect_params())
# {'host': 'localhost', 'port': 5432, 'dbname': 'mydb', 'user': 'postgres', 'password': 'secret'}
```

## Switching Databases

Create a new config pointing to a different database:

```python
admin_config = Config.from_env()  # Points to 'postgres'
app_config = admin_config.with_database("myapp")  # Points to 'myapp'
```

## SSL Modes

Supported SSL modes:

| Mode | Description |
|------|-------------|
| `disable` | No SSL |
| `allow` | Prefer non-SSL, allow SSL |
| `prefer` | Prefer SSL, allow non-SSL |
| `require` | Require SSL (no verification) |
| `verify-ca` | Require SSL + verify CA |
| `verify-full` | Require SSL + verify CA + hostname |

```python
config = Config(
    host="db.example.com",
    database="mydb",
    user="app",
    password="secret",
    sslmode="verify-full"
)
```
