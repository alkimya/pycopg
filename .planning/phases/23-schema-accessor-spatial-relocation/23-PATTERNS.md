# Phase 23: Schema Accessor & Spatial Relocation — Pattern Map

**Mapped:** 2026-06-17
**Files analyzed:** 8 (2 new + 6 modified)
**Analogs found:** 8 / 8

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `pycopg/schema.py` | accessor module (new) | request-response (CRUD delegation) | `pycopg/admin.py` | exact |
| `pycopg/database.py` | db wiring (modify) | request-response | `pycopg/database.py` timescale/admin property block | exact |
| `pycopg/async_database.py` | db wiring (modify) | request-response | `pycopg/async_database.py` timescale/admin property block | exact |
| `pycopg/spatial.py` | existing-accessor edit (modify) | request-response | `pycopg/spatial.py` SpatialAccessor/AsyncSpatialAccessor | exact |
| `pycopg/__init__.py` | package export (modify) | — | `pycopg/__init__.py` AdminAccessor/AsyncAdminAccessor block | exact |
| `tests/test_schema_aliases.py` | new test (DB-free alias) | — | `tests/test_timescale_aliases.py` | exact |
| `tests/test_parity.py` | test registry (modify) | — | `tests/test_parity.py` ACCESSOR_PAIRS list | exact |
| `tests/test_spatial.py` or `tests/test_spatial_aliases.py` | test edit / new test | — | `tests/test_timescale_aliases.py` alias section | role-match |

---

## Pattern Assignments

### `pycopg/schema.py` (new accessor module, request-response)

**Analog:** `pycopg/admin.py`

**Module docstring + imports pattern** (admin.py lines 1-31):
```python
"""Schema accessor classes for db.schema.* / async_db.schema.*.

This module provides :class:`SchemaAccessor` and
:class:`AsyncSchemaAccessor` — the real implementation of the 27
DDL + introspection helper methods, moved verbatim from
``Database`` / ``AsyncDatabase`` as part of the v0.6.0 accessor
reorganisation (D-06).

Both classes are exposed on the parent database via a lazy-cached
``schema`` property added in plan 02.  The flat ``db.*`` names remain
as thin deprecated aliases (see :mod:`pycopg.aliases`) until v0.7.0.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import psycopg

from pycopg import queries
from pycopg.utils import (
    validate_identifier,
    validate_identifiers,
    validate_extension_name,
    validate_index_method,
)

if TYPE_CHECKING:
    from pycopg.async_database import AsyncDatabase
    from pycopg.database import Database
```

Note: `validate_extension_name` and `validate_index_method` are used by the schema bodies (checked via RESEARCH.md self.X inventory). Import only what the 27 bodies actually call. `psycopg` is required for the 3 database-level methods (`create_database`, `drop_database`, `database_exists`) that open an admin connection directly.

**Class constructor pattern** (admin.py lines 33-49):
```python
class SchemaAccessor:
    """Schema helper namespace exposed as ``db.schema``."""

    def __init__(self, db: Database) -> None:
        """Store the parent database reference.

        Parameters
        ----------
        db : Database
            Parent database instance.  Stored as ``self._db``; no
            connection check is performed at construction time.
        """
        self._db = db
```

**Simple `self._db.execute(...)` method pattern** (extrapolate from admin.py method shape):
```python
def list_tables(self, schema: str = "public") -> list[str]:
    """List tables in a schema.

    Parameters
    ----------
    schema : str, optional
        Schema name, by default "public".

    Returns
    -------
    list of str
        Table names.
    """
    result = self._db.execute(queries.LIST_TABLES, [schema])
    return [r["table_name"] for r in result]
```

**`self._db.config` method pattern** — for `create_database`, `drop_database`, `database_exists` (database.py lines 840-863, rewritten from `self.config` → `self._db.config`):
```python
def create_database(
    self, name: str, owner: str | None = None, template: str = "template1"
) -> None:
    """Create a new database.

    Parameters
    ----------
    name : str
        Database name.
    owner : str, optional
        Owner role.
    template : str, optional
        Template database, by default "template1".
    """
    validate_identifier(name)
    if owner:
        validate_identifier(owner)
    validate_identifier(template)
    owner_clause = f" OWNER {owner}" if owner else ""
    # NOTE: self.config → self._db.config (D-04 rewrite)
    admin_config = self._db.config.with_database("postgres")
    with psycopg.connect(**admin_config.connect_params(), autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE {name}{owner_clause} TEMPLATE {template}")
```

**AsyncSchemaAccessor pattern** — mirrors sync exactly, methods use `await self._db.execute(...)`. No constructor guard (schema has no extension guard unlike spatial). Same `__init__(self, db: AsyncDatabase)` shape.

---

### `pycopg/database.py` (db wiring — add `_schema` cache field + `schema` lazy property + 29 stubs)

**Analog:** `pycopg/database.py` existing `_timescale`/`_admin`/`_maint`/`_backup` fields and properties

**Cache field addition** (database.py lines 83-86, add `_schema` alongside):
```python
# In Database.__init__, alongside existing cache fields:
self._spatial: SpatialAccessor | None = None
self._etl: ETLAccessor | None = None
self._timescale: TimescaleAccessor | None = None
self._admin: AdminAccessor | None = None
self._maint: MaintAccessor | None = None
self._backup: BackupAccessor | None = None
# ADD:
self._schema: SchemaAccessor | None = None
```

**Lazy property pattern** (database.py lines 273-290, replicate for `schema`):
```python
@property
def timescale(self) -> TimescaleAccessor:
    """Get or create the TimescaleDB accessor (lazy initialization).

    Provides access to TimescaleDB operations such as hypertable
    management, compression, and retention policies.  The accessor
    is created on first access and cached for subsequent calls.

    Returns
    -------
    TimescaleAccessor
        TimescaleDB helper namespace bound to this database.
    """
    if self._timescale is None:
        from pycopg.timescale import TimescaleAccessor

        self._timescale = TimescaleAccessor(self)
    return self._timescale
```

Replication for `schema`:
```python
@property
def schema(self) -> SchemaAccessor:
    """Get or create the schema accessor (lazy initialization).

    Provides access to DDL and introspection operations.  The accessor
    is created on first access and cached for subsequent calls.

    Returns
    -------
    SchemaAccessor
        Schema helper namespace bound to this database.
    """
    if self._schema is None:
        from pycopg.schema import SchemaAccessor

        self._schema = SchemaAccessor(self)
    return self._schema
```

**`@deprecated_alias` stub pattern** (database.py lines 1724-1726 and surrounding stubs):
```python
@deprecated_alias("timescale.create_hypertable")
def create_hypertable(self, *args, **kwargs):
    """Deprecated: use ``db.timescale.create_hypertable`` instead."""
```

Applied to schema methods (one per each of 27):
```python
@deprecated_alias("schema.create_database")
def create_database(self, *args, **kwargs):
    """Deprecated: use ``db.schema.create_database`` instead."""

@deprecated_alias("schema.list_tables")
def list_tables(self, *args, **kwargs):
    """Deprecated: use ``db.schema.list_tables`` instead."""

# ... 25 more, same shape ...
```

Applied to the 2 spatial-relocation stubs:
```python
@deprecated_alias("spatial.create_spatial_index")
def create_spatial_index(self, *args, **kwargs):
    """Deprecated: use ``db.spatial.create_spatial_index`` instead."""

@deprecated_alias("spatial.list_geometry_columns")
def list_geometry_columns(self, *args, **kwargs):
    """Deprecated: use ``db.spatial.list_geometry_columns`` instead."""
```

**Stay-flat call-site rewrites** (D-05 — must happen in the same wave as stubs):

Sync `database.py`:
- Line 1503: `self.add_primary_key(...)` → `self.schema.add_primary_key(...)`
- Line 1583: `self.has_extension("postgis")` → `self.schema.has_extension("postgis")`
- Line 1619: `self.add_primary_key(...)` → `self.schema.add_primary_key(...)`
- Line 1622: `self.create_spatial_index(...)` → `self.spatial.create_spatial_index(...)`

---

### `pycopg/async_database.py` (db wiring — mirror of database.py changes)

**Analog:** `pycopg/async_database.py` existing `_timescale`/`_admin`/`_maint`/`_backup` fields (lines 80-84) and `spatial` property (lines 95-109).

**Cache field addition** (async_database.py lines 80-84, add alongside):
```python
self._etl: AsyncETLAccessor | None = None
self._timescale: AsyncTimescaleAccessor | None = None
self._admin: AsyncAdminAccessor | None = None
self._maint: AsyncMaintAccessor | None = None
self._backup: AsyncBackupAccessor | None = None
# ADD:
self._schema: AsyncSchemaAccessor | None = None
```

**Lazy property pattern** (async_database.py lines 95-109, replicate for `schema`):
```python
@property
def spatial(self) -> AsyncSpatialAccessor:
    """Get or create the async spatial accessor (lazy initialization)..."""
    if self._spatial is None:
        from pycopg.spatial import AsyncSpatialAccessor
        self._spatial = AsyncSpatialAccessor(self)
    return self._spatial
```

Same shape for `schema` (no guard since SchemaAccessor has no PostGIS requirement).

**Async `@deprecated_alias` stubs** — identical shape to sync stubs; `@deprecated_alias` branches sync/async automatically via `iscoroutinefunction` in `pycopg/aliases.py`. The stub form is the same `(*args, **kwargs)` generic signature.

**Async stay-flat call-site rewrites** (D-05):
- Line 1479: `await self.add_primary_key(...)` → `await self.schema.add_primary_key(...)`
- Line 1568: `await self.has_extension("postgis")` → `await self.schema.has_extension("postgis")`
- Line 1607: `await self.add_primary_key(...)` → `await self.schema.add_primary_key(...)`
- Line 1610: `await self.create_spatial_index(...)` → `await self.spatial.create_spatial_index(...)`

---

### `pycopg/spatial.py` (existing-accessor edit — add 2 relocated methods)

**Analog:** `pycopg/spatial.py` `SpatialAccessor` (line 1023) / `AsyncSpatialAccessor` (line 1859)

**SpatialAccessor constructor guard** (spatial.py lines 1033-1048) — the 2 relocated methods inherit this automatically; no extra code:
```python
def __init__(self, db: Database) -> None:
    """Initialize the accessor and verify PostGIS availability."""
    self._db = db
    if not db.has_extension("postgis"):
        raise ExtensionNotAvailable(_POSTGIS_GUARD_MSG)
```

**AsyncSpatialAccessor deferred guard** (spatial.py lines 1868-1890) — the 2 relocated async methods MUST call `await self._check_postgis()` as their first line (all other async spatial methods do so):
```python
def __init__(self, db: AsyncDatabase) -> None:
    self._db = db
    self._postgis_ok: bool = False

async def _check_postgis(self) -> None:
    if not self._postgis_ok:
        if not await self._db.has_extension("postgis"):
            raise ExtensionNotAvailable(_POSTGIS_GUARD_MSG)
        self._postgis_ok = True
```

**Verbatim move + rewrite pattern** (database.py lines 1671-1718, rewritten `self.execute` → `self._db.execute`):

Sync placement — add after the last existing `SpatialAccessor` method, before `class AsyncSpatialAccessor`:
```python
def create_spatial_index(
    self,
    table: str,
    column: str = "geometry",
    schema: str = "public",
    name: str | None = None,
) -> None:
    """Create a GIST spatial index on a geometry column.

    Parameters
    ----------
    table : str
        Table name.
    column : str, optional
        Geometry column name, by default "geometry".
    schema : str, optional
        Schema name, by default "public".
    name : str, optional
        Index name (auto-generated if not provided).
    """
    validate_identifiers(table, column, schema)
    if name:
        validate_identifier(name)
    index_name = name or f"idx_{table}_{column}_gist"
    # NOTE: self.execute → self._db.execute (D-04 rewrite)
    self._db.execute(f"""
        CREATE INDEX IF NOT EXISTS {index_name}
        ON {schema}.{table} USING GIST ({column})
    """)

def list_geometry_columns(self, schema: str | None = None) -> list[dict]:
    """List geometry columns in the database.

    Parameters
    ----------
    schema : str, optional
        Schema filter.

    Returns
    -------
    list of dict
        List of geometry column info.
    """
    where_clause = "WHERE f_table_schema = %s" if schema else ""
    params = [schema] if schema else None
    # NOTE: self.execute → self._db.execute (D-04 rewrite)
    return self._db.execute(
        queries.LIST_GEOMETRY_COLUMNS.format(where_clause=where_clause),
        params,
    )
```

Async placement — add analogous methods to `AsyncSpatialAccessor`, PREPENDING `await self._check_postgis()`:
```python
async def create_spatial_index(
    self,
    table: str,
    column: str = "geometry",
    schema: str = "public",
    name: str | None = None,
) -> None:
    """...(same docstring)..."""
    await self._check_postgis()  # REQUIRED — deferred guard (D-06 + RESEARCH finding #4)
    validate_identifiers(table, column, schema)
    if name:
        validate_identifier(name)
    index_name = name or f"idx_{table}_{column}_gist"
    await self._db.execute(f"""
        CREATE INDEX IF NOT EXISTS {index_name}
        ON {schema}.{table} USING GIST ({column})
    """)

async def list_geometry_columns(self, schema: str | None = None) -> list[dict]:
    """...(same docstring)..."""
    await self._check_postgis()  # REQUIRED
    where_clause = "WHERE f_table_schema = %s" if schema else ""
    params = [schema] if schema else None
    return await self._db.execute(
        queries.LIST_GEOMETRY_COLUMNS.format(where_clause=where_clause),
        params,
    )
```

**Do NOT use `_run()`** — these 2 methods call `self._db.execute` directly (D-07: move verbatim, no builder/`_run` conformance).

---

### `pycopg/__init__.py` (package export — add SchemaAccessor/AsyncSchemaAccessor)

**Analog:** `pycopg/__init__.py` AdminAccessor/AsyncAdminAccessor block (lines 7 and 66-67)

**Import line pattern** (line 7):
```python
from pycopg.admin import AdminAccessor, AsyncAdminAccessor
```

Add:
```python
from pycopg.schema import AsyncSchemaAccessor, SchemaAccessor
```

**`__all__` entry pattern** (lines 65-68):
```python
    # Admin
    "AdminAccessor",
    "AsyncAdminAccessor",
```

Add (place after Backup block, before Exceptions, or alongside the spatial/admin cluster):
```python
    # Schema
    "SchemaAccessor",
    "AsyncSchemaAccessor",
```

---

### `tests/test_schema_aliases.py` (new DB-free alias test)

**Analog:** `tests/test_timescale_aliases.py` (lines 1-180, full file)

**File-level structure** (copy from test_timescale_aliases.py):
```python
"""Tests that deprecated flat aliases warn and delegate (REORG-04, D-09).

Asserts that each of the 27 flat ``db.*`` schema aliases:

1. Emits exactly one :class:`DeprecationWarning` with the correct message.
2. Points the warning at the *caller's* file (``stacklevel=2`` proof).
3. Delegates to the corresponding ``db.schema.*`` accessor method with
   identical arguments.

All tests are DB-free: the ``schema`` accessor is replaced by a
:class:`unittest.mock.MagicMock` so no live PostgreSQL connection is needed.
"""

from __future__ import annotations

import os
import warnings
from unittest.mock import AsyncMock, MagicMock

import pytest

from pycopg import AsyncDatabase, Database
from pycopg.schema import AsyncSchemaAccessor, SchemaAccessor

_SYNC_ALIAS_ARGS: dict[str, tuple] = {
    "create_database": ("mydb",),
    "drop_database": ("mydb",),
    "database_exists": ("mydb",),
    "list_databases": (),
    "create_extension": ("postgis",),
    "drop_extension": ("postgis",),
    "list_extensions": (),
    "has_extension": ("postgis",),
    "create_schema": ("myschema",),
    "drop_schema": ("myschema",),
    "list_schemas": (),
    "schema_exists": ("myschema",),
    "list_tables": (),
    "table_exists": ("users",),
    "list_columns": ("users",),
    "columns_with_types": ("users",),
    "drop_table": ("users",),
    "truncate_table": ("users",),
    "table_info": ("users",),
    "row_count": ("users",),
    "add_primary_key": ("users", "id"),
    "add_foreign_key": ("orders", "user_id", "users", "id"),
    "add_unique_constraint": ("users", ["email"]),
    "create_index": ("users", ["email"]),
    "drop_index": ("idx_users_email",),
    "list_indexes": ("users",),
    "list_constraints": ("users",),
}
# _ASYNC_ALIAS_ARGS is identical to _SYNC_ALIAS_ARGS
```

**Sync test method** (test_timescale_aliases.py lines 55-115):
```python
class TestSchemaAliases:
    @pytest.mark.parametrize("name", list(_SYNC_ALIAS_ARGS.keys()))
    def test_sync_alias_warns_and_delegates(self, name, config):
        """..."""
        db = Database(config)
        mock_accessor = MagicMock(spec=SchemaAccessor)
        db._schema = mock_accessor  # inject into cache field

        args = _SYNC_ALIAS_ARGS[name]

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            getattr(db, name)(*args)

        alias_warnings = [
            rec
            for rec in w
            if rec.category is DeprecationWarning
            and f"db.schema.{name}" in str(rec.message)
        ]
        assert len(alias_warnings) == 1, ...
        rec = alias_warnings[0]
        msg_str = str(rec.message)
        assert f"db.schema.{name}" in msg_str
        assert "v0.7.0" in msg_str

        # stacklevel=2: warning must point at this test file
        basename = os.path.basename(rec.filename)
        assert "test_" in basename
        assert basename != "aliases.py"
        assert basename != "database.py"

        getattr(mock_accessor, name).assert_called_once_with(*args)
```

**Async test method** (test_timescale_aliases.py lines 121-179):
```python
    @pytest.mark.parametrize("name", list(_ASYNC_ALIAS_ARGS.keys()))
    @pytest.mark.asyncio
    async def test_async_alias_warns_and_delegates(self, name, config):
        """..."""
        db = AsyncDatabase(config)
        mock_accessor = MagicMock(spec=AsyncSchemaAccessor)
        for method_name in _ASYNC_ALIAS_ARGS:
            setattr(mock_accessor, method_name, AsyncMock())
        db._schema = mock_accessor  # inject into cache field

        args = _ASYNC_ALIAS_ARGS[name]

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            await getattr(db, name)(*args)

        alias_warnings = [
            rec
            for rec in w
            if rec.category is DeprecationWarning
            and f"db.schema.{name}" in str(rec.message)
        ]
        assert len(alias_warnings) == 1, ...
        rec = alias_warnings[0]
        msg_str = str(rec.message)
        assert f"db.schema.{name}" in msg_str
        assert "v0.7.0" in msg_str

        async_basename = os.path.basename(rec.filename)
        assert "test_" in async_basename
        assert async_basename != "aliases.py"

        getattr(mock_accessor, name).assert_called_once_with(*args)
```

---

### `tests/test_parity.py` (test registry — append 2 pairs)

**Analog:** `tests/test_parity.py` lines 22-28 (ACCESSOR_PAIRS list)

**Current state** (lines 11-28):
```python
from pycopg.admin import AdminAccessor, AsyncAdminAccessor
from pycopg.backup import AsyncBackupAccessor, BackupAccessor
from pycopg.etl import AsyncETLAccessor, ETLAccessor
from pycopg.maint import AsyncMaintAccessor, MaintAccessor
from pycopg.timescale import AsyncTimescaleAccessor, TimescaleAccessor

ACCESSOR_PAIRS = [
    (TimescaleAccessor, AsyncTimescaleAccessor),
    (ETLAccessor, AsyncETLAccessor),
    (AdminAccessor, AsyncAdminAccessor),
    (MaintAccessor, AsyncMaintAccessor),
    (BackupAccessor, AsyncBackupAccessor),
]
```

**Required additions** (schema-track plan adds SchemaAccessor; spatial-relocation plan adds SpatialAccessor):

Import additions:
```python
from pycopg.schema import AsyncSchemaAccessor, SchemaAccessor
from pycopg.spatial import AsyncSpatialAccessor, SpatialAccessor
```

ACCESSOR_PAIRS additions (append both tuples):
```python
ACCESSOR_PAIRS = [
    (TimescaleAccessor, AsyncTimescaleAccessor),
    (ETLAccessor, AsyncETLAccessor),
    (AdminAccessor, AsyncAdminAccessor),
    (MaintAccessor, AsyncMaintAccessor),
    (BackupAccessor, AsyncBackupAccessor),
    (SchemaAccessor, AsyncSchemaAccessor),       # schema-track plan
    (SpatialAccessor, AsyncSpatialAccessor),     # spatial-relocation plan (NOT pre-existing — RESEARCH finding #3)
]
```

**Critical note:** `SpatialAccessor` is NOT currently in ACCESSOR_PAIRS (RESEARCH finding #3 — CONTEXT.md claim was wrong). The spatial-relocation plan must add it; the schema-track plan must NOT assume it is there.

---

### `tests/test_spatial_aliases.py` (new test — 2 spatial alias tests)

**Decision:** Create a new `tests/test_spatial_aliases.py` (separate from `tests/test_spatial.py`). Rationale: `tests/test_spatial.py` imports builder functions and is DB-free builder tests + PostGIS integration (line 1: "DB-free builder/guard tests + PostGIS integration") — the alias tests have a different purpose and would clutter an already-structured file.

**Analog:** `tests/test_timescale_aliases.py` (same template, 2-method subset)

**Structure:**
```python
"""Tests that deprecated flat spatial aliases warn and delegate (REORG-04, D-09).

Asserts that each of the 2 flat ``db.*`` spatial aliases (create_spatial_index,
list_geometry_columns):

1. Emits exactly one :class:`DeprecationWarning` with the correct message.
2. Points the warning at the *caller's* file (``stacklevel=2`` proof).
3. Delegates to the corresponding ``db.spatial.*`` accessor method.

All tests are DB-free: the ``spatial`` accessor is replaced by a MagicMock.
"""

from __future__ import annotations

import os
import warnings
from unittest.mock import AsyncMock, MagicMock

import pytest

from pycopg import AsyncDatabase, Database
from pycopg.spatial import AsyncSpatialAccessor, SpatialAccessor

_SYNC_ALIAS_ARGS: dict[str, tuple] = {
    "create_spatial_index": ("my_table",),
    "list_geometry_columns": (),
}
_ASYNC_ALIAS_ARGS = _SYNC_ALIAS_ARGS.copy()


class TestSpatialAliases:
    @pytest.mark.parametrize("name", list(_SYNC_ALIAS_ARGS.keys()))
    def test_sync_alias_warns_and_delegates(self, name, config):
        db = Database(config)
        mock_accessor = MagicMock(spec=SpatialAccessor)
        db._spatial = mock_accessor  # inject — bypasses PostGIS guard

        args = _SYNC_ALIAS_ARGS[name]
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            getattr(db, name)(*args)

        alias_warnings = [
            rec for rec in w
            if rec.category is DeprecationWarning
            and f"db.spatial.{name}" in str(rec.message)
        ]
        assert len(alias_warnings) == 1
        rec = alias_warnings[0]
        assert f"db.spatial.{name}" in str(rec.message)
        assert "v0.7.0" in str(rec.message)
        basename = os.path.basename(rec.filename)
        assert "test_" in basename
        assert basename != "aliases.py"
        assert basename != "database.py"
        getattr(mock_accessor, name).assert_called_once_with(*args)

    @pytest.mark.parametrize("name", list(_ASYNC_ALIAS_ARGS.keys()))
    @pytest.mark.asyncio
    async def test_async_alias_warns_and_delegates(self, name, config):
        db = AsyncDatabase(config)
        mock_accessor = MagicMock(spec=AsyncSpatialAccessor)
        for method_name in _ASYNC_ALIAS_ARGS:
            setattr(mock_accessor, method_name, AsyncMock())
        db._spatial = mock_accessor  # inject — bypasses deferred guard

        args = _ASYNC_ALIAS_ARGS[name]
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            await getattr(db, name)(*args)

        alias_warnings = [
            rec for rec in w
            if rec.category is DeprecationWarning
            and f"db.spatial.{name}" in str(rec.message)
        ]
        assert len(alias_warnings) == 1
        rec = alias_warnings[0]
        assert f"db.spatial.{name}" in str(rec.message)
        assert "v0.7.0" in str(rec.message)
        async_basename = os.path.basename(rec.filename)
        assert "test_" in async_basename
        assert async_basename != "aliases.py"
        getattr(mock_accessor, name).assert_called_once_with(*args)
```

---

## Shared Patterns

### `@deprecated_alias` decorator
**Source:** `pycopg/aliases.py`
**Apply to:** All 29 stubs in `database.py` and `async_database.py` (27 schema + 2 spatial)
**Usage:** `@deprecated_alias("schema.<method>")` or `@deprecated_alias("spatial.<method>")` — the decorator handles sync/async branching via `iscoroutinefunction`, lazy accessor resolution via `getattr(self, accessor_name)`, and `stacklevel=2`. **Reuse verbatim — zero changes to `aliases.py`.**

### Lazy-cached property idiom
**Source:** `pycopg/database.py` lines 273-290 (`timescale` property) / `pycopg/async_database.py` lines 95-109 (`spatial` property)
**Apply to:** `schema` property in both `database.py` and `async_database.py`
**Shape:** `if self._<name> is None: from pycopg.<name> import <Class>; self._<name> = <Class>(self); return self._<name>`

### DB-free MagicMock alias test structure
**Source:** `tests/test_timescale_aliases.py` lines 1-180
**Apply to:** `tests/test_schema_aliases.py` (27 methods), `tests/test_spatial_aliases.py` (2 methods)
**Key points:**
- Inject mock into cache field (`db._schema = mock_accessor`) to bypass lazy construction
- Use `warnings.catch_warnings(record=True)` + `warnings.simplefilter("always")`
- Filter warnings by `rec.category is DeprecationWarning and f"db.<accessor>.<name>" in str(rec.message)` — do not assert on raw `len(w)`, as other DeprecationWarnings may leak
- Assert `"v0.7.0"` in message
- Assert `"test_"` in `os.path.basename(rec.filename)` (stacklevel=2 proof)
- Assert `getattr(mock_accessor, name).assert_called_once_with(*args)` (delegation proof)
- Async path: wrap each mock method with `AsyncMock()` before injecting

### numpydoc docstring shape
**Source:** `pycopg/admin.py` lines 51-80 (any method with full docstring)
**Apply to:** All methods in `SchemaAccessor`/`AsyncSchemaAccessor` (moved bodies keep their existing docstrings; no docstring rewrite needed since they are verbatim moves)
**Shape:** Parameters / Returns sections; no Examples section; `interrogate ≥ 95` is enforced.

---

## No Analog Found

None — all files have direct codebase analogs.

---

## Critical Notes for Planner

1. **D-04 self.X rewrite map** (from RESEARCH.md verified AST scan):
   - `self.config` → `self._db.config` in 3 methods only: `create_database`, `drop_database`, `database_exists` (sync + async)
   - `self.execute(...)` → `self._db.execute(...)` in all remaining 26 schema methods + 2 spatial methods

2. **D-05 stay-flat call-site rewrites** — 8 exact sites (4 sync + 4 async) must be rewritten atomically with Wave 2 stubs. Listed above under `database.py` and `async_database.py` sections.

3. **Spatial ACCESSOR_PAIRS gap** — `(SpatialAccessor, AsyncSpatialAccessor)` is NOT in `ACCESSOR_PAIRS` today (RESEARCH finding #3). The spatial-relocation plan must add it. The comment at test_parity.py line 19 says "Phases 22-24 APPEND here".

4. **AsyncSpatialAccessor `_check_postgis()`** — must be added as first line of both async relocated methods (RESEARCH finding #4). The sync path is guarded at `__init__` (line 1047); the async path requires explicit per-method calls matching all other async spatial methods.

5. **Wave sync discipline** — sync + async stubs for both `database.py` and `async_database.py` must land in the same commit to avoid `TestAsyncParity` failures (RESEARCH pitfall #5).

---

## Metadata

**Analog search scope:** `pycopg/admin.py`, `pycopg/maint.py`, `pycopg/backup.py`, `pycopg/timescale.py`, `pycopg/spatial.py`, `pycopg/database.py`, `pycopg/async_database.py`, `pycopg/__init__.py`, `tests/test_timescale_aliases.py`, `tests/test_parity.py`, `tests/test_spatial.py`
**Files scanned:** 11
**Pattern extraction date:** 2026-06-17
