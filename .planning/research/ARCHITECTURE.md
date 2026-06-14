# Architecture Research

**Domain:** ETL pipeline-runner layer on top of an existing sync/async PostgreSQL library
**Researched:** 2026-06-14
**Confidence:** HIGH — based on direct source-code reading of the existing codebase

---

## Standard Architecture

### System Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                          Public API surface                           │
│   db.etl.init()   db.etl.run(pipeline)   db.etl.list_runs(name)     │
│   async_db.etl.init()  async_db.etl.run(pipeline)  ...              │
├──────────────────────────────────────────────────────────────────────┤
│                    pycopg/etl.py  (NEW FILE)                         │
│  ┌──────────────────────────────┐   ┌──────────────────────────────┐ │
│  │  Pure builders / dataclasses  │   │  EtlAccessor (sync)          │ │
│  │  Pipeline  ExtractSpec        │   │  AsyncEtlAccessor (async)    │ │
│  │  LoadSpec                     │   │  lazy db._etl/async_db._etl  │ │
│  │  build_init_sql()             │   │  .init() .run() .list_runs() │ │
│  │  build_upsert_sql()           │   └──────────────────────────────┘ │
│  │  build_truncate_sql()         │                                    │
│  └──────────────────────────────┘                                    │
├──────────────────────────────────────────────────────────────────────┤
│                 pycopg/queries.py  (MODIFIED FILE)                   │
│   ETL_INIT_PIPELINE_RUNS  ETL_INSERT_RUN  ETL_UPDATE_RUN            │
│   ETL_LIST_RUNS  ETL_GET_LAST_RUN                                   │
├──────────────────────────────────────────────────────────────────────┤
│              pycopg/database.py  (MODIFIED — adds etl property)      │
│              pycopg/async_database.py  (MODIFIED — adds etl property)│
├──────────────────────────────────────────────────────────────────────┤
│                    Existing infrastructure                            │
│  Database / AsyncDatabase   psycopg_pool   tenacity   pandas        │
│  to_dataframe()  insert_many()  upsert_many()  transaction()        │
└──────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Location |
|-----------|----------------|----------|
| `Pipeline` | Immutable, DB-free descriptor of a pipeline (extract + transform + load) | `etl.py` |
| `ExtractSpec` | Describes source: table-name OR raw SQL, optional schema | `etl.py` |
| `LoadSpec` | Describes target: table-name, schema, load mode (`truncate` or `upsert`), conflict keys | `etl.py` |
| Pure SQL builders | Build DDL / DML strings without any DB access (shared between sync and async) | `etl.py` |
| SQL constants | Multi-line SQL strings for `pipeline_runs` DDL and DML | `queries.py` |
| `EtlAccessor` | Sync orchestrator: init table, run pipeline, record outcome | `etl.py` |
| `AsyncEtlAccessor` | Async mirror of `EtlAccessor`; re-uses same pure builders | `etl.py` |
| `db.etl` property | Lazy accessor factory on `Database` | `database.py` |
| `async_db.etl` property | Lazy accessor factory on `AsyncDatabase` | `async_database.py` |

---

## Recommended Project Structure

```
pycopg/
├── etl.py               # NEW — pure builders + EtlAccessor + AsyncEtlAccessor
├── queries.py           # MODIFIED — add ETL_* SQL constants section
├── database.py          # MODIFIED — add `etl` lazy property + `_etl` field
├── async_database.py    # MODIFIED — add `etl` lazy property + `_etl` field
├── __init__.py          # MODIFIED — export EtlAccessor, AsyncEtlAccessor, Pipeline
└── exceptions.py        # MODIFIED (optional) — add PipelineError

tests/
├── test_etl.py              # NEW — unit tests for pure builders + Pipeline dataclass
├── test_etl_integration.py  # NEW — integration tests for EtlAccessor (real DB)
├── test_etl_async.py        # NEW — async mirror of test_etl_integration.py
└── test_parity.py           # NO CHANGES needed if method names match
```

### Structure Rationale

- **etl.py:** mirrors `spatial.py` exactly. All pure functions at module level; both accessor classes in the same file. This keeps the pattern consistent and avoids a separate accessors/builders split that would add indirection without benefit.
- **queries.py:** existing convention — every multi-line SQL constant lives here with a section comment block. ETL constants join existing sections with a new `# ETL QUERIES` block.
- **database.py / async_database.py:** only a `_etl` field in `__init__` and an `etl` lazy property need to be added. Zero logic changes to the core DB classes.

---

## Architectural Patterns

### Pattern 1: Pure Builders + Accessor Split (mirror of spatial.py)

**What:** All SQL assembly lives in stateless module-level functions that return `(sql, params)` or a plain SQL string. The accessor classes hold the DB reference and call these builders.

**When to use:** Always for ETL — the same extract SQL, upsert SQL, and run-tracking SQL is used by both `EtlAccessor` and `AsyncEtlAccessor` without duplication.

**Trade-offs:** Slightly more boilerplate (separate builder + accessor method), but builders are fully unit-testable without a DB, and the pattern is already established throughout `spatial.py`.

**Example (builder in etl.py):**
```python
def build_upsert_sql(
    table: str,
    columns: list[str],
    conflict_columns: list[str],
    schema: str = "public",
) -> tuple[str, str]:
    """Build INSERT ... ON CONFLICT DO UPDATE SQL for idempotent load.

    Pure function: no I/O, no DB reference.

    Returns
    -------
    tuple of (str, str)
        (sql_template, columns_csv) matching QueryMixin._build_insert_sql shape.
    """
    validate_identifiers(table, schema, *columns, *conflict_columns)
    cols = ", ".join(columns)
    ph = ", ".join(["%s"] * len(columns))
    update_cols = [c for c in columns if c not in conflict_columns]
    update_str = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
    conflict_str = ", ".join(conflict_columns)
    sql = (
        f"INSERT INTO {schema}.{table} ({cols}) VALUES ({ph}) "
        f"ON CONFLICT ({conflict_str}) DO UPDATE SET {update_str}"
    )
    return sql, cols
```

### Pattern 2: Frozen Dataclass Pipeline Descriptor

**What:** `Pipeline` is a `@dataclass(frozen=True)` that carries all declarative fields but performs no I/O. It is passed to `db.etl.run(pipeline)`.

**When to use:** Always — frozen ensures the pipeline definition is not mutated between runs, which is important for idempotency guarantees.

**Trade-offs:** Frozen dataclasses cannot have mutable defaults directly; `tuple` is used for `conflict_columns` instead of `list`. The `transform` callable is included, which means the dataclass is not JSON-serializable by default — acceptable for v0.5.0.

**Example (Pipeline + supporting specs in etl.py):**
```python
from __future__ import annotations
import dataclasses
from typing import Callable
import pandas as pd


@dataclasses.dataclass(frozen=True)
class ExtractSpec:
    table: str | None = None
    sql: str | None = None
    schema: str = "public"

    def __post_init__(self) -> None:
        if (self.table is None) == (self.sql is None):
            raise ValueError("Exactly one of table= or sql= must be provided")
        if self.table:
            validate_identifiers(self.table, self.schema)


@dataclasses.dataclass(frozen=True)
class LoadSpec:
    table: str
    schema: str = "public"
    mode: str = "upsert"              # "truncate" | "upsert"
    conflict_columns: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.mode not in ("truncate", "upsert"):
            raise ValueError(f"mode must be 'truncate' or 'upsert', got {self.mode!r}")
        if self.mode == "upsert" and not self.conflict_columns:
            raise ValueError("conflict_columns must be non-empty for mode='upsert'")
        validate_identifiers(self.table, self.schema)
        if self.conflict_columns:
            validate_identifiers(*self.conflict_columns)


@dataclasses.dataclass(frozen=True)
class Pipeline:
    name: str
    extract: ExtractSpec
    load: LoadSpec
    transform: Callable[[pd.DataFrame], pd.DataFrame] | None = None
```

### Pattern 3: Separate Transaction for Run-Log Write

**What:** The load transaction and the `pipeline_runs` write transaction are separate connections. The load uses `db.transaction()` which rolls back on error. The run-log write uses an independent `db.connect()` block that always commits, even if the load failed.

**When to use:** Always, in `EtlAccessor.run()` and `AsyncEtlAccessor.run()`.

**Trade-offs:** Two round-trips to the DB for the run record (INSERT at start, UPDATE at end). Acceptable — run tracking is lightweight metadata. The alternative (same transaction) would lose the failure record on rollback.

**Example (sync execution flow):**
```python
def run(self, pipeline: Pipeline) -> dict:
    run_id = self._start_run(pipeline.name)   # independent connection, commits immediately
    try:
        with self._db.transaction() as conn:
            df = self._extract(pipeline.extract)
            if pipeline.transform is not None:
                df = pipeline.transform(df)
            rows_loaded = self._load(pipeline.load, df)
        self._end_run(run_id, "success", rows_loaded)
        return {"run_id": run_id, "status": "success", "rows_loaded": rows_loaded}
    except Exception as exc:
        self._end_run(run_id, "error", 0, error=str(exc))  # commits failure record
        raise
```

---

## Data Flow

### ETL Execution Flow (sync)

```
db.etl.run(pipeline)
    |
    +-- _start_run(name)                    [independent conn, commits]
    |       INSERT INTO pipeline_runs (status='running', started_at=now())
    |       returns run_id (int)
    |
    +-- with db.transaction():              [load transaction -- rolls back on error]
    |       |
    |       +-- _extract(extract_spec)
    |       |     db.to_dataframe(table=... or sql=...) -> pd.DataFrame
    |       |
    |       +-- pipeline.transform(df)      [Python, no I/O, sync callable]
    |       |     -> pd.DataFrame
    |       |
    |       +-- _load(load_spec, df)
    |             mode="truncate": TRUNCATE TABLE ... then df via from_dataframe(if_exists="append")
    |             mode="upsert":   db.upsert_many(table, rows, conflict_columns)
    |             returns rows_loaded (int)
    |
    +-- _end_run(run_id, status, rows_loaded [, error])
            [independent conn, commits always -- even if load raised]
            UPDATE pipeline_runs SET status=..., finished_at=now(), rows_loaded=... WHERE id=...
```

### ETL Execution Flow (async)

```
await async_db.etl.run(pipeline)
    |
    +-- await _start_run(name)              [independent async conn, commits]
    |
    +-- async with async_db.transaction(): [load transaction]
    |       |
    |       +-- await _extract(extract_spec)
    |       |     await async_db.to_dataframe(...)       [uses conn.run_sync internally]
    |       |
    |       +-- await loop.run_in_executor(None, pipeline.transform, df)
    |       |     [thread pool for sync callable -- consistent with run_sync pattern]
    |       |
    |       +-- await _load(load_spec, df)
    |             await async_db.upsert_many(...)  OR  TRUNCATE + conn.run_sync(df.to_sql)
    |
    +-- await _end_run(run_id, status, rows_loaded [, error])
```

### Key Data Flows

1. **Run tracking:** `pipeline_runs` row inserted before load starts; updated after load completes or fails. Two independent connections ensure the failure record always commits.
2. **Extract:** Delegates to existing `db.to_dataframe()` / `async_db.to_dataframe()` — no new extract logic needed beyond wrapping.
3. **Transform:** Pure Python callable on a DataFrame. No DB I/O. In async context, delegated to thread pool via `run_in_executor`.
4. **Load (truncate):** TRUNCATE DDL (autocommit=False inside transaction), then `from_dataframe(if_exists="append")`.
5. **Load (upsert):** Direct `upsert_many()` call — existing method handles batching and conflict resolution.

---

## Module Layout — What Goes Where

### pycopg/etl.py (NEW FILE)

```
Module-level (pure -- no DB, no I/O):
  @dataclass(frozen=True)  ExtractSpec
  @dataclass(frozen=True)  LoadSpec
  @dataclass(frozen=True)  Pipeline
  build_init_sql() -> str           # returns queries.ETL_INIT_PIPELINE_RUNS
  build_truncate_sql(table, schema) -> str
  _validate_pipeline(pipeline)      # raises ValueError on bad input

class EtlAccessor:
  __init__(db: Database)
  init() -> None                    # CREATE TABLE IF NOT EXISTS pipeline_runs
  run(pipeline: Pipeline) -> dict   # full ETL + run tracking
  list_runs(name: str | None, limit: int) -> list[dict]
  get_last_run(name: str) -> dict | None
  _start_run(name) -> int           # private: insert run row, return id
  _end_run(run_id, status, rows, error=None) -> None   # private: update row
  _extract(spec) -> pd.DataFrame    # private: calls db.to_dataframe
  _load(spec, df) -> int            # private: truncate or upsert, returns row count

class AsyncEtlAccessor:
  __init__(db: AsyncDatabase)
  async init() -> None
  async run(pipeline: Pipeline) -> dict
  async list_runs(name: str | None, limit: int) -> list[dict]
  async get_last_run(name: str) -> dict | None
  async _start_run(name) -> int
  async _end_run(run_id, status, rows, error=None) -> None
  async _extract(spec) -> pd.DataFrame
  async _load(spec, df) -> int
```

### pycopg/queries.py (MODIFIED)

Add a `# ETL QUERIES` section at the bottom:

```python
# =============================================================================
# ETL QUERIES
# =============================================================================

ETL_INIT_PIPELINE_RUNS = """
    CREATE TABLE IF NOT EXISTS pipeline_runs (
        id             BIGSERIAL    PRIMARY KEY,
        pipeline_name  TEXT         NOT NULL,
        status         TEXT         NOT NULL DEFAULT 'running',
        started_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
        finished_at    TIMESTAMPTZ,
        rows_loaded    BIGINT,
        error_message  TEXT,
        watermark      JSONB
    )
"""

ETL_INSERT_RUN = """
    INSERT INTO pipeline_runs (pipeline_name, status, started_at)
    VALUES (%s, 'running', now())
    RETURNING id
"""

ETL_UPDATE_RUN = """
    UPDATE pipeline_runs
    SET status = %s, finished_at = now(), rows_loaded = %s, error_message = %s
    WHERE id = %s
"""

ETL_LIST_RUNS = """
    SELECT id, pipeline_name, status, started_at, finished_at,
           rows_loaded, error_message
    FROM pipeline_runs
    {where_clause}
    ORDER BY started_at DESC
    LIMIT %s
"""

ETL_GET_LAST_RUN = """
    SELECT id, pipeline_name, status, started_at, finished_at,
           rows_loaded, error_message
    FROM pipeline_runs
    WHERE pipeline_name = %s
    ORDER BY started_at DESC
    LIMIT 1
"""
```

### pycopg/database.py (MODIFIED)

Two additions only:

```python
# In __init__:
self._etl: EtlAccessor | None = None

# New lazy property (after spatial property, same shape):
@property
def etl(self) -> EtlAccessor:
    """Get or create the ETL accessor (lazy initialization).

    Returns
    -------
    EtlAccessor
        ETL pipeline runner namespace bound to this database.
    """
    if self._etl is None:
        from pycopg.etl import EtlAccessor
        self._etl = EtlAccessor(self)
    return self._etl
```

### pycopg/async_database.py (MODIFIED)

```python
# In __init__:
self._etl: AsyncEtlAccessor | None = None

# New lazy property:
@property
def etl(self) -> AsyncEtlAccessor:
    """Get or create the async ETL accessor (lazy initialization).

    Returns
    -------
    AsyncEtlAccessor
        Async ETL pipeline runner namespace bound to this database.
    """
    if self._etl is None:
        from pycopg.etl import AsyncEtlAccessor
        self._etl = AsyncEtlAccessor(self)
    return self._etl
```

### pycopg/__init__.py (MODIFIED)

```python
from pycopg.etl import AsyncEtlAccessor, EtlAccessor, ExtractSpec, LoadSpec, Pipeline
```

Add to `__all__`:  `"EtlAccessor"`, `"AsyncEtlAccessor"`, `"Pipeline"`, `"ExtractSpec"`, `"LoadSpec"`.

---

## Runner Method Signatures (Complete Reference)

### EtlAccessor (sync)

```python
def init(self) -> None:
    """Create the pipeline_runs tracking table if it does not exist."""

def run(self, pipeline: Pipeline) -> dict:
    """Execute a pipeline end-to-end and record the run outcome.

    Parameters
    ----------
    pipeline : Pipeline
        Declarative pipeline descriptor.

    Returns
    -------
    dict
        Keys: run_id (int), status ("success" or "error"), rows_loaded (int).

    Raises
    ------
    Exception
        Re-raises the original exception after recording failure in pipeline_runs.
    """

def list_runs(
    self,
    name: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Return recent pipeline run records.

    Parameters
    ----------
    name : str, optional
        Filter to this pipeline name. None returns all pipelines.
    limit : int, optional
        Maximum rows to return, by default 100.

    Returns
    -------
    list of dict
        Run records ordered newest-first.
    """

def get_last_run(self, name: str) -> dict | None:
    """Return the most recent run for a pipeline name, or None.

    Parameters
    ----------
    name : str
        Pipeline name.

    Returns
    -------
    dict or None
        Most recent run record, or None if no runs exist.
    """
```

### AsyncEtlAccessor (async -- identical parameter names)

```python
async def init(self) -> None: ...
async def run(self, pipeline: Pipeline) -> dict: ...
async def list_runs(self, name: str | None = None, limit: int = 100) -> list[dict]: ...
async def get_last_run(self, name: str) -> dict | None: ...
```

**Parity note:** `test_parity.py` uses `inspect.getmembers(Database)` and `inspect.getmembers(AsyncDatabase)`. The `etl` property is a member of both classes, so it is picked up automatically. The public methods `init`, `run`, `list_runs`, `get_last_run` exist on both accessor classes — their signatures have identical parameter names, which satisfies `test_method_signatures_match`. No changes to `test_parity.py` are needed.

---

## Transaction Boundaries

### The Tension

A failed load must roll back all inserted data (atomicity). But the `pipeline_runs` failure record must commit independently — otherwise a failed run leaves no trace, defeating the purpose of run tracking.

### Recommended Pattern: Two Independent Connections

Run-tracking writes (`_start_run` and `_end_run`) each open their own short-lived connection via `db.connect()` (sync) or an independent `async_db.connect()` (async). These commits are unconditional.

The load step (`_extract` + `transform` + `_load`) runs inside `db.transaction()`. If it raises, the load transaction rolls back, but `_end_run` is called in the `except` block using a fresh connection.

```
START:  independent conn
            INSERT pipeline_runs (status='running') COMMIT

LOAD:   db.transaction()
            extract -> transform -> load
            [COMMIT on success]  [ROLLBACK on error]

END:    independent conn
            UPDATE pipeline_runs (status, finished_at, rows_loaded) COMMIT
            [called in both success path AND except block]
```

**Why not use the session connection for run tracking?** Sessions and transactions in psycopg share the underlying connection. Writing to `pipeline_runs` inside the same transaction means the failure record is lost on rollback. A fresh connection avoids this — the same approach used by PostgreSQL job schedulers and migration systems.

**Why not SAVEPOINT?** Savepoints are deferred to v0.6.0 (API-05 in PROJECT.md). The two-connection approach is simpler and sufficient for v0.5.0.

**Impact on async:** `AsyncDatabase` uses psycopg async connections. The same two-connection pattern applies: `_start_run` and `_end_run` open independent `AsyncConnection` instances via `psycopg.AsyncConnection.connect(...)` or the async pool, bypassing the active session.

---

## `pipeline_runs` Schema and Forward Compatibility

### Recommended Schema

```sql
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id             BIGSERIAL    PRIMARY KEY,
    pipeline_name  TEXT         NOT NULL,
    status         TEXT         NOT NULL DEFAULT 'running',
                   -- allowed values: 'running' | 'success' | 'error'
    started_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    finished_at    TIMESTAMPTZ,           -- NULL until run completes
    rows_loaded    BIGINT,                -- NULL until run completes
    error_message  TEXT,                  -- NULL unless status='error'

    -- Reserved for v0.6.0 incremental watermarks.
    -- Always NULL in v0.5.0 rows. JSONB accommodates any watermark
    -- shape (timestamp, integer offset, string cursor) without ALTER TABLE.
    watermark      JSONB
);
```

### Forward-Compat Design Choices

- **`watermark JSONB`** is present but always NULL in v0.5.0. v0.6.0 writes watermark values into this column without an `ALTER TABLE` or migration. No migration pain — the column exists, it's just unused.
- **`status TEXT`** (not ENUM) — avoids `ALTER TYPE` to add future status values. A CHECK constraint can be added later if desired.
- **`BIGSERIAL`** id — handles high-volume pipelines without risk of integer overflow.
- **`TIMESTAMPTZ`** (not `TIMESTAMP`) for all time columns — timezone-aware, required for deployments running across zones.
- All nullable columns (`finished_at`, `rows_loaded`, `error_message`, `watermark`) are NOT constrained NOT NULL — they are genuinely unknown at insert time.

### Table Initialization: Explicit `db.etl.init()`

**Recommendation: explicit `db.etl.init()` call, not lazy auto-create inside `run()`.**

Rationale:
- Lazy init inside `run()` adds an existence-check round-trip on every pipeline execution. For frequent pipelines this matters.
- Migration system approach (versioned SQL files) would require the migration runner — coupling ETL setup to migration workflow is invasive and inconsistent with how PostGIS is handled (`db.create_extension('postgis')` is always explicit).
- `db.etl.init()` is a single bootstrap call. Callers put it in their startup script. `CREATE TABLE IF NOT EXISTS` makes it idempotent — calling `init()` multiple times is always safe.
- This is consistent with the existing `db.spatial` accessor pattern: PostGIS availability is checked explicitly, not lazily injected into every helper call.

---

## Parity-Safe Data Flow: Pure vs Accessor

### What is Pure (shared, no I/O — usable in both accessors and unit tests)

| Item | Why Pure |
|------|----------|
| `ExtractSpec`, `LoadSpec`, `Pipeline` dataclasses | no DB, no I/O; validated in `__post_init__` |
| `build_init_sql()` | returns `queries.ETL_INIT_PIPELINE_RUNS` string |
| `build_truncate_sql(table, schema)` | returns `TRUNCATE TABLE ...` string |
| `_validate_pipeline(pipeline)` | raises `ValueError` on invalid combos |
| All `queries.py` ETL constants | string literals |

### What is Accessor-Only (does I/O, differs sync/async)

| Method | Sync implementation | Async implementation |
|--------|---------------------|----------------------|
| `init()` | `db.execute(ETL_INIT_PIPELINE_RUNS)` | `await async_db.execute(...)` |
| `_start_run(name)` | `db.execute(ETL_INSERT_RUN, [name])` | `await async_db.execute(...)` |
| `_end_run(...)` | `db.execute(ETL_UPDATE_RUN, [...])` | `await async_db.execute(...)` |
| `_extract(spec)` | `db.to_dataframe(table=... or sql=...)` | `await async_db.to_dataframe(...)` |
| `transform(df)` | `pipeline.transform(df)` direct call | `await loop.run_in_executor(None, fn, df)` |
| `_load mode=truncate` | `db.execute("TRUNCATE ...")` + `db.from_dataframe(if_exists="append")` | `await async_db.execute(...)` + `await conn.run_sync(df.to_sql)` |
| `_load mode=upsert` | `db.upsert_many(table, rows, conflict_columns)` | `await async_db.upsert_many(...)` |
| `list_runs(...)` | `db.execute(ETL_LIST_RUNS, [...])` | `await async_db.execute(...)` |
| `get_last_run(name)` | `db.execute(ETL_GET_LAST_RUN, [name])` | `await async_db.execute(...)` |

### The One Parity Risk: Transform Callable in Async Context

The `transform` callable is a sync Python function (pandas is sync-only). In the async accessor, calling it directly blocks the event loop. The existing `run_sync` pattern (used in `async_database.py` at lines 1937, 1971, 2026) shows how to handle this for pandas operations: `await conn.run_sync(lambda sync_conn: pd.read_sql(...))`. However, `transform` takes a DataFrame, not a connection.

**Recommendation:** In `AsyncEtlAccessor.run()`, wrap the transform call:
```python
import asyncio
loop = asyncio.get_event_loop()
df = await loop.run_in_executor(None, pipeline.transform, df)
```
This delegates the sync callable to the default thread pool executor, consistent with how `conn.run_sync` works internally. Document this in the numpydoc docstring under a "Notes" section. This is the only divergence between sync and async execution paths.

---

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| Small pipelines (<100K rows) | No changes; `upsert_many` batch insert suffices |
| Large pipelines (>1M rows) | For truncate-load mode, swap `from_dataframe` for `copy_insert()` (already on `Database`); upsert-by-key stays row-batched |
| High-frequency pipelines | Add index on `(pipeline_name, started_at)` in `pipeline_runs` for efficient `list_runs` queries |
| Many parallel pipelines | `pipeline_runs` is append-only; no locking contention on run-tracking writes |

These are v0.6.0+ concerns. v0.5.0 uses the standard `upsert_many` / `from_dataframe` paths that exist today.

---

## Integration Points with Existing Architecture

### Existing Patterns Being Reused

| Existing Pattern | How ETL Uses It |
|-----------------|-----------------|
| `db.spatial` lazy property in `database.py` | `db.etl` property follows identical shape |
| `_spatial` private field in `__init__` | `_etl` private field follows identical shape |
| `AsyncSpatialAccessor` deferred guard pattern | `AsyncEtlAccessor` — no guard needed; `init()` is explicit |
| `queries.py` SQL constants with section headers | ETL SQL constants added in new `# ETL QUERIES` section |
| `db.transaction()` context manager | Used for the load step |
| `db.connect()` context manager | Used for isolated run-tracking writes (`_start_run`, `_end_run`) |
| `db.to_dataframe()` | Used in `EtlAccessor._extract()` |
| `db.upsert_many()` | Used in `EtlAccessor._load(mode="upsert")` |
| `db.from_dataframe()` | Used in `EtlAccessor._load(mode="truncate")` |
| `conn.run_sync(fn)` pattern | Used in `AsyncEtlAccessor._load` for `df.to_sql` |
| `validate_identifiers()` | Called in `ExtractSpec.__post_init__` and `LoadSpec.__post_init__` |
| `test_parity.py` harness | No changes needed — `etl` property appears on both classes automatically |

---

## New vs Modified Files (Explicit List)

### New Files

| File | Purpose |
|------|---------|
| `pycopg/etl.py` | All ETL code: dataclasses, pure builders, EtlAccessor, AsyncEtlAccessor |
| `tests/test_etl.py` | Unit tests for pure builders and Pipeline dataclass validation (no DB needed) |
| `tests/test_etl_integration.py` | Integration tests for EtlAccessor (real PostgreSQL) |
| `tests/test_etl_async.py` | Integration tests for AsyncEtlAccessor (real PostgreSQL) |
| `docs/etl.md` | Sphinx documentation page (mirrors `docs/spatial.md`) |

### Modified Files

| File | Change |
|------|--------|
| `pycopg/queries.py` | Add `# ETL QUERIES` section with 5 SQL constants |
| `pycopg/database.py` | Add `_etl: EtlAccessor | None = None` in `__init__`; add `etl` property |
| `pycopg/async_database.py` | Add `_etl: AsyncEtlAccessor | None = None` in `__init__`; add `etl` property |
| `pycopg/__init__.py` | Import and export `EtlAccessor`, `AsyncEtlAccessor`, `Pipeline`, `ExtractSpec`, `LoadSpec` |
| `docs/index.rst` | Add ETL page to the Sphinx TOC |
| `CHANGELOG.md` | Record new `db.etl.*` surface |
| `MIGRATION.md` | Document `db.etl.init()` bootstrap requirement |

### Untouched Files

| File | Why |
|------|-----|
| `pycopg/base.py` | ETL logic is accessor-level; no new base-class behavior needed |
| `pycopg/spatial.py` | Not affected |
| `tests/test_parity.py` | Existing harness catches `etl` property automatically; no changes needed |

---

## Anti-Patterns

### Anti-Pattern 1: Lazy `init()` Inside `run()`

**What people do:** Check `IF NOT EXISTS pipeline_runs` on every `run()` call to avoid requiring an explicit init step.

**Why it's wrong:** Adds a redundant existence-check round-trip on every pipeline execution. Hides the setup step from the caller's view. Inconsistent with `db.create_extension('postgis')` which is always explicit.

**Do this instead:** Require `db.etl.init()` once at startup. `CREATE TABLE IF NOT EXISTS` makes it safe to call repeatedly.

### Anti-Pattern 2: Writing Run-Tracking Inside the Load Transaction

**What people do:** Put `pipeline_runs` INSERTs/UPDATEs inside the same `db.transaction()` block as the load.

**Why it's wrong:** When the load fails and the transaction rolls back, the `pipeline_runs` row disappears. A failed run leaves no trace.

**Do this instead:** Use independent connections for run-tracking writes, as described in the Transaction Boundaries section.

### Anti-Pattern 3: Blocking Transform in Async Accessor

**What people do:** Call `pipeline.transform(df)` directly inside an async method.

**Why it's wrong:** pandas operations are synchronous and can take seconds. This blocks the entire event loop, starving all other coroutines.

**Do this instead:** `await loop.run_in_executor(None, pipeline.transform, df)`, consistent with the `conn.run_sync` pattern already in `async_database.py`.

### Anti-Pattern 4: ETL Logic in base.py

**What people do:** Add `_extract`, `_load`, or pipeline helpers to `DatabaseBase` or `QueryMixin`.

**Why it's wrong:** The base/mixin layer is for SQL builders and shared config, not for feature-specific orchestration. Adding ETL logic there couples all Database subclasses to ETL concepts. `spatial.py` established the correct pattern: feature logic goes in a dedicated module with a dedicated accessor.

**Do this instead:** All ETL logic stays in `etl.py`. The `Database` and `AsyncDatabase` classes get only a lazy property — no logic.

---

## Suggested Build Order

Dependencies drive this order. Each step produces a stable, testable artifact before the next step begins. Sync and async are built simultaneously at each step (not sync-first then async catch-up — the PAR-* rework lesson from v0.4.0).

| Step | Components | Deliverable | Test coverage |
|------|------------|-------------|---------------|
| 1 | `Pipeline`, `ExtractSpec`, `LoadSpec` frozen dataclasses + `_validate_pipeline()` | Stable, serializable descriptors | `test_etl.py` unit tests, no DB |
| 2 | `queries.py` ETL constants + `build_init_sql()` + `build_truncate_sql()` pure builders | SQL string constants ready for accessors | `test_etl.py` unit tests, no DB |
| 3 | `EtlAccessor.init()` + `AsyncEtlAccessor.init()` + `pipeline_runs` table DDL | Foundation for run tracking | Integration: table exists after `init()` |
| 4 | `_start_run()` + `_end_run()` (sync + async) | Run lifecycle recording | Integration: rows with correct status appear |
| 5 | `_extract()` (sync + async) | Extract step for both modes | Integration: DataFrame returned from table or SQL |
| 6 | `_load(mode="truncate")` (sync + async) | Truncate-load path | Integration: data in target table, idempotent on re-run |
| 7 | `_load(mode="upsert")` (sync + async) | Upsert-by-key path | Integration: idempotent re-runs, conflict resolution |
| 8 | `EtlAccessor.run()` + `AsyncEtlAccessor.run()` full wiring | End-to-end pipeline execution | Integration: `run()` returns correct dict; `list_runs()` shows history; failure records commit |
| 9 | `list_runs()` + `get_last_run()` (sync + async) | Query surface complete | Integration: filtering by name, newest-first ordering |
| 10 | `db.etl` / `async_db.etl` lazy properties + `__init__.py` exports | Public API wired | Parity test passes; import `from pycopg import Pipeline` works |
| 11 | Docs page + CHANGELOG + coverage gate check | Shippable milestone | `interrogate >= 95`, coverage >= 94 |

**Phase decomposition hint for roadmapper:**
- Phase A: Steps 1–2 (pure layer — no DB, fully unit-tested before any I/O code)
- Phase B: Steps 3–4 (run tracking foundation — `init()` + `_start_run`/`_end_run`, sync + async)
- Phase C: Steps 5–7 (load modes — extract + truncate + upsert, sync + async)
- Phase D: Steps 8–9 (full runner — `run()` + `list_runs` + `get_last_run`, sync + async)
- Phase E: Step 10–11 (property wiring + exports + docs + release gate)

---

## Sources

- Direct source reading: `pycopg/spatial.py` (2731 lines) — canonical pattern mirrored
- Direct source reading: `pycopg/queries.py` — SQL constant style and sectioning convention
- Direct source reading: `pycopg/base.py` — `DatabaseBase`, `QueryMixin`, `SessionMixin`, pure builder functions
- Direct source reading: `pycopg/database.py` — `spatial` property (lines 229–249), `transaction()` (lines 316–335), `upsert_many` (lines 484–527)
- Direct source reading: `pycopg/async_database.py` — `spatial` property (lines 95–110), `run_sync` usage in `to_dataframe`/`from_dataframe` (lines 1937, 1971, 2026)
- Direct source reading: `pycopg/__init__.py` — `__all__` export conventions
- Direct source reading: `tests/test_parity.py` — parity harness mechanics (lines 1–110): `inspect.getmembers`, `SYNC_ONLY_METHODS`, `ASYNC_ONLY_METHODS`, signature comparison
- Direct source reading: `.planning/PROJECT.md` — v0.5.0 scope, deferred items (API-05 savepoints, v0.6.0 watermarks), architectural decisions table

---

*Architecture research for: pycopg v0.5.0 ETL Pipeline Runner*
*Researched: 2026-06-14*
