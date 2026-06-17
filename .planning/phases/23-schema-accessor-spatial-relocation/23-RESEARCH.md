# Phase 23: Schema Accessor & Spatial Relocation — Research

**Researched:** 2026-06-17
**Domain:** Python accessor-extraction pattern — 27 DDL/introspection schema methods + 2 PostGIS spatial relocations
**Confidence:** HIGH (all claims verified against live source)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01 [informational]:** 27 methods (not "~26"). Phase total: 29 flat names.
- **D-02:** Schema track and spatial-relocation track kept cleanly separate in plans.
- **D-03 [informational]:** Schema track mirrors Phase 22 3-wave decomposition. Spatial relocation is its own plan.
- **D-04:** Generalized self-reference rewrite: `self.execute` → `self._db.execute`; `self.<sibling>` → `self._db.schema.<sibling>`; `self.config` → `self._db.config`. ZERO sibling-schema self-calls found (verified).
- **D-05:** 8 stay-flat call-sites (4 sync + 4 async in `from_dataframe`/`from_geodataframe`) MUST be rewritten to accessor paths.
- **D-06:** Spatial relocation inherits the SpatialAccessor PostGIS guard — behavior change accepted. No guard bypass. Document in CHANGELOG/MIGRATION (Phase 24).
- **D-07:** Move `create_spatial_index`/`list_geometry_columns` verbatim. Do NOT conform to pure-builder/`_run` style. No new queries.py builders.
- **Entire Phase 21 pattern (D-01..D-10):** `@deprecated_alias` reused verbatim; one dedicated module; lazy-cached property; generic `(*args, **kwargs)` stubs with one-line docstrings; `stacklevel=2`; DB-free MagicMock alias tests; `ACCESSOR_PAIRS` registry.
- **Phase 22 refinements:** D-02/D-03 self-call rewrite rule; D-04 3-wave decomposition; D-06 move-don't-improve.

### Claude's Discretion

- Exact per-track plan boundaries / number of plans (D-02/D-03 separation locked; precise cut is planner's call).
- Whether `test_schema_aliases.py` is one parametrized module or split.
- Whether the 2 spatial alias tests live in a new `test_spatial_aliases.py` or extend an existing spatial test module.
- `from __future__ import annotations` + `TYPE_CHECKING` in `schema.py` — follow `timescale.py`/`admin.py`/`spatial.py`.
- Order of waves' internal work; order of schema track vs spatial-reloc track.

### Deferred Ideas (OUT OF SCOPE)

- Public exports hardening / README / Sphinx / CHANGELOG / MIGRATION / version bump / PyPI publish (Phase 24).
- Conforming the 2 relocated spatial methods to pure-builder/`_run` house style (spatial v2, v1.0.0).
- Opportunistic `queries.py` builder extraction for schema SQL.
- Carving `db.meta.*` out of `db.schema.*` (v0.9.0 if ever).
- Alias removal (v0.7.0).
- New DDL/introspection/PostGIS power (v0.8.0+).
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SCH-01 | `db.schema.*` / `async_db.schema.*` exposes the 27 DDL + introspection methods as a single block; flat `db.*` names remain as deprecated aliases | Verified: all 27 present in both files, self.X enumeration complete, zero sibling calls confirmed |
| SCH-02 | `create_spatial_index` and `list_geometry_columns` relocated to `db.spatial.*` / `async_db.spatial.*`; flat `db.*` names remain as deprecated aliases | Verified: bodies confirmed at correct lines, SpatialAccessor guard semantics understood, async guard difference documented |
</phase_requirements>

---

## Summary

Phase 23 is the third (and largest) application of the Phase 21/22 accessor-extraction pattern. Two distinct tracks: (1) 27 schema methods extracted into a new `pycopg/schema.py` module (`SchemaAccessor`/`AsyncSchemaAccessor`), and (2) 2 spatial-index methods relocated into the already-existing `SpatialAccessor`/`AsyncSpatialAccessor` in `pycopg/spatial.py`.

All of CONTEXT.md's load-bearing factual claims have been verified against the live code — with **one critical exception**: CONTEXT.md states "SpatialAccessor pair is already registered" in `ACCESSOR_PAIRS` (lines 29, 259 of CONTEXT.md). **This is FALSE.** The live `tests/test_parity.py` does NOT include `(SpatialAccessor, AsyncSpatialAccessor)` in `ACCESSOR_PAIRS`. The planner must decide whether to add it as part of this phase (not required by the SCH-01/SCH-02 parity requirement, since schema is the new pair) or leave it absent. This is a low-risk gap — the relocated 2 methods only need the `SchemaAccessor` pair added, and parity of the spatial surface is already checked indirectly by `TestAsyncParity`.

A second structural subtlety: `AsyncSpatialAccessor.__init__` does NOT raise immediately on missing PostGIS — it defers to `_check_postgis()` which is called from each method body. The 2 methods being relocated (`create_spatial_index`, `list_geometry_columns`) currently bypass `_check_postgis()` entirely (they call `self.execute()` directly). When moved into `AsyncSpatialAccessor`, the planner must decide whether to add `await self._check_postgis()` to these two methods — D-06 says "accept the changed failure mode", which implies yes for consistency with all other async spatial methods.

**Primary recommendation:** Follow the pattern exactly. Schema track = 3 waves, mirror Phase 22. Spatial relocation = separate plan. The 8 stay-flat call-site rewrites are the highest-risk execution item.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Schema DDL/introspection methods | Python library (accessor class) | PostgreSQL (execution) | Pure delegation pattern; logic stays flat on Database, accessor is a namespace |
| Spatial index creation | Python library (SpatialAccessor) | PostgreSQL (execution) | PostGIS guard lives at accessor construction in sync path, per-method in async path |
| Deprecated alias dispatch | Python library (Database/AsyncDatabase) | accessor | `@deprecated_alias` decorator handles warn+delegate; lives on the flat `db.*` stub |
| Test validation (alias warn/delegate) | Test layer (no DB) | — | DB-free MagicMock tests; live DB not needed for alias correctness |

---

## Verification Results — CONTEXT.md Claims

### Claim 1: 27 schema methods present in both files [PASS]

Sync `database.py` — exact line numbers verified:

| Group | Method | Sync Line | CONTEXT Claims | Status |
|-------|--------|-----------|----------------|--------|
| Databases | `create_database` | 840 | 840 | PASS |
| Databases | `drop_database` | 865 | 865 | PASS |
| Databases | `database_exists` | 892 | 892 | PASS |
| Databases | `list_databases` | 911 | 911 | PASS |
| Extensions | `create_extension` | 926 | 926 | PASS |
| Extensions | `drop_extension` | 949 | 949 | PASS |
| Extensions | `list_extensions` | 970 | 970 | PASS |
| Extensions | `has_extension` | 980 | 980 | PASS |
| Schemas | `create_schema` | 1000 | 1000 | PASS |
| Schemas | `drop_schema` | 1021 | 1021 | PASS |
| Schemas | `list_schemas` | 1040 | 1040 | PASS |
| Schemas | `schema_exists` | 1051 | 1051 | PASS |
| Tables | `list_tables` | 1071 | 1071 | PASS |
| Tables | `table_exists` | 1087 | 1087 | PASS |
| Columns | `list_columns` | 1105 | 1105 | PASS |
| Columns | `columns_with_types` | 1123 | 1123 | PASS |
| Tables | `drop_table` | 1143 | 1143 | PASS |
| Tables | `truncate_table` | 1168 | 1168 | PASS |
| Tables | `table_info` | 1186 | 1186 | PASS |
| Tables | `row_count` | 1204 | 1204 | PASS |
| Constraints | `add_primary_key` | 1228 | 1228 | PASS |
| Constraints | `add_foreign_key` | 1260 | 1260 | PASS |
| Constraints | `add_unique_constraint` | 1331 | 1331 | PASS |
| Constraints | `create_index` | 1362 | 1362 | PASS |
| Constraints | `drop_index` | 1408 | 1408 | PASS |
| Constraints | `list_indexes` | 1426 | 1426 | PASS |
| Constraints | `list_constraints` | 1443 | 1443 | PASS |

**Count: 27 sync methods confirmed. No parity gaps found. All 27 async equivalents confirmed present in `async_database.py`.**

Async line numbers (all verified against live code): `list_schemas` 712, `schema_exists` 723, `create_schema` 739, `list_tables` 760, `table_exists` 776, `list_columns` 794, `columns_with_types` 812, `table_info` 832, `row_count` 850, `drop_schema` 870, `drop_table` 889, `truncate_table` 914, `add_primary_key` 936, `add_foreign_key` 968, `add_unique_constraint` 1039, `create_index` 1070, `drop_index` 1116, `list_indexes` 1134, `list_constraints` 1151, `has_extension` 1172, `create_extension` 1188, `list_extensions` 1211, `drop_extension` 1221, `create_database` 1740, `drop_database` 1769, `database_exists` 1798, `list_databases` 1819.

### Claim 2: D-04 self.X enumeration — ZERO sibling calls [PASS]

AST scan of all 29 method bodies (27 schema + 2 spatial) in both `database.py` and `async_database.py`:

**Sync — complete self.X inventory:**
- `create_database`: `self.config` @ line 860 (attribute → becomes `self._db.config`)
- `drop_database`: `self.config` @ line 877 (attribute → becomes `self._db.config`)
- `database_exists`: `self.config` @ line 905 (attribute → becomes `self._db.config`)
- `list_databases`: `self.execute` @ line 919
- `create_extension`: `self.execute` @ line 945
- `drop_extension`: `self.execute` @ line 966
- `list_extensions`: `self.execute` @ line 978
- `has_extension`: `self.execute` @ line 993
- `create_schema`: `self.execute` @ line 1019
- `drop_schema`: `self.execute` @ line 1038
- `list_schemas`: `self.execute` @ line 1048
- `schema_exists`: `self.execute` @ line 1064
- `list_tables`: `self.execute` @ line 1084
- `table_exists`: `self.execute` @ line 1102
- `list_columns`: `self.execute` @ line 1120
- `columns_with_types`: `self.execute` @ line 1140
- `drop_table`: `self.execute` @ line 1166
- `truncate_table`: `self.execute` @ line 1184
- `table_info`: `self.execute` @ line 1202
- `row_count`: `self.execute` @ line 1221
- `add_primary_key`: `self.execute` @ line 1256
- `add_foreign_key`: `self.execute` @ line 1322
- `add_unique_constraint`: `self.execute` @ line 1358
- `create_index`: `self.execute` @ line 1403
- `drop_index`: `self.execute` @ line 1424
- `list_indexes`: `self.execute` @ line 1441
- `list_constraints`: `self.execute` @ line 1458
- `create_spatial_index`: `self.execute` @ line 1695
- `list_geometry_columns`: `self.execute` @ line 1715

**Async — same pattern confirmed:** all 29 methods use `self.execute` (async path) or `self.config` (3 database-level methods). ZERO sibling-schema calls in either sync or async.

**Rewrite map for the move:**
- `self.config` → `self._db.config` (3 database-level methods only)
- `self.execute(...)` → `self._db.execute(...)` (all others, 26 schema + 2 spatial)

### Claim 3: D-05 — 8 stay-flat call-sites [PASS with correction]

CONTEXT.md claims exact sites. Verified against live code:

**Sync `database.py`:**
- Line 1503: `self.add_primary_key(table, primary_key, schema)` inside `from_dataframe` — PASS
- Line 1583: `if not self.has_extension("postgis"):` inside `from_geodataframe` — PASS
- Line 1619: `self.add_primary_key(table, primary_key, schema)` inside `from_geodataframe` — PASS
- Line 1622: `self.create_spatial_index(table, geometry_column, schema)` inside `from_geodataframe` — PASS

**Async `async_database.py`:**
- Line 1479: `await self.add_primary_key(table, primary_key, schema)` inside `from_dataframe` — PASS
- Line 1568: `if not await self.has_extension("postgis"):` inside `from_geodataframe` — PASS
- Line 1607: `await self.add_primary_key(table, primary_key, schema)` inside `from_geodataframe` — PASS
- Line 1610: `await self.create_spatial_index(table, geometry_column, schema)` inside `from_geodataframe` — PASS

**Required rewrites after Phase 23:**
- `self.add_primary_key(...)` → `self.schema.add_primary_key(...)`
- `self.has_extension("postgis")` → `self.schema.has_extension(...)`
- `self.create_spatial_index(...)` → `self.spatial.create_spatial_index(...)`

No additional stay-flat callers found. Grep of the full `pycopg/` package for all 29 flat names (excluding def sites) surfaces zero additional callers beyond these 8 sites and the `from_geodataframe` PostGIS guard.

### Claim 4: Spatial relocation specifics [PASS with async nuance]

**Sync spatial.py:**
- `SpatialAccessor.__init__` at line 1033: confirmed `self._db = db` then `if not db.has_extension("postgis"): raise ExtensionNotAvailable(_POSTGIS_GUARD_MSG)` at line 1047 — PASS
- `create_spatial_index` (sync database.py:1671): inline f-string `CREATE INDEX IF NOT EXISTS {index_name} ON {schema}.{table} USING GIST ({column})`, calls `self.execute(...)` — PASS
- `list_geometry_columns` (sync database.py:1700): `queries.LIST_GEOMETRY_COLUMNS.format(where_clause=where_clause)`, calls `self.execute(...)` — PASS
- `AsyncSpatialAccessor` at spatial.py:1859 — PASS

**Async guard nuance (NOT in CONTEXT.md — NEW FINDING):**
`AsyncSpatialAccessor.__init__` does NOT raise immediately. It stores `self._postgis_ok: bool = False` and defers the check to `_check_postgis()` (spatial.py:1879). Every existing async spatial method calls `await self._check_postgis()` before `await self._run(...)`. The 2 methods being relocated (`create_spatial_index`, `list_geometry_columns`) currently bypass `_check_postgis()` in async_database.py. When moved into `AsyncSpatialAccessor`, they must add `await self._check_postgis()` as the first line — otherwise they will behave inconsistently with all other async spatial methods (no guard) even though D-06 says "accept the changed failure mode". This is consistent with D-06's intent; it just requires one line per method in the async bodies.

**No new property/cache field needed:** `db.spatial` / `async_db.spatial` already exist (database.py:231, async_database.py:96). CONTEXT.md claim confirmed — PASS.

### Claim 5: SpatialAccessor in ACCESSOR_PAIRS [FAIL — P1 finding]

CONTEXT.md (line 29, line 259): "SpatialAccessor pair is already registered" / "SpatialAccessor pair already exists."

**ACTUAL:** `tests/test_parity.py` `ACCESSOR_PAIRS` list contains only:
```python
ACCESSOR_PAIRS = [
    (TimescaleAccessor, AsyncTimescaleAccessor),
    (ETLAccessor, AsyncETLAccessor),
    (AdminAccessor, AsyncAdminAccessor),
    (MaintAccessor, AsyncMaintAccessor),
    (BackupAccessor, AsyncBackupAccessor),
]
```

`(SpatialAccessor, AsyncSpatialAccessor)` is NOT present. The `TestAsyncParity` class provides indirect parity coverage for the spatial surface via `inspect.getmembers(Database)` / `AsyncDatabase`, but the dedicated `test_accessor_parity` parametrized test does not include it.

**Planning impact:** The CONTEXT.md claim "the parity test must still pass for the 2 newly-added spatial methods" holds (because TestAsyncParity covers db-level parity). But "SpatialAccessor pair is already registered" as ACCESSOR_PAIRS entry is incorrect. The planner should NOT add `(SpatialAccessor, AsyncSpatialAccessor)` to ACCESSOR_PAIRS as part of Phase 23 scope (D-02 says this phase adds SchemaAccessor pair only) — note this is pre-existing absence, not a gap to fill this phase. However, if the executor adds the 2 spatial methods to `SpatialAccessor`, the accessor-level parity test would NOT automatically cover them unless the pair is registered. The planner should decide: (a) add `(SpatialAccessor, AsyncSpatialAccessor)` to ACCESSOR_PAIRS in the spatial-relocation plan, or (b) rely on TestAsyncParity and note the gap. Option (a) is safer and low-cost.

---

## Standard Stack

No new packages introduced. The Phase 21/22 pattern is fully in place.

### Reusable Assets (all verified present)

| Asset | Location | Status |
|-------|----------|--------|
| `@deprecated_alias(target_path)` decorator | `pycopg/aliases.py` | In place, reuse verbatim — no changes |
| `admin.py`/`maint.py`/`backup.py`/`timescale.py` module shape | `pycopg/` | Template for `schema.py` |
| Lazy `_timescale`/`_admin`/… cache fields + lazy properties | `database.py:83-86`, `async_database.py:80-84` | Replicate once for `_schema` |
| `ACCESSOR_PAIRS` + `test_accessor_parity` | `tests/test_parity.py:22-28` | Append `(SchemaAccessor, AsyncSchemaAccessor)` |
| `test_timescale_aliases.py` | `tests/` | DB-free MagicMock template |
| ~14 `queries.py` SQL constants | `pycopg/queries.py` | Travel unchanged (D-07) |
| `SpatialAccessor`/`AsyncSpatialAccessor` | `pycopg/spatial.py:1023/1859` | Already exists; 2 methods added as plain self._db.execute methods |

---

## Architecture Patterns

### System Architecture Diagram

```
User code
    │
    ├─► db.schema.create_database(...)  ──────────► SchemaAccessor.create_database(...)
    │                                                      │  self._db.config  (admin conn)
    │                                                      │  psycopg.connect(...)
    │
    ├─► db.schema.list_tables(...)  ──────────────► SchemaAccessor.list_tables(...)
    │                                                      │  self._db.execute(queries.LIST_TABLES, ...)
    │
    ├─► db.create_database(...)     ──[DEPRECATED]─► @deprecated_alias("schema.create_database")
    │    (old flat alias)                                  │  warns → delegates to db.schema
    │
    ├─► db.spatial.create_spatial_index(...)  ────► SpatialAccessor.create_spatial_index(...)
    │    (relocated from db.*)                             │  PostGIS guard at __init__ (sync)
    │                                                      │  self._db.execute(f"CREATE INDEX ...")
    │
    └─► db.create_spatial_index(...)  [DEPRECATED]─► @deprecated_alias("spatial.create_spatial_index")
         (old flat alias)                                  │  warns → self.spatial → guard → execute
```

### Recommended Project Structure (additions only)

```
pycopg/
├── schema.py          # NEW — SchemaAccessor + AsyncSchemaAccessor (27 methods each)
├── spatial.py         # MODIFIED — add create_spatial_index + list_geometry_columns to both classes
├── database.py        # MODIFIED — add _schema cache field + schema property + 29 @deprecated_alias stubs
├── async_database.py  # MODIFIED — same as database.py async mirror
└── __init__.py        # MODIFIED — add SchemaAccessor, AsyncSchemaAccessor to __all__

tests/
├── test_schema_aliases.py    # NEW — 27×2 DB-free alias tests
├── test_spatial_aliases.py   # NEW or extend existing spatial test module (2 alias tests)
└── test_parity.py            # MODIFIED — append (SchemaAccessor, AsyncSchemaAccessor)
```

### Pattern: schema.py module shape (copy of admin.py)

```python
# Source: pycopg/admin.py (verified template)
"""Schema accessor classes for db.schema.* / async_db.schema.*.

This module provides :class:`SchemaAccessor` and
:class:`AsyncSchemaAccessor` — the real implementation of the 27
DDL + introspection helper methods, moved verbatim from
``Database`` / ``AsyncDatabase`` as part of the v0.6.0 accessor
reorganisation (D-06).
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
    from pycopg.database import Database
    from pycopg.async_database import AsyncDatabase


class SchemaAccessor:
    """Schema helper namespace exposed as ``db.schema``."""

    def __init__(self, db: Database) -> None:
        """Store the parent database reference."""
        self._db = db

    def create_database(self, name, owner=None, template="template1"):
        """..."""
        # self.config → self._db.config
        admin_config = self._db.config.with_database("postgres")
        with psycopg.connect(**admin_config.connect_params(), autocommit=True) as conn:
            ...

    def list_tables(self, schema="public"):
        """..."""
        result = self._db.execute(queries.LIST_TABLES, [schema])
        return [r["table_name"] for r in result]
    # ... (24 more, all self.execute → self._db.execute)
```

### Pattern: Lazy property addition to Database (mirror of timescale/admin)

```python
# Source: pycopg/database.py:273-290 (TimescaleAccessor pattern, verified)

# In __init__:
self._schema: SchemaAccessor | None = None  # add alongside _timescale/_admin/…

# New lazy property:
@property
def schema(self) -> SchemaAccessor:
    """Get or create the schema accessor (lazy initialization)."""
    if self._schema is None:
        from pycopg.schema import SchemaAccessor
        self._schema = SchemaAccessor(self)
    return self._schema
```

### Pattern: @deprecated_alias stub (copy of existing Phase 21/22 stubs)

```python
# Source: pycopg/database.py:1724-1726 (verified template)
@deprecated_alias("schema.create_database")
def create_database(self, *args, **kwargs):
    """Deprecated: use ``db.schema.create_database`` instead."""
```

### Pattern: Spatial relocation into SpatialAccessor

```python
# In SpatialAccessor (sync) — verbatim move with self.execute → self._db.execute
def create_spatial_index(self, table, column="geometry", schema="public", name=None):
    """Create a GIST spatial index on a geometry column. ..."""
    validate_identifiers(table, column, schema)
    if name:
        validate_identifier(name)
    index_name = name or f"idx_{table}_{column}_gist"
    self._db.execute(f"""
        CREATE INDEX IF NOT EXISTS {index_name}
        ON {schema}.{table} USING GIST ({column})
    """)

# In AsyncSpatialAccessor — verbatim move + add _check_postgis call
async def create_spatial_index(self, table, column="geometry", schema="public", name=None):
    """..."""
    await self._check_postgis()  # ADD THIS — consistent with all other async spatial methods
    validate_identifiers(table, column, schema)
    if name:
        validate_identifier(name)
    index_name = name or f"idx_{table}_{column}_gist"
    await self._db.execute(f"""...""")
```

### Anti-Patterns to Avoid

- **Calling the deprecated flat alias from inside the accessor body:** e.g. if SchemaAccessor's body contains `self._db.create_database()` instead of `self._db.config.with_database(...)`. After Phase 23, `self._db.create_database()` is the deprecated alias — it will emit a DeprecationWarning and break the `-W error` gate.
- **Missing the 8 stay-flat call-site rewrites:** `from_dataframe`/`from_geodataframe` calling `self.add_primary_key`, `self.has_extension`, `self.create_spatial_index` — these MUST become `self.schema.X` / `self.spatial.X`.
- **Improving the 2 relocated spatial methods:** Do not extract queries.py builders, do not add `_run` routing. Move verbatim.
- **Adding `(SpatialAccessor, AsyncSpatialAccessor)` to ACCESSOR_PAIRS without the 2 methods:** If you add the pair, the parity test will fail unless both methods are present in both classes first.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Warn + delegate on 29 flat stubs | 29 custom wrapper functions | `@deprecated_alias` from `pycopg/aliases.py` | Already handles stacklevel, sync/async branching, lazy accessor resolution — proven in Phases 21/22 |
| Parity test infrastructure | New inspect-based test | `ACCESSOR_PAIRS` + `test_accessor_parity` | Already parametrized — append one tuple |
| Async guard in relocated methods | New guard mechanism | `await self._check_postgis()` (already in AsyncSpatialAccessor) | Pre-existing pattern at spatial.py:1879, used by every other async spatial method |

---

## Common Pitfalls

### Pitfall 1: Stay-flat caller rewrites missed
**What goes wrong:** `from_dataframe` (line 1503 sync, 1479 async) and `from_geodataframe` (lines 1583/1619/1622 sync, 1568/1607/1610 async) still call `self.add_primary_key`, `self.has_extension`, `self.create_spatial_index` after the move. At runtime under `-W error::DeprecationWarning`, these internal calls through the deprecated alias raise `DeprecationWarning` as an error.
**Why it happens:** These 2 DataFrame methods stay flat on `db.*` (by design), but their internal call-sites use moved methods.
**How to avoid:** Rewrite all 8 sites atomically in the same plan that stubs out the moved methods. Use the exact rewrite: `self.schema.add_primary_key`, `self.schema.has_extension`, `self.spatial.create_spatial_index`.
**Warning signs:** If Wave 2 (stubs) is merged without the call-site rewrites, `from_geodataframe` will fail the gate.

### Pitfall 2: AsyncSpatialAccessor _check_postgis omission
**What goes wrong:** The 2 relocated async methods are moved verbatim (just `self.execute` → `self._db.execute`) without adding `await self._check_postgis()`. Result: `async_db.spatial.create_spatial_index()` skips the PostGIS guard that every other async spatial method enforces.
**Why it happens:** The sync `SpatialAccessor` raises at `__init__` (line 1047), so sync bodies don't need an extra guard. The async `AsyncSpatialAccessor.__init__` does NOT raise (deferred to `_check_postgis()`), so async bodies must explicitly call it.
**How to avoid:** Add `await self._check_postgis()` as the first awaitable line in both async relocated methods.
**Warning signs:** Test `test_list_geometry_columns_without_postgis` (if run async) would not raise `ExtensionNotAvailable`.

### Pitfall 3: ACCESSOR_PAIRS SpatialAccessor claim
**What goes wrong:** Executor reads CONTEXT.md "SpatialAccessor pair is already registered" and does not add `(SpatialAccessor, AsyncSpatialAccessor)` to ACCESSOR_PAIRS, assuming it's already there. After relocation, `test_accessor_parity` does not cover the spatial accessor surface.
**Why it happens:** CONTEXT.md D-04 / code_context incorrectly states SpatialAccessor is already in ACCESSOR_PAIRS.
**How to avoid:** Verify `test_parity.py` ACCESSOR_PAIRS directly; decide whether to add the spatial pair in the spatial-relocation plan.
**Warning signs:** `grep "SpatialAccessor" tests/test_parity.py` returns nothing.

### Pitfall 4: `self.config` not rewritten in 3 database-level methods
**What goes wrong:** `create_database`, `drop_database`, `database_exists` access `self.config.with_database("postgres")`. After move into SchemaAccessor, `self.config` has no meaning — `AttributeError`.
**Why it happens:** Easy to overlook since 24 of 27 methods only use `self.execute` and look identical. These 3 are structurally different.
**How to avoid:** `self.config` → `self._db.config` in all 3 bodies (sync + async).

### Pitfall 5: `test_parity.py` TestAsyncParity catch during transition
**What goes wrong:** `TestAsyncParity.test_all_database_public_methods_exist_in_async` and `test_known_exceptions_documented` scan `inspect.getmembers(Database)` vs `AsyncDatabase`. If sync stubs are added (Wave 2 sync) before async stubs, parity test fails.
**Why it happens:** Async and sync stubs must be deployed together in Wave 2.
**How to avoid:** Within Wave 2, add both sync AND async stubs + cache fields + properties in the same commit.

---

## Test / Gate Surface

### Existing test call-sites to migrate (after Wave 2 stubs added)

**`tests/test_database.py`** — uses flat names for: `list_schemas` (line 270), `schema_exists` (287, 304), `list_tables` (328), `table_exists` (345), `table_info` (657), `row_count` (675), `has_extension` (696, 711), `list_extensions` (729), `truncate_table` (1035), `list_indexes` (1059), `list_constraints` (1084), `drop_table` (1105, 1124), `create_schema` (1146), `drop_schema` (1165), `list_columns` (1185), `columns_with_types` (1204), `list_databases` (1401).

**`tests/test_async_database.py`** — uses flat names for: `list_schemas` (280), `schema_exists` (295, 310), `list_tables` (334), `table_exists` (349), `list_columns` (434), `columns_with_types` (453), `has_extension` (738, 745, 757, 775, 793, 811, 832), `create_spatial_index` (794, 812, 833, 840, 2200, 2212, 2223), `drop_table` (854, 865), `create_index` (876, 888), `drop_index` (900), `list_indexes` (924), `list_constraints` (952), `drop_schema` (967, 978), `create_database` (1039, 1066), `drop_database` (1090, 1123), `list_geometry_columns` (2245, 2263).

**`tests/test_database_integration.py`** — uses: `table_exists` (73, 186, 195, 276, 349, 352), `list_schemas` (164), `list_tables` (178), `table_info` (208), `schema_exists` (218, 219, 409, 425, 428, 431), `drop_table` (352, 742, 743, 745), `create_index` (369, 386), `list_indexes` (372, 388, 396), `drop_index` (393), `create_schema` (406), `drop_schema` (428, 750, 753), `list_extensions` (532, 548), `create_extension` (545, 843), `has_extension` (820, 841, 846), `add_foreign_key` (683, 692, 694), `add_unique_constraint` (701), `truncate_table` (719), `database_exists` (725, 726), `list_databases` (727), `drop_extension` (733, 734), `drop_table` (742), `row_count` (809).

**`tests/test_sql_injection.py`** — uses: `create_spatial_index` (72, 77, 168), `drop_index` (67, 162), `create_extension` (91, 100, 185), `drop_extension` (104, 108, 190), `has_extension` (55).

**`tests/test_postgis_errors.py`** — uses: `create_spatial_index` (38, 59, 128, 160), `list_geometry_columns` (84, 102).

**`tests/test_spatial.py`** — uses: `has_extension` (542).

**`tests/test_parity.py`** — uses: `add_primary_key` (350), `truncate_table` (370/376), `database_exists` (388), `list_databases` (397), `create_schema` (466), `schema_exists` (468/469), `drop_database` (508/509).

**Note on the flaky test:** `test_create_spatial_index_name_parameter` (test_postgis_errors.py:112) calls `db.create_spatial_index(...)` directly. After Phase 23, this call goes through the deprecated alias and then into the PostGIS-guarded SpatialAccessor. If PostGIS is absent the test still skips (line 115: `if not has_postgis(db_config): pytest.skip(...)`). The relocation does NOT change the test's flakiness profile — it was fixture-isolation (UndefinedTable), not PostGIS-related.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (with pytest-asyncio) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command (no DB) | `uv run pytest tests/test_schema_aliases.py tests/test_spatial_aliases.py tests/test_parity.py -x -q -o addopts=""` |
| Full suite command | `uv run pytest` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SCH-01 | `db.schema.create_database()` returns same results | DB-live (via `TestBehavioralParity`) | `uv run pytest tests/test_parity.py -x -q -o addopts=""` | Exists (parity infra) |
| SCH-01 | All 27 flat aliases warn + delegate | DB-free alias test | `uv run pytest tests/test_schema_aliases.py -x -q -o addopts=""` | Wave 0 gap |
| SCH-01 | `ACCESSOR_PAIRS` parity check passes for `(SchemaAccessor, AsyncSchemaAccessor)` | Unit | `uv run pytest tests/test_parity.py::test_accessor_parity -x -q -o addopts=""` | After Wave 3 append |
| SCH-02 | `db.spatial.create_spatial_index()` and `list_geometry_columns()` work | DB-live | `uv run pytest tests/test_postgis_errors.py -x -q -o addopts=""` | Exists (will need migration) |
| SCH-02 | 2 flat spatial aliases warn + delegate | DB-free alias test | `uv run pytest tests/test_spatial_aliases.py -x -q -o addopts=""` | Wave 0 gap |
| REORG-04 | No internal DeprecationWarning under `-W error` | Gate | `uv run pytest -W error::DeprecationWarning -o addopts=""` | Enabled by call-site migration |
| REORG-04 | Coverage ≥ 94% | Coverage gate | `uv run pytest` (full suite) | Existing gate |

### -W error::DeprecationWarning gate

This is NOT a pyproject.toml `filterwarnings` setting — it is applied at test-run time:

```bash
uv run pytest -W error::DeprecationWarning tests/ -o addopts=""
```

This gate catches:
1. Any test that calls a moved flat method without migrating to the accessor path → test itself raises `DeprecationWarning` as error.
2. Internal call-sites in `from_dataframe`/`from_geodataframe` that still use `self.add_primary_key` etc. after Wave 2 stubs.
3. Any accessor body that calls `self._db.<deprecated-flat-name>()` instead of `self._db.schema.<method>()`.

### Sampling Rate

- **Per task commit:** `uv run pytest tests/test_schema_aliases.py tests/test_parity.py -x -q -o addopts=""`
- **Per wave merge:** `uv run pytest -W error::DeprecationWarning -o addopts=""` (targeted gate)
- **Phase gate:** Full suite `uv run pytest` (coverage ≥ 94% enforced by `--cov-fail-under=94`)

### Wave 0 Gaps

- [ ] `tests/test_schema_aliases.py` — DB-free alias tests for all 27 schema method aliases (sync + async), following `test_timescale_aliases.py` template. Must assert warn + stacklevel + delegate for each.
- [ ] `tests/test_spatial_aliases.py` (or extend existing spatial test module) — 2 alias tests for `create_spatial_index` + `list_geometry_columns`.
- [ ] `pycopg/schema.py` — new module with `SchemaAccessor` + `AsyncSchemaAccessor` (Wave 1 deliverable, but planner needs to include its creation as an explicit task).

*(If no gaps: "None — existing test infrastructure covers all phase requirements")*

---

## Code Examples

### Alias test template (from test_timescale_aliases.py — verified)

```python
# Source: tests/test_timescale_aliases.py (verified pattern)
class TestSchemaAliases:
    @pytest.mark.parametrize("name", list(_SYNC_ALIAS_ARGS.keys()))
    def test_sync_alias_warns_and_delegates(self, name, config):
        db = Database(config)
        mock_accessor = MagicMock(spec=SchemaAccessor)
        db._schema = mock_accessor  # inject mock into cache field
        args = _SYNC_ALIAS_ARGS[name]
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            getattr(db, name)(*args)
        alias_warnings = [
            rec for rec in w
            if rec.category is DeprecationWarning
            and f"db.schema.{name}" in str(rec.message)
        ]
        assert len(alias_warnings) == 1
        assert "v0.7.0" in str(alias_warnings[0].message)
        assert "test_" in os.path.basename(alias_warnings[0].filename)
        getattr(mock_accessor, name).assert_called_once_with(*args)
```

### Async alias test — AsyncMock required per method

```python
# Source: tests/test_timescale_aliases.py:133-139 (verified pattern)
db = AsyncDatabase(config)
mock_accessor = MagicMock(spec=AsyncSchemaAccessor)
for method_name in _ASYNC_ALIAS_ARGS:
    setattr(mock_accessor, method_name, AsyncMock())
db._schema = mock_accessor  # inject
```

### @deprecated_alias stubs (verified from database.py:1724-1726 pattern)

```python
@deprecated_alias("schema.create_database")
def create_database(self, *args, **kwargs):
    """Deprecated: use ``db.schema.create_database`` instead."""

# ... 26 more schema stubs ...

@deprecated_alias("spatial.create_spatial_index")
def create_spatial_index(self, *args, **kwargs):
    """Deprecated: use ``db.spatial.create_spatial_index`` instead."""

@deprecated_alias("spatial.list_geometry_columns")
def list_geometry_columns(self, *args, **kwargs):
    """Deprecated: use ``db.spatial.list_geometry_columns`` instead."""
```

---

## Open Questions (RESOLVED)

> Both questions below were resolved during planning (2026-06-17). Resolutions are encoded in the
> Phase 23 plans; the recommendations were adopted as-is. Kept here for provenance — NOT open.

1. **Should `(SpatialAccessor, AsyncSpatialAccessor)` be added to `ACCESSOR_PAIRS` in Phase 23?**
   - What we know: It is NOT currently there (CONTEXT.md wrong). The spatial relocation plan adds 2 methods to both classes.
   - What's unclear: Is adding the pair in scope for Phase 23's spatial-relocation plan or deferred to Phase 24?
   - Recommendation: Add it in the spatial-relocation plan (it is low-cost, already-existing classes, and the pair would then be tested via `test_accessor_parity` like all others). The planner should include one task for it.
   - **RESOLVED:** Adopted — see **plan 23-03 task 3** (adds the import + `(SpatialAccessor, AsyncSpatialAccessor)` tuple to `ACCESSOR_PAIRS`). In scope for Phase 23, not deferred.

2. **Should async `create_spatial_index`/`list_geometry_columns` in `AsyncSpatialAccessor` call `await self._check_postgis()`?**
   - What we know: All other async spatial methods call `_check_postgis()`. D-06 says "accept the changed failure mode." The sync path guards at `__init__`, the async path guards per-method.
   - What's unclear: Is this a "move verbatim" (skip `_check_postgis()`) or "move to be consistent with the class" (add it)?
   - Recommendation: Add `await self._check_postgis()` for consistency with all other async spatial methods. D-06's "accept the changed failure mode" refers to the behavior vs the OLD flat path (no guard at all), not an instruction to skip the class's own consistency. This is a one-line addition per async method body.
   - **RESOLVED:** Adopted — see **plan 23-03 task 1** (mandates `await self._check_postgis()` as the first awaitable line of both relocated async methods; sync versions inherit the constructor guard per D-06).

---

## Environment Availability

Step 2.6: SKIPPED (no external dependencies — this phase is pure Python/library code changes only).

---

## Security Domain

This phase moves existing methods into accessor namespaces. All input validation (`validate_identifier`, `validate_identifiers`, `validate_extension_name`) travels verbatim with the moved bodies. No new SQL construction patterns are introduced. Security domain is unchanged from current baseline — no ASVS category materially changes.

---

## Project Constraints (from CLAUDE.md)

- `pycopg` is an independent generic PyPI library — no dependencies on Solaris/MarketStream/Kala.
- Use independent venv: `pycopg/venv/` (via `uv sync --all-extras --dev`).
- Tests: `uv run pytest tests/ -x -q` (quick) / `uv run pytest` (full with coverage gate).
- Lint: `uv run ruff check pycopg tests`.
- Format: `uv run black pycopg tests`.
- `--cov-fail-under=94` is enforced — every new alias stub must be exercised by DB-free alias tests.

---

## Sources

### Primary (HIGH confidence)
- `pycopg/database.py` — live source, AST-verified line numbers and self.X references
- `pycopg/async_database.py` — live source, full method enumeration
- `pycopg/spatial.py` — live source, SpatialAccessor/AsyncSpatialAccessor constructor guard
- `pycopg/aliases.py` — live source, `@deprecated_alias` decorator
- `pycopg/admin.py` — live source, template module shape
- `tests/test_parity.py` — live source, `ACCESSOR_PAIRS` actual contents
- `tests/test_timescale_aliases.py` — live source, alias test template

### Secondary (HIGH confidence — planning docs)
- `.planning/phases/23-schema-accessor-spatial-relocation/23-CONTEXT.md`
- `.planning/phases/21-infrastructure-timescale-accessor/21-CONTEXT.md`
- `.planning/phases/22-admin-maint-backup-accessors/22-CONTEXT.md`
- `.planning/REQUIREMENTS.md`

---

## Metadata

**Confidence breakdown:**
- Method count (27/29): HIGH — AST-verified against live source
- Self.X enumeration: HIGH — exhaustive AST scan, zero sibling calls confirmed
- D-05 call-sites (8): HIGH — grep-verified exact lines in both files
- Spatial guard semantics: HIGH — read spatial.py source directly
- ACCESSOR_PAIRS state: HIGH — read test_parity.py directly
- AsyncSpatialAccessor _check_postgis nuance: HIGH — read method bodies in spatial.py

**Research date:** 2026-06-17
**Valid until:** 2026-07-17 (30 days — stable codebase, no fast-moving dependencies)

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Adding `await self._check_postgis()` to async relocated methods is the correct interpretation of D-06 | Pitfall 2 / Open Questions | If skipped, async path has inconsistent guard behavior; pre-existing flaky test `test_create_spatial_index_name_parameter` exercises sync path only |

**All other claims were directly verified against live source code. The assumptions table is minimal.**
