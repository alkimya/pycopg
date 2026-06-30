# Phase 45: API Completeness Gaps + Structured Logging - Pattern Map

**Mapped:** 2026-06-30
**Files analyzed:** 6 (1 new, 5 modified)
**Analogs found:** 6 / 6

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `pycopg/logging.py` | utility (new module) | event-driven | `pycopg/migrations.py` (stdlib logging pattern) | role-match |
| `pycopg/database.py` | core class (modified) | request-response | itself — `transaction()` / `session()` / `fetch_one()` at existing lines | exact (self-analog) |
| `pycopg/async_database.py` | core class (modified) | request-response | `pycopg/database.py` — sync→async mirror | exact (mirror convention) |
| `pycopg/pool.py` | core class (modified) | request-response | itself — `stats` property at lines 199-215 / 422-431 | exact (self-analog) |
| `pycopg/__init__.py` | package init (modified) | n/a | itself — `__all__` block lines 85-140 | exact (self-analog) |
| `pycopg/base.py` | shared utility (modified) | n/a | itself — `QueryMixin` static helpers; `from typing import Any` already present | exact (self-analog) |

---

## Pattern Assignments

### `pycopg/logging.py` (new utility module)

**Analog:** `pycopg/migrations.py` (stdlib logging pattern) and the RESEARCH.md Pattern 6.

**Module docstring + imports pattern** (copy structure from `pycopg/migrations.py` lines 1-18, adapt):
```python
"""
Structured logging helpers for pycopg.

Provides get_logger() and the log_operation context manager.
Library rule: NullHandler attached by default — callers own the handler stack.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any
```

**NullHandler + get_logger pattern** (RESEARCH.md Pattern 6, lines 316-321):
```python
_logger = logging.getLogger("pycopg")
_logger.addHandler(logging.NullHandler())


def get_logger() -> logging.Logger:
    """Return the pycopg library logger."""
    return _logger
```

**log_operation context manager** (RESEARCH.md Pattern 6, lines 325-352 — note explicit `dict[str, Any]` annotation for Phase 46 mypy-strict):
```python
@contextmanager
def log_operation(
    operation: str,
    *,
    rows: int | None = None,
) -> Generator[None, None, None]:
    t0 = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = (time.perf_counter() - t0) * 1000
        extra: dict[str, Any] = {
            "operation": operation,
            "duration_ms": round(duration_ms, 2),
        }
        if rows is not None:
            extra["rows"] = rows
        _logger.debug("pycopg: %s completed", operation, extra=extra)
```

**Key constraints:**
- `Generator[None, None, None]` return type (not `Iterator[None]`) — required for mypy-strict on `@contextmanager` decorated generators (RESEARCH.md Pitfall 2 / A2).
- `extra: dict[str, Any]` must be explicitly annotated — Python narrows bare dict literals; explicit annotation needed for `--disallow-any-generics` (RESEARCH.md Pitfall 2).
- Never call `logging.basicConfig()` — library rule (RESEARCH.md Anti-Patterns).
- `rows` parameter is keyword-only (`*` separator at D-04).

---

### `pycopg/database.py` (modified — 5 additions)

**Analog:** itself — self-analogs at confirmed live line numbers.

#### 1. Imports widening

**Current import block** (`database.py` lines 9-10):
```python
import logging
from collections.abc import Iterator, Sequence
```

**Add after widening** (add `Mapping` to collections.abc import; add `time`; import `IsolationLevel` from psycopg; import `Params` from `pycopg.base`; import `log_operation` from `pycopg.logging`):
```python
import logging
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
...
import psycopg
from psycopg import IsolationLevel, OperationalError
...
from pycopg.base import DatabaseBase, QueryMixin, Params
from pycopg.logging import log_operation
```

#### 2. transaction() — add isolation_level + savepoint_name kw-only params

**Current pattern** (`database.py` lines 506-525 — CONFIRMED live):
```python
@contextmanager
def transaction(self) -> Iterator[psycopg.Connection]:
    if self._session_conn is not None:
        with self._session_conn.transaction():
            yield self._session_conn
    else:
        with self.connect() as conn:
            with conn.transaction():
                yield conn
```

**Target pattern** (RESEARCH.md Pattern 1):
```python
@contextmanager
def transaction(
    self,
    *,
    isolation_level: IsolationLevel | None = None,
    savepoint_name: str | None = None,
) -> Iterator[psycopg.Connection]:
    if self._session_conn is not None:
        if isolation_level is not None:
            raise RuntimeError(
                "Cannot set isolation_level inside an active db.session(). "
                "Set isolation_level on db.session(isolation_level=...) instead."
            )
        with self._session_conn.transaction(savepoint_name=savepoint_name):
            yield self._session_conn
    else:
        with self.connect() as conn:
            if isolation_level is not None:
                conn.isolation_level = isolation_level
            with conn.transaction(savepoint_name=savepoint_name):
                yield conn
```

**kw-only `*` separator convention** — copy from `notify()` at `database.py` line 993: `def notify(self, channel: str, *, payload: str = "") -> None:`. All new optional params use `*` separator after last required positional arg (D-04).

#### 3. session() — add isolation_level kw-only param

**Current pattern** (`database.py` lines 527-581 — CONFIRMED live):
```python
@contextmanager
def session(self, autocommit: bool = False) -> Iterator[Database]:
    ...
    self._session_conn = psycopg.connect(
        **self.config.connect_params(), autocommit=autocommit
    )
    try:
        yield self
    finally:
        ...  # commit/close/cleanup — do NOT touch this block
```

**Target pattern** (RESEARCH.md Pattern 2 — add `isolation_level` after `autocommit`; set it immediately after `connect()` before any transaction):
```python
@contextmanager
def session(
    self,
    autocommit: bool = False,
    *,
    isolation_level: IsolationLevel | None = None,
) -> Iterator[Database]:
    ...
    self._session_conn = psycopg.connect(
        **self.config.connect_params(), autocommit=autocommit
    )
    if isolation_level is not None:
        self._session_conn.isolation_level = isolation_level
    try:
        yield self
    finally:
        ...  # existing commit/close/cleanup block unchanged
```

**Critical:** `autocommit` stays positional (not keyword-only) — it was already positional before Phase 45. Only NEW optional params added in Phase 45 are kw-only. Do NOT add `*` before `autocommit` as that would be a breaking change.

#### 4. savepoint() — new standalone context manager

**Pattern** (RESEARCH.md Pattern 3 — new method, add after `in_session` property):
```python
@contextmanager
def savepoint(self, *, name: str | None = None) -> Iterator[None]:
    """Nested savepoint within an active session.

    Parameters
    ----------
    name : str or None, optional
        Savepoint name. When None, psycopg auto-generates a name.
        Keyword-only.

    Yields
    ------
    None

    Raises
    ------
    RuntimeError
        If called outside an active db.session().
    """
    if self._session_conn is None:
        raise RuntimeError(
            "db.savepoint() requires an active db.session(). "
            "Use 'with db.session(): with db.savepoint(): ...' pattern."
        )
    with self._session_conn.transaction(savepoint_name=name):
        yield
```

When `name=None`, psycopg auto-generates the savepoint name. Do NOT pass explicit `savepoint_name=None` differently — psycopg handles the None case natively.

#### 5. health() — new method (never raises)

**Pattern** (RESEARCH.md Pattern 4 + 5 — add after `savepoint()`):
```python
def health(self) -> dict[str, Any]:
    """Probe database connectivity and latency.
    ...
    """
    with log_operation("database.health"):
        try:
            t0 = time.perf_counter()
            with self.connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                server_ver_int = conn.info.server_version
            latency_ms = (time.perf_counter() - t0) * 1000
            return {
                "connected": True,
                "latency_ms": round(latency_ms, 2),
                "server_version": _decode_server_version(server_ver_int),
            }
        except Exception as exc:
            return {
                "connected": False,
                "latency_ms": None,
                "server_version": None,
                "error": str(exc),
            }
```

**_decode_server_version helper** (RESEARCH.md Pattern 5 — module-level private function, add near top of database.py):
```python
def _decode_server_version(v: int) -> str:
    major = v // 10000
    if major >= 10:
        return f"{major}.{v % 100}"
    minor = (v % 10000) // 100
    return f"{major}.{minor}.{v % 100}"
```

**D-05 constraint:** the `except Exception` block MUST NOT re-raise. Every error path returns `{"connected": False, ..., "error": str(exc)}`. The `with self.connect() as conn` CM handles connection cleanup automatically even on exception — do NOT add `conn.close()` in the except block.

#### 6. Params widening — execute / fetch_one / fetch_val / fetch_all / to_dataframe

**Current annotations** (CONFIRMED live lines):
- `database.py:595` — `params: Sequence | None = None` (execute)
- `database.py:1131` — `params: Sequence | None = None` (fetch_one)
- `database.py:1150` — `params: Sequence | None = None` (fetch_val)
- `database.py:1170` — `params: Sequence | None = None` (fetch_all)
- `database.py:1373` — `params: dict | None = None` (to_dataframe)

**Target:** replace each with `params: Params = None` (after importing `Params` from `pycopg.base`). No body changes — psycopg already accepts `Mapping` natively. For `to_dataframe`, the annotation widens from `dict | None` to `Params` but the internal SQLAlchemy binding uses `:name` style (not `%(name)s`) — add a docstring note.

#### 7. log_operation instrumentation sites in database.py

**Pattern:** wrap the outer body of `from_dataframe` and `from_geodataframe` with `with log_operation("database.from_dataframe", rows=len(df)):`. Wrap after the `if self._session_conn is not None` guard check (if any), bracketing the actual work. Copy from RESEARCH.md Instrumentation Sites table (lines 617-622):

```python
def from_dataframe(self, df: pd.DataFrame, table: str, ...) -> int:
    ...
    with log_operation("database.from_dataframe", rows=len(df)):
        # existing implementation body
        ...
    return len(df)  # if currently returned outside the with
```

---

### `pycopg/async_database.py` (modified — async 1:1 mirror)

**Analog:** `pycopg/database.py` — every sync addition has an async mirror.

**Sync→async mirror convention** (observed at `async_database.py` lines 515-600):
- `@contextmanager` → `@asynccontextmanager`
- `Iterator[X]` → `AsyncIterator[X]`
- `def method(...)` → `async def method(...)`
- `psycopg.connect(...)` → `await psycopg.AsyncConnection.connect(...)`
- `conn.transaction()` → `async with conn.transaction()` (already async CM)
- `cur.execute(...)` → `await cur.execute(...)`
- `conn.commit()` → `await conn.commit()`
- `conn.close()` → `await conn.close()`

**Async transaction() target** (mirror of sync pattern above):
```python
@asynccontextmanager
async def transaction(
    self,
    *,
    isolation_level: IsolationLevel | None = None,
    savepoint_name: str | None = None,
) -> AsyncIterator[AsyncConnection]:
    if self._session_conn is not None:
        if isolation_level is not None:
            raise RuntimeError(...)
        async with self._session_conn.transaction(savepoint_name=savepoint_name):
            yield self._session_conn
    else:
        async with self.connect() as conn:
            if isolation_level is not None:
                conn.isolation_level = isolation_level
            async with conn.transaction(savepoint_name=savepoint_name):
                yield conn
```

**Async session() target** (mirror of sync pattern — note `autocommit` stays positional):
```python
@asynccontextmanager
async def session(
    self,
    autocommit: bool = False,
    *,
    isolation_level: IsolationLevel | None = None,
) -> AsyncIterator[AsyncDatabase]:
    ...
    self._session_conn = await psycopg.AsyncConnection.connect(
        **self.config.connect_params(), autocommit=autocommit
    )
    if isolation_level is not None:
        self._session_conn.isolation_level = isolation_level
    ...  # existing commit/close/cleanup block unchanged
```

**Async savepoint() target** (mirror):
```python
@asynccontextmanager
async def savepoint(self, *, name: str | None = None) -> AsyncIterator[None]:
    if self._session_conn is None:
        raise RuntimeError(...)
    async with self._session_conn.transaction(savepoint_name=name):
        yield
```

**Async health() target** (RESEARCH.md Pitfall 6 — t0 must bracket the await):
```python
async def health(self) -> dict[str, Any]:
    with log_operation("database.health"):
        try:
            t0 = time.perf_counter()
            async with self.connect() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT 1")
                server_ver_int = conn.info.server_version
            latency_ms = (time.perf_counter() - t0) * 1000
            return {
                "connected": True,
                "latency_ms": round(latency_ms, 2),
                "server_version": _decode_server_version(server_ver_int),
            }
        except Exception as exc:
            return {
                "connected": False,
                "latency_ms": None,
                "server_version": None,
                "error": str(exc),
            }
```

NOTE: `_decode_server_version` can be imported from `database.py` or duplicated — prefer import from a shared location (e.g., `pycopg.base` or `pycopg.utils`). Do not duplicate the version-decoding logic.

**Params annotation widening** (same 5 methods, same `Params` import from `pycopg.base`):
- `async_database.py:604-606` — `params: Sequence | None = None` (execute) → `params: Params = None`
- Mirror fetch_one / fetch_val / fetch_all / to_dataframe (locate with grep if offsets drift).

**Instrumentation sites** (RESEARCH.md lines 619-621):
- `AsyncDatabase.from_dataframe` → `with log_operation("database.from_dataframe", rows=len(df)):`
- `AsyncDatabase.from_geodataframe` → `with log_operation("database.from_geodataframe", rows=len(gdf)):`
- `log_operation` is a sync CM — valid inside async methods (wraps the `await` in the body).

**Parity guard:** `test_parity.py` `test_all_database_public_methods_exist_in_async`, `test_method_signatures_match`, `test_accessor_parameter_kind_parity` will catch any divergence automatically. Co-edit both files in the same commit.

---

### `pycopg/pool.py` (modified — health() on both pooled classes)

**Analog:** itself — `stats` property at lines 199-215 (sync) and 422-431 (async).

**Existing `PooledDatabase.stats` property** (lines 199-215 — CONFIRMED, returns full dict):
```python
@property
def stats(self) -> dict:
    return {
        "pool_min": self._pool.min_size,
        "pool_max": self._pool.max_size,
        "pool_size": self._pool.get_stats().get("pool_size", 0),
        "pool_available": self._pool.get_stats().get("pool_available", 0),
        "requests_waiting": self._pool.get_stats().get("requests_waiting", 0),
        "requests_num": self._pool.get_stats().get("requests_num", 0),
    }
```

**Existing `AsyncPooledDatabase.stats` property** (lines 422-431 — CONFIRMED, lacks `requests_num`):
```python
@property
def stats(self) -> dict:
    return {
        "pool_min": self._pool.min_size,
        "pool_max": self._pool.max_size,
        "pool_size": self._pool.get_stats().get("pool_size", 0),
        "pool_available": self._pool.get_stats().get("pool_available", 0),
        "requests_waiting": self._pool.get_stats().get("requests_waiting", 0),
    }
```

**Pooled health() pattern** (add after `stats` property on each class; use `self.connection()` CM for pooled acquisition — not `self.connect()`):
```python
def health(self) -> dict[str, Any]:
    """Probe pool connectivity and latency.
    ...
    """
    with log_operation("database.health"):
        try:
            t0 = time.perf_counter()
            with self.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                server_ver_int = conn.info.server_version
            latency_ms = (time.perf_counter() - t0) * 1000
            return {
                "connected": True,
                "latency_ms": round(latency_ms, 2),
                "server_version": _decode_server_version(server_ver_int),
                "pool_stats": self.stats,   # property, not method — self.stats not self.stats()
            }
        except Exception as exc:
            return {
                "connected": False,
                "latency_ms": None,
                "server_version": None,
                "pool_stats": None,
                "error": str(exc),
            }
```

**CRITICAL note (RESEARCH.md line 600):** `stats` is a `@property` — call `self.stats` NOT `self.stats()`. The research confirmed this diverges from CONTEXT.md's incorrect phrasing `stats()`.

**Async pooled health()** (same pattern; `self.connection()` → `async with self.connection() as conn:`, `cur.execute` → `await cur.execute`, and prefix `async def`):
```python
async def health(self) -> dict[str, Any]:
    with log_operation("database.health"):
        try:
            t0 = time.perf_counter()
            async with self.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT 1")
                server_ver_int = conn.info.server_version
            latency_ms = (time.perf_counter() - t0) * 1000
            return {
                "connected": True,
                "latency_ms": round(latency_ms, 2),
                "server_version": _decode_server_version(server_ver_int),
                "pool_stats": self.stats,
            }
        except Exception as exc:
            return {
                "connected": False,
                "latency_ms": None,
                "server_version": None,
                "pool_stats": None,
                "error": str(exc),
            }
```

**Imports to add to pool.py:** `import time`, `from typing import Any`, `from pycopg.logging import log_operation`, `from pycopg.base import _decode_server_version` (if shared there) or import from wherever the helper is placed.

---

### `pycopg/__init__.py` (modified — add 2 exports)

**Analog:** itself — `__all__` block lines 85-140 (CONFIRMED live).

**Existing export pattern** (lines 85-140 — copy grouping style):
```python
__all__ = [
    # Core
    "Database",
    "AsyncDatabase",
    "Config",
    # Pooling
    "PooledDatabase",
    "AsyncPooledDatabase",
    ...
    # Utilities
    "validate_identifier",
    "validate_identifiers",
    "validate_interval",
    "validate_index_method",
]
```

**Target additions:**
1. Import at top of file: `from psycopg import IsolationLevel` (thin re-export per D-01) and `from pycopg.base import Params`.
2. Add to `__all__` under a new `# Types` group (or append to `# Utilities`):
```python
    # Types
    "IsolationLevel",
    "Params",
```

**IsolationLevel re-export style** (RESEARCH.md Code Examples):
```python
from psycopg import IsolationLevel  # direct re-export — D-01 thin alias
```
Not a copy of the enum values — thin re-export so future psycopg additions are picked up automatically.

---

### `pycopg/base.py` (modified — add Params alias)

**Analog:** itself — existing imports at lines 1-14; `from typing import Any` already present.

**Current imports** (`base.py` lines 1-14 — CONFIRMED live):
```python
from __future__ import annotations

from abc import ABC
from pathlib import Path
from typing import Any

from pycopg.config import Config
from pycopg.utils import validate_identifiers, validate_timestamp
```

**Target additions** (add to imports; define alias at module level after imports):
```python
from collections.abc import Mapping, Sequence

# Public type alias for query parameters — exported via pycopg.__all__
Params = Sequence[Any] | Mapping[str, Any] | None
```

Place `Params` immediately after the imports block, before `_validate_cli_pattern`. This is the single source of truth; all other modules import it from here.

**Why base.py:** it has no imports from pycopg internals except `Config` and `utils`, so there is no circular import risk. `database.py`, `async_database.py`, and `pool.py` all already import from `base.py` via `from pycopg.base import DatabaseBase, QueryMixin`.

**_decode_server_version placement:** place this private helper in `base.py` as well (or `utils.py`). Placing in `base.py` avoids duplication between `database.py` and `async_database.py`. Both files already import from `base.py`.

---

## Shared Patterns

### Kw-only optional parameter convention (D-04 / Phase 41 Stable API Contract)

**Source:** `pycopg/database.py` line 993 + `pycopg/async_database.py` line 1581.
**Apply to:** Every new optional parameter added in Phase 45.

```python
# Pattern: required positional args first, then * separator, then optional kw-only
def notify(self, channel: str, *, payload: str = "") -> None:
```

For `transaction()` and `session()`, all Phase 45 additions (`isolation_level=`, `savepoint_name=`) are kw-only. For `savepoint()`, `name=` is kw-only. **Exception:** `autocommit` in `session()` stays positional — it pre-dates Phase 45 and is already a stable API.

### stdlib logging pattern (pre-existing, to be consolidated)

**Source:** `pycopg/database.py` line 40, `pycopg/async_database.py` line 39, `pycopg/migrations.py` line 18.
**Target:** Reconcile to `from pycopg.logging import get_logger; logger = get_logger()` in each module. Or keep per-module `logger = logging.getLogger(__name__)` and use the shared `log_operation` CM for timed operations — both are acceptable. The reconciliation is a cleanup, not a functional requirement.

Current pattern (all three modules):
```python
logger = logging.getLogger(__name__)
```

Post-Phase-45 option (can be done per module as part of instrumentation):
```python
from pycopg.logging import get_logger, log_operation
logger = get_logger()  # returns logging.getLogger("pycopg")
```

### Error return pattern for health() (D-05)

**Apply to:** `Database.health()`, `AsyncDatabase.health()`, `PooledDatabase.health()`, `AsyncPooledDatabase.health()`.

Always `try / except Exception` with `return {...}` in both branches. Never re-raise. The `except` block must NOT call `conn.close()` — the `with self.connect()` / `with self.connection()` CM handles cleanup.

```python
try:
    ...
    return {"connected": True, ...}
except Exception as exc:
    return {"connected": False, "latency_ms": None, "server_version": None, "error": str(exc)}
```

### Sync→async mirror convention (enforced by test_parity.py)

**Source:** `pycopg/database.py` + `pycopg/async_database.py` — observed across all existing methods.

| Sync | Async |
|------|-------|
| `@contextmanager` | `@asynccontextmanager` |
| `def method(...)` | `async def method(...)` |
| `Iterator[X]` | `AsyncIterator[X]` |
| `psycopg.connect(...)` | `await psycopg.AsyncConnection.connect(...)` |
| `with conn.transaction():` | `async with conn.transaction():` |
| `with conn.cursor() as cur: cur.execute(...)` | `async with conn.cursor() as cur: await cur.execute(...)` |
| `conn.commit()` | `await conn.commit()` |
| `conn.close()` | `await conn.close()` |
| `with self.connect() as conn:` | `async with self.connect() as conn:` |
| `with self.connection() as conn:` (pool) | `async with self.connection() as conn:` (pool) |

`log_operation` is sync-only and can be used inside both sync and async methods with `with log_operation(...):` — a sync CM can wrap `await` expressions inside its `yield` body.

---

## Instrumentation Sites Summary (D-09)

All 13 sites from RESEARCH.md lines 607-622 — add `with log_operation(name, rows=N):` wrapping the outer body:

| File | Method | Operation string | rows |
|------|--------|-----------------|------|
| `pycopg/etl.py` | `ETLAccessor.run()` | `"etl.run"` | `result.rows_written` |
| `pycopg/etl.py` | `AsyncETLAccessor.run()` | `"etl.run"` | `result.rows_written` |
| `pycopg/backup.py` | `BackupAccessor.pg_dump()` | `"backup.pg_dump"` | None |
| `pycopg/backup.py` | `BackupAccessor.pg_restore()` | `"backup.pg_restore"` | None |
| `pycopg/backup.py` | `AsyncBackupAccessor.pg_dump()` | `"backup.pg_dump"` | None |
| `pycopg/backup.py` | `AsyncBackupAccessor.pg_restore()` | `"backup.pg_restore"` | None |
| `pycopg/migrations.py` | `Migrator.migrate()` | `"migrations.migrate"` | `len(applied)` |
| `pycopg/database.py` | `Database.from_dataframe()` | `"database.from_dataframe"` | `len(df)` |
| `pycopg/database.py` | `Database.from_geodataframe()` | `"database.from_geodataframe"` | `len(gdf)` |
| `pycopg/async_database.py` | `AsyncDatabase.from_dataframe()` | `"database.from_dataframe"` | `len(df)` |
| `pycopg/async_database.py` | `AsyncDatabase.from_geodataframe()` | `"database.from_geodataframe"` | `len(gdf)` |
| `pycopg/database.py` | `Database.health()` | `"database.health"` | None |
| `pycopg/async_database.py` | `AsyncDatabase.health()` | `"database.health"` | None |

Note: pooled `health()` also calls `log_operation("database.health")`. `PooledDatabase.health()` and `AsyncPooledDatabase.health()` are new methods in `pool.py` — add the same wrapping there.

---

## No Analog Found

All files have direct analogs or self-analogs. No files require falling back to RESEARCH.md patterns exclusively — though `pycopg/logging.py` (new module) has no existing logging utility module to copy from in the codebase. It should be built from RESEARCH.md Pattern 6 combined with the stdlib `logging` pattern observed at `migrations.py:18`.

---

## Metadata

**Analog search scope:** `pycopg/` directory — `database.py`, `async_database.py`, `pool.py`, `base.py`, `migrations.py`, `__init__.py`
**Files scanned:** 6 source files read
**Pattern extraction date:** 2026-06-30
