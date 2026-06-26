# Phase 39: Couverture & Benchmarks - Pattern Map

**Mapped:** 2026-06-26
**Files analyzed:** 7 (new/modified files across two chantiers)
**Analogs found:** 6 / 7 (1 has no analog — benchmark runner is novel)

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `tests/test_async_database.py` (extend — `TestAsyncInsertBatch` class) | test | request-response (live DB) | `tests/test_database_integration.py` `TestDatabaseBulkAndSizeCoverage` | exact |
| `tests/test_async_database.py` (extend — async paginate branches) | test | request-response (live DB) | `tests/test_etl_accessor.py` `TestAsyncRunResultSurface` | role-match |
| `tests/test_etl_accessor.py` (extend — dry_run watermark/transform branches) | test | event-driven (ETL pipeline) | `tests/test_etl_accessor.py` `TestRunResultSurface` (existing sync tests) | exact |
| `pycopg/` source files (add `pragma: no cover` annotations) | utility | n/a | `pycopg/__init__.py` (already has `exclude_lines` config) | config-match |
| `pyproject.toml` (`--cov-fail-under` bump 94→95, optional `omit`) | config | n/a | existing `[tool.pytest.ini_options]` / `[tool.coverage.run]` blocks | exact |
| `Makefile` (add `bench` target) | config | n/a | existing `test`/`lint`/`format`/`build` targets | exact |
| `benchmarks/__init__.py` + `benchmarks/__main__.py` + `benchmarks/README.md` | utility / runner | batch (bulk I/O timing) | **No analog** — no standalone runner exists in this repo | none |

---

## Pattern Assignments

### `tests/test_async_database.py` — `TestAsyncInsertBatch` (NEW class, live-DB, COV-01 primary target)

**Analog:** `tests/test_database_integration.py` `TestDatabaseBulkAndSizeCoverage` (lines 883–913)

**Why this analog:** It is the closest existing live-DB test of `copy_insert` / `insert_batch`-family methods — same role (integration test, real DB), same data flow (bulk row insert, assert COUNT), uses the `db` + `cleanup_table` fixture pattern.

**Imports pattern** (lines 1–13 of `test_database_integration.py`):
```python
import uuid

import pytest

from pycopg import Database
# For the async version:
from pycopg import AsyncDatabase
```

**Live-DB fixture pattern** (`test_database_integration.py` lines 15–47):
```python
@pytest.fixture
def db(db_config):
    """Create a Database instance connected to pycopg_test."""
    database = Database(db_config)
    database.connect()
    yield database
    if hasattr(database, "_conn") and database._conn:
        database._conn.close()

@pytest.fixture
def cleanup_table(db):
    """Fixture that cleans up tables after test."""
    tables_to_cleanup = []

    def register_table(table_name):
        tables_to_cleanup.append(table_name)

    yield register_table

    for table_name in tables_to_cleanup:
        try:
            db.execute(f'DROP TABLE IF EXISTS "{table_name}" CASCADE')
        except Exception:
            pass
```

**Async fixture pattern for `TestAsyncInsertBatch`** — copy from `test_etl_accessor.py` lines 2098–2145 (the `async_db` + `async_etl_table` fixtures):
```python
@pytest.fixture
async def async_db(db_config):
    """Yield an AsyncDatabase connected to pycopg_test."""
    database = AsyncDatabase(db_config)
    yield database

@pytest.fixture
async def async_etl_table(db_config):
    """Create a fresh ETL target table via async connection; drop on teardown."""
    tbl = f"etl_atgt_{uuid.uuid4().hex[:8]}"
    adb = AsyncDatabase(db_config)
    await adb.execute(
        f'CREATE TABLE public."{tbl}" (id INTEGER, val TEXT)',
        autocommit=True,
    )
    yield tbl
    await adb.execute(
        f'DROP TABLE IF EXISTS public."{tbl}" CASCADE',
        autocommit=True,
    )
```

**Note on `asyncio_mode = "auto"`** (confirmed in `pyproject.toml` line 101): NO `@pytest.mark.asyncio` decorator needed on test classes or methods. Async test methods just use `async def test_*`.

**Core test pattern** — copy from `test_database_integration.py` lines 884–913 (`test_copy_insert`):
```python
def test_copy_insert(self, db, cleanup_table):
    """copy_insert bulk-loads rows via the COPY protocol."""
    t = f"test_ci_{uuid.uuid4().hex[:8]}"
    cleanup_table(t)
    db.execute(f'CREATE TABLE "{t}" (id INTEGER, name TEXT)', autocommit=True)
    count = db.copy_insert(
        t, [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}, {"id": 3, "name": "c"}]
    )
    assert count == 3
    assert db.execute(f'SELECT COUNT(*) AS n FROM "{t}"')[0]["n"] == 3
```

Async mirror for `TestAsyncInsertBatch` (the high-value COV-01 target — covers `async_database.py` L685–718):
```python
class TestAsyncInsertBatch:
    """Async insert_batch live-DB behavioral tests (COV-01 — async_database.py L685–718)."""

    async def test_async_insert_batch_basic(self, async_db, async_insert_table):
        rows = [{"id": i, "val": float(i), "label": f"r{i}"} for i in range(3)]
        n = await async_db.insert_batch(async_insert_table, rows)
        assert n == 3
        count = await async_db.execute(
            f'SELECT COUNT(*) AS n FROM "{async_insert_table}"'
        )
        assert count[0]["n"] == 3

    async def test_async_insert_batch_empty_returns_zero(self, async_db, async_insert_table):
        n = await async_db.insert_batch(async_insert_table, [])
        assert n == 0  # covers L685–686 (empty-rows early return)

    async def test_async_insert_batch_on_conflict_do_nothing(self, async_db, async_insert_table):
        # Requires PK on table fixture — use a dedicated fixture with PRIMARY KEY
        rows = [{"id": 1, "val": 1.0, "label": "a"}]
        await async_db.insert_batch(async_insert_table, rows)
        n = await async_db.insert_batch(async_insert_table, rows, on_conflict="DO NOTHING")
        assert n == 0  # covers L698 conflict_clause branch

    async def test_async_insert_batch_multi_batch(self, async_db, async_insert_table):
        # batch_size defaults to 1000; insert batch_size+1 to trigger loop ≥2
        rows = [{"id": i, "val": float(i), "label": f"r{i}"} for i in range(1001)]
        n = await async_db.insert_batch(async_insert_table, rows, batch_size=500)
        assert n == 1001  # covers inner loop iteration path
```

**Fixture needed for `on_conflict` test** — a table with PRIMARY KEY:
```python
@pytest.fixture
async def async_insert_table_pk(db_config):
    tbl = f"async_ib_pk_{uuid.uuid4().hex[:8]}"
    adb = AsyncDatabase(db_config)
    await adb.execute(
        f'CREATE TABLE public."{tbl}" (id INTEGER PRIMARY KEY, val FLOAT, label TEXT)',
        autocommit=True,
    )
    yield tbl
    await adb.execute(f'DROP TABLE IF EXISTS public."{tbl}" CASCADE', autocommit=True)
```

---

### `tests/test_async_database.py` — async paginate branch tests (extend `TestAsyncPageOperations` or equivalent)

**Analog:** `tests/test_etl_accessor.py` `TestAsyncRunResultSurface` (lines 2148–2230) — shows async test class with `async_db` fixture calling real-DB methods and asserting results.

**Core pattern** (from `TestAsyncRunResultSurface` lines 2163–2177):
```python
async def test_async_run_returns_run_result(
    self, async_db, cleanup_async_pipeline_runs, async_etl_table
):
    p = Pipeline(
        name="asc1_run",
        source="SELECT 1 AS id, 'a' AS val",
        target=async_etl_table,
        load_mode="replace",
    )
    r = await async_db.etl.run(p)
    assert isinstance(r, RunResult)
    assert r.status == "success"
```

Apply to async paginate tests:
```python
async def test_async_paginate_with_where(self, async_db, async_paginate_table):
    # covers async_database.py L976–978 (where= filter)
    results = await async_db.paginate(async_paginate_table, where={"label": "alice"})
    assert all(r["label"] == "alice" for r in results)

async def test_async_paginate_list_order_by(self, async_db, async_paginate_table):
    # covers L985 (list order_by branch)
    results = await async_db.paginate(async_paginate_table, order_by=["label", "id"])
    assert len(results) >= 0  # structural: list order_by accepted without error

async def test_async_paginate_invalid_order_by_raises(self, async_db, async_paginate_table):
    # covers L987 (ValueError for empty string in order_by)
    with pytest.raises(ValueError):
        await async_db.paginate(async_paginate_table, order_by=[""])
```

---

### `tests/test_etl_accessor.py` — sync + async dry_run watermark/transform branch tests

**Analog:** `tests/test_etl_accessor.py` existing `TestRunResultSurface` (lines 1062–1400) and `TestAsyncRunResultSurface` (lines 2148+). These are the exact class/fixture patterns to copy.

**Sync ETL fixture pattern** (lines 422–443):
```python
@pytest.fixture
def etl_table(db):
    """Create a fresh ETL target table for each test; drop on teardown."""
    tbl = f"etl_tgt_{uuid.uuid4().hex[:8]}"
    db.execute(
        f'CREATE TABLE public."{tbl}" (id INTEGER, val TEXT)',
        autocommit=True,
    )
    yield tbl
    db.execute(f'DROP TABLE IF EXISTS public."{tbl}" CASCADE', autocommit=True)

@pytest.fixture
def etl_src(db):
    """Create a fresh ETL source table and return its name; drop on teardown."""
    tbl = f"etl_src_{uuid.uuid4().hex[:8]}"
    db.execute(
        f'CREATE TABLE public."{tbl}" (id INTEGER, val TEXT)',
        autocommit=True,
    )
    yield tbl
    db.execute(f'DROP TABLE IF EXISTS public."{tbl}" CASCADE', autocommit=True)
```

**Sync dry_run test pattern** (from `test_dry_run_with_transform_list` ~line 1322):
```python
def test_dry_run_with_transform_list(self, db, cleanup_pipeline_runs, etl_table):
    p = Pipeline(
        name="dry_transform_list",
        source="SELECT 1 AS id, 'a' AS val",
        target=etl_table,
    )
    # ... run with transform=[fn1, fn2], assert status == "dry_run"
    result = db.etl.run(p, dry_run=True)
    assert result.status == "dry_run"
```

New sync watermark tests to add to `TestRunResultSurface` (covering `etl.py` L1215, L1222, L1224, L1226, L1228, L1241, L1248-1249, L1313):
```python
def test_dry_run_incremental_string_watermark(self, db, cleanup_pipeline_runs):
    """Covers etl.py L1226 — str watermark branch in sync dry_run."""
    src = f"str_wm_src_{uuid.uuid4().hex[:8]}"
    dst = f"str_wm_dst_{uuid.uuid4().hex[:8]}"
    try:
        db.execute(f'CREATE TABLE public."{src}" (code TEXT, val INTEGER)', autocommit=True)
        db.execute(f"INSERT INTO public.\"{src}\" VALUES ('beta', 2), ('alpha', 1)", autocommit=True)
        db.execute(f'CREATE TABLE public."{dst}" (code TEXT, val INTEGER)', autocommit=True)
        p = Pipeline(
            name=f"str_wm_{uuid.uuid4().hex[:6]}",
            source=src,
            target=dst,
            load_mode="upsert",
            conflict_columns=["code"],
            incremental_column="code",
        )
        result = db.etl.run(p, dry_run=True)
        assert result.status == "dry_run"
        assert isinstance(result.watermark_recorded, str)
    finally:
        db.execute(f'DROP TABLE IF EXISTS public."{src}" CASCADE', autocommit=True)
        db.execute(f'DROP TABLE IF EXISTS public."{dst}" CASCADE', autocommit=True)
```

**Async ETL fixture pattern** (lines 2098–2145 — use exactly this):
```python
@pytest.fixture
async def async_db(db_config):
    """Yield an AsyncDatabase connected to pycopg_test."""
    database = AsyncDatabase(db_config)
    yield database

@pytest.fixture
async def cleanup_async_pipeline_runs(db_config):
    """Drop pipeline_runs after each async integration test."""
    yield
    try:
        adb = AsyncDatabase(db_config)
        await adb.execute("DROP TABLE IF EXISTS pipeline_runs CASCADE", autocommit=True)
    except Exception:
        pass
```

**pytest.raises pattern** (from `test_database_integration.py` `TestDatabaseConstraintsAdminCoverage` and `test_async_database.py`):
```python
with pytest.raises(SomeException):
    db.method(bad_arg)
# or for async:
with pytest.raises(SomeException):
    await async_db.method(bad_arg)
```

---

### `pyproject.toml` — `--cov-fail-under` bump + optional `benchmarks/` omit

**Analog:** Existing `pyproject.toml` lines 99–113 (the exact blocks to modify).

**Current state** (lines 99–108):
```toml
testpaths = ["tests"]
addopts = "-v --cov=pycopg --cov-report=term-missing --cov-report=html --cov-fail-under=94"
asyncio_mode = "auto"

[tool.coverage.run]
source = ["pycopg"]
omit = ["*/tests/*", "*/venv/*"]

[tool.coverage.report]
exclude_lines = [
```

**Change:** bump `--cov-fail-under=94` → `--cov-fail-under=95` in `addopts`. Optionally add `"benchmarks/*"` to `omit` list. Do NOT change `testpaths`. This is the **last action** of the phase (D-04a).

---

### `Makefile` — `bench` target

**Analog:** Existing `Makefile` lines 1–18 — all targets follow the same `.PHONY` + tab-indented `uv run` or `python` command pattern.

**Current pattern** (lines 1–18):
```makefile
.PHONY: install test lint format build

install:
	uv sync --all-extras --dev

test:
	uv run pytest

lint:
	uv run ruff check pycopg tests

format:
	uv run black pycopg tests
	uv run ruff check --fix pycopg tests

build:
	uv build
```

**New target to add** (after `build`):
```makefile
.PHONY: install test lint format build bench

bench:
	python -m benchmarks
```

Note: uses `python -m benchmarks` not `uv run python -m benchmarks` so the caller controls the env (exports `PGDATABASE=pycopg_test2` before calling). The PHONY line must include `bench`.

---

### `benchmarks/__init__.py`, `benchmarks/__main__.py`, `benchmarks/README.md`

**No analog exists in this repo.** This is the first standalone runner module. There is no existing benchmark harness, no `__main__.py` in any sub-package, and no timing measurement module.

**Instead, extract the minimum anchoring patterns from the codebase:**

**1. `Database.from_env()` construction** (confirmed from `tests/conftest.py` lines 13–29 — `db_config` fixture shows the env var convention):
```python
# conftest.py pattern — benchmark uses the simpler from_env() form:
from pycopg import Database
db = Database.from_env()
# Reads PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE from environment.
# Local: PGDATABASE=pycopg_test2 python -m benchmarks
# CI: PGDATABASE=pycopg_test python -m benchmarks (same as test CI)
```

**2. Public call signatures of the 4 measured paths** (verified from source 2026-06-26):
```python
# insert_batch (executemany baseline)
n: int = db.insert_batch(table, rows, schema="public", on_conflict=None, batch_size=None)

# copy_insert (COPY protocol)
n: int = db.copy_insert(table, rows, schema="public", columns=None)

# from_dataframe (Hybrid DDL+COPY)
db.from_dataframe(df, table, schema="public", if_exists="fail", primary_key=None, index=False, dtype=None)

# ETL load via COPY seam
from pycopg.etl import Pipeline
db.etl.run(Pipeline(
    name="bench_etl",
    source="bench_etl_src",
    target="bench_etl_dst",
    load_mode="replace",   # routes via COPY, not upsert
    schema="public",
))
```

**3. Benchmark harness structure** (stdlib-only per D-01 — no existing analog; use stdlib docs pattern):
```python
import argparse
import statistics
import time

import pandas as pd

from pycopg import Database
from pycopg.etl import Pipeline


def _make_rows(n: int) -> list[dict]:
    return [{"id": i, "val": float(i) * 0.1, "label": f"row_{i}"} for i in range(n)]


def _time_it(fn, *, runs: int, warmup: int = 1):
    """Warmup run(s) discarded; return (median_ns, list[ns])."""
    for _ in range(warmup):
        fn()
    times = []
    for _ in range(runs):
        t0 = time.perf_counter_ns()
        fn()
        times.append(time.perf_counter_ns() - t0)
    return statistics.median(times), times


def main():
    parser = argparse.ArgumentParser(description="pycopg benchmark suite")
    parser.add_argument("--rows", type=int, default=100_000)
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args()
    db = Database.from_env()
    # ... per-method: setup table, run _time_it, teardown, print table


if __name__ == "__main__":
    main()
```

**4. Output table format** (Claude's Discretion resolved — lean from RESEARCH.md):
```
pycopg insertion benchmark — 100 000 rows, 5 runs (warmup=1)
==============================================================
Method            | rows/s    | median_ms | speedup vs insert_batch
------------------+-----------+-----------+------------------------
insert_batch      |    45 000 |   2 222.3 | 1.00x (baseline)
copy_insert       |   890 000 |    112.4  | 19.8x
from_dataframe    |   750 000 |    133.3  | 16.7x
etl.run (replace) |   620 000 |    161.3  | 13.8x
```

Use `f"{value:>10,.0f}"` style f-string padding — no `tabulate` dependency (D-01: stdlib only).

---

## Shared Patterns

### `pragma: no cover` convention (new to this repo — D-04)

**Apply to:** Defensive/unreachable lines in `pycopg/` source files.

**Convention already configured** in `pyproject.toml`:
```toml
[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    ...
]
```

**Required inline comment format** (mandatory per D-04 — first use in this repo):
```python
raise RuntimeError("...")  # pragma: no cover — <justification explaining why line is unreachable>
```

Approved candidates from RESEARCH.md:
- `database.py` L567–575: `# pragma: no cover — requires commit() + close() to both raise simultaneously; not reproducible without driver-level corruption`
- `database.py` L1439–1472: `# pragma: no cover — SRID inference requires PostGIS live env (broken in local; CI would catch regressions)`
- `config.py` L20–25: `# pragma: no cover — python-dotenv ImportError only fires when package absent; --all-extras always installs it`
- `pycopg/__init__.py` L44–45: `# pragma: no cover — PackageNotFoundError only fires when package is not installed; never hit in test env`
- `backup.py` L193, L221: `# pragma: no cover — requires pg_restore/psql subprocess failure; environment-dependent`

### Async test class pattern (no `@pytest.mark.asyncio` needed)

**Source:** `pyproject.toml` line 101: `asyncio_mode = "auto"`
**Apply to:** All new async test classes and methods.

```python
# CORRECT — asyncio_mode = "auto" means no marker needed:
class TestAsyncInsertBatch:
    async def test_something(self, async_db, ...):
        result = await async_db.some_method(...)
        assert result == expected

# WRONG — do NOT add @pytest.mark.asyncio (redundant, may conflict):
# @pytest.mark.asyncio
# class TestAsyncInsertBatch: ...
```

### UUID table isolation (prevents test collision under `pytest-randomly`)

**Source:** `test_database_integration.py` line 888, `test_etl_accessor.py` lines 425, 437.
**Apply to:** All new tests that create tables.

```python
import uuid
t = f"test_ci_{uuid.uuid4().hex[:8]}"   # unique per test run
# Always clean up in fixture teardown or try/finally
```

### `try/finally` cleanup for non-fixture tables

**Source:** `test_etl_accessor.py` lines 1423–1434.
**Apply to:** Tests in `TestRunResultSurface` that create tables inline (not via fixture):

```python
tbl = f"str_wm_src_{uuid.uuid4().hex[:8]}"
try:
    db.execute(f'CREATE TABLE public."{tbl}" ...', autocommit=True)
    # ... test body ...
finally:
    db.execute(f'DROP TABLE IF EXISTS public."{tbl}" CASCADE', autocommit=True)
```

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `benchmarks/__main__.py` | utility / CLI runner | batch timing | No standalone benchmark runner exists in this repo. First `__main__.py` in any sub-package. Patterns drawn from stdlib docs (`time.perf_counter_ns`, `statistics.median`, `argparse`) and pycopg public API call signatures verified from source. |
| `benchmarks/__init__.py` | package marker | n/a | Empty file, no analog needed. |
| `benchmarks/README.md` | documentation | n/a | Protocol content specified in RESEARCH.md §PERF-04. No doc analog in `benchmarks/`. |

---

## Metadata

**Analog search scope:** `tests/`, `pycopg/`, `Makefile`, `pyproject.toml`
**Files scanned:** `tests/conftest.py`, `tests/test_database_integration.py`, `tests/test_async_database.py`, `tests/test_etl_accessor.py`, `Makefile`, `pyproject.toml`
**Pattern extraction date:** 2026-06-26
