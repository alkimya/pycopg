# Stack Research

**Domain:** Same-DB declarative ETL pipeline runner added to an existing thin PostgreSQL library (pycopg v0.5.0)
**Researched:** 2026-06-14
**Confidence:** HIGH — all claims verified against installed package versions and running source code in the v0.4.0 codebase

---

## Verdict: No New Runtime Dependencies

The ETL pipeline runner (extract → transform → load, idempotent, run-tracked, sync/async parity) can be built
entirely on the existing runtime stack. Every required capability is already present in the library or in Python
3.11+ stdlib. The only additions are new source files within `pycopg/`.

---

## Existing Runtime Stack (Unchanged for v0.5.0)

| Technology | Installed Version | Role in ETL Layer |
| ---------- | ----------------- | ----------------- |
| Python | 3.11+ | `dataclasses`, `typing.Protocol`, `datetime`, `uuid` — all ETL scaffold is stdlib |
| psycopg | 3.3.4 | extract (raw SQL SELECT), load (`INSERT` / `COPY`), DDL for `pipeline_runs` table |
| psycopg_pool | 3.3.1 | sync + async pools already wired — ETL uses them unchanged |
| pandas | 3.0.3 | `DataFrame` returned by `to_dataframe()`; transform callable receives and returns it |
| SQLAlchemy | 2.0.50 | Already used for `to_dataframe` / `from_dataframe` — ETL load phase uses the same path |
| tenacity | 9.1.4 | Retry on `OperationalError` already wired — ETL runner inherits it transparently |
| geopandas (optional) | via `[geo]` extra | GeoDataFrame transforms, same optional path as today |

Versions sourced from `uv run python -c "import ..."` against the live venv at `/home/loc/workspace/pycopg`.

---

## New Source Files (Zero New Deps)

The ETL layer adds Python source files only.

| New File | Purpose | Pattern It Follows |
| -------- | ------- | ------------------ |
| `pycopg/etl.py` | `Pipeline` dataclass, `TransformFn` Protocol, `SyncETLAccessor`, `AsyncETLAccessor`, module-level SQL builders | Mirrors `spatial.py` exactly |
| Additions to `pycopg/queries.py` | `CREATE_PIPELINE_RUNS_TABLE`, `INSERT_PIPELINE_RUN`, `UPDATE_PIPELINE_RUN` SQL constants | Follows existing query constants pattern |

No new module, no new package install step.

---

## How Each ETL Capability Maps to Existing Stack

### 1. Declarative pipeline definition

Use `dataclasses.dataclass` (stdlib, Python 3.11+) for the `Pipeline` descriptor:

```python
from __future__ import annotations
import dataclasses
from typing import Literal

@dataclasses.dataclass
class Pipeline:
    name: str
    extract_sql: str
    load_table: str
    transform: TransformFn | None = None   # see Protocol below
    load_mode: Literal["truncate", "upsert"] = "truncate"
    conflict_columns: list[str] = dataclasses.field(default_factory=list)
    schema: str = "public"
    extract_params: list | None = None

    def __post_init__(self) -> None:
        if self.load_mode == "upsert" and not self.conflict_columns:
            raise ValueError("conflict_columns required when load_mode='upsert'")
```

`dataclasses` is the right choice — lightweight, introspectable, zero-dep, and the `__post_init__` hook
provides validation without Pydantic or attrs.

### 2. Transform callable contract

Use `typing.Protocol` (stdlib, Python 3.11+, stable since Python 3.8) to define the transform shape:

```python
from typing import Protocol, runtime_checkable
import pandas as pd

@runtime_checkable
class TransformFn(Protocol):
    def __call__(self, df: pd.DataFrame) -> pd.DataFrame: ...
```

This covers:

- `transform=None` — identity; runner passes extracted DataFrame through unchanged
- Any plain function `def clean(df): return df.dropna()`
- Any lambda, `functools.partial`, or class with `__call__`

`@runtime_checkable` lets the runner check `isinstance(pipeline.transform, TransformFn)` at construction,
producing a clear error before any SQL runs. No Pydantic, beartype, or typeguard needed.

For async transforms that call sync pandas operations, the async runner applies the existing
`await conn.run_sync(...)` delegation pattern already used in `async_database.py` (lines 1937, 1971, 2026,
2100). No new pattern needed.

### 3. Extract phase

`db.to_dataframe(pipeline.extract_sql, params=pipeline.extract_params)` already exists in both
`Database` and `AsyncDatabase` (full parity shipped in v0.4.0). The ETL runner calls this and feeds
the result to `pipeline.transform(df)` (or passes it through if `transform is None`). No new method.

### 4. Idempotent load — truncate-load mode

```python
# Inside SyncETLAccessor.run()
with self._db.transaction():
    self._db.execute(f"TRUNCATE {schema}.{table}")
    self._db.from_dataframe(transformed_df, table, schema=schema)
```

Both `execute` and `from_dataframe` are already present in `Database` and `AsyncDatabase`. The
truncate + reload sequence is atomic when wrapped in the existing `transaction()` context manager.
No new method needed.

For large DataFrames the existing COPY path (database.py line 654, psycopg `cur.copy()`) is available
for the truncate-load mode where `ON CONFLICT` semantics are not needed. COPY is significantly faster
for bulk loads and already wired.

### 5. Idempotent load — upsert-by-key mode

```python
rows = transformed_df.to_dict("records")   # pandas stdlib, no new dep
self._db.upsert_many(
    table,
    rows,
    conflict_columns=pipeline.conflict_columns,
    schema=schema,
)
```

`upsert_many` is already in `database.py` (line 484). It builds `ON CONFLICT (...) DO UPDATE SET ...`
internally using psycopg parameterized queries — no new SQL builder needed. The async equivalent
`AsyncDatabase.upsert_many` is already at full parity (v0.4.0).

### 6. Run tracking — `pipeline_runs` table

Add SQL constants to `queries.py` (following the exact existing pattern):

```python
# queries.py additions — no new file, no migration framework
CREATE_PIPELINE_RUNS_TABLE = """
    CREATE TABLE IF NOT EXISTS public.pipeline_runs (
        id          BIGSERIAL    PRIMARY KEY,
        pipeline    TEXT         NOT NULL,
        started_at  TIMESTAMPTZ  NOT NULL,
        finished_at TIMESTAMPTZ,
        status      TEXT         NOT NULL
                    CHECK (status IN ('running', 'success', 'error')),
        rows_in     BIGINT,
        rows_out    BIGINT,
        error       TEXT
    )
"""

INSERT_PIPELINE_RUN = """
    INSERT INTO public.pipeline_runs
        (pipeline, started_at, status)
    VALUES (%s, %s, 'running')
    RETURNING id
"""

UPDATE_PIPELINE_RUN = """
    UPDATE public.pipeline_runs
    SET finished_at = %s, status = %s, rows_in = %s, rows_out = %s, error = %s
    WHERE id = %s
"""
```

The ETL accessor's `ensure_schema()` method calls `db.execute(CREATE_PIPELINE_RUNS_TABLE)` on first use —
identical to how pycopg's existing `Migrator` creates its own `_migrations` tracking table (migrations.py).
No external migration framework is warranted.

Timestamps use `datetime.datetime.now(tz=datetime.timezone.utc)` (stdlib). BIGSERIAL primary key (not UUID)
gives better index locality for an append-heavy run log. The `rows_in` / `rows_out` split is designed so
the v0.6.0 incremental watermark addition (reading `rows_out` of the last successful run as a cursor
lower-bound) requires no schema change.

### 7. Accessor pattern — mirrors `spatial.py` exactly

```python
# database.py addition
@property
def etl(self) -> SyncETLAccessor:
    """Get or create the ETL accessor (lazy initialization)."""
    if self._etl is None:
        from pycopg.etl import SyncETLAccessor
        self._etl = SyncETLAccessor(self)
    return self._etl

# async_database.py addition — identical structure
@property
def etl(self) -> AsyncETLAccessor:
    """Get or create the async ETL accessor (lazy initialization)."""
    if self._etl is None:
        from pycopg.etl import AsyncETLAccessor
        self._etl = AsyncETLAccessor(self)
    return self._etl
```

Module-level SQL builder functions (e.g., `build_run_insert_sql`) are shared byte-identical between
`SyncETLAccessor` and `AsyncETLAccessor`, following the `build_*_sql` pattern in `spatial.py`. Stateless,
no I/O, fully unit-testable without a database.

---

## What NOT to Add

| Do NOT Add | Why It Is Overkill | What to Use Instead |
| ---------- | ------------------ | ------------------- |
| **dlt** (data load tool) | Full ETL framework with connectors, schemas, staging, secrets management — pycopg is same-DB only, single-process; dlt becomes a heavyweight transitive dep with its own version matrix | `db.from_dataframe` + `db.upsert_many` |
| **Airflow / Prefect / Dagster** | Distributed scheduler/orchestrators — v0.5.0 is an in-process runner; scheduling, DAG topology, and workers are the caller's concern entirely | Caller's own loop or `schedule` |
| **SQLAlchemy Core query builder** | In `Out of Scope` in PROJECT.md; would balloon the API surface; pycopg intentionally keeps raw SQL | SQL constants in `queries.py` |
| **Pydantic** | Schema validation for `Pipeline` fields — `dataclasses` + `__post_init__` raises `ValueError` and covers all necessary validation with zero new deps | `dataclasses.dataclass` + `__post_init__` |
| **attrs / cattrs** | Same role as Pydantic, richer dataclasses — overkill for a 6-field pipeline descriptor | `dataclasses.dataclass` |
| **alembic** | Schema migration for `pipeline_runs` — `CREATE TABLE IF NOT EXISTS` is sufficient for a single auto-created tracking table; pycopg already has its own migration system | `CREATE_PIPELINE_RUNS_TABLE` constant + `execute()` |
| **apache-beam / petl / dask** | Full ETL pipeline libraries — they replace pycopg entirely for this purpose rather than extending it; multi-process / distributed, not same-DB | The thin ETL layer we're building |
| **asyncpg** | Different async driver — psycopg 3 already ships async natively; switching drivers rewrites the entire library | `psycopg` async (already in use) |
| **beartype / typeguard** | Runtime type-checking of transform callable — `isinstance(fn, TransformFn)` via `@runtime_checkable Protocol` provides structural checking without any new dep | `@runtime_checkable` `Protocol` from `typing` |
| **pyarrow / pyarrow-parquet** | Columnar / Parquet I/O — out of scope for v0.5.0; cross-format sinks deferred to v0.6.0+ | pandas `DataFrame` (already present) |
| **schedule / APScheduler** | Job scheduling — pycopg is a library, not a daemon; callers schedule ETL runs using their own tools | Caller-provided scheduler |

---

## Version Compatibility (Existing Stack)

| Pair | Status | Notes |
| ---- | ------ | ----- |
| psycopg 3.3.x + psycopg_pool 3.3.x | Compatible | Same major stream; both provide async natively |
| pandas 3.0.x + SQLAlchemy 2.0.x | Compatible | `to_dataframe` uses SQLAlchemy 2 engine; `read_sql` signature verified working |
| Python 3.11 + `dataclasses` + `typing.Protocol` | Compatible | Both stable since Python 3.7/3.8 respectively |
| Python 3.11 + `@runtime_checkable` Protocol | Compatible | Stable since Python 3.8; structural instance checks work correctly |
| tenacity 9.x + psycopg `OperationalError` | Compatible | Retry wiring unchanged; ETL runner inherits it transparently |

---

## Installation (No Change for Users)

```bash
# No new dep — identical to v0.4.0
pip install pycopg          # core ETL included in default install
pip install pycopg[geo]     # if transforms use GeoDataFrames
```

```bash
# Dev — no new dev deps either
uv sync --all-extras --dev
```

---

## Supporting Libraries (Dev — Already Present)

| Tool | Version | ETL-specific Use |
| ---- | ------- | ---------------- |
| pytest | existing | ETL integration tests with real PostgreSQL (same `pycopg_test` DB) |
| pytest-asyncio | existing | Async ETL accessor tests; `asyncio_mode = "auto"` already configured |
| black + ruff | existing | Format/lint `etl.py` and queries additions |
| interrogate | existing | Enforce numpydoc docstring coverage on new ETL public API |

---

## Sources

- Live venv introspection: `uv run python -c "import ..."` — psycopg 3.3.4, pandas 3.0.3, psycopg_pool 3.3.1, tenacity 9.1.4, SQLAlchemy 2.0.50 (HIGH confidence)
- `/home/loc/workspace/pycopg/pycopg/spatial.py` — `SpatialAccessor` / `AsyncSpatialAccessor` pattern with lazy `@property` and shared module-level builders (HIGH confidence: read directly)
- `/home/loc/workspace/pycopg/pycopg/database.py` — `upsert_many` (line 484), COPY insert (line 654), `from_dataframe` (line 1364), `spatial` lazy property (line 228) (HIGH confidence: read directly)
- `/home/loc/workspace/pycopg/pycopg/queries.py` — SQL constant pattern and conventions (HIGH confidence: read directly)
- `/home/loc/workspace/pycopg/pycopg/base.py` — `QueryMixin`, `DatabaseBase` shared between sync/async (HIGH confidence: read directly)
- `/home/loc/workspace/pycopg/pycopg/migrations.py` — `Migrator` tracking table pattern (HIGH confidence: read directly)
- `/home/loc/workspace/pycopg/pyproject.toml` — declared runtime deps and optional extras (HIGH confidence: read directly)
- `/home/loc/workspace/pycopg/.planning/PROJECT.md` — Out of Scope list, v0.5.0 ETL goals, key decisions (HIGH confidence: read directly)
- Python 3.11 stdlib — `dataclasses`, `typing.Protocol`, `@runtime_checkable`, `datetime`, `uuid` (HIGH confidence: stable stdlib, confirmed importable in live venv)

---

*Stack research for: pycopg v0.5.0 ETL Pipeline Runner*
*Researched: 2026-06-14*
