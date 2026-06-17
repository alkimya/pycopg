# Phase 21: Infrastructure & Timescale Accessor - Pattern Map

**Mapped:** 2026-06-17
**Files analyzed:** 8 (2 new, 6 modified)
**Analogs found:** 8 / 8

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `pycopg/aliases.py` | utility/decorator | request-response | `pycopg/etl.py` (module boilerplate) | role-match (no decorator analog exists) |
| `pycopg/timescale.py` | accessor/service | CRUD | `pycopg/etl.py` (`ETLAccessor`/`AsyncETLAccessor`) | exact |
| `pycopg/database.py` | service | CRUD | `pycopg/database.py` lines 85-86, 253-271 | exact (self-referential edit) |
| `pycopg/async_database.py` | service | CRUD | `pycopg/async_database.py` lines 84-85, 114-131 | exact (self-referential edit) |
| `pycopg/__init__.py` | config | — | `pycopg/__init__.py` lines 26, 40-55 | exact |
| `tests/test_parity.py` | test | — | `tests/test_parity.py:466-503` (`TestEtlParity`) | exact |
| `tests/test_timescale_aliases.py` | test | — | `tests/test_parity.py:466-503` + research pattern | role-match |
| `tests/test_database_integration.py`, `tests/test_async_database.py`, `tests/test_sql_injection.py` | test | — | themselves (call-site migration only) | exact |

---

## Pattern Assignments

### `pycopg/aliases.py` (NEW — utility, decorator)

**Analog:** `pycopg/etl.py` for module boilerplate; no existing decorator module in the codebase.

**Module boilerplate pattern** (`pycopg/etl.py` lines 1-43):
```python
"""ETL pipeline descriptor and pure SQL builders.

This module provides ...
"""

from __future__ import annotations

import asyncio
import traceback
from collections.abc import Callable
# ...
from typing import TYPE_CHECKING

# ...

if TYPE_CHECKING:
    from pycopg.async_database import AsyncDatabase
    from pycopg.database import Database
```

`pycopg/aliases.py` does NOT need `TYPE_CHECKING` imports (no parent class refs). The full verified implementation (from RESEARCH.md `### Pattern 1`):

```python
"""Deprecated alias decorator for the v0.6.0 accessor reorganisation."""

from __future__ import annotations

import functools
import inspect
import warnings


def deprecated_alias(target_path: str):
    """Decorate a flat stub to warn and delegate to an accessor method.

    Parameters
    ----------
    target_path : str
        Dotted path of the form ``"<accessor>.<method>"`` — e.g.
        ``"timescale.create_hypertable"``.  Resolved lazily on ``self``
        at call time so no hard reference is needed at decoration time.

    Returns
    -------
    Callable
        A decorator that replaces the stub with warn-then-delegate logic.
        The wrapper is ``async def`` when the stub is a coroutine function,
        ``def`` otherwise.
    """

    def decorator(fn):
        msg = (
            f"use `db.{target_path}` instead; "
            f"the flat `db.{fn.__name__}` alias is deprecated "
            "and will be removed in v0.7.0"
        )
        accessor_name, method_name = target_path.split(".", 1)

        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapper(self, *args, **kwargs):
                warnings.warn(msg, DeprecationWarning, stacklevel=2)
                accessor = getattr(self, accessor_name)
                return await getattr(accessor, method_name)(*args, **kwargs)
            return async_wrapper
        else:
            @functools.wraps(fn)
            def sync_wrapper(self, *args, **kwargs):
                warnings.warn(msg, DeprecationWarning, stacklevel=2)
                accessor = getattr(self, accessor_name)
                return getattr(accessor, method_name)(*args, **kwargs)
            return sync_wrapper

    return decorator
```

**Key rules verified by research:**
- `stacklevel=2`: warning points at user call site (frame N), not wrapper (frame N+1) or `aliases.py` (frame N+2).
- `async def async_wrapper` (not `def`): preserves `inspect.iscoroutinefunction() == True` on the wrapper.
- `functools.wraps(fn)`: copies `__name__`, `__doc__`, `__qualname__` from stub onto wrapper.
- Circular import is AVOIDED because the decorator resolves the accessor lazily via `getattr(self, accessor_name)` at call time, not at decoration time.

---

### `pycopg/timescale.py` (NEW — accessor, CRUD)

**Analog:** `pycopg/etl.py` (`ETLAccessor` at line 510, `AsyncETLAccessor` at line 1009)

**Module boilerplate** (copy from `pycopg/etl.py` lines 25-43, adapt for timescale):
```python
"""TimescaleDB accessor classes for db.timescale.* / async_db.timescale.*."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pycopg import queries
from pycopg.exceptions import ExtensionNotAvailable
from pycopg.utils import validate_identifier, validate_identifiers, validate_interval

if TYPE_CHECKING:
    from pycopg.async_database import AsyncDatabase
    from pycopg.database import Database
```

Note: `from __future__ import annotations` is needed because `Database`/`AsyncDatabase` are type-annotation-only (under `TYPE_CHECKING`). Follow `etl.py` line 25 pattern.

**`ETLAccessor.__init__` pattern** (`pycopg/etl.py` lines 530-540) — copy exactly for `TimescaleAccessor`:
```python
def __init__(self, db: Database) -> None:
    """Store the parent database reference (D-02).

    Parameters
    ----------
    db : Database
        Parent database instance. Stored as ``self._db``; no
        extension check is performed (ETL run-tracking is core, not
        an extension — D-08).
    """
    self._db = db
```

Note: `TimescaleAccessor.__init__` does NOT guard for `timescaledb` at construction (unlike `SpatialAccessor` which guards for PostGIS at construction, `pycopg/spatial.py` line 1047). The extension guard is inside each method body (consistent with ETL pattern and D-06).

**Extension guard + self._db call pattern** — verbatim from `pycopg/database.py` lines 1681-1697, with `self.` rewritten to `self._db.`:
```python
def create_hypertable(
    self,
    table: str,
    time_column: str,
    schema: str = "public",
    chunk_time_interval: str = "1 day",
    if_not_exists: bool = True,
    migrate_data: bool = True,
) -> None:
    """Convert a table to a TimescaleDB hypertable.
    ...existing numpydoc docstring moved verbatim...
    """
    if not self._db.has_extension("timescaledb"):      # was: self.has_extension(...)
        raise ExtensionNotAvailable(
            "TimescaleDB extension not installed. Run db.create_extension('timescaledb')"
        )

    validate_identifiers(table, schema, time_column)
    validate_interval(chunk_time_interval)

    self._db.execute(f"""                               # was: self.execute(...)
        SELECT create_hypertable(
            '{schema}.{table}',
            '{time_column}',
            chunk_time_interval => INTERVAL '{chunk_time_interval}',
            if_not_exists => {str(if_not_exists).upper()},
            migrate_data => {str(migrate_data).upper()}
        )
    """)
```

Apply the same `self.` → `self._db.` rewrite to all 6 methods. Source lines: `database.py:1648-1869` (sync), `async_database.py:1220-1456` (async).

**`AsyncETLAccessor.__init__` pattern** (`pycopg/etl.py` lines 1032-1042) — copy for `AsyncTimescaleAccessor`:
```python
def __init__(self, db: AsyncDatabase) -> None:
    """Store the parent async database reference.

    Parameters
    ----------
    db : AsyncDatabase
        Parent async database instance.
    """
    self._db = db
```

---

### `pycopg/database.py` (MODIFY — add field, property, replace 6 method bodies)

**`TYPE_CHECKING` block analog** (`pycopg/database.py` lines 54-59):
```python
if TYPE_CHECKING:
    import geopandas as gpd
    import pandas as pd

    from pycopg.etl import ETLAccessor
    from pycopg.spatial import SpatialAccessor
```
Add: `from pycopg.timescale import TimescaleAccessor` in this block.

**`_spatial`/`_etl` field analog** (`pycopg/database.py` lines 85-86):
```python
        self._spatial: SpatialAccessor | None = None
        self._etl: ETLAccessor | None = None
```
Add after line 86: `self._timescale: TimescaleAccessor | None = None`

**`etl` lazy-cached property analog** (`pycopg/database.py` lines 253-271) — copy exactly for `timescale`:
```python
    @property
    def etl(self) -> ETLAccessor:
        """Get or create the ETL run-tracking accessor (lazy initialization).

        The accessor hosts ``init()``, ``_start_run()``, ``_end_run()``,
        and ``run()`` — the run-log primitives for the v0.5.0 ETL layer.
        All run-log writes use a dedicated autocommit connection fully
        independent of any load transaction (D-01/D-02, ETL-07).

        Returns
        -------
        ETLAccessor
            ETL run-tracking namespace bound to this database.
        """
        if self._etl is None:
            from pycopg.etl import ETLAccessor

            self._etl = ETLAccessor(self)
        return self._etl
```

New `timescale` property follows the same shape. The lazy `from pycopg.timescale import TimescaleAccessor` inside the property body (not at module top) avoids circular imports at runtime.

**Deprecated stub pattern** — 6 stubs replacing `database.py:1645-1869` (all existing body deleted):
```python
    # TIMESCALEDB OPERATIONS (deprecated aliases — real impl in db.timescale.*)

    @deprecated_alias("timescale.create_hypertable")
    def create_hypertable(self, *args, **kwargs):
        """Deprecated: use ``db.timescale.create_hypertable`` instead."""

    @deprecated_alias("timescale.enable_compression")
    def enable_compression(self, *args, **kwargs):
        """Deprecated: use ``db.timescale.enable_compression`` instead."""

    @deprecated_alias("timescale.add_compression_policy")
    def add_compression_policy(self, *args, **kwargs):
        """Deprecated: use ``db.timescale.add_compression_policy`` instead."""

    @deprecated_alias("timescale.add_retention_policy")
    def add_retention_policy(self, *args, **kwargs):
        """Deprecated: use ``db.timescale.add_retention_policy`` instead."""

    @deprecated_alias("timescale.list_hypertables")
    def list_hypertables(self, *args, **kwargs):
        """Deprecated: use ``db.timescale.list_hypertables`` instead."""

    @deprecated_alias("timescale.hypertable_info")
    def hypertable_info(self, *args, **kwargs):
        """Deprecated: use ``db.timescale.hypertable_info`` instead."""
```

Add `from pycopg.aliases import deprecated_alias` to module-level imports (alongside other `from pycopg.*` imports at lines 30-50).

---

### `pycopg/async_database.py` (MODIFY — mirror of database.py edits)

**`TYPE_CHECKING` block analog** (`pycopg/async_database.py` lines 53-59):
```python
if TYPE_CHECKING:
    import geopandas as gpd
    import pandas as pd
    from sqlalchemy.ext.asyncio import AsyncEngine

    from pycopg.etl import AsyncETLAccessor
    from pycopg.spatial import AsyncSpatialAccessor
```
Add: `from pycopg.timescale import AsyncTimescaleAccessor` in this block.

**`_spatial`/`_etl` field analog** (`pycopg/async_database.py` lines 84-85):
```python
        self._spatial: AsyncSpatialAccessor | None = None
        self._etl: AsyncETLAccessor | None = None
```
Add after line 85: `self._timescale: AsyncTimescaleAccessor | None = None`

**`etl` lazy-cached property analog** (`pycopg/async_database.py` lines 114-131) — copy for `timescale`:
```python
    @property
    def etl(self) -> AsyncETLAccessor:
        """Get or create the async ETL run-tracking accessor (lazy initialization).
        ...
        Returns
        -------
        AsyncETLAccessor
            Async ETL helper namespace bound to this database.
        """
        if self._etl is None:
            from pycopg.etl import AsyncETLAccessor

            self._etl = AsyncETLAccessor(self)
        return self._etl
```

**6 async stubs** — mirror sync stubs with `async def` prefix on each:
```python
    @deprecated_alias("timescale.create_hypertable")
    async def create_hypertable(self, *args, **kwargs):
        """Deprecated: use ``async_db.timescale.create_hypertable`` instead."""
    # ... repeat for 5 more methods
```

The `async def` on the stub triggers `iscoroutinefunction(fn) == True` inside `deprecated_alias`, selecting the `async_wrapper` branch. The wrapper is thus `async def` and `iscoroutinefunction(wrapper) == True`.

Source lines for async method bodies to move into `AsyncTimescaleAccessor`: `async_database.py:1220-1456`.

---

### `pycopg/__init__.py` (MODIFY — add 2 exports)

**Existing accessor export pattern** (`pycopg/__init__.py` lines 10, 26, 51-56):
```python
from pycopg.etl import AsyncETLAccessor, ETLAccessor, Pipeline, RunResult
# ...
from pycopg.spatial import AsyncSpatialAccessor, SpatialAccessor
# ...
__all__ = [
    # ...
    # Spatial
    "SpatialAccessor",
    "AsyncSpatialAccessor",
    # ETL
    "ETLAccessor",
    "AsyncETLAccessor",
    # ...
]
```

Add after the `spatial` import line (line 26):
```python
from pycopg.timescale import AsyncTimescaleAccessor, TimescaleAccessor
```

Add in `__all__` after the ETL block:
```python
    # TimescaleDB
    "TimescaleAccessor",
    "AsyncTimescaleAccessor",
```

---

### `tests/test_parity.py` (MODIFY — data-driven registry)

**Existing `TestEtlParity` analog** (`tests/test_parity.py` lines 466-503) — this IS the pattern to generalise:
```python
class TestEtlParity:
    """SC-4: verify full public-surface parity between ETLAccessor and AsyncETLAccessor."""

    def test_etl_accessor_public_methods_match(self):
        """ETLAccessor and AsyncETLAccessor expose identical public surfaces (SC-4)."""
        sync_methods = set(
            name
            for name, _ in inspect.getmembers(ETLAccessor)
            if not name.startswith("_")
        )
        async_methods = set(
            name
            for name, _ in inspect.getmembers(AsyncETLAccessor)
            if not name.startswith("_")
        )

        missing_in_async = sync_methods - async_methods
        assert not missing_in_async, (
            f"Members present in ETLAccessor but missing in AsyncETLAccessor: "
            f"{sorted(missing_in_async)}"
        )

        extra_in_async = async_methods - sync_methods
        assert not extra_in_async, (
            f"Members present in AsyncETLAccessor but absent from ETLAccessor: "
            f"{sorted(extra_in_async)}"
        )
```

**Existing imports** (`tests/test_parity.py` lines 1-11):
```python
import inspect

import pytest

from pycopg import AsyncDatabase, Database
from pycopg.etl import AsyncETLAccessor, ETLAccessor
```

**New parametrized registry pattern** — add after existing imports:
```python
from pycopg.timescale import AsyncTimescaleAccessor, TimescaleAccessor

ACCESSOR_PAIRS = [
    (TimescaleAccessor, AsyncTimescaleAccessor),
    # Phases 22-24 APPEND here — no other change needed
]

@pytest.mark.parametrize("sync_cls, async_cls", ACCESSOR_PAIRS)
def test_accessor_parity(sync_cls, async_cls):
    """Verify public surface parity for each accessor pair (D-10)."""
    sync_methods = {
        name for name, _ in inspect.getmembers(sync_cls) if not name.startswith("_")
    }
    async_methods = {
        name for name, _ in inspect.getmembers(async_cls) if not name.startswith("_")
    }
    missing_in_async = sync_methods - async_methods
    assert not missing_in_async, (
        f"{sync_cls.__name__} has members absent from {async_cls.__name__}: "
        f"{sorted(missing_in_async)}"
    )
    extra_in_async = async_methods - sync_methods
    assert not extra_in_async, (
        f"{async_cls.__name__} has extra members absent from {sync_cls.__name__}: "
        f"{sorted(extra_in_async)}"
    )
```

The planner may optionally fold `TestEtlParity` into this registry by appending `(ETLAccessor, AsyncETLAccessor)` to `ACCESSOR_PAIRS` and deleting the `TestEtlParity` class. RESEARCH.md judges this low-risk; CONTEXT.md flags it optional.

---

### `tests/test_timescale_aliases.py` (NEW — unit test, warn+delegate)

**Closest analog:** `tests/test_parity.py:466-503` for test class structure; RESEARCH.md Footgun 2 for the `warnings.catch_warnings` + `w[0].filename` assertion pattern.

**Full pattern** (from RESEARCH.md `### Pattern 6` + Footgun 2 stacklevel test):
```python
"""Tests that deprecated flat aliases warn and delegate (REORG-04, D-09)."""

import os
import warnings

import pytest

from pycopg.timescale import TimescaleAccessor


class TestTimescaleAliases:
    """Each flat db.* alias must warn AND delegate to db.timescale.*."""

    def test_create_hypertable_warns_and_delegates(self, mocker, db):
        mock_accessor = mocker.MagicMock(spec=TimescaleAccessor)
        mocker.patch.object(
            type(db), "timescale",
            new_callable=lambda: property(lambda self: mock_accessor)
        )
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            db.create_hypertable("events", "ts")
        assert len(w) == 1
        assert w[0].category is DeprecationWarning
        assert "db.timescale.create_hypertable" in str(w[0].message)
        assert "v0.7.0" in str(w[0].message)
        # stacklevel=2 assertion: warning must point at THIS test file
        assert "test_" in os.path.basename(w[0].filename)
        assert "aliases.py" not in w[0].filename
        assert "database.py" not in w[0].filename
        mock_accessor.create_hypertable.assert_called_once_with("events", "ts")

    # Repeat the same pattern for each of the 5 remaining aliases.
    # For async aliases, use pytest-asyncio + AsyncDatabase + AsyncTimescaleAccessor mock.
```

**Fixtures note:** The `db` fixture is already defined in `conftest.py` (real DB). For unit-level alias tests that don't need a live DB, use `mocker` to patch the accessor so the test is fast and does not require TimescaleDB to be installed.

---

### Call-site migration tests (MODIFY — `test_database_integration.py`, `test_async_database.py`, `test_sql_injection.py`)

This is a mechanical search-and-replace, not a pattern extraction task. The 27 call-sites (verified by grep in RESEARCH.md):

**Pattern:** `db.<method>(...)` → `db.timescale.<method>(...)`, `await db.<method>(...)` → `await db.timescale.<method>(...)`

Files and line ranges:
- `tests/test_database_integration.py` lines 858, 860, 863, 872, 873-874, 883 (6 call-sites)
- `tests/test_async_database.py` lines 2224-2397, 2847-2850 (18 call-sites, all in `TestAsyncDatabaseTimescaleDB` class)
- `tests/test_sql_injection.py` lines 124, 130, 200, 205 (4 call-sites: `add_compression_policy`, `add_retention_policy`)

No imports need to be added to any of these files — `db.timescale` is accessed as a property on the existing `db`/`async_db` fixture objects.

---

## Shared Patterns

### Module boilerplate (`from __future__ import annotations` + `TYPE_CHECKING`)
**Source:** `pycopg/etl.py` lines 25-43
**Apply to:** `pycopg/aliases.py` (without `TYPE_CHECKING`), `pycopg/timescale.py` (with `TYPE_CHECKING`)

```python
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pycopg.async_database import AsyncDatabase
    from pycopg.database import Database
```

### Lazy cached property pattern
**Source:** `pycopg/database.py` lines 253-271 (`etl` property)
**Apply to:** both `Database.timescale` and `AsyncDatabase.timescale` new properties

```python
if self._etl is None:
    from pycopg.etl import ETLAccessor
    self._etl = ETLAccessor(self)
return self._etl
```

### Accessor `__init__(self, db)` storing `self._db`
**Source:** `pycopg/etl.py` lines 530-540, 1032-1042
**Apply to:** `TimescaleAccessor.__init__` and `AsyncTimescaleAccessor.__init__`

### `inspect.getmembers` parity check
**Source:** `tests/test_parity.py` lines 481-502
**Apply to:** new `test_accessor_parity` parametrized test (replaces/supplements `TestEtlParity`)

### `__all__` export pattern
**Source:** `pycopg/__init__.py` lines 51-56 (Spatial + ETL accessor export pattern)
**Apply to:** add `TimescaleAccessor`/`AsyncTimescaleAccessor` in same block structure

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `pycopg/aliases.py` | utility/decorator | — | No decorator module exists in codebase; pattern is pure stdlib (`functools`, `warnings`, `inspect`); full implementation is in RESEARCH.md Pattern 1 |

---

## Metadata

**Analog search scope:** `pycopg/`, `tests/`
**Files scanned:** 8 (etl.py, spatial.py, database.py, async_database.py, __init__.py, test_parity.py + 2 source line ranges)
**Key source line anchors:**
- `pycopg/database.py:54-59` — `TYPE_CHECKING` block to extend
- `pycopg/database.py:85-86` — `_spatial`/`_etl` fields (add `_timescale` after)
- `pycopg/database.py:230-271` — `spatial` + `etl` lazy properties (add `timescale` after)
- `pycopg/database.py:1645-1869` — TIMESCALEDB block to DELETE and replace with 6 stubs
- `pycopg/async_database.py:53-59` — `TYPE_CHECKING` block to extend
- `pycopg/async_database.py:84-85` — `_spatial`/`_etl` fields (add `_timescale` after)
- `pycopg/async_database.py:114-131` — `spatial` + `etl` lazy properties (add `timescale` after)
- `pycopg/async_database.py:1220-1456` — async TIMESCALEDB block to DELETE and replace with 6 async stubs
- `pycopg/etl.py:510-540` — `ETLAccessor` class + `__init__` (template for `TimescaleAccessor`)
- `pycopg/etl.py:1009-1042` — `AsyncETLAccessor` class + `__init__` (template for `AsyncTimescaleAccessor`)
- `pycopg/__init__.py:10,26,51-56` — accessor import + `__all__` pattern
- `tests/test_parity.py:466-503` — `TestEtlParity` (template for data-driven registry)
**Pattern extraction date:** 2026-06-17
