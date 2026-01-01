# TimescaleDB Support

pycopg provides built-in support for TimescaleDB, a PostgreSQL extension for time-series data.

## Prerequisites

1. TimescaleDB extension installed on your PostgreSQL server
2. Regular pycopg installation (no additional packages needed)

## Setup

```python
from pycopg import Database

db = Database.from_env()

# Enable TimescaleDB extension
db.create_extension("timescaledb")

# Verify installation
if db.has_extension("timescaledb"):
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
db.create_hypertable("events", "time")
```

### With Options

```python
db.create_hypertable(
    "events",
    "time",
    schema="metrics",              # Target schema
    chunk_time_interval="1 week",  # Chunk interval (default: 1 day)
    if_not_exists=True,            # Don't error if exists
    migrate_data=True,             # Migrate existing data
)
```

### Common Chunk Intervals

| Use Case | Interval |
|----------|----------|
| High-frequency IoT data | `1 hour` |
| Standard metrics | `1 day` |
| Long-term storage | `1 week` or `1 month` |

## Compression

Enable compression to reduce storage for older data.

### Enable Compression

```python
# Enable compression on hypertable
db.enable_compression(
    "events",
    segment_by="device_id",       # Group compressed data
    order_by="time DESC",         # Order within segments
)
```

### Compression Policy

Automatically compress chunks older than a threshold.

```python
# Compress chunks older than 7 days
db.add_compression_policy("events", compress_after="7 days")

# Or custom interval
db.add_compression_policy("events", compress_after="30 days")
```

## Data Retention

Automatically drop old data chunks.

```python
# Drop chunks older than 90 days
db.add_retention_policy("logs", drop_after="90 days")

# For metrics, keep 1 year
db.add_retention_policy("metrics", drop_after="365 days")
```

## Listing Hypertables

```python
hypertables = db.list_hypertables()
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
info = db.hypertable_info("events")
# {
#     'total_size': '1.2 GB',
#     'detailed_size': {...}
# }
```

## Time-Series Queries

### Time Bucketing

```python
# Average temperature per hour
result = db.execute("""
    SELECT
        time_bucket('1 hour', time) AS bucket,
        device_id,
        AVG(temperature) AS avg_temp,
        MAX(temperature) AS max_temp,
        MIN(temperature) AS min_temp
    FROM events
    WHERE time > NOW() - INTERVAL '1 day'
    GROUP BY bucket, device_id
    ORDER BY bucket DESC
""")
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
# Fill gaps in time series
result = db.execute("""
    SELECT
        time_bucket_gapfill('1 minute', time) AS bucket,
        device_id,
        COALESCE(AVG(temperature), locf(AVG(temperature))) AS temperature
    FROM events
    WHERE time BETWEEN NOW() - INTERVAL '1 hour' AND NOW()
    GROUP BY bucket, device_id
    ORDER BY bucket
""")
```

## Continuous Aggregates

Create materialized views that automatically update.

```python
# Create continuous aggregate
db.execute("""
    CREATE MATERIALIZED VIEW hourly_metrics
    WITH (timescaledb.continuous) AS
    SELECT
        time_bucket('1 hour', time) AS bucket,
        device_id,
        AVG(temperature) AS avg_temp,
        MAX(temperature) AS max_temp,
        MIN(temperature) AS min_temp,
        COUNT(*) AS samples
    FROM events
    GROUP BY bucket, device_id
    WITH NO DATA
""")

# Add refresh policy
db.execute("""
    SELECT add_continuous_aggregate_policy('hourly_metrics',
        start_offset => INTERVAL '3 hours',
        end_offset => INTERVAL '1 hour',
        schedule_interval => INTERVAL '1 hour'
    )
""")
```

## Complete Example

```python
from pycopg import Database
import pandas as pd
from datetime import datetime, timedelta

db = Database.from_env()

# Setup
db.create_extension("timescaledb")

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
db.create_hypertable("sensors", "time", if_not_exists=True)

# Create indexes
db.execute("""
    CREATE INDEX IF NOT EXISTS idx_sensors_sensor_id_time
    ON sensors (sensor_id, time DESC)
""")

# Enable compression
db.enable_compression(
    "sensors",
    segment_by="sensor_id",
    order_by="time DESC"
)

# Add policies
db.add_compression_policy("sensors", compress_after="7 days")
db.add_retention_policy("sensors", drop_after="90 days")

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
print(db.list_hypertables())

db.close()
```

## Best Practices

### 1. Choose Appropriate Chunk Intervals

```python
# High-frequency data (1000+ rows/second)
db.create_hypertable("events", "time", chunk_time_interval="1 hour")

# Standard metrics
db.create_hypertable("metrics", "time", chunk_time_interval="1 day")

# Low-frequency, long-term data
db.create_hypertable("monthly_reports", "time", chunk_time_interval="1 month")
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
