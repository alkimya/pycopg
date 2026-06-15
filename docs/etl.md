# ETL Pipeline Runner

pycopg provides a `db.etl.*` (and `async_db.etl.*`) accessor namespace for
declarative extract → transform → load pipelines with built-in run tracking.
Every run is recorded in a `pipeline_runs` table, giving you full history and
observability at zero extra infrastructure cost.

The accessor is built entirely on existing pycopg primitives — no new runtime
dependencies — and offers full sync/async parity: every method available on
`db.etl` has an `await`-able twin on `async_db.etl`.

## Access Pattern

The accessor is exposed as a lazy property on `Database` and `AsyncDatabase`:

```python
from pycopg import Database, Pipeline

db = Database.from_env()

# Sync: db.etl is initialized lazily on first access
result = db.etl.run(Pipeline(
    name="nightly_events",
    source="SELECT * FROM raw_events",
    target="events",
    load_mode="replace",
))
print(result.status, result.rows_loaded)
```

```python
from pycopg import AsyncDatabase, Pipeline

async_db = AsyncDatabase.from_env()

# Async: async_db.etl mirrors the sync API with awaited methods
result = await async_db.etl.run(Pipeline(
    name="nightly_events",
    source="SELECT * FROM raw_events",
    target="events",
    load_mode="replace",
))
print(result.status, result.rows_loaded)
```

Both `db.etl` and `async_db.etl` are cached after the first access — the
accessor object is created once and reused for the lifetime of the database
instance.

## Defining a Pipeline

A `Pipeline` is a frozen dataclass that declares the intent of one ETL run:

```python
from pycopg import Pipeline

# Minimal: append source rows to an existing target table
p = Pipeline(
    name="load_orders",
    source="SELECT * FROM staging_orders",
    target="orders",
)

# Replace: truncate target, then load (atomic — full rollback on error)
p = Pipeline(
    name="refresh_products",
    source="products_staging",   # plain table name
    target="products",
    load_mode="replace",
)

# Upsert: INSERT … ON CONFLICT DO UPDATE
p = Pipeline(
    name="sync_users",
    source="SELECT id, email, updated_at FROM staging_users",
    target="users",
    load_mode="upsert",
    conflict_columns=["id"],     # required for upsert
)
```

**Load modes**

| `load_mode` | Behaviour | Target must exist? |
|-------------|-----------|-------------------|
| `"append"` (default) | Inserts rows into the existing target | Yes |
| `"replace"` | Truncates target, then inserts (atomic) | No — auto-created from extract schema |
| `"upsert"` | `INSERT … ON CONFLICT DO UPDATE` | Yes |

**Source forms**

`source` accepts either a SQL query string (any string containing spaces or
starting with `SELECT` / `WITH`) or a plain table name:

```python
# SQL query source
p = Pipeline(name="p", source="SELECT id, val FROM staging", target="tgt")

# Table name source — reads the whole table
p = Pipeline(name="p", source="staging", target="tgt", schema="raw")
```

**Transform callables**

`transform` is applied between extract and load. Pass `None` (default) for a
no-op, a single callable, or a list of callables applied in sequence:

```python
import pandas as pd

def clean_emails(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["email"] = df["email"].str.lower().str.strip()
    return df

def drop_nulls(df: pd.DataFrame) -> pd.DataFrame:
    return df.dropna(subset=["email"])

p = Pipeline(
    name="clean_users",
    source="SELECT id, email FROM raw_users",
    target="users",
    transform=[clean_emails, drop_nulls],
)
```

**Extract limit**

Pass `extract_limit` to cap rows read from the source (useful for smoke-tests):

```python
p = Pipeline(
    name="sample_run",
    source="large_table",
    target="sample_target",
    extract_limit=1000,
)
```

## run

Execute a full extract → transform → load pipeline and return a `RunResult`:

```python
from pycopg import Pipeline

result = db.etl.run(Pipeline(
    name="load_events",
    source="SELECT * FROM raw_events WHERE date = current_date",
    target="events",
    load_mode="replace",
))

print(result.status)          # "success" or "failed"
print(result.run_id)          # int — pipeline_runs.run_id
print(result.rows_extracted)  # rows read from source
print(result.rows_loaded)     # rows written to target
print(result.started_at)      # UTC datetime
print(result.finished_at)     # UTC datetime
print(result.error)           # None on success; error message on failure
```

`run()` auto-creates the `pipeline_runs` table on first call (idempotent `CREATE
TABLE IF NOT EXISTS`), so no explicit `db.etl.init()` call is required.

## history

Return the run history for a pipeline, newest-first:

```python
runs = db.etl.history("load_events")          # list[RunResult], newest-first
runs = db.etl.history("load_events", limit=5) # cap at 5 entries

for r in runs:
    print(r.run_id, r.status, r.rows_loaded, r.started_at)
```

Returns an empty list when no runs exist for the given pipeline name.

## last_run

Return the most recent run for a pipeline, or `None` if no runs exist:

```python
last = db.etl.last_run("load_events")
if last is None:
    print("Pipeline has never run")
else:
    print(f"Last run: {last.status} at {last.started_at}")
```

`last_run(name)` is equivalent to `history(name, limit=1)[0]` when a run
exists, but returns `None` rather than raising `IndexError` when the history
is empty.

### Dry runs

Pass `dry_run=True` to execute extract and transform without writing to the
target or recording a `pipeline_runs` row:

```python
result = db.etl.run(pipeline, dry_run=True)
print(result.status)          # "dry_run"
print(result.rows_extracted)  # actual rows from source
print(result.rows_loaded)     # always 0
print(result.run_id)          # always None — no DB row written
```

Dry runs are useful for validating pipeline configuration and transform logic
against live data before committing a load.

## Async Usage

All methods are available on `async_db.etl` with identical signatures — prefix
each call with `await`:

```python
from pycopg import AsyncDatabase, Pipeline

async_db = AsyncDatabase.from_env()

# run
result = await async_db.etl.run(Pipeline(
    name="load_events",
    source="SELECT * FROM raw_events",
    target="events",
    load_mode="replace",
))

# history
runs = await async_db.etl.history("load_events", limit=10)

# last_run
last = await async_db.etl.last_run("load_events")

# dry run
result = await async_db.etl.run(pipeline, dry_run=True)
```

Sync transform callables passed via `transform=` are dispatched through
`asyncio.to_thread` so a slow or CPU-bound transform does not block the event
loop. No changes are needed to the callable itself — the same function works
for both `db.etl.run` and `async_db.etl.run`.

## Security

All table and column identifiers (target, schema, conflict_columns) pass
through `validate_identifiers` before any SQL is assembled. No identifier is
interpolated via f-strings; only validated names are embedded in query
strings. User-supplied data values (extract rows) flow exclusively through
parameterized `%s` placeholders and are never directly interpolated.

The `pipeline_runs` DDL uses `CREATE TABLE IF NOT EXISTS` — no user-supplied
identifiers are involved in the schema-init path.
