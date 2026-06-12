# Phase 14: Spatial helpers (Phase 8 réalisée) - Pattern Map

**Mapped:** 2026-06-12
**Files analyzed:** 6 new/modified files
**Analogs found:** 6 / 6

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `pycopg/spatial.py` | service + utility | request-response | `pycopg/base.py` (builders + `_build_select_sql`) | exact |
| `pycopg/database.py` | service | request-response | `pycopg/async_database.py:80-89` (lazy `async_engine` property) | exact |
| `pycopg/async_database.py` | service | request-response | `pycopg/async_database.py:80-89` (lazy `async_engine` property) | exact |
| `pycopg/__init__.py` | config | — | `pycopg/__init__.py:1-60` (existing export block) | exact |
| `tests/test_spatial.py` | test | request-response | `tests/test_base.py` (DB-free) + `tests/test_postgis_errors.py` (integration) | exact |
| `.planning/phases/08-spatial-helpers/08-DESIGN.md` | docs | — | N/A (manual update task) | N/A |

---

## Pattern Assignments

### `pycopg/spatial.py` (service + utility, request-response)

**Analogs:**
- Pure builder functions: `pycopg/base.py:232-310` (`build_pg_dump_cmd`, `build_pg_restore_cmd`)
- SELECT builder convention: `pycopg/base.py:158-208` (`_build_select_sql`)
- PostGIS guard call site: `pycopg/database.py:1456-1460` (`from_geodataframe` guard)

**Module-level pure builder pattern** (`pycopg/base.py:232-246`):
```python
def build_pg_dump_cmd(
    host: str,
    port: int,
    user: str,
    database: str,
    output_file,
    format: str = "custom",
    schema_only: bool = False,
    data_only: bool = False,
    tables: list | None = None,
    exclude_tables: list | None = None,
    schemas: list | None = None,
    compress: int = 6,
    jobs: int = 1,
) -> list:
    """Build a pg_dump command argv list.

    Constructs the argument list for invoking pg_dump. Pure function: no
    I/O, no environment access, no secrets. The caller runs the command
    and manages credentials via environment variables.

    Parameters
    ----------
    host : str
        Database host.
    ...
    """
```
Copy this structural signature style (numpydoc summary + Parameters/Returns/Raises, no Examples) for every builder in `spatial.py`.

**`_build_select_sql` columns/where/order_by/limit pattern** (`pycopg/base.py:158-208`):
```python
@staticmethod
def _build_select_sql(
    table: str,
    columns: list[str] | None = None,
    schema: str = "public",
    where: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> str:
    validate_identifiers(table, schema)
    if columns:
        validate_identifiers(*columns)

    cols_str = ", ".join(columns) if columns else "*"
    sql = f"SELECT {cols_str} FROM {schema}.{table}"

    if where:
        sql += f" WHERE {where}"
    if order_by:
        sql += f" ORDER BY {order_by}"
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    if offset is not None:
        sql += f" OFFSET {int(offset)}"

    return sql
```
Each spatial builder that accepts `columns=`, `where=`, `order_by=`, `limit=` copies this verbatim pattern: validate identifiers first, `cols_str = ", ".join(columns) if columns else "*"`, then append clauses. Spatial builders replace the single `WHERE {where}` with `WHERE {spatial_cond} [AND ({where})]`.

**PostGIS guard call site pattern** (`pycopg/database.py:1456-1460`):
```python
if not self.has_extension("postgis"):
    raise ExtensionNotAvailable(
        "PostGIS extension not installed. Run db.create_extension('postgis')"
    )
```
`SpatialAccessor.__init__` copies this exact guard and error message. `AsyncSpatialAccessor` uses a lazy `_postgis_ok: bool = False` flag checked at the start of each async method (because `__init__` cannot `await`).

**Identifier validation pattern** (`pycopg/utils.py:76-91` + `pycopg/base.py:141`):
```python
validate_identifiers(table, schema, *columns)
```
Each spatial builder calls `validate_identifiers(table, schema, geom_col)` as its first line, then `validate_identifiers(*columns)` if `columns` is provided. Values (coordinates, WKT, GeoJSON, distance) always go through `%s` — never f-string interpolated.

**`to_geodataframe` delegation target** (`pycopg/database.py:1498-1539`):
```python
def to_geodataframe(
    self,
    table: str | None = None,
    schema: str = "public",
    sql: str | None = None,
    geometry_column: str = "geometry",
    params: dict | None = None,
) -> gpd.GeoDataFrame:
    ...
    return gpd.read_postgis(
        text(sql), self.engine, geom_col=geometry_column, params=params
    )
```
The `into="gdf"` path in each accessor method calls `self._db.to_geodataframe(sql=sql, params=params, geometry_column=geom)`. The builder returns `(sql, params)` as a tuple; the accessor unpacks them for this call. Scalar helpers (`area`, `perimeter`, `distance`, `centroid`) raise `ValueError` before reaching this call if `into="gdf"` is requested.

---

### `pycopg/database.py` — lazy `spatial` property addition (controller, request-response)

**Analog:** `pycopg/async_database.py:80-89` (lazy `async_engine` property)

**Lazy property pattern** (`pycopg/async_database.py:80-89`):
```python
# In __init__:
self._async_engine: AsyncEngine | None = None

# Property:
@property
def async_engine(self) -> AsyncEngine:
    """Get or create async SQLAlchemy engine (lazy initialization)."""
    if self._async_engine is None:
        from sqlalchemy.ext.asyncio import create_async_engine

        self._async_engine = create_async_engine(self.config.async_url)
    return self._async_engine
```

Copy this pattern to `database.py`:
1. In `Database.__init__`: add `self._spatial: "SpatialAccessor | None" = None`
2. Add property:
```python
@property
def spatial(self) -> "SpatialAccessor":
    """Lazy accessor for spatial helpers."""
    if self._spatial is None:
        from pycopg.spatial import SpatialAccessor
        self._spatial = SpatialAccessor(self)
    return self._spatial
```
Use a deferred import inside the property body (not at module top level) to avoid circular imports. Same pattern as the `from sqlalchemy.ext.asyncio import ...` deferred import in `async_engine`.

---

### `pycopg/async_database.py` — lazy `spatial` property addition (controller, request-response)

**Analog:** Same lazy property pattern as above (`pycopg/async_database.py:80-89`)

```python
# In AsyncDatabase.__init__:
self._spatial: "AsyncSpatialAccessor | None" = None

# Property:
@property
def spatial(self) -> "AsyncSpatialAccessor":
    """Lazy accessor for async spatial helpers."""
    if self._spatial is None:
        from pycopg.spatial import AsyncSpatialAccessor
        self._spatial = AsyncSpatialAccessor(self)
    return self._spatial
```

Note: `AsyncSpatialAccessor.__init__` cannot call `await self._db.has_extension("postgis")`. The PostGIS guard is deferred to first method call via `self._postgis_ok: bool = False` flag — each async helper checks `if not self._postgis_ok: await self._check_postgis()` at entry.

---

### `pycopg/__init__.py` — export addition (config)

**Analog:** `pycopg/__init__.py:1-60` (existing export block)

**Current export block** (`pycopg/__init__.py:7-27`):
```python
from pycopg.async_database import AsyncDatabase
from pycopg.config import Config
from pycopg.database import Database
from pycopg.exceptions import (
    ConfigurationError,
    ConnectionError,
    DatabaseExists,
    ExtensionNotAvailable,
    InvalidIdentifier,
    MigrationError,
    PycopgError,
    TableNotFound,
)
from pycopg.migrations import Migrator
from pycopg.pool import AsyncPooledDatabase, PooledDatabase
from pycopg.utils import (
    validate_identifier,
    validate_identifiers,
    validate_index_method,
    validate_interval,
)
```
Add to this block:
```python
from pycopg.spatial import AsyncSpatialAccessor, SpatialAccessor
```
And add `"SpatialAccessor"` and `"AsyncSpatialAccessor"` to `__all__`. Follow the existing alphabetical grouping — `spatial` imports go between `pool` and `utils` imports, or as a new grouped section after `migrations`. Use the numpydoc-free import style (no extra comments needed).

---

### `tests/test_spatial.py` (test, request-response)

**Analogs:**
- DB-free builder tests: `tests/test_base.py:221-340` (`TestBuildPgDumpCmd`)
- Integration tests: `tests/test_postgis_errors.py:23-100` (`TestPostGISErrorHandling`)
- Parity mechanism: `tests/test_parity.py:13-52` (`TestAsyncParity`)

**DB-free parametrized test pattern** (`tests/test_base.py:221-300`):
```python
class TestBuildPgDumpCmd:
    """DB-free unit tests for build_pg_dump_cmd (pure argv builder)."""

    def test_leading_connection_args(self):
        """Leading argv is pg_dump + connection params."""
        cmd = build_pg_dump_cmd(**_CONN, output_file="out.dump")
        assert cmd[:9] == ["pg_dump", "-h", "h", ...]

    @pytest.mark.parametrize(
        "fmt,flag",
        [("plain", "p"), ("custom", "c"), ("directory", "d"), ("tar", "t")],
    )
    def test_format_maps_to_format_flag(self, fmt, flag):
        """Each format value maps to its -F flag."""
        cmd = build_pg_dump_cmd(**_CONN, output_file="out", format=fmt)
        assert "-F" in cmd
        assert cmd[cmd.index("-F") + 1] == flag
```
Copy this structure for `TestBuilders` and `TestGeometryResolver`. Each test method has a one-line docstring (not numpydoc — test docstrings are plain). Use `@pytest.mark.parametrize` for exhaustive branch coverage (point/wkt/geojson/ref forms, unit="m"/unit="srid", with/without `where=`/`columns=`).

**Integration test with temp table pattern** (`tests/test_postgis_errors.py:26-51`):
```python
def test_create_spatial_index_without_geometry_column(self, db_config):
    """Test create_spatial_index with non-geometry column produces error."""
    db = Database(db_config)
    table_name = "test_spatial_index_non_geom"
    try:
        db.execute(f"CREATE TEMP TABLE {table_name} (id INTEGER, name TEXT)")
        with pytest.raises(Exception) as exc_info:
            db.create_spatial_index(table_name, "name")
        error_msg = str(exc_info.value).lower()
        assert len(error_msg) > 0
    finally:
        try:
            db.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")
        except:
            pass
```
Copy the `try/finally` fixture cleanup pattern for each `TestIntegration` method. Use `CREATE TEMP TABLE` with minimal geometry data (e.g., `INSERT ... SELECT ST_GeomFromText('POINT(0 0)', 4326)`). The `db_config` fixture is already in `conftest.py` — no new fixtures needed.

**Async integration test pattern** (from `test_parity.py` + existing async tests):
For `TestIntegration` async methods, `asyncio_mode = auto` is set in `pyproject.toml` — just declare `async def test_...` inside the class; no `@pytest.mark.asyncio` decorator needed.

---

## Shared Patterns

### Identifier Validation
**Source:** `pycopg/utils.py:76-91` + `pycopg/base.py:141,192-194`
**Apply to:** Every builder function in `spatial.py`
```python
from pycopg.utils import validate_identifiers

# At the top of every builder:
validate_identifiers(table, schema, geom_col)
if columns:
    validate_identifiers(*columns)
```

### PostGIS Guard (Sync)
**Source:** `pycopg/database.py:1456-1460`
**Apply to:** `SpatialAccessor.__init__`
```python
from pycopg.exceptions import ExtensionNotAvailable

if not db.has_extension("postgis"):
    raise ExtensionNotAvailable(
        "PostGIS extension not installed. Run db.create_extension('postgis')"
    )
```

### PostGIS Guard (Async, lazy flag)
**Source:** Pattern from RESEARCH.md §Pattern 4 (no direct codebase analog exists yet)
**Apply to:** Every method in `AsyncSpatialAccessor`
```python
# In __init__:
self._postgis_ok: bool = False

# In each async method, as first line:
if not self._postgis_ok:
    if not await self._db.has_extension("postgis"):
        raise ExtensionNotAvailable(
            "PostGIS extension not installed. Run db.create_extension('postgis')"
        )
    self._postgis_ok = True
```

### Numpydoc Shallow Docstrings (Phase 13 requirement)
**Source:** `pycopg/base.py:247-290` (`build_pg_dump_cmd` docstring)
**Apply to:** All public classes and methods in `spatial.py`
```
Summary line.

Parameters
----------
param : type
    Description.

Returns
-------
type
    Description.

Raises
------
ExceptionType
    When raised.
```
No `Examples` section (shallow convention). Module docstring required. Class docstring required.

### Pure Builder Return Convention
**Source:** `pycopg/base.py:_build_insert_sql` (returns `(sql, params)` tuple)
**Apply to:** All spatial builders
```python
def build_contains_sql(...) -> tuple[str, list]:
    ...
    return sql, params
```
Return type is always `tuple[str, list]`. The params list is built up incrementally as geometry resolver params are prepended to any additional value params.

### `%s` Parameterization — No f-string for Values
**Source:** `pycopg/base.py:148-155` (`_build_insert_sql` placeholders)
**Apply to:** All geometry values, distances, SRID (via `int(srid)` cast only), buffer distances
```python
# Correct: SRID as int literal (safe), coordinate as %s
f"ST_SetSRID(ST_MakePoint(%s, %s), {int(srid)})"
params = [x, y]

# Never:
f"ST_SetSRID(ST_MakePoint({x}, {y}), {srid})"  # WRONG
```

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `.planning/phases/08-spatial-helpers/08-DESIGN.md` update | docs | N/A | Pure documentation update task; no code analog applies |

---

## Metadata

**Analog search scope:** `pycopg/`, `tests/`
**Files scanned:** `base.py`, `utils.py`, `database.py`, `async_database.py`, `__init__.py`, `exceptions.py`, `tests/test_base.py`, `tests/test_parity.py`, `tests/test_postgis_errors.py`
**Pattern extraction date:** 2026-06-12
