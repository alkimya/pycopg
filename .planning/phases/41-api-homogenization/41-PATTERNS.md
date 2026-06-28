# Phase 41: API Homogenization - Pattern Map

**Mapped:** 2026-06-28
**Files analyzed:** 9 (6 modified + 3 new/new-section)
**Analogs found:** 9 / 9

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `pycopg/spatial.py` (_append_tail + 11 builders + 22 accessor methods) | utility + accessor | transform | itself (in-place rename) | exact |
| `pycopg/exceptions.py` (4 class renames + module `__getattr__`) | model/exception | — | itself (in-place rename + new function) | exact |
| `pycopg/__init__.py` (import block + package `__getattr__`) | config/re-export | — | itself (in-place update) | exact |
| `pyproject.toml` (remove N818 suppression + add `filterwarnings`) | config | — | itself (in-place update) | exact |
| `tests/test_deprecations.py` | test | — | `tests/test_exceptions.py` | role-match |
| `docs/source/stability.md` | docs | — | `docs/source/postgis.md` + `docs/index.md` toctree | partial |
| `MIGRATION.md` (new section `## v0.10.x → 1.0.0`) | docs | — | existing MIGRATION.md sections | exact |

---

## Pattern Assignments

### `pycopg/exceptions.py` — 4 class renames + module `__getattr__` (FREEZE-02)

**Role:** exception module
**Analog:** itself — lines 1-76 are the full current file (76 lines total, no `__all__`, no `__getattr__`)

**Current class definitions to rename** (lines 24-51):
```python
# CURRENT (lines 24-51) — to be renamed in-place:
class ExtensionNotAvailable(PycopgError):
    """Required extension is not installed."""
    pass

class TableNotFound(PycopgError):
    """Table does not exist."""
    pass

class InvalidIdentifier(PycopgError):
    """Invalid SQL identifier (potential injection attempt)."""
    pass

class DatabaseExists(PycopgError):
    """Database already exists."""
    pass
```

**New class names (replace the above):**
```python
class ExtensionNotAvailableError(PycopgError):
    """Required extension is not installed."""
    pass

class TableNotFoundError(PycopgError):
    """Table does not exist."""
    pass

class InvalidIdentifierError(PycopgError):
    """Invalid SQL identifier (potential injection attempt)."""
    pass

class DatabaseExistsError(PycopgError):
    """Database already exists."""
    pass
```

**PEP 562 module `__getattr__` to append at end of file** (pattern from RESEARCH.md §Pattern 1):
```python
import warnings as _warnings

_DEPRECATED_NAMES: dict[str, str] = {
    "ExtensionNotAvailable": "ExtensionNotAvailableError",
    "TableNotFound": "TableNotFoundError",
    "InvalidIdentifier": "InvalidIdentifierError",
    "DatabaseExists": "DatabaseExistsError",
}


def __getattr__(name: str) -> type:
    """Resolve deprecated exception names with a DeprecationWarning (PEP 562).

    Parameters
    ----------
    name : str
        Attribute name being accessed.

    Returns
    -------
    type
        The canonical ``*Error`` class object.

    Raises
    ------
    AttributeError
        If the name is not a known deprecated alias.
    """
    if name in _DEPRECATED_NAMES:
        new = _DEPRECATED_NAMES[name]
        _warnings.warn(
            f"pycopg.exceptions.{name} is deprecated and will be removed in "
            f"pycopg 2.0. Use {new} instead.",
            DeprecationWarning,
            stacklevel=2,  # points to caller's import line, not exceptions.py
        )
        return globals()[new]
    raise AttributeError(f"module 'pycopg.exceptions' has no attribute {name!r}")
```

**Key constraint:** `globals()[new]` returns the **same class object** as `*Error` — this is the same-object guarantee for `except OldName:` catch semantics.

---

### `pycopg/__init__.py` — import block + package `__getattr__` (FREEZE-02)

**Role:** package re-export
**Analog:** itself (lines 1-101 fully read)

**Import block to update** (lines 13-26 — change old names to new `*Error` names):
```python
# CURRENT (lines 13-26):
from pycopg.exceptions import (
    ConfigurationError,
    ConnectionError,
    DatabaseExists,           # → DatabaseExistsError
    ETLError,
    ETLTargetNotFoundError,
    ETLTransformError,
    ExtensionNotAvailable,    # → ExtensionNotAvailableError
    InvalidIdentifier,        # → InvalidIdentifierError
    MigrationError,
    PycopgError,
    TableNotFound,            # → TableNotFoundError
    TimescaleError,
)
```

**`__all__` to update** (lines 82-94 — add new names, keep old names as deprecated):
```python
# AFTER: add *Error canonical names; keep old names with deprecated suffix
# Old names will be served via package __getattr__ below
"DatabaseExistsError",
"ExtensionNotAvailableError",
"InvalidIdentifierError",
"TableNotFoundError",
# Deprecated aliases (resolved via __getattr__, removed in 2.0):
"DatabaseExists",
"ExtensionNotAvailable",
"InvalidIdentifier",
"TableNotFound",
```

**Package `__getattr__` to append** (for `pycopg.OldName` attribute access — pattern from RESEARCH.md):
```python
_DEPRECATED_PACKAGE_ALIASES: dict[str, str] = {
    "ExtensionNotAvailable": "ExtensionNotAvailableError",
    "TableNotFound": "TableNotFoundError",
    "InvalidIdentifier": "InvalidIdentifierError",
    "DatabaseExists": "DatabaseExistsError",
}


def __getattr__(name: str):
    if name in _DEPRECATED_PACKAGE_ALIASES:
        import warnings
        from pycopg import exceptions as _exc
        new_name = _DEPRECATED_PACKAGE_ALIASES[name]
        warnings.warn(
            f"{name} is deprecated and will be removed in pycopg 2.0. "
            f"Use {new_name} instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return getattr(_exc, new_name)
    raise AttributeError(f"module 'pycopg' has no attribute {name!r}")
```

**Pitfall (from RESEARCH.md §Pitfall 2):** Do NOT keep `from pycopg.exceptions import DatabaseExists` after rename — it raises `ImportError` at package import time because `DatabaseExists` is no longer a real name in `exceptions.py` (only via `__getattr__`).

---

### `pycopg/spatial.py` — `_append_tail` + 11 builders + 22 accessor methods (FREEZE-01)

**Role:** utility function + accessor methods
**Analog:** itself (in-place rename)

**`_append_tail` current signature** (lines 148-185):
```python
# CURRENT (lines 148-185):
def _append_tail(
    sql: str,
    where: str | None,      # → rename to: filter: str | None
    order_by: str | None,
    limit: int | None,
    has_where: bool,
) -> str:
    if where:               # → rename to: if filter:
        sql += f" AND ({where})" if has_where else f" WHERE {where}"  # → use filter
    if order_by:
        sql += f" ORDER BY {order_by}"
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    return sql
```

**`_append_tail` after rename** (internal private function — no deprecation wrapper needed):
```python
def _append_tail(
    sql: str,
    filter: str | None,     # renamed from where; no public API impact
    order_by: str | None,
    limit: int | None,
    has_where: bool,
) -> str:
    if filter:
        sql += f" AND ({filter})" if has_where else f" WHERE {filter}"
    if order_by:
        sql += f" ORDER BY {order_by}"
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    return sql
```

**`build_contains_sql` builder current signature** (lines 188-202):
```python
# CURRENT: builder with where= keyword arg (lines 192-202)
def build_contains_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    point: tuple[float, float] | None = None,
    wkt: str | None = None,
    geojson: dict | None = None,
    ref: tuple[str, str] | None = None,
    srid: int = 4326,
    columns: list[str] | None = None,
    where: str | None = None,    # → rename to filter=
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list]:
    ...
    sql = _append_tail(sql, where, order_by, limit, has_where=True)  # → filter
```

**Builder after rename** (clean frozen public signature — no deprecated alias, D-04):
```python
def build_contains_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    point: tuple[float, float] | None = None,
    wkt: str | None = None,
    geojson: dict | None = None,
    ref: tuple[str, str] | None = None,
    srid: int = 4326,
    columns: list[str] | None = None,
    filter: str | None = None,   # renamed; builder is clean (no where= shim)
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list]:
    ...
    sql = _append_tail(sql, filter, order_by, limit, has_where=True)
```

**`SpatialAccessor.contains` current signature** (lines 1079-1155 — the sync template):
```python
# CURRENT (lines 1079-1095):
def contains(
    self,
    table: str,
    geom: str = "geometry",    # currently positional-with-default → kw-only under D-03
    schema: str = "public",    # currently positional-with-default → kw-only under D-03
    *,
    point: tuple[float, float] | None = None,
    wkt: str | None = None,
    geojson: dict | None = None,
    ref: tuple[str, str] | None = None,
    srid: int = 4326,
    into: str = "rows",
    columns: list[str] | None = None,
    where: str | None = None,   # → filter= canonical + where= deprecated shim
    order_by: str | None = None,
    limit: int | None = None,
) -> list[dict] | gpd.GeoDataFrame:
```

**`SpatialAccessor.contains` body that calls builder** (lines 1140-1155):
```python
    _check_into(into, "contains")
    sql, params = build_contains_sql(
        table,
        geom,
        schema,
        point=point,
        wkt=wkt,
        geojson=geojson,
        ref=ref,
        srid=srid,
        columns=columns,
        where=where,     # → must become filter=filter after rename
        order_by=order_by,
        limit=limit,
    )
    return self._run(sql, params, into, geom)
```

**Accessor method after rename** (sync; apply identical shape to all 11 methods + async mirror):
```python
def contains(
    self,
    table: str,
    *,                          # kw-only boundary moves here (D-03); geom+schema promoted
    geom: str = "geometry",
    schema: str = "public",
    point: tuple[float, float] | None = None,
    wkt: str | None = None,
    geojson: dict | None = None,
    ref: tuple[str, str] | None = None,
    srid: int = 4326,
    into: str = "rows",
    columns: list[str] | None = None,
    filter: str | None = None,    # canonical new name
    where: str | None = None,     # deprecated shim — emits DeprecationWarning
    order_by: str | None = None,
    limit: int | None = None,
) -> list[dict] | gpd.GeoDataFrame:
    if where is not None:
        import warnings
        if filter is not None:
            raise TypeError(
                "Cannot specify both 'filter' and 'where'; use 'filter=' only."
            )
        warnings.warn(
            "The 'where' keyword argument is deprecated and will be removed in "
            "pycopg 2.0. Use 'filter=' instead.",
            DeprecationWarning,
            stacklevel=2,  # points to the caller's line, not spatial.py
        )
        filter = where
    _check_into(into, "contains")
    sql, params = build_contains_sql(
        table,
        geom=geom,
        schema=schema,
        point=point,
        wkt=wkt,
        geojson=geojson,
        ref=ref,
        srid=srid,
        columns=columns,
        filter=filter,
        order_by=order_by,
        limit=limit,
    )
    return self._run(sql, params, into, geom)
```

**`AsyncSpatialAccessor.contains` current signature** (lines 1970-2048 — byte-for-byte mirror):
```python
# CURRENT (lines 1970-1986): identical structure to sync except:
async def contains(self, ...) -> list[dict] | gpd.GeoDataFrame:
    await self._check_postgis()          # async-only guard
    _check_into(into, "contains")
    sql, params = build_contains_sql(...)
    return await self._run(...)          # await instead of return
```

**Async method after rename** (identical shim shape as sync, plus `await`):
```python
async def contains(
    self,
    table: str,
    *,
    geom: str = "geometry",
    schema: str = "public",
    ...
    filter: str | None = None,
    where: str | None = None,    # same deprecated shim
    ...
) -> list[dict] | gpd.GeoDataFrame:
    if where is not None:
        import warnings
        if filter is not None:
            raise TypeError("Cannot specify both 'filter' and 'where'; use 'filter=' only.")
        warnings.warn(
            "The 'where' keyword argument is deprecated and will be removed in "
            "pycopg 2.0. Use 'filter=' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        filter = where
    await self._check_postgis()
    _check_into(into, "contains")
    sql, params = build_contains_sql(table, geom=geom, schema=schema, ..., filter=filter, ...)
    return await self._run(sql, params, into, geom)
```

**`within` special case** — has 4 required positional args (`left_table`, `left_geom`, `right_table`, `right_geom`) + `schema="public"`. Under D-03, `schema` becomes keyword-only; the 4 identifiers stay positional:
```python
def within(
    self,
    left_table: str,
    left_geom: str,
    right_table: str,
    right_geom: str,
    *,                       # kw-only boundary; schema moves here
    schema: str = "public",
    ...
    filter: str | None = None,
    where: str | None = None,  # deprecated shim same as above
    ...
)
```

**Repeat count:** All 11 `build_*_sql` builders + 11 `SpatialAccessor` methods + 11 `AsyncSpatialAccessor` methods = 33 signature sites. Each builder gets a clean `filter=` rename; each accessor method gets the `filter=`/`where=` shim. The `_append_tail` choke-point is renamed once.

---

### `pyproject.toml` — N818 suppression removal + `filterwarnings` gate (FREEZE-02 + D-10)

**Role:** config
**Analog:** itself (in-place edit)

**Lines 92-96 — N818 suppression block to REMOVE:**
```toml
[tool.ruff.lint.per-file-ignores]
# N818: The 4 exception names below ... (entire comment + line below)
"pycopg/exceptions.py" = ["N818"]
```
Remove that key from `[tool.ruff.lint.per-file-ignores]` entirely (or remove the file entirely if it becomes empty).

**Lines 98-101 — `[tool.pytest.ini_options]` to extend with `filterwarnings`:**
```toml
# CURRENT:
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --cov=pycopg --cov-report=term-missing --cov-report=html --cov-fail-under=95"
asyncio_mode = "auto"

# AFTER (add filterwarnings; third-party list must be discovered before committing gate):
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --cov=pycopg --cov-report=term-missing --cov-report=html --cov-fail-under=95"
asyncio_mode = "auto"
filterwarnings = [
    "error::DeprecationWarning",
    # Third-party suppressions (populate after discovery run: uv run pytest -W error::DeprecationWarning):
    "ignore::DeprecationWarning:psycopg",
    "ignore::DeprecationWarning:geopandas",
    "ignore::DeprecationWarning:pandas",
]
```

**Discovery step required (Pitfall 4):** Run `uv run pytest -W error::DeprecationWarning 2>&1 | grep DeprecationWarning` before committing the gate to collect the actual third-party sources; the list above may need extension.

---

### `tests/test_deprecations.py` — new test module (FREEZE-01 + FREEZE-02 + FREEZE-03)

**Role:** test
**Analog:** `tests/test_exceptions.py` (lines 1-82) — class-per-concern structure, `import pytest`, `from pycopg.exceptions import ...`, `pytest.raises` pattern

**File structure to copy from `tests/test_exceptions.py`** (lines 1-17):
```python
"""Tests for pycopg deprecation warnings and aliases."""

import warnings
import pytest
from unittest.mock import MagicMock

from pycopg import exceptions
from pycopg.spatial import SpatialAccessor
```

**FREEZE-02 test pattern — exception alias identity** (from RESEARCH.md §Code Examples):
```python
class TestExceptionAliases:
    """PEP 562 deprecated exception name behaviour (FREEZE-02)."""

    def test_exception_alias_same_object(self):
        """Old name resolves to the identical class object."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            OldName = exceptions.InvalidIdentifier
        assert OldName is exceptions.InvalidIdentifierError

    def test_exception_alias_warns_on_access(self):
        """Accessing old exception name emits DeprecationWarning."""
        with pytest.warns(DeprecationWarning) as record:
            _ = exceptions.InvalidIdentifier
        w = record[0]
        assert "InvalidIdentifierError" in str(w.message)
        # D-09: stacklevel must point at THIS file, not exceptions.py
        assert w.filename.endswith("test_deprecations.py"), (
            f"Warning pointed at {w.filename!r}, expected test file"
        )

    def test_old_exception_name_still_catchable(self):
        """except OldName: catches exception raised with NewNameError (same object)."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            OldName = exceptions.InvalidIdentifier
        with pytest.raises(OldName):
            raise exceptions.InvalidIdentifierError("test")
```

**FREEZE-01 test pattern — `where=` stacklevel** (from RESEARCH.md §Code Examples):
```python
class TestWhereDeprecation:
    """where= shim deprecation behaviour (FREEZE-01)."""

    def test_where_deprecation_points_to_caller(self):
        """DeprecationWarning from where= must point to THIS file, not spatial.py."""
        db = MagicMock()
        db.schema.has_extension.return_value = True
        db.execute.return_value = []
        accessor = SpatialAccessor(db)
        with pytest.warns(DeprecationWarning) as record:
            accessor.contains("tbl", point=(0.0, 0.0), where="id > 0")
        assert len(record) == 1
        w = record[0]
        assert "filter" in str(w.message)
        assert w.filename.endswith("test_deprecations.py"), (
            f"Warning pointed at {w.filename!r}, expected test file"
        )

    def test_filter_and_where_both_supplied_raises(self):
        """Supplying both filter= and where= raises TypeError."""
        db = MagicMock()
        db.schema.has_extension.return_value = True
        db.execute.return_value = []
        accessor = SpatialAccessor(db)
        with pytest.raises(TypeError, match="Cannot specify both"):
            accessor.contains("tbl", point=(0.0, 0.0), filter="x > 0", where="y > 0")
```

**FREEZE-03 kw-only enforcement test pattern:**
```python
class TestKwOnlyEnforcement:
    """Keyword-only boundary enforcement (FREEZE-03, D-03/D-04)."""

    def test_contains_geom_is_kw_only(self):
        """Passing geom positionally must raise TypeError in 1.0."""
        db = MagicMock()
        accessor = SpatialAccessor(db)
        with pytest.raises(TypeError):
            accessor.contains("tbl", "geometry")  # geom is now kw-only
```

---

### `docs/source/stability.md` — new SemVer + deprecation policy doc (FREEZE-04)

**Role:** docs
**Analog:** `docs/source/postgis.md` (MyST Markdown style), `docs/index.md` (toctree pattern, lines 5-23)

**Toctree entry to add in `docs/index.md`** (insert after `api-autodoc`, before closing fence):
```markdown
stability
```

**`docs/source/stability.md` top-level structure** (follows MyST Markdown convention used throughout `docs/source/`):
```markdown
# API Stability

pycopg follows [Semantic Versioning 2.0.0](https://semver.org/).
At **1.0.0** the public API is frozen.

## SemVer Contract

### Breaking vs Non-Breaking Changes

| Change | Classification |
|--------|---------------|
| Removing a public method or parameter | BREAKING (major bump) |
| Renaming a parameter without alias | BREAKING (major bump) |
| Adding an optional parameter with default | Non-breaking (minor bump) |
| Changing a parameter default value | BREAKING (major bump) |
| Changing a return type | BREAKING (major bump) |
| Changing an exception type raised | BREAKING (major bump) |
| Bug fix that changes documented behaviour | Patch (noted in CHANGELOG) |

## Deprecation Policy

Deprecated names are kept for the **entirety of 1.x** and removed only in 2.0.
Every deprecated call emits `DeprecationWarning`. Update your code before 2.0.

## Stable API Contract

[Table of every public method with positional vs keyword-only boundary — produced by FREEZE-03 audit]

## Supported Versions

| Component | Floor | Recommended |
|-----------|-------|-------------|
| Python | 3.11 | 3.12+ |
| PostgreSQL | 13 | 16+ |
| PostGIS | 3.0 | 3.2+ (`ST_MakeValid method=structure` requires 3.2) |
| TimescaleDB | 2.0 | 2.10+ |
| psycopg | 3.1.0 | latest |
| psycopg_pool | 3.2.0 | latest |

## API Stability Tiers

| API Surface | Stability |
|---|---|
| `Database.*` flat core | Stable |
| `AsyncDatabase.*` flat core | Stable |
| `db.spatial.*` | Stable |
| `db.schema.*` | Stable |
| `db.timescale.*` | Stable |
| `db.etl.*` | Stable |
| `db.admin.*` | Stable |
| `db.maint.*` | Stable |
| `db.backup.*` | Stable |
| Module-level `build_*_sql` builders | Stable |
| `pycopg.exceptions.*Error` | Stable |
| Internal `_*` names | Private — no stability guarantee |
```

**README link to add** (grep pattern: find existing PyPI badge block or Features section):
```markdown
See [API Stability](https://pycopg.readthedocs.io/en/latest/stability.html) for the SemVer contract and deprecation policy.
```

---

### `MIGRATION.md` — new section `## v0.10.x → 1.0.0` (FREEZE-01 + FREEZE-02 + FREEZE-03)

**Role:** docs
**Analog:** existing `MIGRATION.md` (lines 1-60) — plain Markdown with `## v0.X → v0.Y` header, "Breaking Changes" subsection, before/after code blocks, rename table

**Section structure to copy from existing pattern (lines 1-30):**
```markdown
# Migration Guide: v0.10.x → 1.0.0

This guide covers **all breaking changes** at the 1.0 boundary.
Deprecated names (`where=`, old exception names) are kept until pycopg 2.0 but emit
`DeprecationWarning` on use — update your code to silence them now.

## Breaking Changes

### 1. Spatial `where=` renamed to `filter=` (FREEZE-01)

**All 11 `db.spatial.*` methods** and the 11 corresponding `build_*_sql` builders
rename the raw SQL filter parameter from `where=` to `filter=`.

```python
# BEFORE (pycopg ≤ 0.10.x):
rows = db.spatial.contains("parks", point=(1.0, 2.0), where="area > 1000")

# AFTER (pycopg 1.0+):
rows = db.spatial.contains("parks", point=(1.0, 2.0), filter="area > 1000")
```

The old `where=` emits `DeprecationWarning` through 1.x and is removed in 2.0.

### 2. Exception renames → `*Error` convention (FREEZE-02)

| Old name (deprecated) | New name (canonical) |
|---|---|
| `ExtensionNotAvailable` | `ExtensionNotAvailableError` |
| `TableNotFound` | `TableNotFoundError` |
| `InvalidIdentifier` | `InvalidIdentifierError` |
| `DatabaseExists` | `DatabaseExistsError` |

```python
# BEFORE:
from pycopg.exceptions import InvalidIdentifier

# AFTER:
from pycopg.exceptions import InvalidIdentifierError
```

`except OldName:` continues to work (aliases resolve to the same class object).
Accessing the old name emits `DeprecationWarning`. Old names removed in 2.0.

### 3. Keyword-only parameter enforcement (FREEZE-03)

All optional/defaulted parameters on public methods are now keyword-only (enforced via `*`).
This is a **clean break** with no deprecation alias.

```python
# BEFORE — positional call (pycopg ≤ 0.10.x, now raises TypeError):
db.spatial.contains("parks", "geometry", "public", point=(1.0, 2.0))

# AFTER — keyword-only (pycopg 1.0+):
db.spatial.contains("parks", geom="geometry", schema="public", point=(1.0, 2.0))
```

[Additional rows from FREEZE-03 audit table — added after user review gate (D-05)]
```

---

## Shared Patterns

### Internal raise site update pattern (FREEZE-02)

**Source:** RESEARCH.md §Code Examples — applies to all internal files with old exception names.
**Files affected:** `pycopg/utils.py`, `pycopg/schema.py`, `pycopg/database.py`,
`pycopg/async_database.py`, `pycopg/timescale.py`, `pycopg/spatial.py`

```python
# BEFORE (any internal file):
from pycopg.exceptions import InvalidIdentifier
raise InvalidIdentifier("Identifier cannot be empty")

# AFTER (atomic update — must land in same commit as exceptions.py rename):
from pycopg.exceptions import InvalidIdentifierError
raise InvalidIdentifierError("Identifier cannot be empty")
```

**Scope:** ~15 sites for `ExtensionNotAvailable`, ~15 for `InvalidIdentifier`, ~2 for `TableNotFound`, ~2 for `DatabaseExists` (from RESEARCH.md §Sources grep counts). All must be updated before `filterwarnings = error::DeprecationWarning` gate is committed.

### `validate_identifiers` guard preservation (security)

**Source:** `pycopg/spatial.py` line 247 — `validate_identifiers(table, schema, geom)` is the
first call in every `build_*_sql` function. The v0.10.0 lesson: parameter renames can silently
drop this guard if the implementer refactors carelessly.

```python
# CURRENT (line 247 in build_contains_sql — preserve verbatim in all builders after rename):
validate_identifiers(table, schema, geom)
if columns:
    validate_identifiers(*columns)
```

**Rule:** After each builder rename, verify this guard is still the **first statement** in the function body.

### pytest `warns` + `filename` assertion pattern for D-09

**Source:** RESEARCH.md §Code Examples — `tests/test_deprecations.py` must use this exact shape.

```python
with pytest.warns(DeprecationWarning) as record:
    <call that triggers the deprecated path>
w = record[0]
assert "new_name" in str(w.message)
assert w.filename.endswith("test_deprecations.py"), (
    f"Warning pointed at {w.filename!r}, expected test file"
)
```

### Test class structure (from `tests/test_exceptions.py` lines 16-82)

```python
class TestFeatureName:
    """Docstring for the concern."""

    def test_something(self):
        """Single-sentence docstring."""
        ...
```

---

## No Analog Found

No files in this phase lack a codebase analog. All patterns are grounded in existing code or RESEARCH.md verified references.

---

## Metadata

**Analog search scope:** `pycopg/`, `tests/`, `docs/`, `MIGRATION.md`
**Files scanned:** 9 (exceptions.py, `__init__.py`, spatial.py ×2 class locations, pyproject.toml,
tests/test_exceptions.py, tests/test_parity.py, docs/index.md, MIGRATION.md)
**Pattern extraction date:** 2026-06-28
