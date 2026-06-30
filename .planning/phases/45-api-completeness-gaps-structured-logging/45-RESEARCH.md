# Phase 45: API Completeness Gaps + Structured Logging - Research

**Researched:** 2026-06-30
**Domain:** psycopg3 transaction/savepoint/health API + stdlib logging + Python type aliases
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Transaction control — isolation & savepoints (TXN-01, TXN-02)**
- **D-01:** Re-export `pycopg.IsolationLevel` as a thin alias of psycopg's enum (NOT a copy); export in `__all__`. No string→enum parser.
- **D-02:** Expose savepoints two ways: standalone `db.savepoint(name=None)` CM AND `transaction(savepoint_name=...)` kwarg. Both delegate to psycopg's native `conn.transaction(savepoint_name=...)`.
- **D-03:** Calling `transaction(isolation_level=)` while a `db.session()` is active RAISES a clear error. Outside a session, sets isolation on the fresh per-call connection.
- **D-04:** All new optional params are keyword-only per Phase 41 Stable API Contract.

**Health probe (HEALTH-01)**
- **D-05:** `health()` NEVER raises. On failure returns `{connected: False, latency_ms: None, server_version: None, error: <str>}`.
- **D-06:** `server_version` is a human dotted string (`'16.1'`), parsed from `conn.info.server_version` int.
- **D-07:** `health()` on all four classes — `Database`/`AsyncDatabase` plus `PooledDatabase`/`AsyncPooledDatabase` (adds `pool_stats` key from existing `.stats` property).

**Structured logging (LOG-01)**
- **D-08:** New `pycopg/logging.py` with `get_logger()` and `log_operation` CM. Stdlib `logging` only, `NullHandler` by default. No structlog.
- **D-09:** Coarse instrumentation only: `etl.run`, `backup`/`restore`, `migrations`, COPY paths (`from_dataframe`/`from_geodataframe`), `health`. NOT `execute()`/`fetch_*` hot path.
- **D-10:** `log_operation` emits `extra={operation, duration_ms, rows}` at DEBUG level.

**Named params (PARAM-01)**
- **D-11:** Shared public type alias `pycopg.Params = Sequence | Mapping[str, Any] | None`, exported in `__all__`.
- **D-12:** Annotation + docs ONLY. NO `_rewrite_named_params()` parser. The SUMMARY.md L84 mention of `_rewrite_named_params()` is an internal contradiction — the LOCK WINS.

### Claude's Discretion
- Exact `latency_ms` measurement recipe (monotonic clock around `SELECT 1`).
- Default/auto-generated savepoint `name` when `name=None` (psycopg auto-names if omitted).
- Internal mechanism for setting `conn.isolation_level` on per-call vs session connection.
- Precise placement of the `Params` alias definition (`base.py` vs `utils.py`).
- Exact `pool_stats` dict shape returned by pooled `health()` (reuse `.stats` verbatim vs subset).

### Deferred Ideas (OUT OF SCOPE)
- Per-`execute()` logging instrumentation (no per-query timing cost).
- Raw-int `server_version_num` key.
- String→enum isolation coercion surface.
- All deferred 1.x items (TSDB-F, ETL-INC-F, CRUD-F, INTRO-F).
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TXN-01 | User can set transaction isolation level via `db.transaction(isolation_level=...)` and `db.session(isolation_level=...)` | psycopg3 `IsolationLevel` enum + `conn.isolation_level` property verified; exact choke points in database.py and async_database.py identified |
| TXN-02 | User can create nested savepoints with partial rollback via `db.savepoint(name=None)` CM and `transaction(savepoint_name=...)` | `conn.transaction(savepoint_name=None)` auto-generates name; full nesting semantics verified in psycopg3 docs |
| PARAM-01 | User can pass named query params as dict using `%(name)s` on all 5 methods; annotated; no `:name` translator | Already works in psycopg3 natively; annotation-only deliverable confirmed; all 5 method signatures located |
| HEALTH-01 | `db.health()` returns `{connected, latency_ms, server_version}` (plus pool stats when pooled), sync + async | `conn.closed`/`conn.broken`, `conn.info.server_version` int format, `pool.get_stats()` keys — all verified |
| LOG-01 | New `pycopg/logging.py`; `NullHandler` default; `get_logger` + `log_operation` CM; coarse instrumentation | stdlib `logging` pattern, `extra={}` dict shape, typing for mypy-strict surviveability documented |
</phase_requirements>

---

## Summary

Phase 45 is a purely additive phase on the flat transactional core (`Database` / `AsyncDatabase`), requiring zero new runtime dependencies. Every capability is served by psycopg3 >= 3.1.0 native APIs, psycopg_pool >= 3.2.0, and stdlib `logging` — the existing version floors already cover everything needed.

The four capabilities have very different implementation weights: named params (PARAM-01) is annotations + docstrings + tests only (no code change, psycopg3 already handles `%(name)s` dicts natively via `cursor.execute()`); transaction isolation (TXN-01) is two parameter additions to existing context managers; savepoints (TXN-02) is a new `db.savepoint()` CM plus a `savepoint_name=` kwarg threaded through `transaction()`; health probe (HEALTH-01) is a new `health()` method on all four classes; structured logging (LOG-01) is a new `pycopg/logging.py` module plus instrumentation calls at 5-6 sites.

The critical cross-cutting constraints are: (1) all new optional params are keyword-only (D-04 / Phase 41 Stable API Contract), (2) `Database`/`AsyncDatabase` methods must be co-edited — the existing `test_method_signatures_match` in `test_parity.py` will catch divergence, (3) `log_operation` typing must be clean now so Phase 46 mypy-strict does not choke on `extra={}`, and (4) the `isolation_level` / `savepoint_name` params are the last new signature additions before the 1.0 API freeze — every name chosen here is frozen under SemVer.

**Primary recommendation:** Implement in this order — (1) `Params` alias + annotation widening (safest, zero risk), (2) isolation/savepoint additions to `transaction()`/`session()` (surgical additions to existing CMs), (3) `db.savepoint()` new CM (small, new method), (4) `pycopg/logging.py` + instrumentation, (5) `health()` on all four classes (touches the most files). Commit each as a separate verifiable increment.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Transaction isolation | Database / AsyncDatabase flat core | psycopg3 driver | Isolation is a connection-level property; pycopg wraps `conn.isolation_level` |
| Savepoints | Database / AsyncDatabase flat core | psycopg3 driver | `conn.transaction(savepoint_name=)` is the native primitive; pycopg adds ergonomic wrapper |
| Named params annotation | Type layer only (`base.py` or `utils.py`) | All 5 method signatures | Zero-runtime-cost; alias enables mypy checking |
| Health probe | All four database classes | psycopg3 driver + psycopg_pool | Non-pooled: fresh `SELECT 1` round-trip; pooled: reuse existing `.stats` property |
| Structured logging | `pycopg/logging.py` (new) + instrumentation sites | stdlib `logging` | Library-pattern: NullHandler default, callers own the handler stack |

---

## Standard Stack

### Core (no changes to pyproject.toml `[project.dependencies]`)

| Library | Version Floor | Purpose | Why Standard |
|---------|--------------|---------|--------------|
| psycopg | >= 3.1.0 | `IsolationLevel` enum, `conn.transaction(savepoint_name=)`, `conn.info.server_version`, `conn.closed`/`broken` | All Phase 45 APIs are native at this floor [VERIFIED: psycopg official docs] |
| psycopg_pool | >= 3.2.0 | `pool.get_stats()`, `pool.check()` for pooled `health()` | Already at floor in pyproject.toml; `.stats` property already wraps `get_stats()` [VERIFIED: psycopg_pool 3.3.1 PyPI + live source] |
| stdlib `logging` | Python 3.11+ | `logging.getLogger`, `NullHandler`, `extra={}` dict fields | Library-rule: zero runtime dep; PEP 3148 pattern [VERIFIED: Python docs] |

### No New Dependencies

Zero additions to `[project.dependencies]`. The three dev-group stubs (`pandas-stubs`, `types-geopandas`, `types-shapely`) belong to Phase 46 (mypy-strict gate), not this phase.

---

## Package Legitimacy Audit

> Phase 45 installs ZERO new packages (no changes to `[project.dependencies]` or `[dependency-groups]`).

**No packages to audit.** All capabilities use pre-existing dependencies at their current version floors.

---

## Architecture Patterns

### System Architecture Diagram

```
                         Phase 45 additions
                         ──────────────────
caller code
    │
    ├─ db.transaction(isolation_level=IsolationLevel.SERIALIZABLE)
    │       │
    │       ├─ [if in session] → RAISE RuntimeError (D-03)
    │       └─ [fresh conn]   → conn.isolation_level = enum_value
    │                           conn.transaction() [psycopg CM]
    │
    ├─ db.session(isolation_level=...)
    │       └─ new conn → conn.isolation_level = enum_value (before first txn)
    │
    ├─ db.savepoint(name=None)
    │       └─ requires active session conn
    │           └─ conn.transaction(savepoint_name=name_or_auto)
    │
    ├─ db.execute(sql, {"key": val})   ← %(name)s dict, NO CODE CHANGE
    │
    ├─ db.health()
    │       ├─ time.perf_counter() start
    │       ├─ fresh conn / pool conn → SELECT 1
    │       ├─ time.perf_counter() end → latency_ms
    │       ├─ conn.info.server_version → decode int → dotted string
    │       └─ returns dict (never raises — D-05)
    │
    └─ log_operation("etl.run", rows=N) [context manager]
            ├─ start = time.perf_counter()
            ├─ yield
            └─ logger.debug("...", extra={operation, duration_ms, rows})

pycopg/logging.py  ←── NEW MODULE
    get_logger()         returns logging.getLogger("pycopg")
    log_operation(name, rows=None)  context manager (sync)
    NullHandler attached to "pycopg" logger on import

pycopg/__init__.py  ←── ADDITIONS
    IsolationLevel = psycopg.IsolationLevel   (thin alias, D-01)
    Params = Sequence | Mapping[str, Any] | None  (type alias, D-11)
    __all__ += ["IsolationLevel", "Params"]
```

### Recommended Project Structure Changes

```
pycopg/
├── logging.py          # NEW — get_logger, log_operation, NullHandler setup
├── database.py         # Modified — transaction(isolation_level=*, savepoint_name=*)
│                       #            session(isolation_level=*)
│                       #            savepoint(name=None)
│                       #            health()
│                       #            execute/fetch_*/to_dataframe Params widening
│                       #            log_operation instrumentation at COPY paths
├── async_database.py   # Modified — async mirrors of all above (parity enforced)
├── pool.py             # Modified — PooledDatabase.health(), AsyncPooledDatabase.health()
├── base.py or utils.py # Modified — Params alias defined here (re-exported in __init__)
└── __init__.py         # Modified — IsolationLevel, Params in __all__
```

### Pattern 1: Isolation Level on transaction()

The natural choke point is the branch inside `transaction()` that already differentiates "in session" vs "fresh connection":

```python
# Source: database.py lines 506-525 (verified live)
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

[VERIFIED: live database.py source + psycopg3 docs for `conn.isolation_level` setter]

### Pattern 2: session() with isolation_level

```python
# session() opens the connection — add isolation_level BEFORE any transaction begins
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
    ...
```

[VERIFIED: psycopg3 docs — `isolation_level` property can only be set before a transaction starts, which is immediately after `connect()` and before any SQL is run]

### Pattern 3: savepoint() standalone CM

```python
@contextmanager
def savepoint(self, *, name: str | None = None) -> Iterator[None]:
    """Nested savepoint within an active session."""
    if self._session_conn is None:
        raise RuntimeError(
            "db.savepoint() requires an active db.session(). "
            "Use 'with db.session(): with db.savepoint(): ...' pattern."
        )
    with self._session_conn.transaction(savepoint_name=name):
        yield
```

When `name=None`, psycopg auto-generates the savepoint name. [VERIFIED: psycopg3 docs — "If None, one will be chosen automatically." No manual naming is required.]

### Pattern 4: health() — latency measurement with perf_counter

```python
import time

def health(self) -> dict[str, Any]:
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

`time.perf_counter()` is the correct choice: it is monotonic (unaffected by clock adjustments), high-resolution, and the standard Python idiom for wall-clock timing. `time.time()` is explicitly wrong for latency measurement (not monotonic). [ASSUMED — stdlib perf_counter is the de-facto standard for Python latency measurement; no alternative is meaningfully different]

### Pattern 5: server_version int → dotted string

PostgreSQL encodes its version as an integer via the `PQserverVersion()` C API format:
- **PostgreSQL >= 10 (current):** `major * 10000 + minor * 100 + patch` — but since PG 10+ dropped the three-part version scheme, format is `major * 10000 + patch`. E.g. PG 16.1 = `160001`.
- **PostgreSQL < 10 (pre-10, three-part):** `major * 10000 + minor * 100 + patch`. E.g. 9.6.5 = `90605`.

**Decoding formula (PG 10+):**

```python
def _decode_server_version(v: int) -> str:
    """Decode psycopg server_version int to dotted string.

    PostgreSQL 10+ format: XXYYZZ where XX=major, YY=00 (minor dropped), ZZ=patch.
    Example: 160001 → '16.1', 150004 → '15.4'.
    Pre-10 format: XXYYZZ where XX=major, YY=minor, ZZ=patch.
    Example: 90605 → '9.6.5'.
    """
    major = v // 10000
    if major >= 10:
        patch = v % 100
        return f"{major}.{patch}"
    else:
        minor = (v % 10000) // 100
        patch = v % 100
        return f"{major}.{minor}.{patch}"
```

[VERIFIED: psycopg3 docs — "9.3.5 is returned as 90305, version 10.2 as 100002"; PG 10+ middle digits are always 00; verified arithmetic: 160001 // 10000 = 16, 160001 % 100 = 1 → '16.1']

### Pattern 6: log_operation context manager + typing

For Phase 46 mypy-strict compatibility, `extra` must be typed explicitly:

```python
# pycopg/logging.py
import logging
import time
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

_logger = logging.getLogger("pycopg")
_logger.addHandler(logging.NullHandler())


def get_logger() -> logging.Logger:
    """Return the pycopg library logger."""
    return _logger


@contextmanager
def log_operation(
    operation: str,
    *,
    rows: int | None = None,
) -> Generator[None, None, None]:
    """Context manager that times an operation and emits a DEBUG log record.

    Parameters
    ----------
    operation : str
        Operation name (e.g. "etl.run", "backup.pg_dump").
    rows : int or None, optional
        Row count to include in the log record when known.
    """
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

The `extra: dict[str, Any]` annotation is the key mypy-strict survivor: `--disallow-any-generics` requires `dict[str, Any]` not bare `dict`. `Generator[None, None, None]` is required over `Iterator[None]` for a `contextmanager`-decorated function under strict mode. [ASSUMED — based on mypy-strict behavior with `--disallow-any-generics`; to be confirmed in Phase 46]

**For async wrappers (instrumenting async operations):** `log_operation` is a sync context manager that brackets the `await`. Since it wraps at the caller site (e.g., inside `etl.run`'s async version), no async CM is needed — the CM wraps the block that contains the `await`:

```python
# In AsyncETLAccessor.run()
with log_operation("etl.run"):
    result = await self._execute_pipeline(...)
```

[VERIFIED: This is valid Python — a sync CM can wrap `await` expressions inside its body]

### Pattern 7: Params type alias placement

**Recommendation: `pycopg/base.py`** — it has no imports from pycopg internals except `Config` and `utils`, so placing `Params` there avoids circular imports. Re-export from `__init__.py`.

```python
# pycopg/base.py (additions)
from collections.abc import Mapping, Sequence
from typing import Any

Params = Sequence[Any] | Mapping[str, Any] | None
```

Then in each method signature that currently has `Sequence | None`:

```python
# Before: params: Sequence | None = None
# After:  params: Params = None
```

The 5 methods to widen: `execute`, `fetch_one`, `fetch_val`, `fetch_all` (currently `Sequence | None`), and `to_dataframe` (currently `dict | None` → widen to `Params`). [VERIFIED: live source — database.py L594, L1131, L1150, L1170, L1373; all confirmed with current annotation]

### Pattern 8: pooled health() — pool_stats shape

The `PooledDatabase.stats` property (pool.py:200) already returns:

```python
{
    "pool_min": self._pool.min_size,
    "pool_max": self._pool.max_size,
    "pool_size": self._pool.get_stats().get("pool_size", 0),
    "pool_available": self._pool.get_stats().get("pool_available", 0),
    "requests_waiting": self._pool.get_stats().get("requests_waiting", 0),
    "requests_num": self._pool.get_stats().get("requests_num", 0),
}
```

[VERIFIED: live pool.py source, lines 199-215]

**Recommendation (Claude's Discretion):** Reuse `.stats` verbatim as the `pool_stats` value. This is a stable property already tested; subsetting it would create a maintenance divergence. The pooled `health()` returns:

```python
{
    "connected": True,
    "latency_ms": ...,
    "server_version": ...,
    "pool_stats": self.stats,   # the full dict from .stats property
}
```

### Anti-Patterns to Avoid

- **`_rewrite_named_params()` parser:** D-12 hard lock. Do not build this. psycopg3 already handles `%(name)s` from `Mapping` natively. The only deliverable is the annotation + docstring.
- **`logging.basicConfig()` in library code:** Never call `basicConfig()` in a PyPI library. It reconfigures the caller's logging stack. The only acceptable calls are `getLogger()` and `addHandler(NullHandler())`.
- **Setting `isolation_level` inside an active transaction:** psycopg3 raises `ProgrammingError` if you attempt to change `conn.isolation_level` after a transaction has started. The guard must be at the pycopg layer (D-03), not left to psycopg to surface as an opaque driver error.
- **Raising in `health()`:** D-05 hard lock. Every exception path must be caught and returned as `{connected: False, ..., error: str(exc)}`.
- **`time.time()` for latency:** Not monotonic. Use `time.perf_counter()` only.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Savepoint lifecycle | Manual `SAVEPOINT` / `ROLLBACK TO` SQL | `conn.transaction(savepoint_name=)` | psycopg handles RELEASE on success, ROLLBACK on exception, naming; hand-rolled misses edge cases |
| Isolation enum | A copy of the IsolationLevel values as a pycopg enum | `import psycopg; IsolationLevel = psycopg.IsolationLevel` | Single source of truth; if psycopg adds an isolation level in future, re-export picks it up automatically |
| `%(name)s` → `:name` translation | `_rewrite_named_params()` parser | Annotation + docs only | D-12 hard lock; parser handles `::cast` and quoted literals incorrectly in edge cases |
| Pool stats collection | Direct `_pool.get_stats()` with custom keys | `.stats` property already in `PooledDatabase` | Property exists, is tested, and already wraps `get_stats()` correctly |
| Structured logging framework | Adding `structlog` or `loguru` | `logging.getLogger("pycopg")` + `NullHandler()` | Library rule: callers own the logging stack; D-08 hard lock |

**Key insight:** Every "new" capability in this phase is already implemented inside psycopg3 or stdlib. The phase is about surfacing native APIs cleanly at the right abstraction level, not building new mechanisms.

---

## Common Pitfalls

### Pitfall 1: Setting isolation_level After Transaction Has Started

**What goes wrong:** `conn.isolation_level = value` raises `psycopg.errors.ActiveSqlTransaction` if called after `BEGIN` has been issued (even autocommit=False connections have implicit transactions). Calling `transaction(isolation_level=)` inside an active `db.session()` must be caught at the pycopg layer and turned into a clear `RuntimeError`, not left to bubble up as a driver error.

**Why it happens:** The D-03 guard is checked at `transaction()` entry against `self._session_conn is not None`, but if the guard is missed or only partial, psycopg surfaces a confusing error.

**How to avoid:** The guard must be the first line inside the `_session_conn is not None` branch of `transaction()`. Test: call `transaction(isolation_level=...)` inside a `with db.session()` block and assert `RuntimeError` is raised.

**Warning signs:** Tests pass but only test the non-session path; no test exercises `transaction(isolation_level=)` while a session is active.

---

### Pitfall 2: log_operation extra={} Dict Fails mypy-strict

**What goes wrong:** `extra={"operation": "x", "duration_ms": 1.5}` without explicit `dict[str, Any]` annotation fails `--disallow-any-generics` and `--warn-return-any` in Phase 46. mypy infers `dict[str, float | str]` which is narrower than `dict[str, Any]` and breaks when `rows: int` is conditionally added.

**Why it happens:** Python's type inference narrows dict literals. `dict[str, Any]` must be explicit.

**How to avoid:** Always annotate as `extra: dict[str, Any] = {...}` with `from typing import Any`. The `Generator[None, None, None]` return type on `log_operation` is also required (not `Iterator[None]`) for `contextmanager`-decorated generators under strict mode. Write this correctly now so Phase 46 passes without touching logging.py.

**Warning signs:** `extra = {"operation": ..., "duration_ms": ...}` without type annotation on the variable.

---

### Pitfall 3: savepoint() Called Outside a Session Gives Wrong Error

**What goes wrong:** `db.savepoint()` requires `self._session_conn is not None`. If called on a Database without a session, it must raise `RuntimeError` with a clear, actionable message (tell the user to use `with db.session()`). A bare `AttributeError` on `None` is confusing.

**How to avoid:** Explicit guard at the top of `savepoint()`: `if self._session_conn is None: raise RuntimeError(...)`.

---

### Pitfall 4: health() Leaks Connections on Error

**What goes wrong:** If `SELECT 1` raises before the cursor context manager closes, the connection is not released properly. The `with self.connect() as conn` pattern already handles this correctly — but if the `health()` implementation bypasses the CM (e.g., to acquire a pool connection differently), a crash leaves a connection checked out.

**How to avoid:** Use `with self.connect() as conn:` exclusively (not raw `psycopg.connect()`). On pooled classes, use `with self.connection() as conn:` (the pooled acquisition CM). The `except Exception` block inside `health()` must NOT call `conn.close()` directly — the CM handles it.

---

### Pitfall 5: Params Alias Breaks `to_dataframe` SQLAlchemy Path

**What goes wrong:** `to_dataframe()` passes `params` to SQLAlchemy's `text()` binding, not to `psycopg`. SQLAlchemy uses `:name` style, not `%(name)s`. Widening `to_dataframe`'s annotation to `Params` is correct, but the internal implementation must not blindly pass a `%(name)s`-style dict to SQLAlchemy.

**What to verify:** `to_dataframe` already accepts `dict | None` (confirmed live: database.py:1373). The internal plumbing passes it to SQLAlchemy's `text(...).bindparams()` using `:name` style. The annotation widening changes the type annotation only; the actual dict passed by the caller must still use `:name` syntax for `to_dataframe`, or the method must convert. **This needs a note in the docstring and an explicit test.**

**How to avoid:** In the PARAM-01 docstring update for `to_dataframe`, note that it uses SQLAlchemy's `:name` style (not `%(name)s`) because it routes through SQLAlchemy `text()`. The `Params` alias is correct for the type, but the param style differs between `execute/fetch_*` (psycopg `%(name)s`) and `to_dataframe` (SQLAlchemy `:name`). This is a pre-existing behavior; the annotation widening must not silently change the expectation.

**Warning signs:** A test that passes a `%(name)s`-style dict to `to_dataframe()` and expects it to work — it won't, because SQLAlchemy handles the binding differently.

---

### Pitfall 6: Async health() Not Timing the Await

**What goes wrong:** `time.perf_counter()` is called before and after `await conn.execute("SELECT 1")`, but if the timing brackets only the synchronous setup and not the actual await, the latency measurement is wrong (measures zero or near-zero).

**How to avoid:**

```python
async def health(self) -> dict[str, Any]:
    try:
        t0 = time.perf_counter()
        async with self.connect() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT 1")   # ← the await IS inside the bracket
            server_ver = conn.info.server_version
        latency_ms = (time.perf_counter() - t0) * 1000
        ...
```

The `t0` is set before `connect()`, so the latency includes the connection acquisition time (appropriate — it's a full round-trip health check). If measuring only query latency is desired, set `t0` after the `async with self.connect()` block opens.

---

## Code Examples

### IsolationLevel re-export (D-01)

```python
# pycopg/__init__.py addition — verified pattern
import psycopg as _psycopg
IsolationLevel = _psycopg.IsolationLevel
# Or equivalently:
from psycopg import IsolationLevel  # direct re-export
```

[VERIFIED: `psycopg.IsolationLevel` exists as `IntEnum` with READ_UNCOMMITTED=1, READ_COMMITTED=2, REPEATABLE_READ=3, SERIALIZABLE=4 — confirmed via psycopg3 official docs]

### Named params usage (PARAM-01 — annotation change only)

```python
# Already works in psycopg3 natively (no code change needed):
db.execute(
    "SELECT * FROM orders WHERE user_id = %(uid)s AND status = %(status)s",
    {"uid": 42, "status": "open"},  # passes as Mapping[str, Any]
)
# The fetch_* equivalents work identically.
# Note: to_dataframe() uses SQLAlchemy :name style (pre-existing behavior).
```

[VERIFIED: psycopg3 `cursor.execute()` accepts both `Sequence` and `Mapping` natively]

### Pool get_stats() keys (verified live in pool.py)

```python
# pool.py stats property (lines 199-215, verified live):
{
    "pool_min": int,           # pool.min_size
    "pool_max": int,           # pool.max_size
    "pool_size": int,          # current pool size
    "pool_available": int,     # idle connections
    "requests_waiting": int,   # queued requests
    "requests_num": int,       # total requests served (sync only)
}
# AsyncPooledDatabase.stats (lines 422-431, verified live) lacks "requests_num"
```

[VERIFIED: live pool.py source inspection]

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| String isolation level (`"serializable"`) | `psycopg.IsolationLevel` enum | psycopg3 (2021+) | Typo-safe, IDE autocomplete, no string parsing needed |
| Manual `SAVEPOINT sp1; ... ROLLBACK TO sp1` SQL | `conn.transaction(savepoint_name="sp1")` CM | psycopg3 | Driver handles RELEASE/ROLLBACK automatically |
| `logging.basicConfig()` in libraries | `logging.NullHandler()` + `getLogger("lib")` | PEP 3148 (2009+) | Libraries must not configure the caller's logging stack |
| `params: list` | `params: Sequence[Any] | Mapping[str, Any] | None` | mypy-strict era | Required for `--disallow-any-generics` compliance |

**Deprecated/outdated:**
- `conn.set_isolation_level()` (psycopg2 style): psycopg3 uses `conn.isolation_level` property setter directly. `set_isolation_level()` exists as a method in psycopg3 too (added 3.2), but the property setter is the primary interface.
- Bare `dict | None` for params: still works at runtime but fails mypy-strict `--disallow-any-generics`. `Mapping[str, Any] | None` or the `Params` alias is required.

---

## Source File Verification (line anchors from CONTEXT.md)

The following anchors from CONTEXT.md were verified against the live source on 2026-06-30:

| CONTEXT.md Reference | Actual Location | Status |
|---------------------|-----------------|--------|
| `database.py transaction()` ~line 507 | Line 507: `@contextmanager` / line 507-525 `transaction()` | CONFIRMED |
| `database.py session()` ~line 528 | Line 527-581 `session(autocommit=)` | CONFIRMED (line 527, not 528) |
| `database.py in_session` ~line 584 | Line 583-592 `in_session` property | CONFIRMED |
| `async_database.py session()` ~line 516 | Line 515-567 `async session()` | CONFIRMED |
| `async_database.py transaction()` ~line 581 | Line 580-600 `async transaction()` | CONFIRMED |
| `async_database.py in_session` ~line 570 | Line 569-578 `in_session` | CONFIRMED |
| `pool.py PooledDatabase.stats()` ~line 200 | Line 199-215 `.stats` property | CONFIRMED |
| `pool.py AsyncPooledDatabase.stats()` ~line 423 | Line 422-431 `.stats` property | CONFIRMED |
| `database.py to_dataframe params: dict | None` ~line 1373 | Line 1373 `params: dict | None = None` | CONFIRMED |
| `database.py fetch_one` | Line 1131 | CONFIRMED |
| `database.py fetch_val` | Line 1150 | CONFIRMED |
| `database.py fetch_all` | Line 1170 | CONFIRMED |
| `database.py execute` params annotation | Line 595: `params: Sequence | None = None` | CONFIRMED |
| `async_database.py execute` params annotation | Line 604-606: `params: Sequence | None = None` | CONFIRMED |
| `database.py logger` at ~line 40 | Line 40: `logger = logging.getLogger(__name__)` | CONFIRMED |
| `async_database.py logger` at ~line 39 | Line 39: `logger = logging.getLogger(__name__)` | CONFIRMED |

**Key divergence from CONTEXT.md:** `PooledDatabase.stats` is a `@property` returning a dict, not a method `stats()`. This matters for `health()` — call `self.stats` (property), not `self.stats()`.

---

## Instrumentation Sites (D-09)

The following sites require `log_operation` wrapping (D-09 — coarse only):

| Module | Method | Operation name | rows source |
|--------|--------|---------------|-------------|
| `etl.py` | `ETLAccessor.run()` | `"etl.run"` | `result.rows_written` |
| `etl.py` | `AsyncETLAccessor.run()` | `"etl.run"` | `result.rows_written` |
| `backup.py` | `BackupAccessor.pg_dump()` | `"backup.pg_dump"` | None (no row count) |
| `backup.py` | `BackupAccessor.pg_restore()` | `"backup.pg_restore"` | None |
| `backup.py` | `AsyncBackupAccessor.pg_dump()` | `"backup.pg_dump"` | None |
| `backup.py` | `AsyncBackupAccessor.pg_restore()` | `"backup.pg_restore"` | None |
| `migrations.py` | `Migrator.migrate()` | `"migrations.migrate"` | `len(applied)` |
| `database.py` | `Database.from_dataframe()` | `"database.from_dataframe"` | `len(df)` |
| `database.py` | `Database.from_geodataframe()` | `"database.from_geodataframe"` | `len(gdf)` |
| `async_database.py` | `AsyncDatabase.from_dataframe()` | `"database.from_dataframe"` | `len(df)` |
| `async_database.py` | `AsyncDatabase.from_geodataframe()` | `"database.from_geodataframe"` | `len(gdf)` |
| `database.py` | `Database.health()` | `"database.health"` | None |
| `async_database.py` | `AsyncDatabase.health()` | `"database.health"` | None |

**Total instrumentation sites: ~13** (sync + async pairs). Each is a coarse wrap of the outer method body, not a per-row call.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `time.perf_counter()` is the correct timer for latency_ms measurement | Pattern 4 | Functionally identical to alternatives; risk is cosmetic |
| A2 | `Generator[None, None, None]` return type required for `contextmanager` under mypy-strict | Pattern 6 | Phase 46 may require adjustment; not a runtime risk |
| A3 | `dict[str, Any]` annotation on `extra` in `log_operation` survives `--disallow-any-generics` | Pattern 6 | `Any` is explicitly allowed in `dict[str, Any]`; this should be correct but untested under strict |
| A4 | `to_dataframe()` uses SQLAlchemy `:name` style internally (not `%(name)s`) | Pitfall 5 | Needs a test to confirm; if wrong, Pitfall 5 diagnosis is incorrect |

**If this table is empty of HIGH-risk items:** all assumptions above are LOW-risk cosmetic or type-annotation questions that Phase 46 resolves.

---

## Open Questions (RESOLVED)

1. **`to_dataframe` `:name` vs `%(name)s` param style**
   - What we know: `to_dataframe` already accepts `dict | None`; it routes through SQLAlchemy `text()`.
   - What's unclear: Does the existing implementation use SQLAlchemy's `:name` bindparams style, or does it pass the dict directly to psycopg? Needs one targeted test.
   - Recommendation: Add a test in Wave 0 that calls `to_dataframe(sql="SELECT :val", params={"val": 1})` and confirms it works, before widening the annotation.
   - **RESOLVED (planning):** `to_dataframe` uses the SQLAlchemy `:name` style (it binds through `text()`), distinct from the `%(name)s` style of `execute`/`fetch_*`. This is confirmed by the targeted test `test_to_dataframe_named_style` in Plan 03 Task 1 and documented in the method's widened-annotation docstring. NO translator/`_rewrite_named_params` is built (D-12 lock holds); the annotation is widened to `Params` and the divergence is documented, not papered over.

2. **`AsyncPooledDatabase.stats` missing `requests_num`**
   - What we know: The sync `PooledDatabase.stats` includes `requests_num` (line 214) but the async `AsyncPooledDatabase.stats` (lines 422-431) only has 5 keys (no `requests_num`). This is a pre-existing asymmetry.
   - What's unclear: Should `pooled health()` on async use the async `.stats` (which lacks `requests_num`) or should the async stats be fixed as a pre-req?
   - Recommendation: Do not fix the async stats asymmetry in this phase (out of scope). Use `self.stats` verbatim on both pooled classes; the shape difference is pre-existing and documented.
   - **RESOLVED (planning):** Pre-existing asymmetry left AS-IS (out of scope for Phase 45). Both pooled classes' `health()` use `self.stats` verbatim for the `pool_stats` key (Plan 03 Task 2); the async shape simply lacks `requests_num`, which is acceptable and documented. No pool plumbing changes.

---

## Environment Availability

> Phase 45 is purely additive Python code. No new external tools, services, or CLIs are required.

Step 2.6: SKIPPED — no new external dependencies identified. All capabilities (psycopg3, psycopg_pool, stdlib logging) are already present in the running environment.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (uv run pytest) |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/ -x -q` |
| Full suite command | `uv run pytest` (with coverage gate ≥95%) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File |
|--------|----------|-----------|-------------------|------|
| TXN-01a | `transaction(isolation_level=SERIALIZABLE)` sets isolation outside session | unit | `uv run pytest tests/test_transaction_isolation.py -x -q` | Wave 0 new |
| TXN-01b | `transaction(isolation_level=)` inside `db.session()` raises RuntimeError | unit | `uv run pytest tests/test_transaction_isolation.py::test_isolation_inside_session_raises -x` | Wave 0 new |
| TXN-01c | `session(isolation_level=REPEATABLE_READ)` sets isolation on session connection | unit | `uv run pytest tests/test_transaction_isolation.py::test_session_isolation -x` | Wave 0 new |
| TXN-01d | Async mirrors: `AsyncDatabase.transaction/session(isolation_level=)` | unit | same file, async test functions | Wave 0 new |
| TXN-02a | `transaction(savepoint_name="sp1")` creates named savepoint; rollback to sp1 on inner error | integration | `uv run pytest tests/test_savepoints.py -x -q` | Wave 0 new |
| TXN-02b | `db.savepoint(name=None)` auto-names; inner exception rolls back only the savepoint | integration | `uv run pytest tests/test_savepoints.py::test_savepoint_autoname -x` | Wave 0 new |
| TXN-02c | `db.savepoint()` outside a session raises RuntimeError | unit | `uv run pytest tests/test_savepoints.py::test_savepoint_requires_session -x` | Wave 0 new |
| TXN-02d | Async mirrors: `AsyncDatabase.savepoint()` and `transaction(savepoint_name=)` | unit+integration | same file | Wave 0 new |
| PARAM-01a | `execute()` accepts `dict` params with `%(name)s` SQL | unit | `uv run pytest tests/test_named_params.py::test_execute_dict_params -x` | Wave 0 new |
| PARAM-01b | `fetch_one/fetch_val/fetch_all` accept dict params | unit | `uv run pytest tests/test_named_params.py -x` | Wave 0 new |
| PARAM-01c | `to_dataframe()` `:name` style confirmed (existing behavior, explicit test) | unit | `uv run pytest tests/test_named_params.py::test_to_dataframe_named_style -x` | Wave 0 new |
| PARAM-01d | `Params` alias is in `pycopg.__all__` | unit | `uv run pytest tests/test_named_params.py::test_params_alias_exported -x` | Wave 0 new |
| PARAM-01e | Async mirror methods accept dict params | unit | same file | Wave 0 new |
| HEALTH-01a | `db.health()` returns correct dict shape with connected=True | unit (mock conn) | `uv run pytest tests/test_health.py::test_health_connected -x` | Wave 0 new |
| HEALTH-01b | `db.health()` returns `{connected: False, error: ...}` on failure (never raises) | unit | `uv run pytest tests/test_health.py::test_health_never_raises -x` | Wave 0 new |
| HEALTH-01c | `server_version` decodes PG 16.1 → '16.1', PG 9.6.5 → '9.6.5' | unit | `uv run pytest tests/test_health.py::test_server_version_decode -x` | Wave 0 new |
| HEALTH-01d | Pooled `health()` includes `pool_stats` key | unit | `uv run pytest tests/test_health.py::test_pooled_health_stats -x` | Wave 0 new |
| HEALTH-01e | Async mirrors: `AsyncDatabase.health()`, `AsyncPooledDatabase.health()` | unit | same file | Wave 0 new |
| LOG-01a | `get_logger()` returns logger named "pycopg" with NullHandler | unit | `uv run pytest tests/test_logging_module.py::test_get_logger -x` | Wave 0 new |
| LOG-01b | `log_operation` emits DEBUG record with operation/duration_ms/rows in extra | unit | `uv run pytest tests/test_logging_module.py::test_log_operation_extra -x` | Wave 0 new |
| LOG-01c | No log records emitted when no handler configured (NullHandler default) | unit | `uv run pytest tests/test_logging_module.py::test_null_handler_silence -x` | Wave 0 new |
| LOG-01d | ETL.run, backup methods, migrations.migrate instrumented (smoke) | integration | `uv run pytest tests/test_logging_module.py::test_instrumentation_sites -x` | Wave 0 new |

### Parity Guard (existing — must stay green)

The existing `test_parity.py` `TestDatabaseAsyncParity` class covers:
- `test_all_database_public_methods_exist_in_async` — catches missing `health()`, `savepoint()` on either side
- `test_method_signatures_match` — catches signature drift between sync/async `transaction(isolation_level=*)` etc.
- `test_accessor_parameter_kind_parity` — catches positional vs keyword-only divergence (D-04)

These are existing tests that will AUTOMATICALLY FAIL if Phase 45 adds a method to `Database` but not `AsyncDatabase`, or adds it with the wrong parameter kinds. No new parity test code is needed.

### Coverage Gate

Baseline measured 96.18% at Phase 44. Phase 45 adds ~200-300 lines across 6 files + ~5 new test files. All new branches must be covered (especially the `health()` error path and the `transaction(isolation_level=)` session-guard branch). `# pragma: no cover` is permitted only with an em-dash justification comment.

Gate: `--cov-fail-under=95` (target: maintain 96%+).

### Interrogate Gate

`interrogate` must remain at 100% for public docstrings. Every new public method (`health`, `savepoint`, `get_logger`, `log_operation`) and the new type alias (`Params`) must have a complete numpydoc docstring.

### DeprecationWarning Gate

`-W error::DeprecationWarning` CI gate must stay green. Phase 45 adds no deprecated aliases, but existing deprecated spatial `where=` aliases must not be accidentally touched.

### Wave 0 Gaps (new test files to create before implementation)

- [ ] `tests/test_transaction_isolation.py` — TXN-01 tests (unit, no live DB needed for guard tests)
- [ ] `tests/test_savepoints.py` — TXN-02 tests (integration tests need live DB)
- [ ] `tests/test_named_params.py` — PARAM-01 annotation + behavior tests
- [ ] `tests/test_health.py` — HEALTH-01 tests (unit with mocked connections)
- [ ] `tests/test_logging_module.py` — LOG-01 tests (pure unit)

---

## Security Domain

> `security_enforcement` is not set to `false` in config.json — section required.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | — |
| V3 Session Management | yes (isolation level) | `conn.isolation_level` via psycopg native enum; no string eval |
| V4 Access Control | no | — |
| V5 Input Validation | partial | `isolation_level` is a typed enum (no string injection); `savepoint_name` is passed to psycopg as-is (psycopg quotes it internally) |
| V6 Cryptography | no | — |

### Phase 45 Threat Assessment

**No new SQL builders are introduced in this phase.** The `savepoint_name` parameter is passed directly to `conn.transaction(savepoint_name=)` — psycopg handles quoting. The `isolation_level` is an `IntEnum` value, not a string. Named params (`Params` alias) are annotation-only; the underlying psycopg binding is already injection-safe.

The validate_identifiers / per-builder injection-test acceptance criterion from the v0.10.0 lesson is NOT triggered here because no new SQL string builders are introduced. All SQL in this phase is either:
- A fixed literal (`SELECT 1` in `health()`)
- A psycopg-native CM (`conn.transaction(savepoint_name=)`)
- Annotation-only (PARAM-01)

**Only security note:** `savepoint_name` is an arbitrary string passed to psycopg. psycopg handles savepoint identifier quoting internally via `Identifier(savepoint_name)`. Do not manually interpolate `savepoint_name` into a SQL string — delegate entirely to `conn.transaction(savepoint_name=name)`. [ASSUMED — psycopg's handling of savepoint names should be safe; confirm with a test that passes a name containing SQL metacharacters and verifies no injection occurs]

---

## Sources

### Primary (HIGH confidence)
- psycopg3 official docs (CrunchyData mirror 3.1.9): `isolation_level` property (read/write setter), `transaction(savepoint_name=None, force_rollback=False)`, `IsolationLevel` IntEnum (READ_UNCOMMITTED=1, READ_COMMITTED=2, REPEATABLE_READ=3, SERIALIZABLE=4), `conn.closed`/`conn.broken`, savepoint auto-naming when `name=None` [CITED: access.crunchydata.com/documentation/psycopg3/3.1.9/api/connections.html]
- psycopg3 `conn.info.server_version` int format: "9.3.5 → 90305, 10.2 → 100002; PG 10+ middle digits always 00" [CITED: access.crunchydata.com/documentation/psycopg3/3.1.9/api/objects.html]
- pycopg live source inspection: database.py (L40, L507-525, L527-581, L583-592, L594-617, L1131, L1150, L1170, L1373), async_database.py (L39, L515-600, L602-), pool.py (L199-215, L422-431), utils.py, base.py, __init__.py [VERIFIED: direct file inspection 2026-06-30]
- Python stdlib logging — PEP 3148 NullHandler pattern, `extra={}` dict fields, `logging.getLogger()` [VERIFIED: Python docs]
- psycopg_pool `.get_stats()` keys: confirmed live in pool.py source — pool_min, pool_max, pool_size, pool_available, requests_waiting, requests_num [VERIFIED: live source]

### Secondary (MEDIUM confidence)
- WebSearch cross-verification of `conn.isolation_level` setter + async `set_isolation_level()` added in psycopg3 3.2 [CITED: psycopg.org/psycopg3/docs/api/connections.html]
- WebSearch confirmation of `get_stats()` key names [CITED: psycopg.org/psycopg3/docs/advanced/pool.html]

### Tertiary (LOW confidence)
- `Generator[None, None, None]` vs `Iterator[None]` under mypy-strict for `contextmanager` — assumed from training knowledge; to be verified in Phase 46

---

## Metadata

**Confidence breakdown:**
- psycopg3 API surface (IsolationLevel, transaction, savepoint, server_version): HIGH — verified against official docs
- Pool stats shape: HIGH — verified against live source
- log_operation typing for mypy-strict: MEDIUM — assumed correct, Phase 46 verifies
- to_dataframe param style (SQLAlchemy :name vs %(name)s): MEDIUM — needs one targeted test to confirm internal routing

**Research date:** 2026-06-30
**Valid until:** 2026-07-30 (psycopg3 API is stable; logging pattern is timeless)
