# Architecture Research

**Domain:** High-level Python library API for PostgreSQL/PostGIS/TimescaleDB (v1.0.0 integration)
**Researched:** 2026-06-27
**Confidence:** HIGH (based on direct code inspection of spatial.py, base.py, database.py, async_database.py, exceptions.py, and PROJECT.md)

## How v1.0.0 Features Integrate with the Existing Architecture

This document answers the four integration questions for the v1.0.0 "Spatial v2 + API freeze" milestone.
All claims are derived from direct source reading.

---

## 1. Spatial v2: Builder Shape Analysis

### Existing builder taxonomy (spatial.py)

The current 11 helpers split into two builder shapes:

| Shape | Helpers | Characteristic |
|-------|---------|----------------|
| Geometry-resolver | `contains`, `intersects`, `dwithin`, `distance`, `nearest` | Takes `point=/wkt=/geojson=/ref=` — resolves input geometry via `_resolve_geometry()` |
| Column-only | `within`, `area`, `perimeter`, `centroid`, `buffer`, `transform` | Operates on table columns; no input geometry |

### Processing helpers (ST_Union pairwise, ST_Simplify, ST_ConvexHull, ST_MakeValid, ST_Difference, ST_Intersection)

These operate on **existing table geometry columns**, not on a caller-supplied input geometry.
They belong to the column-only builder shape. No `_resolve_geometry()` involvement.

Two sub-shapes within processing:

**Unary column operations** (ST_Simplify, ST_ConvexHull, ST_MakeValid):

Follow `build_buffer_sql` / `build_transform_sql` exactly:
- `validate_identifiers(table, schema, geom)` first
- Scalar parameter (e.g. `tolerance`) as `%s`
- Output is a geometry column — `into="gdf"` valid
- `_append_tail(sql, where, order_by, limit, has_where=False)` as tail

Example builder shape for `build_simplify_sql`:
```python
build_simplify_sql(table, geom, schema, *, tolerance, columns, where, order_by, limit)
# SELECT {cols}, ST_Simplify(t.{geom}, %s) AS geometry_simplified
# FROM {schema}.{table} AS t
```

**Binary column operations** (ST_Difference, ST_Intersection):
```python
build_difference_sql(table, geom_a, geom_b, schema, *, columns, where, order_by, limit)
# SELECT {cols}, ST_Difference(t.{geom_a}, t.{geom_b}) AS geometry_diff
# FROM {schema}.{table} AS t
```
Both `geom_a` and `geom_b` are table columns, both identifier-validated.
`into="gdf"` valid (result is a geometry). No new builder infrastructure needed.

**ST_Union pairwise** (two geometry columns in same row):
Same binary column shape as ST_Difference. Distinct from the aggregate ST_Union (see below).

### Spatial aggregates (ST_Union agg, ST_Collect, ST_Extent)

Aggregates are a **new builder shape** with distinct characteristics:
- Returns one row (or one row per group) — not one row per table row
- Optional `group_by` parameter changes cardinality from scalar to grouped
- `ST_Extent` returns box2d, not geometry — `into="gdf"` must be blocked

Proposed builder:
```python
build_spatial_aggregate_sql(
    table: str,
    geom: str,
    schema: str = "public",
    *,
    aggregate: str,            # "union" | "collect" | "extent"
    group_by: list[str] | None = None,
    where: str | None = None,
) -> tuple[str, list]:
    # validate table/schema/geom, validate_identifiers(*group_by) if provided
    # SELECT {group_cols}, ST_Union(t.{geom}) AS geometry_union
    # FROM {schema}.{table} AS t [WHERE {where}] [GROUP BY {group_cols}]
```

Return type: `list[dict]` always (ungrouped = one-element list; grouped = multiple rows).
Using `list[dict]` for both avoids a `dict | list[dict]` union type.

`ST_Extent` returns box2d text — add `"spatial_extent"` (or `"extent"`) to `_SCALAR_HELPERS`
in `spatial.py` so `into="gdf"` raises `ValueError` for that specific aggregate.

### ST_AsMVT: dedicated method with bytes return

ST_AsMVT is an aggregate that returns **bytes** (binary Mapbox Vector Tile data). It composes:
1. `ST_TileEnvelope(zoom, x, y)` — tile bounding box
2. `ST_AsMVTGeom(geom, envelope)` — project features into tile pixel space
3. `ST_AsMVT(q, layer, extent, geom_name)` — outer aggregate over the projected rows

Integration decision: ST_AsMVT lives in `db.spatial.*` (same accessor, same PostGIS guard),
but as a **dedicated method returning `bytes` unconditionally** with no `into=` parameter.

```python
# accessor method (always returns bytes, no into=)
def as_mvt(
    self,
    table: str,
    zoom: int,
    x: int,
    y: int,
    geom: str = "geometry",
    schema: str = "public",
    layer: str = "default",
    columns: list[str] | None = None,
    where: str | None = None,
) -> bytes:
    sql, params = build_as_mvt_sql(...)
    result = self._db.execute(sql, params)
    return result[0]["st_asmvt"] if result else b""
```

The builder `build_as_mvt_sql` returns `(sql, params)` exactly like all builders.
The accessor extracts the bytes field. No changes to `_run()` or `_check_into()`.

Parity: `AsyncSpatialAccessor.as_mvt()` awaits `self._db.execute()`, returns bytes.

### Serialization helpers (ST_AsGeoJSON, ST_AsText)

Operate on a table geometry column, return **text per row**. Column-only builder shape.
`into="rows"` only (text output, not geometry). Add both to `_SCALAR_HELPERS`.

```python
build_as_geojson_sql(table, geom, schema, *, columns, where, order_by, limit)
# SELECT {cols}, ST_AsGeoJSON(t.{geom}) AS geojson FROM {schema}.{table} AS t
```

### Summary: new vs. modified components for Spatial v2

| File | Change | Details |
|------|--------|---------|
| `pycopg/spatial.py` | Modified | 8-10 new `build_*_sql` builders (column-only + aggregate shape) |
| `pycopg/spatial.py` | Modified | `_SCALAR_HELPERS` extended with `"extent"`, `"as_geojson"`, `"as_text"` |
| `pycopg/spatial.py` | Modified | `SpatialAccessor` + `AsyncSpatialAccessor`: 8-10 new methods + `as_mvt` |
| `pycopg/spatial.py` | Unchanged | `_VALID_INTO` stays `("rows", "gdf")` — no new values |
| `pycopg/queries.py` | Possibly minor | SQL constants for MVT composition if inline gets complex |
| All other files | Unchanged | No changes to base.py, database.py, async_database.py |

No new modules. `AsyncSpatialAccessor` mirrors every new method.
The existing `_check_postgis()` / `_run()` infrastructure is reused identically.

---

## 2. Transaction Control: Isolation Level and Savepoints

### Psycopg3 API (verified via live inspection)

```python
psycopg.IsolationLevel  # IntEnum: READ_UNCOMMITTED(1), READ_COMMITTED(2),
                        #          REPEATABLE_READ(3), SERIALIZABLE(4)
conn.set_isolation_level(value: IsolationLevel | None)  # connection-level setter
conn.transaction(savepoint_name: str | None = None, force_rollback: bool = False)
```

Isolation level is a **connection-level** setting applied before any statement executes.
Savepoints are nested transactions managed by `conn.transaction(savepoint_name=...)`.

### Placement: flat transactional core only

Both features belong on `Database.transaction()` / `AsyncDatabase.transaction()` — NOT on
any accessor. They are transaction scoping concerns.

**Current `Database.transaction()` signature:**
```python
@contextmanager
def transaction(self) -> Iterator[psycopg.Connection]:
```

**Proposed extension:**
```python
@contextmanager
def transaction(
    self,
    isolation_level: psycopg.IsolationLevel | None = None,
    savepoint_name: str | None = None,
) -> Iterator[psycopg.Connection]:
```

**Sync implementation logic:**
```python
if self._session_conn is not None:
    # savepoint on existing session connection (isolation_level ignored — already set)
    with self._session_conn.transaction(savepoint_name=savepoint_name):
        yield self._session_conn
else:
    conn = self._connect_with_retry()
    if isolation_level is not None:
        conn.set_isolation_level(isolation_level)
    try:
        with conn.transaction(savepoint_name=savepoint_name):
            yield conn
    finally:
        conn.close()
```

Note: `isolation_level` in session mode is a no-op (the connection already exists and may
have had prior statements). Raise `ValueError` if caller passes `isolation_level` while in
session mode — fail loudly rather than silently ignoring it.

**Session-mode isolation level:** Add `isolation_level` to `session()` as well:
```python
@contextmanager
def session(
    self,
    autocommit: bool = False,
    isolation_level: psycopg.IsolationLevel | None = None,
) -> Iterator[Database]:
    conn = psycopg.connect(**self.config.connect_params(), autocommit=autocommit)
    if isolation_level is not None:
        conn.set_isolation_level(isolation_level)
    self._session_conn = conn
    ...  # existing finally logic unchanged
```

**ETL autocommit isolation seam:** The ETL accessor opens its own dedicated
`connect(autocommit=True)` connection for run-log writes, fully bypassing `_session_conn`.
This seam is unaffected — no changes needed in `pycopg/etl.py`.

**Sync/async parity:** `AsyncDatabase.transaction()` gains the same two parameters.
`psycopg.AsyncConnection` exposes `set_isolation_level()` and
`conn.transaction(savepoint_name=...)` identically. The async implementation is a direct
`await` mirror. `AsyncDatabase.session()` gains `isolation_level` the same way.

**`DatabaseBase` changes:** None. `DatabaseBase` holds `config` only. Isolation level and
savepoints are execution-time concerns handled in `Database` / `AsyncDatabase` only.

---

## 3. Named Params, Health Checks, Structured Logging

### Named params: flat transactional core

**Placement:** `Database.execute()` / `AsyncDatabase.execute()` — type widening only.

Psycopg3 already supports `%(name)s`-style placeholders when `params` is a `dict`.
The feature translates `:name` markers (user-facing ergonomic syntax) to `%(name)s`:

```python
# pycopg/utils.py — new pure helper, no I/O
import re

def _rewrite_named_params(sql: str, params: dict) -> tuple[str, dict]:
    """Rewrite :name markers to %(name)s for psycopg dict-params."""
    out = re.sub(r':([A-Za-z_][A-Za-z0-9_]*)', r'%(\1)s', sql)
    return out, params
```

`execute()` signature widening:
```python
def execute(
    self,
    sql: str,
    params: Sequence | dict | None = None,
    autocommit: bool = False,
) -> list[dict]:
    if isinstance(params, dict):
        sql, params = _rewrite_named_params(sql, params)
    ...  # existing cursor logic
```

This is NOT a `QueryMixin` builder — it is a low-level SQL-string preprocessor in
`pycopg/utils.py`. Every method that calls `cur.execute()` via `execute()` benefits.

**Parity:** `AsyncDatabase.execute()` gains the same `params: Sequence | dict | None` type.
Same `_rewrite_named_params` helper from `utils.py` is shared (it is pure/sync, safe to
call in both paths).

**Note:** `_to_named_binds` in `spatial.py` rewrites `%s` → `:pN` for SQLAlchemy `text()`.
Named params for `execute()` do the opposite (`:name` → `%(name)s` for psycopg). These are
separate concerns and must not share implementation.

### Health checks: flat transactional core

**Placement:** `db.health()` as a flat method on `Database` / `AsyncDatabase` — NOT an accessor.
Health checks are a connection/instance concern, not domain-specific.

```python
def health(self) -> dict:
    """Check database connection health.

    Returns
    -------
    dict
        Keys: "connected" (bool), "latency_ms" (float), "server_version" (str).

    Raises
    ------
    ConnectionError
        If the connection check fails.
    """
    import time
    t0 = time.perf_counter()
    result = self.execute("SELECT version()")
    latency = (time.perf_counter() - t0) * 1000
    return {
        "connected": True,
        "latency_ms": round(latency, 2),
        "server_version": result[0]["version"] if result else "",
    }
```

Uses a fresh connection (not `_session_conn`) when not in session mode — same as regular
`execute()`. Returns `dict` so callers can log/inspect all fields. No new accessor needed.

**Parity:** `AsyncDatabase.health()` is a direct `async def` mirror.

### Structured logging: new cross-cutting module

**Placement:** New `pycopg/logging.py` (new file) — shared by sync and async paths.

The existing `database.py` already uses `logger = logging.getLogger(__name__)`. The goal is
to add structured context (table name, row count, duration) without changing the public API
and without adding a runtime dependency (`structlog` is out — "zero new runtime deps" Core Value).

```python
# pycopg/logging.py
import logging
import time
from contextlib import contextmanager
from typing import Any

def get_logger(name: str) -> logging.Logger:
    """Return a logger under the pycopg hierarchy."""
    return logging.getLogger(f"pycopg.{name}")

@contextmanager
def log_operation(logger: logging.Logger, operation: str, **context: Any):
    """Log start/end/error of an operation with structured context dict."""
    t0 = time.perf_counter()
    logger.debug("start", extra={"operation": operation, **context})
    try:
        yield
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        logger.debug("done", extra={"operation": operation, "elapsed_ms": elapsed_ms, **context})
    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        logger.warning(
            "error",
            extra={"operation": operation, "error": str(exc), "elapsed_ms": elapsed_ms, **context},
        )
        raise
```

Integration via `with log_operation(...)` wrappers in key methods — zero public API change.
Target wrap points: `execute`, `from_dataframe`, `insert_batch`, `copy_insert`.

Users configure structured log handlers on Python's standard `logging` module.

**Parity:** The same `logging.py` is shared by sync and async paths.
The `@contextmanager` version works in both (it yields synchronously; the async body runs
between enter and exit).

---

## 4. API Freeze and Homogenization

### Return-shape conventions

The existing return-shape landscape is already largely coherent:
- `execute()`, `fetch_all()`: `list[dict]`
- `fetch_one()`: `dict | None`
- `fetch_val()`: `Any`
- `spatial.*` with `into="rows"`: `list[dict]`
- `spatial.*` with `into="gdf"`: `gpd.GeoDataFrame`
- `timescale.time_bucket()` with `into="df"`: `pd.DataFrame`

New spatial v2 methods must be consistent from day one:
- `spatial.aggregate.*` → `list[dict]` always (ungrouped or grouped)
- `spatial.as_mvt()` → `bytes` always (no `into=`)
- `spatial.as_geojson()`, `spatial.as_text()` → `list[dict]` via `into="rows"` only

### `into=` parameter conventions across accessors

Two distinct `_VALID_INTO` sets exist intentionally:
- `spatial.py`: `("rows", "gdf")` — GeoDataFrame for geometry results
- `timescale.py`: `("df", "rows")` — pandas DataFrame for time-series results

These are correct and should not be merged — they reflect genuine semantic differences.
What needs documenting: the API reference must explicitly explain `into="gdf"` (GeoDataFrame)
vs `into="df"` (pandas DataFrame) so users understand the distinction.

### The `where=` naming collision — critical seam

| Method family | `where=` type | Semantics |
|--------------|--------------|----------|
| `db.spatial.*` (all 11 current helpers) | `str \| None` | Raw SQL fragment appended by `_append_tail` |
| `db.delete_where`, `db.update_where`, `db.exists`, `db.count`, `db.paginate` | `dict \| None` | Dict of equality conditions via `_build_where_dict` |

These are two different features sharing the same parameter name across different surfaces.

**Recommended resolution (Option B — rename spatial `where=` to `filter=`):**

Given that breaking changes are explicitly allowed in v1.0.0 (last window before API freeze)
and this is the most consequential consistency seam, rename spatial `where=` → `filter=` on
all 11 existing spatial helpers, plus all new spatial v2 helpers. Serve via `DeprecationWarning`
aliases + MIGRATION entry (same pattern as v0.6→v0.7 alias removal).

After the rename:
- `where=` always means dict-of-equality conditions (CRUD helpers)
- `filter=` always means raw SQL fragment (spatial/timescale raw filter)

The 11 current spatial methods must all change simultaneously in the homogenization phase.
New spatial v2 builders must use `filter=` from day one.

**Alternative (Option A — no rename):** Keep both as-is, document the distinction. Lower
cost but leaves a permanent inconsistency in the frozen 1.0 API. Not recommended given the
"last window" framing.

### Exception-naming homogenization (N818)

Current hierarchy (from `exceptions.py`):
```
PycopgError
├── ConnectionError        # builtin name conflict (lower priority)
├── ConfigurationError     # consistent
├── ExtensionNotAvailable  # N818: not Error-suffixed
├── TableNotFound          # N818: not Error-suffixed
├── InvalidIdentifier      # N818: not Error-suffixed
├── MigrationError         # consistent
├── DatabaseExists         # N818: not Error-suffixed
├── TimescaleError         # consistent
├── ETLError               # consistent
├── ETLTransformError      # consistent
└── ETLTargetNotFoundError # consistent
```

N818 violations (ruff rule: exception class names should end in Error):
- `ExtensionNotAvailable` → `ExtensionNotAvailableError`
- `TableNotFound` → `TableNotFoundError`
- `InvalidIdentifier` → `InvalidIdentifierError`
- `DatabaseExists` → `DatabaseExistsError`

All four appear in user-facing `__all__`, docs, and `except` clauses in user code.
Serve via `DeprecationWarning` aliases in `exceptions.py` + MIGRATION entry.

`ConnectionError` conflicts with the Python builtin. Options: rename to
`DatabaseConnectionError` or keep as-is. Defer this rename — the current name shadows the
builtin only inside pycopg's own namespace, not globally. Mypy-strict may or may not flag it.

### Build order recommendation

Dependency chain drives this order:

```
Phase A: Homogenization pass (FIRST)
  ├── Exception renames (add old names as DeprecationWarning aliases)
  ├── Spatial where= → filter= (add where= as DeprecationWarning alias on all 11 methods)
  ├── into= documentation pass (no code change, doc only)
  └── Any other cosmetic seams (return-type annotations, docstring updates for ruff)

Phase B: Spatial v2 (SECOND)
  ├── New spatial builders: column-only processing shape (simplify, convex_hull, make_valid,
  │   difference, intersection) — all use filter= from day one
  ├── New spatial builders: aggregate shape (union_agg, collect, extent)
  ├── New spatial builders: serialization (as_geojson, as_text, as_mvt)
  └── Sync + async parity (SpatialAccessor + AsyncSpatialAccessor)

Phase C: API completeness gaps (THIRD)
  ├── transaction(isolation_level=, savepoint_name=) — sync + async
  ├── session(isolation_level=) — sync + async
  ├── Named params: _rewrite_named_params in utils.py + execute() type widening
  └── db.health() — sync + async

Phase D: Structured logging (FOURTH)
  └── pycopg/logging.py + log_operation wrappers in key methods

Phase E: mypy strict + py.typed (LAST)
  ├── Flip mypy to blocking in CI (remove continue-on-error)
  ├── Complete py.typed (all public signatures annotated)
  └── Fix any remaining type errors from phases A-D
```

**Why this order:**

1. Homogenization BEFORE spatial v2: new spatial builders must use the renamed `filter=`
   parameter from day one. Building Spatial v2 first and then renaming means an immediate
   double-rename on new code.

2. Homogenization BEFORE mypy-strict: renaming `ExtensionNotAvailable` to
   `ExtensionNotAvailableError` changes `except` clauses and type annotations across the
   codebase (~30+ sites). Doing it before strict means fixing annotations once, not twice.

3. Spatial v2 BEFORE transaction control: spatial v2 is purely additive to an existing
   accessor. Transaction control touches the flat core's existing method signatures.
   Stabilize the accessor surface before modifying the core seam.

4. Logging BEFORE mypy-strict: `log_operation` wrappers introduce new `extra={}` dict
   arguments that may require type annotations that mypy-strict will flag.

5. mypy-strict LAST: it freezes the type surface. All renaming, parameter additions, and
   annotation work must be complete before the gate is raised to blocking.

---

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     Public API Surface                       │
├─────────────────────────────────────────────────────────────┤
│  Flat Transactional Core (database.py / async_database.py)   │
│  execute(params: Sequence|dict) / session(isolation_level=)  │
│  transaction(isolation_level=, savepoint_name=) / health()   │
│  insert_batch / copy_insert / upsert / fetch_one / paginate  │
│  (ALL v0.9.0 flat CRUD helpers — unchanged)                  │
├──────────────────────────────────────────────────────────────┤
│  Accessor Namespace (lazy, cached properties on Database)    │
│  ┌──────────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │
│  │  spatial     │ │  schema  │ │timescale │ │   etl    │   │
│  │  (v2 +11    │ │  (32     │ │  (15     │ │  (incr.  │   │
│  │   methods)  │ │  methods)│ │  methods)│ │  ETL)    │   │
│  └──────────────┘ └──────────┘ └──────────┘ └──────────┘   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                     │
│  │  admin   │ │  maint   │ │  backup  │                     │
│  └──────────┘ └──────────┘ └──────────┘                     │
├──────────────────────────────────────────────────────────────┤
│  Builder Layer (pure functions, no I/O, shared sync/async)   │
│  spatial.py builders / base.py QueryMixin / timescale.py    │
│  NEW: _rewrite_named_params (utils.py)                      │
│  NEW: build_simplify_sql / build_aggregate_sql / etc.       │
├──────────────────────────────────────────────────────────────┤
│  Cross-cutting                                               │
│  logging.py (NEW) / exceptions.py (renamed) / utils.py      │
│  config.py / queries.py (minor additions)                    │
└──────────────────────────────────────────────────────────────┘
```

### New vs. modified components — complete map

| Component | Status | Nature of change |
|-----------|--------|-----------------|
| `pycopg/spatial.py` | Modified | 8-10 new `build_*_sql` builders; 8-10 new accessor methods + `as_mvt`; `_SCALAR_HELPERS` extended |
| `pycopg/database.py` | Modified | `transaction()` gains `isolation_level`, `savepoint_name`; `session()` gains `isolation_level`; `execute()` params type widened; `health()` added |
| `pycopg/async_database.py` | Modified | Mirror of all database.py changes (parity) |
| `pycopg/exceptions.py` | Modified | 4 renames with old names as `DeprecationWarning` aliases |
| `pycopg/utils.py` | Modified | `_rewrite_named_params()` added |
| `pycopg/logging.py` | New file | `get_logger()` + `log_operation()` context manager |
| `pycopg/base.py` | Unchanged | `DatabaseBase` / `QueryMixin` have no transaction or isolation seam |
| `pycopg/queries.py` | Minor | SQL constants for MVT/aggregate queries if inline gets complex |
| All other accessors | Unchanged | admin, maint, backup, schema, timescale, etl |

---

## Sync/Async Parity Seams

Every new surface must be mirrored. Explicit callouts per feature:

| New feature | Sync seam | Async seam | Parity gotcha |
|-------------|-----------|------------|---------------|
| Spatial v2 builders | `SpatialAccessor` methods | `AsyncSpatialAccessor` methods | `await self._check_postgis()` at top of each async method |
| `as_mvt()` | `SpatialAccessor.as_mvt()` returns `bytes` | `AsyncSpatialAccessor.as_mvt()` awaits `execute()` | PostGIS guard must `await` |
| `transaction(isolation_level=)` | `Database.transaction()` calls `conn.set_isolation_level()` | `AsyncDatabase.transaction()` calls `await conn.set_isolation_level()` (check if async API needs await) |
| `session(isolation_level=)` | `Database.session()` | `AsyncDatabase.session()` | Same sync/async divergence |
| Named params | `Database.execute()` | `AsyncDatabase.execute()` | Same `_rewrite_named_params` util (pure function) |
| `health()` | `Database.health()` | `AsyncDatabase.health()` | Async version uses `await execute("SELECT version()")` |
| Structured logging | Sync method wrappers | Async method wrappers | `@contextmanager` `log_operation` works in both |
| Exception renames | `exceptions.py` aliases | Shared module | No duplication — single module |

The `ACCESSOR_PAIRS` registry in `tests/test_parity.py` must be updated for any new accessor
methods on `SpatialAccessor`. New flat-core methods (`health`, expanded `transaction`,
expanded `session`) need parity assertions added to `test_accessor_parity` or a new
`test_flat_core_parity` test module.

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Adding isolation_level state to DatabaseBase

`DatabaseBase` holds only `config`. Lifting isolation-level state to the shared base class
would require mutable execution-time state on a shared infrastructure class. Keep isolation
level as a call-time parameter passed to `transaction()` / `session()`.

### Anti-Pattern 2: New accessor for transaction control

Transaction control is a core connection concern, not a domain. Creating `db.tx.*` or
`db.control.*` violates the established rule: transactional core stays flat.

### Anti-Pattern 3: Making ST_AsMVT use `into="mvt"`

Adding "mvt" to `_VALID_INTO` forces `_run()` to handle bytes, changes `_check_into()`
for every helper, and adds a return-type branch to the dispatch path. A dedicated method
returning bytes unconditionally is simpler and more discoverable for users.

### Anti-Pattern 4: Sharing `_to_named_binds` from spatial.py for named params

The spatial `_to_named_binds` rewrites `%s` → `:pN` for SQLAlchemy `text()`.
Named params for `execute()` do the opposite (`:name` → `%(name)s` for psycopg).
These are separate concerns with inverse transformation directions.

### Anti-Pattern 5: Homogenization after mypy-strict

Renaming exceptions or spatial `where=` → `filter=` after mypy-strict is raised means every
annotation update must also pass the strict gate simultaneously. Do all renames first, then
raise the gate.

### Anti-Pattern 6: Structured logging via an external dependency

`structlog` or similar adds a runtime dependency (violates "zero new runtime dependencies"
Core Value). Use stdlib `logging` with `extra={}` dict. Log handlers in user code can emit
JSON or structured formats from stdlib `logging.Formatter`.

### Anti-Pattern 7: Spatial v2 builders using `where=` instead of `filter=`

If the homogenization phase (spatial `where=` → `filter=`) runs first, all new Spatial v2
builders must use `filter=` from day one. Writing Spatial v2 builders with `where=` creates
an immediate debt that requires immediate fixing.

---

## Sources

- Direct code inspection: `pycopg/spatial.py` (2832 lines, full read) — builder patterns,
  `_resolve_geometry`, `_SCALAR_HELPERS`, `_VALID_INTO`, `_check_into`, `_run`, `_to_named_binds`,
  `SpatialAccessor`, `AsyncSpatialAccessor`
- Direct code inspection: `pycopg/base.py` (581 lines, full read) — `DatabaseBase`, `QueryMixin`,
  `_build_where_dict`, `SessionMixin`
- Direct code inspection: `pycopg/database.py` (partial read) — `transaction()`, `session()`,
  `execute()`, `cursor()`, `connect()`, lazy accessor properties
- Direct code inspection: `pycopg/async_database.py` (session/transaction mirror confirmed)
- Direct code inspection: `pycopg/exceptions.py` (76 lines, full read) — complete hierarchy
- Direct code inspection: `.planning/PROJECT.md` — architecture history, locked decisions,
  v1.0.0 scope, Core Value constraint
- Live psycopg3 inspection: `psycopg.IsolationLevel` enum values confirmed,
  `Connection.transaction(savepoint_name=)` signature confirmed,
  `Connection.set_isolation_level()` signature confirmed,
  `psycopg_pool.ConnectionPool.check()` / `get_stats()` confirmed

---
*Architecture research for: pycopg v1.0.0 "Spatial v2 + API freeze"*
*Researched: 2026-06-27*
