# Phase 19: Sync Runner & Query Surface - Pattern Map

**Mapped:** 2026-06-15
**Files analyzed:** 4 (2 modified source files + 2 modified test files)
**Analogs found:** 6 / 6

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `pycopg/etl.py` — `RunResult` dataclass | model | transform | `Pipeline` frozen dataclass (`etl.py:70`) | exact |
| `pycopg/etl.py` — `_row_to_result` function | utility | transform | `_step_label` / `_build_insert_sql` pure builders (`etl.py:414`, `etl.py:291`) | exact |
| `pycopg/etl.py` — `ETLAccessor.run()` (upgrade) | service | request-response | current `ETLAccessor.run()` body (`etl.py:579–781`) | exact (self-analog) |
| `pycopg/etl.py` — `ETLAccessor.history()` / `last_run()` | service | CRUD | `ETLAccessor._start_run()` / `_end_run()` dict_row pattern (`etl.py:514–577`) | exact |
| `pycopg/queries.py` — `ETL_GET_RUN` constant | config | request-response | `ETL_GET_LAST_RUN` / `ETL_LIST_RUNS` (`queries.py:281–295`) | exact |
| `tests/test_etl.py` — `TestRowToResult` class | test | transform | `TestPipeline` class (`test_etl.py:21`) | role-match |
| `tests/test_etl_accessor.py` — `TestRunResultSurface` class | test | CRUD | `TestRunPipelineIntegration` / `TestETLAccessorIntegration` (`test_etl_accessor.py:231, 446`) | exact |

---

## Pattern Assignments

### `RunResult` dataclass — `pycopg/etl.py` (model, transform)

**Analog:** `Pipeline` frozen dataclass, `pycopg/etl.py` lines 70–75

**Placement:** Immediately after the `Pipeline` class block (which ends before `_is_sql_source` at line 202). `RunResult` is the second module-level value object, placed at ~line 202.

**Decorator + field block pattern** (`etl.py:70–71`, decorator only shown; full `Pipeline` body is 70–199):
```python
@dataclass(frozen=True)
class Pipeline:
```

**Frozen-dataclass style to copy exactly** (from RESEARCH.md §"RunResult frozen-dataclass idiom"):
```python
@dataclass(frozen=True)
class RunResult:
    """Immutable snapshot of a completed (or dry-run) ETL pipeline run."""
    run_id: int | None
    pipeline_name: str
    status: str
    rows_extracted: int
    rows_loaded: int
    started_at: datetime
    finished_at: datetime
    error: str | None
```

**Key notes:**
- `@dataclass(frozen=True)` — exact decorator, same as `Pipeline` at `etl.py:70`
- No `__post_init__` (D-02 — no validation on `RunResult`)
- `from __future__ import annotations` already at `etl.py:25` — `int | None` and `str | None` union syntax works
- `datetime` type hint from `from datetime import UTC, datetime` at `etl.py:30`
- `run_id: int | None` (D-05: `None` for dry runs, `int` for persisted)
- `error: str | None` (D-03: maps from `pipeline_runs.error_message`)

---

### `_row_to_result` — `pycopg/etl.py` (utility, transform)

**Analog:** `_step_label` pure builder, `pycopg/etl.py` lines 414–440

**Placement:** After `_step_label` (line 440) and before `class ETLAccessor` (line 443). Slots in as a peer pure module-level function.

**Pure-builder placement pattern** (`etl.py:414–440`):
```python
def _step_label(fn: object) -> str:
    """Return a human-readable label for a transform step function.

    ...

    Parameters
    ----------
    fn : callable
        The transform step whose label is needed.

    Returns
    -------
    str
        ``fn.__name__`` when it is a non-empty string other than
        ``"<lambda>"``; ``repr(fn)`` otherwise.
    """
    name = getattr(fn, "__name__", None)
    if name and name != "<lambda>":
        return name
    return repr(fn)


class ETLAccessor:   # ← _row_to_result inserts immediately before this line
```

**`_row_to_result` column-mapping pattern** (D-10, from RESEARCH.md):
```python
def _row_to_result(row: dict) -> RunResult:
    """Map a ``dict_row`` from ``pipeline_runs`` to a :class:`RunResult`.

    Pure function — no I/O, no ``self``. Maps ``error_message -> error``
    and drops ``error_traceback`` and ``watermark`` (D-10).

    Parameters
    ----------
    row : dict
        A row from ``pipeline_runs`` fetched with the ``dict_row`` factory.

    Returns
    -------
    RunResult
        Immutable snapshot of the run.
    """
    return RunResult(
        run_id=row["run_id"],
        pipeline_name=row["pipeline_name"],
        status=row["status"],
        rows_extracted=row["rows_extracted"],
        rows_loaded=row["rows_loaded"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        error=row["error_message"],   # rename: DB column -> RunResult field
    )
```

**Critical:** use `row["error_message"]` (DB column name), not `row["error"]`. The rename happens here, not in the schema.

---

### `ETLAccessor.run()` return upgrade — `pycopg/etl.py` (service, request-response)

**Analog:** current `ETLAccessor.run()`, `pycopg/etl.py` lines 579–781

**Current signature** (`etl.py:579`):
```python
def run(self, pipeline: Pipeline) -> int:
```

**New signature:**
```python
def run(self, pipeline: Pipeline, dry_run: bool = False) -> RunResult:
```

**Seam A — dry_run fork point** (insert before `etl.py:641`, after `name = pipeline.name` at line 640):
```python
name = pipeline.name
if dry_run:
    started_at = datetime.now(UTC)
    # ... extract + transform (same as normal path) ...
    finished_at = datetime.now(UTC)
    return RunResult(
        run_id=None,
        pipeline_name=name,
        status="dry_run",
        rows_extracted=rows_extracted,
        rows_loaded=0,
        started_at=started_at,
        finished_at=finished_at,
        error=None,
    )
self.init()              # etl.py:641 — only reached when not dry_run
run_id = self._start_run(name)   # etl.py:642
```

**Seam B — return upgrade** (replaces `return run_id` at `etl.py:781` and `etl.py:710`):

The `dict_row` connection pattern to copy from `etl.py:514–520` (`_start_run`):
```python
# _start_run existing pattern (etl.py:514–520):
with self._db.connect(autocommit=True) as conn:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            queries.ETL_INSERT_RUN,
            [name, "running", datetime.now(UTC)],
        )
        return cur.fetchone()["run_id"]
```

Apply same pattern for the re-SELECT at `etl.py:781`:
```python
# Replace "return run_id" at line 781 with:
with self._db.connect(autocommit=True) as conn:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(queries.ETL_GET_RUN, [run_id])
        row = cur.fetchone()
return _row_to_result(row)
```

Also replace the empty-DataFrame early return at `etl.py:709–710`:
```python
# Was (etl.py:708–710):
if not rows:
    self._end_run(run_id, "success", rows_extracted, 0)
    return run_id   # ← change this

# Becomes:
if not rows:
    self._end_run(run_id, "success", rows_extracted, 0)
    with self._db.connect(autocommit=True) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(queries.ETL_GET_RUN, [run_id])
            row = cur.fetchone()
    return _row_to_result(row)
```

**Exception handler (`etl.py:769–778`) — NO CHANGE.** The `raise` re-raises immediately; no return value needed on the failure path.

---

### `ETLAccessor.history()` and `ETLAccessor.last_run()` — `pycopg/etl.py` (service, CRUD)

**Analog:** `ETLAccessor._start_run()` and `_end_run()`, `pycopg/etl.py` lines 514–577

**`dict_row` autocommit connection pattern** (copy from `etl.py:514–520`):
```python
# _start_run — the canonical template (etl.py:514–520):
with self._db.connect(autocommit=True) as conn:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(queries.ETL_INSERT_RUN, [...])
        return cur.fetchone()["run_id"]
```

**`history()` method** (new, follows pattern above):
```python
def history(self, name: str, limit: int = 100) -> list[RunResult]:
    with self._db.connect(autocommit=True) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(queries.ETL_LIST_RUNS, [name, limit])
            rows = cur.fetchall()
    return [_row_to_result(row) for row in rows]
```

**`last_run()` method** (new, runs `ETL_GET_LAST_RUN` directly per D-07):
```python
def last_run(self, name: str) -> RunResult | None:
    with self._db.connect(autocommit=True) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(queries.ETL_GET_LAST_RUN, [name])
            row = cur.fetchone()
    return _row_to_result(row) if row is not None else None
```

**Key pattern rules:**
- Always use `autocommit=True` (same as `_start_run`/`_end_run`) — read methods are clean connections, not inside a session transaction
- `%s`-only parameterization — `pipeline_name` is a bound value, never f-string interpolated
- `dict_row` factory already imported at `etl.py:34`: `from psycopg.rows import dict_row`

---

### `ETL_GET_RUN` constant — `pycopg/queries.py` (config, request-response)

**Analog:** `ETL_GET_LAST_RUN`, `pycopg/queries.py` lines 289–295

**Existing constants to mirror** (`queries.py:281–295`):
```python
ETL_LIST_RUNS = """
    SELECT *
    FROM pipeline_runs
    WHERE pipeline_name = %s
    ORDER BY started_at DESC
    LIMIT %s
"""

ETL_GET_LAST_RUN = """
    SELECT *
    FROM pipeline_runs
    WHERE pipeline_name = %s
    ORDER BY started_at DESC
    LIMIT 1
"""
```

**New constant to add** (after `ETL_GET_LAST_RUN` at line 295, in the same ETL QUERIES block):
```python
ETL_GET_RUN = """
    SELECT *
    FROM pipeline_runs
    WHERE run_id = %s
"""
```

**Why `run_id`-keyed:** `ETL_GET_LAST_RUN` filters by `pipeline_name` — unsafe under concurrent runs of the same pipeline (two runs could finish in close succession and the wrong row returned). `ETL_GET_RUN` with `WHERE run_id = %s` targets the exact row by BIGSERIAL PK.
No `LIMIT` clause needed (PK guarantees at most one row).

---

### `TestRowToResult` — `tests/test_etl.py` (test, transform)

**Analog:** `TestPipeline` class, `tests/test_etl.py` lines 21–57

**Import block to extend** (`test_etl.py:1–18`):
```python
"""Tests for pycopg.etl — DB-free Pipeline + builder tests."""

import functools

import pytest

from pycopg import queries
from pycopg.etl import (
    Pipeline,
    _build_insert_sql,
    _build_upsert_sql,
    _is_sql_source,
    _step_label,
    _validate_load_mode,
    build_init_sql,
    build_truncate_sql,
)
from pycopg.exceptions import ETLTransformError, InvalidIdentifier
```

**Add to the import block** (extend the `from pycopg.etl import (...)` tuple):
```python
from pycopg.etl import (
    Pipeline,
    RunResult,          # ← add
    _build_insert_sql,
    _build_upsert_sql,
    _is_sql_source,
    _row_to_result,     # ← add
    _step_label,
    _validate_load_mode,
    build_init_sql,
    build_truncate_sql,
)
```

**`TestPipeline` class structure to mirror** (`test_etl.py:21–57`):
```python
class TestPipeline:
    """DB-free construction and validation tests for Pipeline."""

    def test_valid_construction_all_attributes(self):
        """Pipeline instantiates and all 8 attributes are readable (ROADMAP SC-1)."""
        p = Pipeline(
            name="nightly",
            source="raw_events",
            target="events",
            load_mode="append",
            conflict_columns=("id",),
            schema="public",
            transform=None,
            extract_limit=None,
        )
        assert p.name == "nightly"
        ...
```

**`TestRowToResult` class pattern** (DB-free, pure unit tests — no fixtures):
```python
class TestRowToResult:
    """Unit tests for _row_to_result — pure function, no DB."""

    def _sample_row(self, **overrides):
        """Return a minimal valid pipeline_runs dict_row."""
        from datetime import timezone
        base = {
            "run_id": 7,
            "pipeline_name": "test_pipeline",
            "status": "success",
            "rows_extracted": 10,
            "rows_loaded": 10,
            "started_at": datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            "finished_at": datetime(2026, 1, 1, 0, 0, 5, tzinfo=timezone.utc),
            "error_message": None,
            "error_traceback": None,
            "watermark": None,
        }
        base.update(overrides)
        return base

    def test_maps_all_8_fields(self):
        row = self._sample_row()
        result = _row_to_result(row)
        assert result.run_id == 7
        assert result.pipeline_name == "test_pipeline"
        assert result.status == "success"
        assert result.rows_extracted == 10
        assert result.rows_loaded == 10
        assert result.started_at is not None
        assert result.finished_at is not None
        assert result.error is None
```

**Key point:** No pytest fixtures needed — `_sample_row` is a plain helper method. No DB connection.

---

### `TestRunResultSurface` — `tests/test_etl_accessor.py` (test, CRUD)

**Analog:** `TestRunPipelineIntegration` and `TestETLAccessorIntegration`, `test_etl_accessor.py` lines 231 and 446

**Import block to extend** (`test_etl_accessor.py:1–13`):
```python
"""Tests for ETLAccessor — unit (param order / status string) + DB integration (SC-1..SC-4)."""

import traceback
import uuid
from datetime import datetime

import pandas as pd
import pytest
from psycopg.rows import dict_row

from pycopg import Database, queries
from pycopg.etl import ETLAccessor, Pipeline
from pycopg.exceptions import ETLTargetNotFoundError, ETLTransformError
```

**Add `RunResult` import:**
```python
from pycopg.etl import ETLAccessor, Pipeline, RunResult   # ← add RunResult
```

**Fixtures pattern** (`test_etl_accessor.py:20–34, 428–443`):
```python
@pytest.fixture
def db(db_config):
    """Create a Database instance connected to pycopg_test."""
    database = Database(db_config)
    yield database


@pytest.fixture
def cleanup_pipeline_runs(db):
    """Drop pipeline_runs after each integration test so tests are isolated."""
    yield
    try:
        db.execute("DROP TABLE IF EXISTS pipeline_runs CASCADE", autocommit=True)
    except Exception:
        pass


# etl_table fixture (test_etl_accessor.py:428–443):
@pytest.fixture
def etl_table(db):
    tbl = f"etl_test_{uuid.uuid4().hex[:8]}"
    db.execute(
        f'CREATE TABLE public."{tbl}" (id INTEGER, val TEXT)',
        autocommit=True,
    )
    yield tbl
    db.execute(f'DROP TABLE IF EXISTS public."{tbl}" CASCADE', autocommit=True)
```

**Integration test style to copy** (`test_etl_accessor.py:231–257`):
```python
def test_run_writes_full_row(self, db, cleanup_pipeline_runs):
    """SC-1: run() writes a complete pipeline_runs row including NULL watermark."""
    tbl = f"etl_fullrow_{uuid.uuid4().hex[:8]}"
    p = Pipeline(
        name="demo",
        source="SELECT 1 AS id",
        target=tbl,
        load_mode="replace",
    )
    try:
        run_id = db.etl.run(p)
    finally:
        db.execute(f'DROP TABLE IF EXISTS public."{tbl}" CASCADE', autocommit=True)

    rows = db.execute(
        "SELECT * FROM pipeline_runs WHERE run_id = %s",
        [run_id],
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["pipeline_name"] == "demo"
    assert row["status"] in ("running", "success", "failed")
    assert row["started_at"] is not None
```

**`TestRunResultSurface` skeleton** (mirrors `TestRunPipelineIntegration` at line 446):
```python
class TestRunResultSurface:
    """SC-1..SC-4: run/history/last_run/dry_run return RunResult objects."""

    # SC-1
    def test_run_returns_run_result(self, db, cleanup_pipeline_runs, etl_table):
        p = Pipeline(name="sc1", source="SELECT 1 AS id", target=etl_table, load_mode="replace")
        result = db.etl.run(p)
        assert isinstance(result, RunResult)

    def test_run_result_fields_match_pipeline_runs_row(self, db, cleanup_pipeline_runs, etl_table):
        p = Pipeline(name="sc1_fields", source="SELECT 1 AS id", target=etl_table, load_mode="replace")
        result = db.etl.run(p)
        rows = db.execute("SELECT * FROM pipeline_runs WHERE run_id = %s", [result.run_id])
        row = rows[0]
        assert result.pipeline_name == row["pipeline_name"]
        assert result.status == row["status"]
        assert result.rows_extracted == row["rows_extracted"]
        assert result.rows_loaded == row["rows_loaded"]
        assert result.error == row["error_message"]
    ...
```

---

## Shared Patterns

### `dict_row` autocommit connection pattern
**Source:** `pycopg/etl.py` lines 514–520 (`_start_run`) and 564–577 (`_end_run`)
**Apply to:** `ETLAccessor.history()`, `ETLAccessor.last_run()`, and the re-SELECT in `ETLAccessor.run()` (D-11)
```python
with self._db.connect(autocommit=True) as conn:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(queries.<CONSTANT>, [<params>])
        row = cur.fetchone()   # or cur.fetchall()
```

### `%s` parameter binding (never f-string for values)
**Source:** `pycopg/etl.py:516–519`, `pycopg/queries.py` (all constants use `%s`)
**Apply to:** All new `cur.execute()` calls in `history()`, `last_run()`, re-SELECT
```python
cur.execute(queries.ETL_LIST_RUNS, [name, limit])    # (pipeline_name, limit) → %s, %s
cur.execute(queries.ETL_GET_LAST_RUN, [name])         # (pipeline_name,) → %s
cur.execute(queries.ETL_GET_RUN, [run_id])            # (run_id,) → %s
```

### Frozen dataclass with `from __future__ import annotations`
**Source:** `pycopg/etl.py:25, 70`
**Apply to:** `RunResult` definition
```python
from __future__ import annotations   # etl.py:25 — already present
...
@dataclass(frozen=True)               # etl.py:70 — the style to copy
```

### `datetime.now(UTC)` timestamp pattern
**Source:** `pycopg/etl.py:518, 570` (used inside `_start_run` and `_end_run`)
**Apply to:** dry-run `RunResult` construction (D-08 `started_at`/`finished_at`)
```python
started_at = datetime.now(UTC)
# ... extract + transform ...
finished_at = datetime.now(UTC)
```
`UTC` already imported at `etl.py:30`: `from datetime import UTC, datetime`

---

## Existing Tests That Must Be Updated

These are not new tests but required fixes for Phase 19 (the return type changes from `int` to `RunResult`):

| File | Line range | Current | Required change |
|------|-----------|---------|-----------------|
| `test_etl_accessor.py` | 451–459 | `run_id = db.etl.run(p); assert isinstance(run_id, int)` | `result = db.etl.run(p); assert isinstance(result, RunResult)` |
| `test_etl_accessor.py` | 461–475 | `run_id = db.etl.run(p)` used as raw int | `result = db.etl.run(p); run_id = result.run_id` |
| `test_etl_accessor.py` | 231–257 | `run_id = db.etl.run(p)` at line 241 | `result = db.etl.run(p); run_id = result.run_id` |
| `test_etl_accessor.py` | 526–541 | `run_id = db.etl.run(p)` | `result = db.etl.run(p); run_id = result.run_id` |

Grep for all `run_id = db.etl.run` and `isinstance(run_id, int)` in `test_etl_accessor.py` to find any additional sites.

---

## No Analog Found

No files are without an analog. All patterns have direct codebase precedent.

---

## Metadata

**Analog search scope:** `pycopg/etl.py`, `pycopg/queries.py`, `tests/test_etl.py`, `tests/test_etl_accessor.py`
**Files scanned:** 4 source files
**Pattern extraction date:** 2026-06-15
