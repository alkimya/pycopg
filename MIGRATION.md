# Migration Guide: v0.2.0 to v0.3.0

This guide helps you upgrade from pycopg 0.2.0 to 0.3.0. Version 0.3.0 is a consolidation release that achieves full async/sync parity, adds resilience features, and includes one breaking change.

## Breaking Changes

### 1. GeoDataFrame CRS Validation (from_geodataframe)

**What changed:** `from_geodataframe()` now raises `ValueError` on unknown CRS instead of silently defaulting to SRID 4326.

**Why:** Silent defaults hide configuration errors and can lead to data corruption. Explicit errors ensure you always know which coordinate system your spatial data is using.

**Who is affected:** Anyone using `from_geodataframe()` with GeoDataFrames that have unknown or missing CRS. If you're already using standard EPSG codes like "EPSG:4326", your code will continue to work unchanged.

**Before (0.2.0):**
```python
import geopandas as gpd
from pycopg import Database

gdf = gpd.read_file("parcels.geojson")  # Unknown or missing CRS
db = Database.from_env()

# Silently defaulted to SRID 4326 - potential data corruption
db.from_geodataframe(gdf, "parcels")
```

**After (0.3.0):**
```python
import geopandas as gpd
from pycopg import Database

gdf = gpd.read_file("parcels.geojson")
db = Database.from_env()

# Now raises: ValueError("GeoDataFrame CRS could not be converted to SRID...")
# db.from_geodataframe(gdf, "parcels")  # This will raise an error

# FIX 1: Explicitly set the CRS if you know what it should be
gdf = gdf.set_crs("EPSG:4326")
db.from_geodataframe(gdf, "parcels")  # Works

# FIX 2: Or specify SRID directly
db.from_geodataframe(gdf, "parcels", srid=4326)  # Works
```

**Impact:** Low - only affects GeoDataFrames with unknown or missing CRS. Standard EPSG CRS codes like "EPSG:4326", "EPSG:3857", etc., continue to work automatically.

## New Features

### Full Async Parity

**What's new:** AsyncDatabase now has complete feature parity with Database. Every public method available in Database is now available in AsyncDatabase.

**DataFrame Operations:**
```python
from pycopg import AsyncDatabase

db = AsyncDatabase.from_env()

# Read table to DataFrame
df = await db.to_dataframe("users")
df = await db.to_dataframe(sql="SELECT * FROM users WHERE age > :min", params={"min": 18})

# Insert from DataFrame
import pandas as pd
df = pd.DataFrame({"name": ["Alice", "Bob"], "age": [30, 25]})
await db.from_dataframe(df, "users_backup", primary_key="id")

# Spatial data
gdf = await db.to_geodataframe("parcels")
await db.from_geodataframe(gdf, "parcels_copy", spatial_index=True)
```

**Admin Operations:**
```python
# Maintenance
await db.vacuum("users", analyze=True)
await db.analyze("orders")

# Query analysis
plan = await db.explain("SELECT * FROM users WHERE email = %s", ["test@example.com"])

# Indexes
await db.create_index("users", "email", unique=True)
await db.drop_index("idx_users_email")

# Tables
await db.create_table("logs", {"id": "SERIAL PRIMARY KEY", "message": "TEXT"})
await db.drop_table("temp_data")
```

**Backup Operations:**
```python
# Full backup
await db.pg_dump("backup.dump")
await db.pg_dump("backup.sql", format="plain")

# Restore
await db.pg_restore("backup.dump")

# CSV export/import
await db.copy_to_csv("users", "users.csv")
await db.copy_from_csv("users", "users.csv")
```

**Role Management:**
```python
# Create roles
await db.create_role("analyst", password="secret", login=True)
await db.create_role("readonly", login=False)

# Grant/revoke privileges
await db.grant("SELECT", "users", "readonly")
await db.grant("ALL", "orders", "analyst")
await db.revoke("INSERT", "users", "readonly")

# Role membership
await db.grant_role("readonly", "analyst")
await db.list_role_grants("analyst")
```

**PostGIS Operations:**
```python
# Spatial indexes
await db.create_spatial_index("parcels", "geometry")

# List geometry columns
columns = await db.list_geometry_columns()
```

**TimescaleDB Operations:**
```python
# Create hypertables
await db.create_hypertable("events", "timestamp", chunk_time_interval="1 week")

# Compression
await db.enable_compression("events", segment_by="device_id", order_by="timestamp DESC")
await db.add_compression_policy("events", compress_after="30 days")

# Retention
await db.add_retention_policy("logs", drop_after="90 days")

# List hypertables
tables = await db.list_hypertables()
info = await db.hypertable_info("events")
```

### Retry/Backoff for Resilience

**What's new:** Automatic retry with exponential backoff for transient connection errors. No configuration needed - it just works.

**How it works:**
```python
from pycopg import Database, AsyncDatabase

# Retry automatically enabled on connect()
db = Database.from_env()
# On connection failure: retries 3 times with exponential backoff (1-10s)

# Same for async
db = AsyncDatabase.from_env()
# Automatically retries on OperationalError (connection failures)
```

**Details:**
- 3 retry attempts (initial attempt + 2 retries)
- Exponential backoff: wait 1s, then 2.7s, then 7.4s
- Only retries on `OperationalError` (transient connection failures)
- Does not retry on `ProgrammingError` (SQL syntax errors, etc.)
- Applies to `Database.connect()` and `AsyncDatabase.connect()` only
- Connection pools already have built-in reconnection handling

### Statement Timeout

**What's new:** Configurable query timeout to prevent runaway queries from consuming resources.

**Basic usage:**
```python
from pycopg import Database, Config

config = Config.from_env()
config.statement_timeout = 30000  # 30 seconds (in milliseconds)
db = Database(config)

# Queries exceeding 30s will be cancelled automatically
# db.execute("SELECT pg_sleep(60)")  # Raises exception after 30s
```

**With URL:**
```python
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

**What's new:** Control the batch size for insert operations to optimize memory usage and performance.

**Usage:**
```python
from pycopg import Database

db = Database.from_env()

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

## Upgrade Checklist

- [ ] Review breaking changes above
- [ ] Update `from_geodataframe()` calls to handle CRS explicitly if needed
- [ ] Test that GeoDataFrames have valid CRS before insertion
- [ ] Optional: Configure `statement_timeout` for query protection
- [ ] Optional: Explore new async DataFrame/admin/backup methods if using AsyncDatabase
- [ ] Optional: Adjust `batch_size` if experiencing memory issues or want performance tuning
- [ ] Run test suite to verify compatibility

## Getting Help

If you encounter issues during migration:

1. Check that you're using a supported Python version (3.11+)
2. Review the [CHANGELOG.md](CHANGELOG.md) for full list of changes
3. Open an issue on [GitHub](https://github.com/alkimya/pycopg/issues) with your use case

---

# Migration Guide: v0.3.x to v0.4.0

This guide helps you upgrade from pycopg 0.3.x to 0.4.0. Version 0.4.0 adds spatial helpers,
full sync/async parity, and custom exception types. There are three breaking changes.

## Breaking Changes

### 1. AsyncDatabase engine URL (psycopg_async driver)

**Affected users:** Anyone inspecting or passing through `AsyncDatabase._async_engine` URLs.

**What changed:** The async engine now uses the `postgresql+psycopg_async://` URL scheme (was
`postgresql+psycopg://`). This is the correct driver for async psycopg v3.

**Impact:** Low. Only affects code that reads or logs `async_engine.url`. The API
(`execute`, `connect`, etc.) is unchanged — you do not need to update connection strings
passed to `AsyncDatabase.from_env()` or `AsyncDatabase.from_url()`.

### 2. AsyncDatabase.close() now disposes the engine

**What changed:** `close()` now calls `await engine.dispose()`. Previously it was a no-op.

**Impact:** Any code that called `close()` and then attempted to use the same
`AsyncDatabase` instance again will now fail — the engine is disposed. This was already
incorrect behavior: `close()` semantics have always implied the object should not be
used afterward. Treat this as a bug fix rather than a behavior change.

### 3. Custom exception types replace RuntimeError/ValueError

**What changed:** Several methods now raise domain-specific exceptions instead of
`RuntimeError` or `ValueError`:

| Method | Old exception | New exception |
|--------|---------------|---------------|
| `create_extension()` when extension is missing | `RuntimeError` | `ExtensionNotAvailable` |
| `create_database()` when database already exists | `RuntimeError` | `DatabaseExists` |
| Other extension-requiring methods | `RuntimeError` | `ExtensionNotAvailable` |

**Migration:** Update `except` clauses:

```python
# Before (0.3.x)
try:
    db.create_extension("postgis")
except RuntimeError:
    pass

# After (0.4.0)
from pycopg import ExtensionNotAvailable
try:
    db.create_extension("postgis")
except ExtensionNotAvailable:
    pass
```

```python
# Before (0.3.x)
try:
    db.create_database("mydb")
except RuntimeError:
    pass

# After (0.4.0)
from pycopg import DatabaseExists
try:
    db.create_database("mydb")
except DatabaseExists:
    pass
```

**Impact:** Medium. Code with broad `except Exception` or `except PycopgError` catch-all
clauses is unaffected. Only explicit `except RuntimeError` or `except ValueError` blocks
that catch database-domain errors need updating.

## Upgrade Checklist

- [ ] Review breaking changes above
- [ ] Search codebase for `except RuntimeError` near `create_extension` / `create_database`
  calls and update to `except ExtensionNotAvailable` / `except DatabaseExists`
- [ ] Import new exception types: `from pycopg import ExtensionNotAvailable, DatabaseExists`
- [ ] If you inspect `async_engine.url` anywhere, update expected URL scheme to
  `postgresql+psycopg_async://`
- [ ] Run test suite to verify compatibility

## New in 0.4.0

- `db.spatial.*` / `async_db.spatial.*`: 11 spatial helpers (contains, within, intersects,
  dwithin, distance, nearest, area, perimeter, centroid, buffer, transform)
- Full sync/async API parity (all public methods now available on both `Database` and `AsyncDatabase`)
- `PooledDatabase.execute` commits results before returning (fixes `INSERT ... RETURNING`)

## Getting Help

If you encounter issues during migration:

1. Check that you're using a supported Python version (3.11+)
2. Review the [CHANGELOG.md](CHANGELOG.md) for the full list of changes
3. Open an issue on [GitHub](https://github.com/alkimya/pycopg/issues) with your use case
