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

## Incremental loading

Incremental loading extracts only rows that are newer than the last successful
run, using a monotonic "watermark" column as the progress marker. Instead of
reloading the entire source on every run, subsequent runs pull only the rows
where ``watermark_column > last_watermark``.

### Worked example

```python
from pycopg import Database, Pipeline

db = Database.from_env()

# Incremental upsert: only rows with updated_at > last successful watermark
# are extracted on each run; upsert makes boundary rows idempotent.
p = Pipeline(
    name="sync_events",
    source="SELECT id, user_id, event_type, updated_at FROM raw_events",
    target="events",
    load_mode="upsert",
    conflict_columns=["id"],
    incremental_column="updated_at",
)

result = db.etl.run(p)
print(result.status)              # "success"
print(result.rows_extracted)      # rows pulled this run (> last watermark)
print(result.watermark_used)      # the filter floor applied (None on first run)
print(result.watermark_recorded)  # the new high-water mark persisted
```

``async_db.etl.run(p)`` behaves identically — full sync/async parity is
maintained for the incremental surface.

### Watermark-column requirements

The ``incremental_column`` must satisfy:

- **Monotonic / non-decreasing** — values must never decrease over time for
  the watermark filter to be reliable.  Typical choices are an auto-updated
  ``updated_at`` timestamp or an auto-incrementing integer primary key.
- **Type** — the column must be a timezone-aware datetime (offset is preserved
  as-is; it is NOT coerced to UTC), an integer, or a text value.  Float
  columns are rejected at runtime with an ``ETLError``.
- **Single column** — composite watermarks are not supported in v0.7.0.
- **Exclusive boundary** — the filter is ``col > last_watermark`` (strictly
  greater than).  Rows exactly equal to the previous watermark are NOT
  re-extracted.

### Why ``upsert`` is required

Specifying ``incremental_column`` with ``load_mode="append"`` or
``load_mode="replace"`` raises a ``ValueError`` at ``Pipeline`` construction.
``upsert`` is required because the boundary row (the row whose value equals
``last_watermark``) is excluded from subsequent extracts — but that same row
was loaded in the prior run.  Upsert makes re-loading that boundary row
idempotent if the source is queried with ``>=`` in the future and ensures no
silent duplicates appear under concurrent writes near the boundary.

### First-run and subsequent-run semantics

- **First run** (no prior successful watermark): the pipeline performs a full
  extract of the source with no ``WHERE`` filter.  After a successful load,
  ``max(incremental_column)`` from the raw extracted batch is recorded as the
  watermark for the next run.
- **Subsequent runs**: the pipeline reads the watermark from the last
  *successful* run (``status = 'success' AND watermark IS NOT NULL``) and
  extracts only rows where ``col > last_watermark``.
- **Failed runs** do not advance the watermark — the next run retries from the
  same floor.
- **Empty batches** preserve the prior watermark; a ``NULL`` watermark is never
  written.  The run succeeds with ``rows_loaded = 0``.
- **Max taken from the raw batch** — the high-water mark is captured before any
  ``transform`` callables are applied, so transforms that drop rows cannot cause
  watermark regression.

### RunResult watermark fields

``run()`` returns a ``RunResult`` with two new fields for incremental
pipelines:

``watermark_used``
    The filter floor applied this run — the value passed to
    ``WHERE col > watermark_used``.  ``None`` on the first run (full extract)
    and ``None`` for non-incremental pipelines.

``watermark_recorded``
    The new high-water mark that was persisted to ``pipeline_runs`` after a
    successful load — ``max(incremental_column)`` of the raw extracted batch.
    ``None`` for non-incremental pipelines and for empty or all-``NULL``
    batches.

``history()`` and ``last_run()`` surface ``watermark_recorded`` from stored
rows (decoded from ``pipeline_runs.watermark``).  ``watermark_used`` is always
``None`` for stored rows — it is a per-run input that is never persisted.

### Dry-run preview for incremental pipelines

``dry_run=True`` on an incremental pipeline reads the prior watermark and
applies the **same** ``WHERE col > last_watermark`` filter as a real run, so
``rows_extracted`` is an honest "what would a real run pull" count.  Both
``watermark_used`` and ``watermark_recorded`` (the max of the filtered batch)
are populated on the returned ``RunResult``.  No ``pipeline_runs`` row is
written (``run_id`` is ``None``).

```python
preview = db.etl.run(p, dry_run=True)
print(preview.status)              # "dry_run"
print(preview.rows_extracted)      # rows that would be pulled
print(preview.rows_loaded)         # always 0
print(preview.run_id)              # always None
print(preview.watermark_used)      # filter floor that would be applied
print(preview.watermark_recorded)  # max(col) of the would-be batch
```

### Backfill and watermark reset

There is no ``reset_watermark()`` API.  To force a full reload on the next
run, neutralize the last successful watermark directly with manual SQL:

```sql
UPDATE pipeline_runs SET watermark = NULL WHERE pipeline_name = %s;
-- or delete the run history entirely:
-- DELETE FROM pipeline_runs WHERE pipeline_name = %s;
```

After this, the next ``run()`` reads ``None`` → performs a full extract →
records a fresh watermark.

.. note::

   An ``initial_watermark`` option to bound the first full-load scan is
   planned for v0.8.0 (ETL-INC-F01).  Until then, the first incremental run
   always reads the entire source table.

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
