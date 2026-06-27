# Technology Stack — v1.0.0 Spatial v2 + API Freeze

**Project:** pycopg v1.0.0 — Spatial v2 + API freeze
**Researched:** 2026-06-27
**Scope:** Stack additions and version floors needed for Spatial v2 (ST_Union/Simplify/ConvexHull/MakeValid/Difference/Intersection + aggregates ST_Union(agg)/Collect/Extent + serialization ST_AsGeoJSON/AsText/AsMVT), 4 API-backlog gaps (isolation level + savepoints, named params, health checks, structured logging), and the API freeze mechanics (mypy strict blocking, py.typed completeness, SemVer policy).
**Confidence:** HIGH — verified against psycopg3 Context7 docs (authoritative), official PostGIS docs (postgis.net), mypy 2.1.0 docs, and PyPI package pages.

---

## Verdict: Zero New Runtime Dependencies Required

All v1.0.0 features are buildable on the existing runtime stack. **No additions to the
`[project.dependencies]` table in `pyproject.toml` are needed.**

The three dev-group additions below are all dev/CI tooling:

- `pandas-stubs` — dev-only, enables mypy strict on DataFrame-touching code
- `types-geopandas` — dev-only, enables mypy strict on GeoDataFrame-touching code
- `types-shapely` — dev-only, enables mypy strict on shapely geometry objects

The structured-logging answer is definitively stdlib-only (see section below).

---

## Existing Runtime Stack (Do Not Change)

| Technology | Current Floor | Latest Stable | Role in v1.0.0 |
| ---------- | ------------- | ------------- | --------------- |
| Python | 3.11+ | 3.13 | Language; no change |
| psycopg | >=3.1.0 | 3.3.4 | PostgreSQL driver; isolation, savepoints, health checks all native |
| psycopg_pool | >=3.2.0 | 3.3.1 | Pool health check API (pool.check(), get_stats()) |
| pandas | >=2.0.0 | — | DataFrame path; 2.1+ ships py.typed natively |
| geopandas | >=0.14.0 | 1.1.3 | GeoDataFrame path; no new capabilities needed |
| shapely | >=2.0.0 | 2.1.* | Geometry objects; no new capabilities needed |
| tenacity | >=9.0.0 | — | Retry/backoff; no change |

**PostgreSQL server floor:** 12 (implied by PostGIS 3.0 requirement — see section below).

**PostGIS server floor:** 3.0 (see section below — critical for ST_AsMVT and ST_MakeValid options).

---

## New Dev-Group Additions (Typing Only)

These go in `[dependency-groups] dev = [...]` in `pyproject.toml`. They are never
installed by end users; they exist solely to make `mypy --strict` run clean in CI.

| Package | Version Floor | Purpose | Why This Package |
| ------- | ------------- | ------- | ---------------- |
| `pandas-stubs` | `>=2.0.0` | Type stubs for pandas DataFrame/Series API | pandas 2.1+ ships py.typed but stubs provide better coverage under strict mode; `pandas-stubs==3.0.3.*` is current (Jun 2026) |
| `types-geopandas` | `>=0.14.0` | Type stubs for geopandas GeoDataFrame | From typeshed; latest `1.1.3.20260518` targets geopandas 1.1.3; covers `>=0.14` paths we use |
| `types-shapely` | `>=2.0.0` | Type stubs for shapely geometry objects | From typeshed; latest targets shapely 2.1.*; covers all geometry type annotations |

Without them, `mypy --strict` on any module that imports `pandas`, `geopandas`, or
`shapely` raises `Cannot find implementation or library stub` or infers `Any` for return
types, violating `--disallow-any-generics` and `--warn-return-any` (both enabled by
`--strict`). The current `pyproject.toml` silences these errors via
`[[tool.mypy.overrides]] ignore_missing_imports = true` — that workaround must be replaced
with real stubs to achieve strict mode.

Installation:

```bash
uv add --dev pandas-stubs types-geopandas types-shapely
```

---

## 1. PostGIS Version Floor

Verdict: Document PostGIS >= 3.0 as the hard floor; recommend >= 3.2 for full feature set.

### Function-by-function analysis (confirmed against postgis.net official docs)

| Function | Available Since | Notes |
| -------- | --------------- | ----- |
| `ST_Simplify` | PostGIS 1.x | Core function; no version concern |
| `ST_ConvexHull` | PostGIS 1.x | Core function; no version concern |
| `ST_Difference` | PostGIS 1.x | Core function; gridSize param requires GEOS 3.9 (PostGIS 3.1+) |
| `ST_Intersection` | PostGIS 1.x | Core function; gridSize param requires GEOS 3.9 (PostGIS 3.1+) |
| `ST_Union (binary)` | PostGIS 1.x | Core function; gridSize param requires GEOS 3.9 (PostGIS 3.1+) |
| `ST_Union (aggregate)` | PostGIS 1.4.0 | Standard SQL aggregate; no version concern |
| `ST_Collect (aggregate)` | PostGIS 1.4.0 | Standard aggregate; no version concern |
| `ST_Extent (aggregate)` | PostGIS 1.x | Returns box2d; added polyhedra support in 2.0 |
| `ST_AsGeoJSON` | PostGIS 1.3.4 | `maxdecimaldigits` available since 1.3.4; `id_column` added in 3.5.0 |
| `ST_AsText` | PostGIS 1.x | Core function; no version concern |
| `ST_AsMVT` | **PostGIS 2.4.0** | Feature ID support in 3.0; parallel query in 2.5; Wagyu mandatory for MVT in 3.2+ |
| `ST_MakeValid` | PostGIS 2.0.0 | linework algorithm (default) since 2.0; `method=structure` option requires **PostGIS 3.2 + GEOS 3.10** |

### Hard floor: PostGIS >= 3.0

Rationale:

- ST_AsMVT is the highest-floor function at 2.4, but PostGIS 3.0 improved ST_AsMVT feature IDs, removed SFCGAL dependency for ST_Union, and set PostgreSQL 12 as minimum (which is itself a sensible floor).
- PostGIS 3.0 with PostgreSQL 12 is old enough (released 2019) that virtually all production environments are at or above it.
- PostGIS 3.0 dropped GEOS < 3.6, so GEOS 3.6+ is guaranteed at this floor.

### Recommended floor: PostGIS >= 3.2 (document separately in Spatial v2 docs)

Rationale:

- PostGIS 3.2 enables `ST_MakeValid(geom, 'method=structure')` which is 2.7x faster and provides semantically better repairs for complex geometries. This is the variant worth exposing as a parameter option.
- PostGIS 3.2 requires GEOS 3.10, which also makes ST_IsValid 30-100% faster.
- PostGIS 3.2 drops GEOS < 3.6 and Proj < 4.9 — a cleaner minimum for any new geometry work.
- PostGIS 3.2 was released December 2021 and is now the baseline for most cloud providers (AWS RDS, GCP CloudSQL, Supabase all offer 3.x by default).

### Implementation approach

- Document the hard floor as PostGIS 3.0 (existing `has_extension('postgis')` guard covers this; no version introspection needed).
- For `ST_MakeValid`, expose `method` as a parameter (`"linework"` default, `"structure"` optional), and note in the docstring that `method="structure"` requires PostGIS >= 3.2 with GEOS >= 3.10. Do NOT runtime-gate it — let PostgreSQL surface the error; a documentation warning is sufficient (same approach as TimescaleDB 2.13 for `add_dimension`).
- For `ST_AsMVT`, document PostGIS >= 3.0 as the minimum in the docstring (feature IDs require 3.0; the function itself works from 2.4 but that is below our floor).

---

## 2. psycopg3 Native APIs for the 4 API-Backlog Gaps

### 2a. Transaction Isolation Levels

Verdict: Fully native in psycopg3 — use `psycopg.IsolationLevel` enum and `conn.isolation_level`.

psycopg3 ships `psycopg.IsolationLevel` as an enum with values:

- `READ_UNCOMMITTED`
- `READ_COMMITTED`
- `REPEATABLE_READ`
- `SERIALIZABLE`

Setting isolation at the connection level:

```python
# sync
conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
# or via method:
conn.set_isolation_level(psycopg.IsolationLevel.SERIALIZABLE)

# async
await conn.set_isolation_level(psycopg.IsolationLevel.SERIALIZABLE)
```

Additional connection transaction properties (all native, no extra deps):

- `conn.read_only` — bool or None (None = server default)
- `conn.deferrable` — bool or None

These properties can only be changed when no transaction is currently active. They affect
all subsequent transactions on the connection. They do NOT affect autocommit sessions (use
`SET default_transaction_isolation = ...` GUC for those).

**pycopg integration:** Expose via a `db.set_isolation_level(level)` method (or
`db.session(isolation_level=...)` parameter extension). The `IsolationLevel` enum should be
re-exported from `pycopg` public API so callers never need to import psycopg directly.

**Confidence:** HIGH — verified via Context7 psycopg3 docs.

### 2b. Savepoints / Nested Transactions

Verdict: Fully native in psycopg3 — `conn.transaction()` nesting automatically uses SAVEPOINTs.

psycopg3's `Connection.transaction()` is a context manager. When called inside an
already-open transaction, it automatically issues `SAVEPOINT` (not a new `BEGIN`):

```python
with conn.transaction():          # BEGIN
    do_work()
    with conn.transaction():      # SAVEPOINT sp1
        risky_work()              # RELEASE SAVEPOINT sp1 on success
                                  # ROLLBACK TO SAVEPOINT sp1 on exception
    do_more_work()
# COMMIT
```

Named savepoints:

```python
with conn.transaction(savepoint_name="my_sp") as tx:
    ...
```

Force rollback (useful for testing):

```python
with conn.transaction(force_rollback=True):
    ...
```

Inside a `transaction()` block, `conn.commit()` and `conn.rollback()` cannot be called
directly — they raise an error. The context manager owns the transaction lifecycle.

**pycopg integration:** The existing `db.session()` context manager wraps
`conn.transaction()`. Savepoint support is already available to callers who nest
`db.session()` calls. The gap to close is: (1) documenting this clearly, and (2)
potentially exposing `savepoint_name` pass-through if callers need named savepoints.
No new infrastructure is needed.

**Confidence:** HIGH — verified via Context7 psycopg3 docs with code examples.

### 2c. Named Parameters

Verdict: psycopg3 does NOT support `:name` natively — use `%(name)s` dict-style instead.

psycopg3 supports two parameter styles:

1. **Positional:** `%s` with a list/tuple — the project's existing convention.
2. **Named (dict-style):** `%(name)s` with a dict — fully supported natively.

```python
cur.execute(
    "SELECT * FROM users WHERE id = %(user_id)s AND active = %(active)s",
    {"user_id": 42, "active": True}
)
```

The `:name` syntax (used by SQLAlchemy `text()`, ODBC drivers) is NOT psycopg3's native
format. The existing `_to_named_binds()` function in `spatial.py` converts `%s` to
`:p0, :p1, ...` for SQLAlchemy's `text()` path — that adapter is the right pattern for
the SQLAlchemy integration layer.

What "named params" means for pycopg v1.0.0: the backlog item is about exposing
`db.execute(sql, params={"name": value})` as a documented, stable API. The underlying
psycopg3 mechanism is `%(name)s` dict-style, which already works. The implementation gap:

- Ensuring `db.execute()` and `db.fetch_one()` / `db.fetch_all()` clearly accept `dict` params.
- Documenting the `%(name)s` convention in user-facing docs.
- No `:name` translation layer is needed or appropriate.

**Confidence:** HIGH — verified via Context7 psycopg3 docs (multiple examples shown).

### 2d. Connection / Pool Health Checks

Verdict: Fully native in psycopg3 and psycopg_pool — no new deps.

Three layers of health checking are available natively.

**Layer 1 — Individual connection attributes:**

```python
conn.closed   # True if explicitly closed
conn.broken   # True if interrupted unexpectedly (also sets closed=True)
```

**Layer 2 — Pool-level health sweep (psycopg_pool >= 3.2):**

```python
pool.check()           # sync: tests each connection, replaces broken ones
await pool.acheck()    # async equivalent
```

Returns None; broken connections are replaced transparently.

**Layer 3 — Per-checkout connection validation (psycopg_pool >= 3.2):**

```python
with ConnectionPool(..., check=ConnectionPool.check_connection) as pool:
    ...
```

`ConnectionPool.check_connection` is a built-in static method that runs `SELECT 1`
before handing a connection to a caller. Adds approximately 1 network RTT per acquisition.

**Layer 4 — Pool statistics (monitoring/health dashboard):**

```python
stats = pool.get_stats()   # dict with pool_min, pool_max, pool_available, etc.
stats = pool.pop_stats()   # same but resets counters
```

**pycopg integration:** Expose via `db.health_check()` and `async_db.health_check()` methods
that: (a) call `pool.check()` to sweep the pool, (b) fetch `pool.get_stats()` and return
a structured dict, (c) optionally run `SELECT 1` to confirm DB connectivity.
No new infrastructure or dependencies needed — all of this is in the existing
`psycopg_pool >= 3.2.0` floor.

**Confidence:** HIGH — verified via Context7 psycopg3 docs and PyPI psycopg_pool 3.3.1 confirmed.

---

## 3. mypy Strict Mode for a py.typed Library

### 3a. What --strict Enables (mypy 2.1.0)

`--strict` is a composite flag that enables exactly these 13 individual flags:

| Flag | Effect |
| ---- | ------ |
| `--disallow-any-generics` | Ban `List`, `Dict` etc. without type params |
| `--disallow-subclassing-any` | No subclassing `Any`-typed classes |
| `--disallow-untyped-calls` | No calling untyped functions from typed code |
| `--disallow-untyped-defs` | All function defs must be fully annotated |
| `--disallow-incomplete-defs` | Partial annotations forbidden |
| `--check-untyped-defs` | Type-check bodies of untyped functions too |
| `--disallow-untyped-decorators` | Decorators must be typed |
| `--warn-redundant-casts` | Flag pointless `cast()` calls |
| `--warn-unused-ignores` | Flag stale `# type: ignore` comments |
| `--warn-return-any` | Flag functions that return `Any` |
| `--no-implicit-reexport` | Explicit `__all__` required for re-exports |
| `--strict-equality` | No trivially-false comparisons |
| `--extra-checks` | Additional soundness checks |

The current `pyproject.toml` `[tool.mypy]` config is NOT strict: it has
`disallow_untyped_defs = false` and `check_untyped_defs = true` only, plus
`ignore_missing_imports = false` at global scope with per-module `ignore_missing_imports = true`
overrides for all third-party deps. This must be replaced.

### 3b. Recommended pyproject.toml Config for Strict + py.typed

```toml
[tool.mypy]
python_version = "3.11"
strict = true
warn_unreachable = true          # not in --strict; useful addition

# After installing pandas-stubs, types-geopandas, types-shapely,
# remove the ignore_missing_imports overrides for those modules.
# Keep overrides only for libs that have NO stubs:

[[tool.mypy.overrides]]
module = "sqlalchemy.*"
ignore_missing_imports = true    # SQLAlchemy 2.0 has inline stubs; verify first

[[tool.mypy.overrides]]
module = "psycopg.*"
ignore_missing_imports = true    # psycopg3 ships inline stubs; verify coverage

[[tool.mypy.overrides]]
module = "psycopg_pool.*"
ignore_missing_imports = true    # same

[[tool.mypy.overrides]]
module = "geoalchemy2.*"
ignore_missing_imports = true    # no stubs known; keep

[[tool.mypy.overrides]]
module = "tenacity.*"
ignore_missing_imports = true    # no stubs known; keep
```

Note on psycopg/psycopg_pool stubs: psycopg3 ships inline type annotations and a
`py.typed` marker. With `ignore_missing_imports = false` globally (strict implies this),
mypy will consume psycopg3's native types. Test whether the overrides are still needed
before adding them — they may be unnecessary.

Note on SQLAlchemy: SQLAlchemy 2.0+ ships bundled stubs and a py.typed marker. The
existing override is likely no longer needed with SQLAlchemy >= 2.0.

### 3c. py.typed Completeness Requirements

A `py.typed` marker (already present in the repo) tells mypy to enforce type completeness
on the package's public API. For the freeze to be meaningful:

1. All public functions and methods must have full annotations — no `Any` returns,
   no untyped parameters, no bare `list` or `dict` without type params.
2. `__all__` must be declared in every public module — required by `--no-implicit-reexport`.
3. Overload signatures (`@overload`) must be used wherever a function returns different
   types based on argument combinations (e.g., `into="rows"` -> `list[dict]`,
   `into="gdf"` -> `gpd.GeoDataFrame`). The `spatial.py` accessor methods all have this
   pattern and will fail strict without overloads.
4. `TYPE_CHECKING` imports — third-party types used only in annotations must be under
   `if TYPE_CHECKING:` (already done in `spatial.py` for `gpd`).

The biggest mypy-strict challenge in this codebase: the `into="rows" | "gdf"` return
type pattern throughout `spatial.py` — these all currently return `list[dict] | gpd.GeoDataFrame`
without overloads. Under strict, `--warn-return-any` will fire unless proper `@overload`
stubs are added. This is the most labor-intensive part of the typing work.

**Confidence:** HIGH — verified against mypy 2.1.0 official docs.

### 3d. CI Integration

Change the mypy invocation from non-blocking (current: `continue-on-error: true`) to
blocking. The recommended CI step:

```bash
uv run mypy pycopg --strict
```

This should be a gate (not `continue-on-error`) on the `tests.yml` workflow.

---

## 4. Structured Logging

Verdict: stdlib `logging` with `extra={}` dict fields. Zero new runtime dependency.

The library rule: a PyPI-published library must never pull in a logging framework as a
runtime dependency. The caller (application author) chooses their logging stack. The
library emits events via `logging.getLogger(__name__)` and the caller's handlers format
them.

The approach:

1. Add a module-level logger: `logger = logging.getLogger(__name__)` in each module.
2. Emit structured context via the `extra={}` dict.
3. Add `logging.getLogger("pycopg").addHandler(logging.NullHandler())` to `pycopg/__init__.py`
   (PEP 3148 / Python logging best practice for libraries — suppresses "No handlers" warnings).

Example usage:

```python
logger.debug("ETL run started", extra={"pipeline": pipeline.name, "run_id": run_id})
logger.info("COPY complete", extra={"table": table, "rows": row_count, "duration_ms": ms})
logger.warning("PostGIS guard triggered", extra={"extension": "postgis"})
```

Why not structlog: it adds a runtime dependency for every pycopg user, violating the
project's zero-runtime-dep rule. structlog is an application-layer tool, not a
library-layer tool. The 2025-2026 community consensus is unambiguous: libraries use
stdlib + NullHandler; applications use structlog.

What callers get: if the calling application uses structlog or loguru, the stdlib
`logging` events from pycopg flow through automatically (structlog integrates with stdlib
`logging`). The caller formats them with whatever processor they want.

**Confidence:** HIGH — aligns with Python logging best practices (PEP 3148) and verified
against community consensus in 2025-2026 sources.

---

## 5. SemVer + Deprecation Policy (Freeze Mechanics — No New Tooling)

No new tooling is needed. The freeze mechanics are documentation + process:

- **SemVer policy:** document in `CHANGELOG.md` header and `README.md` that v1.0.0+
  follows SemVer strictly: MAJOR for breaking changes, MINOR for additive (1.x), PATCH
  for bug fixes.
- **Deprecation policy:** document minimum 1 minor-version deprecation cycle before removal
  (e.g., deprecated in 1.1 -> removable in 2.0). The existing `@deprecated_alias` decorator
  mechanism is the implementation vehicle.
- **Exception-name cleanup:** The `N818` ruff ignore in `exceptions.py` (for
  `ExtensionNotAvailable`, `TableNotFound`, `InvalidIdentifier`, `DatabaseExists` — names
  without "Error" suffix) was deferred to v1.0.0 in `pyproject.toml` comments. This is the
  right time to rename them (breaking change, served via deprecation cycle).

---

## Version Compatibility Summary

| Component | Hard Minimum | Recommended | Notes |
| --------- | ------------ | ----------- | ----- |
| Python | 3.11 | 3.11-3.13 | No change |
| PostgreSQL | 12 | 14+ | Implied by PostGIS 3.0 minimum |
| PostGIS | **3.0** | **3.2+** | 3.0 = hard floor (ST_AsMVT feature IDs); 3.2 = `ST_MakeValid method=structure` |
| psycopg | 3.1.0 | 3.3.4 (latest) | IsolationLevel, savepoints, health attrs all present since 3.0 |
| psycopg_pool | 3.2.0 | 3.3.1 (latest) | `pool.check()`, `check_connection`, `get_stats()` all available at floor |
| pandas | 2.0.0 | 2.1+ | 2.1+ ships py.typed; pandas-stubs (dev) for strict coverage |
| geopandas | 0.14.0 | 1.1.3 | types-geopandas (dev) targets 1.1.3 |
| shapely | 2.0.0 | 2.1.* | types-shapely (dev) targets 2.1.* |
| mypy | 2.1.0 | 2.1.0 | Already installed; switch to `strict = true`, blocking |
| pandas-stubs | — | 3.0.3.* | **New dev dep** — enables mypy strict on DataFrame paths |
| types-geopandas | — | 1.1.3.* | **New dev dep** — enables mypy strict on GeoDataFrame paths |
| types-shapely | — | 2.1.*.* | **New dev dep** — enables mypy strict on shapely geometry paths |

---

## What NOT to Add

| Rejected Approach | Reason |
| ----------------- | ------ |
| `structlog` as runtime dep | Library rule: callers own the logging stack; stdlib NullHandler pattern is correct |
| `:name` parameter translation layer | psycopg3 uses `%(name)s` natively; `:name` is SQLAlchemy territory, already handled by `_to_named_binds()` |
| `postgis` Python package / PostGIS ORM | No such thing exists as a stable library; SQL is the interface (same conclusion as TimescaleDB) |
| `shapely` PostGIS geometry translation | Shapely is already in the stack; server-side PostGIS processing is always better than round-trip to Python |
| Version-introspection guard for PostGIS 3.2 `ST_MakeValid` options | Over-engineering; document the floor, let PostgreSQL surface the error |
| `mypy-strict-config` or `pyright` | mypy 2.1.0 already installed; switch to strict mode, do not add a second type checker |
| `geopandas >= 1.0.0` floor bump | Current floor `>= 0.14.0` is fine; types-geopandas targets 1.1.3 but the stubs work for our usage patterns on 0.14+ |
| Any new runtime dep for health checks | psycopg_pool.check() + connection.closed/broken + get_stats() cover all health check needs |

---

## Sources

- psycopg3 IsolationLevel enum, set_isolation_level, transaction(), savepoints, named params, pool check:
  Context7 `/websites/psycopg_psycopg3` and `/psycopg/psycopg`
- psycopg3 latest version 3.3.4: <https://pypi.org/project/psycopg/>
- psycopg_pool latest version 3.3.1: <https://pypi.org/project/psycopg-pool/>
- PostGIS ST_MakeValid — 2.0.0 availability, 3.2.0 structure algorithm, GEOS 3.10 requirement:
  <https://postgis.net/docs/ST_MakeValid.html> and <https://www.crunchydata.com/blog/waiting-for-postgis-3.2-st_makevalid>
- PostGIS ST_AsMVT — 2.4.0 availability, 3.0.0 feature IDs: <https://postgis.net/docs/ST_AsMVT.html>
- PostGIS ST_AsGeoJSON — 1.3.4 availability, maxdecimaldigits parameter: <https://postgis.net/docs/ST_AsGeoJSON.html>
- PostGIS ST_Union — 1.4.0 aggregate form, 3.1.0 gridSize: <https://postgis.net/docs/ST_Union.html>
- PostGIS ST_Collect — 1.4.0 aggregate form: <https://postgis.net/docs/ST_Collect.html>
- PostGIS 3.5.0 release (PostgreSQL 12-17 support): <https://postgis.net/2024/09/PostGIS-3.5.0/>
- mypy 2.1.0 --strict flag list (13 flags): <https://mypy.readthedocs.io/en/stable/command_line.html>
- pandas-stubs latest 3.0.3.260530, pandas 2.1+ py.typed: <https://pypi.org/project/pandas-stubs/>
- types-geopandas 1.1.3.20260518, typeshed provenance: <https://pypi.org/project/types-geopandas/>
- types-shapely (typeshed, targets shapely 2.1.*): <https://pypi.org/project/types-shapely/>
- Structured logging library convention (NullHandler for library code, structlog for apps):
  Python PEP 3148 and 2025-2026 community consensus

---

*Stack research for: pycopg v1.0.0 — Spatial v2 + API freeze*
*Researched: 2026-06-27*
