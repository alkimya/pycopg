# TimescaleDB Support

pycopg provides a `db.timescale.*` (and `async_db.timescale.*`) accessor namespace with
built-in support for TimescaleDB, a PostgreSQL extension for time-series data.

## Prerequisites

1. TimescaleDB extension installed on your PostgreSQL server
2. Regular pycopg installation (no additional packages needed)

## Access Pattern

```python
from pycopg import Database

db = Database.from_env()

# Enable TimescaleDB extension (uses transactional-core execute — stays flat)
db.schema.create_extension("timescaledb")

# Sync: db.timescale is initialized lazily on first access
db.timescale.create_hypertable("events", "time")
```

```python
from pycopg import AsyncDatabase

async_db = AsyncDatabase.from_env()

# Async: async_db.timescale mirrors the sync API with awaited methods
await async_db.timescale.create_hypertable("events", "time")
```

> **Note:** The flat `db.*` methods (e.g. `db.create_hypertable`) were removed in v0.7.0.
> Use `db.timescale.*` instead.
> See [MIGRATION.md](https://github.com/alkimya/pycopg/blob/main/MIGRATION.md) for the complete name mapping.

## Setup

```python
from pycopg import Database

db = Database.from_env()

# Enable TimescaleDB extension
db.schema.create_extension("timescaledb")

# Verify installation
if db.schema.has_extension("timescaledb"):
    print("TimescaleDB is ready")
```

## Creating Hypertables

A hypertable is TimescaleDB's core table type, automatically partitioning data by time.

### Basic Creation

```python
# First, create a regular table with a time column
db.execute("""
    CREATE TABLE events (
        time TIMESTAMPTZ NOT NULL,
        device_id TEXT NOT NULL,
        temperature DOUBLE PRECISION,
        humidity DOUBLE PRECISION
    )
""")

# Convert to hypertable
db.timescale.create_hypertable("events", "time")
```

### With Options

```python
db.timescale.create_hypertable(
    "events",
    "time",
    schema="metrics",              # Target schema
    chunk_time_interval="1 week",  # Chunk interval (default: 1 day)
    if_not_exists=True,            # Don't error if exists
    migrate_data=True,             # Migrate existing data
)
```

### Common Chunk Intervals

| Use Case                 | Interval              |
| ------------------------ | --------------------- |
| High-frequency IoT data  | `1 hour`              |
| Standard metrics         | `1 day`               |
| Long-term storage        | `1 week` or `1 month` |

## Compression

Enable compression to reduce storage for older data.

### Enable Compression

```python
# Enable compression on hypertable
db.timescale.enable_compression(
    "events",
    segment_by="device_id",       # Group compressed data
    order_by="time DESC",         # Order within segments
)
```

### Compression Policy

Automatically compress chunks older than a threshold.

```python
# Compress chunks older than 7 days
db.timescale.add_compression_policy("events", compress_after="7 days")

# Or custom interval
db.timescale.add_compression_policy("events", compress_after="30 days")
```

## Data Retention

Automatically drop old data chunks.

```python
# Drop chunks older than 90 days
db.timescale.add_retention_policy("logs", drop_after="90 days")

# For metrics, keep 1 year
db.timescale.add_retention_policy("metrics", drop_after="365 days")
```

## Listing Hypertables

```python
hypertables = db.timescale.list_hypertables()
# [
#     {
#         'schema': 'public',
#         'table_name': 'events',
#         'num_dimensions': 1,
#         'num_chunks': 30,
#         'compression_enabled': True
#     },
#     ...
# ]
```

## Hypertable Info

```python
info = db.timescale.hypertable_info("events")
# {
#     'total_size': '1.2 GB',
#     'detailed_size': {...}
# }
```

## Time-Series Queries

### Time Bucketing

```python
import pandas as pd

# Average temperature per hour, returned as a DataFrame
df = db.timescale.time_bucket(
    "events",
    "time",
    "1 hour",
    aggregates="device_id, AVG(temperature) AS avg_temp, MAX(temperature) AS max_temp",
    where="time > NOW() - INTERVAL '1 day'",
    into="df",
)
# df is a pandas DataFrame with columns: bucket, device_id, avg_temp, max_temp

# Return as a list of dicts instead
rows = db.timescale.time_bucket(
    "events",
    "time",
    "1 hour",
    aggregates="device_id, AVG(temperature) AS avg_temp",
    into="rows",
)

# Note: `aggregates` and `where` are structural SQL fragments injected directly
# into the query builder.  Aggregate expressions (e.g. column names, AVG calls)
# must come from trusted sources — not from untrusted user input.
# The `where` *value* is parameterised safely; only the column/expression names
# in `aggregates` are structural.
```

### Last Values

```python
# Get last reading for each device
result = db.execute("""
    SELECT DISTINCT ON (device_id)
        device_id,
        time,
        temperature,
        humidity
    FROM events
    ORDER BY device_id, time DESC
""")
```

### Moving Average

```python
# 5-minute moving average
result = db.execute("""
    SELECT
        time,
        device_id,
        temperature,
        AVG(temperature) OVER (
            PARTITION BY device_id
            ORDER BY time
            RANGE BETWEEN INTERVAL '5 minutes' PRECEDING AND CURRENT ROW
        ) AS moving_avg
    FROM events
    WHERE time > NOW() - INTERVAL '1 hour'
    ORDER BY time DESC
""")
```

### Gap Filling

```python
from datetime import datetime, timedelta

now = datetime.utcnow()
start = now - timedelta(hours=1)

# Fill time-series gaps with last-observation-carried-forward (locf)
# start and finish MUST be passed as explicit positional datetime arguments —
# gap-fill requires them as bound parameters inside the function call, not as
# a WHERE clause (TimescaleDB planner restriction).
df = db.timescale.time_bucket_gapfill(
    "events",
    "time",
    "1 minute",
    start=start,
    finish=now,
    aggregates="device_id, locf(AVG(temperature)) AS temperature",
    into="df",
)
# df has columns: bucket, device_id, temperature (nulls filled by locf)
```

## Continuous Aggregates

Create materialized views that automatically update.

```python
# Create a continuous aggregate view
db.timescale.create_continuous_aggregate(
    "hourly_metrics",
    select_sql=(
        "SELECT time_bucket('1 hour', time) AS bucket, "
        "device_id, AVG(temperature) AS avg_temp, "
        "MAX(temperature) AS max_temp, MIN(temperature) AS min_temp, "
        "COUNT(*) AS samples "
        "FROM events GROUP BY bucket, device_id"
    ),
    materialized_only=True,
    with_no_data=True,
)

# Manually refresh a window (e.g. backfill the last 3 hours)
from datetime import datetime, timedelta

now = datetime.utcnow()
db.timescale.refresh_continuous_aggregate(
    "hourly_metrics",
    window_start=now - timedelta(hours=3),
    window_end=now,
)

# Add an automatic refresh policy (runs every hour, refreshes last 3 hours)
db.timescale.add_continuous_aggregate_policy(
    "hourly_metrics",
    start_offset="3 hours",
    end_offset="1 hour",
    schedule_interval="1 hour",
)
```

## Advanced Chunk & Dimension Management

> **Note:** `time_bucket_gapfill` (and its `locf`/`interpolate` gap-fill functions) and the
> continuous-aggregate methods (`create_continuous_aggregate`, `refresh_continuous_aggregate`,
> `add_continuous_aggregate_policy`) require a **Community/TSL-licensed** TimescaleDB build.
> On Apache-licensed builds (including most self-hosted open-source installations) these raise
> `FeatureNotSupported`. `time_bucket`, `show_chunks`, `drop_chunks`, `add_dimension`, and
> `add_reorder_policy` are available on all TimescaleDB builds.

### Inspecting Chunks

```python
# List all chunks for the 'events' hypertable (oldest first)
chunks = db.timescale.show_chunks("events")
# ['_timescaledb_internal._hyper_1_1_chunk', '_timescaledb_internal._hyper_1_2_chunk', ...]

# List only chunks older than 30 days (interval string)
old_chunks = db.timescale.show_chunks("events", older_than="30 days")

# Or use a datetime cutoff
from datetime import datetime, timedelta
cutoff = datetime.utcnow() - timedelta(days=30)
old_chunks = db.timescale.show_chunks("events", older_than=cutoff)
```

Returns `list[str]` of fully-qualified chunk names, sorted oldest-first by `range_start`.

### Dropping Chunks

> **DESTRUCTIVE / IRREVERSIBLE** — dropped chunks are permanently removed.
> Use `dry_run=True` first to preview which chunks will be affected.
> Both bounds set to `None` (the default) raises `ValueError` to prevent accidental
> full-table truncation.

```python
# Preview what would be dropped — no data is actually removed
would_drop = db.timescale.drop_chunks("events", older_than="90 days", dry_run=True)
print(f"Would drop {len(would_drop)} chunks: {would_drop}")

# Drop for real once you have confirmed the list
dropped = db.timescale.drop_chunks("events", older_than="90 days")
```

### Adding a Space Dimension

Add a secondary partition dimension (hash or range) to an existing hypertable.
TimescaleDB 2.x uses the modern `by_hash`/`by_range` form.

```python
# Hash partition on device_id across 4 partitions
db.timescale.add_dimension(
    "events",
    "device_id",
    partition_type="hash",
    number_partitions=4,
)

# Range partition on a secondary time/numeric column
# (number_partitions and chunk_interval are mutually exclusive)
db.timescale.add_dimension(
    "metrics",
    "region_id",
    partition_type="range",
    chunk_interval=100,
)
```

### Adding a Reorder Policy

Automatically reorder chunks on a specified index to improve compression and query
performance.

```python
db.timescale.add_reorder_policy(
    "events",
    index_name="events_device_id_time_idx",
)
```

## Complete Example

```python
from pycopg import Database
import pandas as pd
from datetime import datetime, timedelta

db = Database.from_env()

# Setup
db.schema.create_extension("timescaledb")

# Create sensor table
db.execute("""
    CREATE TABLE IF NOT EXISTS sensors (
        time TIMESTAMPTZ NOT NULL,
        sensor_id TEXT NOT NULL,
        location TEXT,
        temperature DOUBLE PRECISION,
        humidity DOUBLE PRECISION,
        pressure DOUBLE PRECISION
    )
""")

# Convert to hypertable
db.timescale.create_hypertable("sensors", "time", if_not_exists=True)

# Create indexes
db.execute("""
    CREATE INDEX IF NOT EXISTS idx_sensors_sensor_id_time
    ON sensors (sensor_id, time DESC)
""")

# Enable compression
db.timescale.enable_compression(
    "sensors",
    segment_by="sensor_id",
    order_by="time DESC"
)

# Add policies
db.timescale.add_compression_policy("sensors", compress_after="7 days")
db.timescale.add_retention_policy("sensors", drop_after="90 days")

# Insert sample data
import random
now = datetime.now()
data = [
    {
        "time": now - timedelta(minutes=i),
        "sensor_id": f"sensor_{i % 5}",
        "location": f"room_{i % 3}",
        "temperature": 20 + random.uniform(-5, 10),
        "humidity": 50 + random.uniform(-20, 30),
        "pressure": 1013 + random.uniform(-10, 10),
    }
    for i in range(1000)
]

df = pd.DataFrame(data)
db.from_dataframe(df, "sensors", if_exists="append")

# Query: hourly averages
hourly = db.execute("""
    SELECT
        time_bucket('1 hour', time) AS hour,
        sensor_id,
        AVG(temperature) AS avg_temp,
        AVG(humidity) AS avg_humidity
    FROM sensors
    WHERE time > NOW() - INTERVAL '24 hours'
    GROUP BY hour, sensor_id
    ORDER BY hour DESC
""")

# Query: latest readings
latest = db.execute("""
    SELECT DISTINCT ON (sensor_id)
        sensor_id,
        location,
        time,
        temperature,
        humidity,
        pressure
    FROM sensors
    ORDER BY sensor_id, time DESC
""")

# Check hypertable info
print(db.timescale.list_hypertables())

db.close()
```

## Best Practices

### 1. Choose Appropriate Chunk Intervals

```python
# High-frequency data (1000+ rows/second)
db.timescale.create_hypertable("events", "time", chunk_time_interval="1 hour")

# Standard metrics
db.timescale.create_hypertable("metrics", "time", chunk_time_interval="1 day")

# Low-frequency, long-term data
db.timescale.create_hypertable("monthly_reports", "time", chunk_time_interval="1 month")
```

### 2. Use Appropriate Indexes

```python
# Index for common queries
db.execute("""
    CREATE INDEX ON sensors (sensor_id, time DESC)
""")

# Covering index for specific queries
db.execute("""
    CREATE INDEX ON sensors (sensor_id, time DESC)
    INCLUDE (temperature, humidity)
""")
```

### 3. Monitor Chunk Sizes

```python
# Check chunk information
chunks = db.execute("""
    SELECT
        chunk_name,
        range_start,
        range_end,
        is_compressed
    FROM timescaledb_information.chunks
    WHERE hypertable_name = 'sensors'
    ORDER BY range_start DESC
    LIMIT 10
""")
```

### 4. Use Continuous Aggregates for Dashboards

Pre-aggregate data for faster dashboard queries instead of computing on the fly.
