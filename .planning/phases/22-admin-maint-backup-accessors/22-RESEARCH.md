# Phase 22: Admin, Maint & Backup Accessors - Research

**Researched:** 2026-06-17
**Domain:** Accessor pattern replication — Phase 21 pattern applied to admin (11), maint (6), backup (4) methods
**Confidence:** HIGH — all findings verified directly from live source files

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01 (method count):** Admin has **11 methods**, not 12. Total phase = **21 flat names** (11+6+4). Validate against 21, not 22.
- **D-02 (sibling calls):** `create_role` body calls `self.role_exists(...)` and `self.grant_role(...)` — both admin siblings. After move, rewrite to `self._db.admin.role_exists(...)` / `self._db.admin.grant_role(...)`, NOT `self._db.role_exists(...)`.
- **D-03 (rewrite rule):** Sibling-accessor `self.X(...)` → `self._db.<accessor>.X(...)`; core-flat `self.Y(...)` → `self._db.Y(...)`.
- **D-04 (3-wave structure):** W1=create modules, W2=wire properties+stubs, W3=tests+migration+gates.
- **D-05 (parallel within wave):** 3 accessors are independent within each wave; shared touch-points (init fields, `__init__.py`, `ACCESSOR_PAIRS`) concentrated in W2/W3.
- **D-06 (verbatim move):** Move bodies verbatim; rewrite `self.` references only. No SQL extraction, no new helpers.
- From Phase 21 D-01..D-10 (all carried forward): decorator shape, verbatim-move, dedicated module per accessor, lazy cached property, DB-free MagicMock alias tests, `ACCESSOR_PAIRS` registry, one-line stub docstrings, `stacklevel=2`.

### Claude's Discretion

- Exact per-accessor test-module naming/layout (follow `test_timescale_aliases.py`).
- Whether the 3 alias test modules are 3 files or one parametrized module.
- Order of the 3 accessors within each wave (independent).
- `from __future__ import annotations` + `TYPE_CHECKING` import guards — follow `timescale.py`.

### Deferred Ideas (OUT OF SCOPE)

- `db.schema.*` (~26 methods) + spatial-index relocation — Phase 23.
- Public exports hardening / README / Sphinx / CHANGELOG / MIGRATION / version bump / PyPI — Phase 24.
- Opportunistic `queries.py` builder extraction — intentionally NOT done (D-06).
- Cosmetic ROADMAP "12/22" → "11/21" text fix — Phase 24 doc pass.
- Alias removal — v0.7.0.
- New admin/maint/backup power.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ADM-01 | `db.admin.*` / `async_db.admin.*` exposes 11 role & permission methods; flat `db.*` names remain as deprecated aliases | D-03 self-call table, import matrix, wiring touch-points |
| MNT-01 | `db.maint.*` / `async_db.maint.*` exposes 6 maintenance/size methods; flat `db.*` names remain as deprecated aliases | D-03 self-call table, import matrix, wiring touch-points |
| BKP-01 | `db.backup.*` / `async_db.backup.*` exposes 4 dump/restore/CSV methods; flat `db.*` names remain as deprecated aliases | D-03 self-call table, `_psql_restore` companion, subprocess pattern |
</phase_requirements>

---

## Summary

Phase 22 is a mechanical replication of the Phase 21 `@deprecated_alias` pattern, applied three times (admin, maint, backup). The core infrastructure (`aliases.py`, `timescale.py` skeleton, `ACCESSOR_PAIRS`, test template) already exists. There is one substantive departure from Phase 21: two sibling self-calls inside `AdminAccessor.create_role` that must be rewritten to `self._db.admin.X(...)`. There is also one structural wrinkle: `pg_restore` calls the private `_psql_restore` helper — both must move together into `BackupAccessor`, with `self._psql_restore(...)` remaining as-is (private sibling call within the same accessor class).

The backup methods (`pg_dump`, `pg_restore`, `_psql_restore`) use `subprocess` / `asyncio.create_subprocess_exec` instead of `self._db.execute(...)`. This is valid and the rewrite rule still applies normally: all `self.config.*` attribute accesses become `self._db.config.*`, and `self.cursor()` becomes `self._db.cursor()`. No `self.execute(...)` appears in backup bodies — the subprocess pattern is complete.

**Primary recommendation:** Apply the Phase 21 template verbatim for all 21 methods. The only human decisions are (a) the two sibling-call rewrites in `create_role`, (b) moving `_psql_restore` as an unlisted private companion of `pg_restore` into `BackupAccessor`, and (c) rewriting `self._psql_restore(...)` inside `pg_restore` to remain `self._psql_restore(...)` (not `self._db.*`) because both are on the same accessor.

---

## D-03 Self-Call Classification Table

> This is the primary deliverable of this research. Every cell is verified from live source. "No self-calls" entries are explicit, not omitted.

Legend:
- **(A) Sibling-accessor** — `self.X(...)` where X is one of the 21 methods being moved into the SAME accessor. Rewrite to `self._db.<accessor>.X(...)`
- **(B) Core-flat** — `self.Y(...)` where Y stays flat on `db.*`. Rewrite to `self._db.Y(...)`
- **(C) Cross-accessor** — `self.Z(...)` where Z moves into a DIFFERENT accessor. Rewrite to `self._db.<other_accessor>.Z(...)`
- **(P) Private companion** — `self._X(...)` where `_X` is a private helper that also moves into the same accessor class. Stays as `self._X(...)` — no rewrite needed.

### Admin Accessor (11 methods)

| Method | File | Self-call found | Bucket | Rewrite target |
|--------|------|-----------------|--------|----------------|
| `create_role` | `database.py:1854` | `self.role_exists(name)` | A | `self._db.admin.role_exists(name)` |
| `create_role` | `database.py:1854` | `self.grant_role(role, name)` (in loop) | A | `self._db.admin.grant_role(role, name)` |
| `create_role` | `database.py:1854` | `self.cursor(autocommit=True)` (for password path) | B | `self._db.cursor(autocommit=True)` |
| `create_role` | `database.py:1854` | `self.execute(...)` (no-password path) | B | `self._db.execute(...)` |
| `drop_role` | `database.py:1928` | `self.execute(...)` | B | `self._db.execute(...)` |
| `role_exists` | `database.py:1942` | `self.execute(...)` | B | `self._db.execute(...)` |
| `list_roles` | `database.py:1958` | `self.execute(...)` | B | `self._db.execute(...)` |
| `alter_role` | `database.py:1974` | `self.execute(...)` (rename branch) | B | `self._db.execute(...)` |
| `alter_role` | `database.py:1974` | `self.cursor(autocommit=True)` (options branch) | B | `self._db.cursor(autocommit=True)` |
| `grant_role` | `database.py:2043` | `self.execute(...)` | B | `self._db.execute(...)` |
| `revoke_role` | `database.py:2059` | `self.execute(...)` | B | `self._db.execute(...)` |
| `grant` | `database.py:2072` | `self.execute(...)` (4 branches) | B | `self._db.execute(...)` |
| `revoke` | `database.py:2133` | `self.execute(...)` (4 branches) | B | `self._db.execute(...)` |
| `list_role_members` | `database.py:2193` | `self.execute(...)` | B | `self._db.execute(...)` |
| `list_role_grants` | `database.py:2209` | `self.execute(...)` | B | `self._db.execute(...)` |

**Async parity (async_database.py):**

| Method | Lines | Self-calls | Bucket | Rewrite target |
|--------|-------|------------|--------|----------------|
| `create_role` | `1309` | `await self.role_exists(name)` | A | `await self._db.admin.role_exists(name)` |
| `create_role` | `1309` | `await self.grant_role(role, name)` (in loop) | A | `await self._db.admin.grant_role(role, name)` |
| `create_role` | `1309` | `async with self.cursor(autocommit=True)` (password path) | B | `self._db.cursor(autocommit=True)` |
| `create_role` | `1309` | `await self.execute(...)` (no-password path) | B | `self._db.execute(...)` |
| `drop_role` | `1385` | `await self.execute(...)` | B | `self._db.execute(...)` |
| `role_exists` | `1273` | `await self.execute(...)` | B | `self._db.execute(...)` |
| `list_roles` | `1289` | `await self.execute(...)` | B | `self._db.execute(...)` |
| `alter_role` | `1399` | `await self.execute(...)` (rename) | B | `self._db.execute(...)` |
| `alter_role` | `1399` | `async with self.cursor(autocommit=True)` | B | `self._db.cursor(autocommit=True)` |
| `grant_role` | `1591` | `await self.execute(...)` | B | `self._db.execute(...)` |
| `revoke_role` | `1609` | `await self.execute(...)` | B | `self._db.execute(...)` |
| `grant` | `1470` | `await self.execute(...)` (4 branches) | B | `self._db.execute(...)` |
| `revoke` | `1531` | `await self.execute(...)` (4 branches) | B | `self._db.execute(...)` |
| `list_role_members` | `1622` | `await self.execute(...)` | B | `self._db.execute(...)` |
| `list_role_grants` | `1638` | `await self.execute(...)` | B | `self._db.execute(...)` |

**Cross-accessor calls:** None found in admin methods.

---

### Maint Accessor (6 methods)

| Method | File | Self-call found | Bucket | Rewrite target |
|--------|------|-----------------|--------|----------------|
| `size` | `database.py:1697` | `self.execute(...)` (×2, pretty/raw branches) | B | `self._db.execute(...)` |
| `size` | `database.py:1697` | `self.config.database` (attribute, not method) | B | `self._db.config.database` |
| `table_size` | `database.py:1720` | `self.execute(...)` (×2) | B | `self._db.execute(...)` |
| `table_sizes` | `database.py:1747` | `self.execute(...)` | B | `self._db.execute(...)` |
| `vacuum` | `database.py:1769` | `self.execute(...)` | B | `self._db.execute(...)` |
| `analyze` | `database.py:1803` | `self.execute(...)` | B | `self._db.execute(...)` |
| `explain` | `database.py:1818` | `self.execute(...)` | B | `self._db.execute(...)` |

No sibling-accessor calls, no cross-accessor calls in maint methods.

**Async parity (`async_database.py`):**

| Method | Lines | Self-calls | Bucket | Rewrite target |
|--------|-------|------------|--------|----------------|
| `size` | `1657` | `await self.execute(...)` (×2) + `self.config.database` | B | `self._db.execute(...)` / `self._db.config.database` |
| `table_size` | `1680` | `await self.execute(...)` (×2) | B | `self._db.execute(...)` |
| `table_sizes` | `1707` | `await self.execute(...)` | B | `self._db.execute(...)` |
| `vacuum` | `2168` | `await self.execute(...)` | B | `self._db.execute(...)` |
| `analyze` | `2202` | `await self.execute(...)` | B | `self._db.execute(...)` |
| `explain` | `2217` | `await self.execute(...)` | B | `self._db.execute(...)` |

**Note on async maint layout:** `size`, `table_size`, `table_sizes` appear at lines 1657–1723 (between timescale stubs and DataFrame operations). `vacuum`, `analyze`, `explain` appear at lines 2168–2247 (after `create_database`/`drop_database` block). Both groups form the full MaintAccessor surface. No self-calls between the two clusters.

---

### Backup Accessor (4 public methods + 1 private companion)

| Method | File | Self-call found | Bucket | Rewrite target |
|--------|------|-----------------|--------|----------------|
| `pg_dump` | `database.py:2228` | `self.config.*` (host/port/user/database/password) | B (attr) | `self._db.config.*` |
| `pg_dump` | `database.py:2228` | NO `self.execute()` — uses `subprocess.run(...)` | — | no rewrite; `import subprocess` stays local |
| `pg_restore` | `database.py:2291` | `self._psql_restore(input_file)` | P | stays `self._psql_restore(input_file)` — private companion moves to same accessor |
| `pg_restore` | `database.py:2291` | `self.config.*` (host/port/user/database/password) | B (attr) | `self._db.config.*` |
| `pg_restore` | `database.py:2291` | NO `self.execute()` — uses `subprocess.run(...)` | — | no rewrite |
| `_psql_restore` | `database.py:2369` | `self.config.*` (host/port/user/database/password) | B (attr) | `self._db.config.*` |
| `_psql_restore` | `database.py:2369` | NO `self.execute()` — uses `subprocess.run(...)` | — | no rewrite |
| `copy_to_csv` | `database.py:2395` | `self.cursor()` | B | `self._db.cursor()` |
| `copy_to_csv` | `database.py:2395` | `self.execute(...)` (row count SELECT) — WAIT: uses `cur.execute(...)` directly on cursor, not `self.execute()` | — | `cur.execute(...)` stays as-is (cursor-level, not db-level) |
| `copy_from_csv` | `database.py:2469` | `self.cursor()` | B | `self._db.cursor()` |
| `copy_from_csv` | `database.py:2469` | cursor-level `cur.execute(...)` / `cur.rowcount` | — | stays as-is |

**Async backup (`async_database.py`):**

| Method | Lines | Self-calls | Bucket | Rewrite target |
|--------|-------|------------|--------|----------------|
| `pg_dump` | `2253` | `self.config.*` | B (attr) | `self._db.config.*` |
| `pg_dump` | `2253` | `asyncio.create_subprocess_exec(...)` — NOT `self.execute()` | — | no rewrite |
| `pg_restore` | `2322` | `await self._psql_restore(input_file)` | P | stays `await self._psql_restore(input_file)` |
| `pg_restore` | `2322` | `self.config.*` | B (attr) | `self._db.config.*` |
| `_psql_restore` | `2406` | `self.config.*` | B (attr) | `self._db.config.*` |
| `copy_to_csv` | `2438` | `async with self.cursor()` | B | `self._db.cursor()` |
| `copy_to_csv` | `2438` | `await self.execute(...)` (row count SELECT) | B | `self._db.execute(...)` |
| `copy_from_csv` | `2524` | `async with self.cursor()` | B | `self._db.cursor()` |

**Cross-accessor calls:** None found in backup methods.

---

### Summary: Sibling-accessor rewrites required (Bucket A only)

| File | Method | `self.X(...)` | Rewrite to |
|------|--------|---------------|------------|
| `database.py` | `create_role` | `self.role_exists(name)` | `self._db.admin.role_exists(name)` |
| `database.py` | `create_role` | `self.grant_role(role, name)` | `self._db.admin.grant_role(role, name)` |
| `async_database.py` | `create_role` | `await self.role_exists(name)` | `await self._db.admin.role_exists(name)` |
| `async_database.py` | `create_role` | `await self.grant_role(role, name)` | `await self._db.admin.grant_role(role, name)` |

**Total Bucket A occurrences: 4 (2 sync + 2 async). All in `create_role`. Zero Bucket A in maint or backup.**

---

## Import Matrix for New Modules

Each new module (`admin.py`, `maint.py`, `backup.py`) needs specific imports. The template is `timescale.py` which uses:
- `from __future__ import annotations`
- `from typing import TYPE_CHECKING`
- `from pycopg import queries`
- `from pycopg.exceptions import ExtensionNotAvailable`
- `from pycopg.utils import validate_identifier, validate_identifiers, validate_interval`
- `if TYPE_CHECKING:` guard for `Database` / `AsyncDatabase`

[VERIFIED: live source `pycopg/timescale.py:1-23`]

### `pycopg/admin.py` imports needed

```python
from __future__ import annotations
from typing import TYPE_CHECKING
from pycopg import queries
from pycopg.base import build_role_options
from pycopg.utils import (
    validate_identifier,
    validate_identifiers,
    validate_object_type,
    validate_privileges,
    validate_timestamp,
)
if TYPE_CHECKING:
    from pycopg.database import Database
    from pycopg.async_database import AsyncDatabase
```

**`queries` constants used by admin bodies:**
- `queries.ROLE_EXISTS` — `role_exists`
- `queries.LIST_ROLES` — `list_roles` (uses `.format(where_clause=...)`)
- `queries.LIST_ROLE_MEMBERS` — `list_role_members`
- `queries.LIST_ROLE_GRANTS` — `list_role_grants`

**`utils` validators used by admin bodies:**
- `validate_identifier` — `create_role`, `drop_role`, `alter_role`, `grant`, `revoke`
- `validate_identifiers` — `grant_role`, `revoke_role`, `grant`, `revoke`
- `validate_object_type` — `grant`, `revoke`
- `validate_privileges` — `grant`, `revoke`
- `validate_timestamp` — `alter_role` (valid_until branch)

**`base` helpers used by admin bodies:**
- `build_role_options` — `create_role`, `alter_role` — imported from `pycopg.base`

**No exceptions from `pycopg.exceptions` required by admin bodies.** (No `ExtensionNotAvailable` guards — admin methods have no extension dependency.)

[VERIFIED: live source `database.py:1854-2222`, `async_database.py:1273-1651`]

### `pycopg/maint.py` imports needed

```python
from __future__ import annotations
from typing import TYPE_CHECKING
from pycopg import queries
from pycopg.utils import validate_identifiers
if TYPE_CHECKING:
    from pycopg.database import Database
    from pycopg.async_database import AsyncDatabase
```

**`queries` constants used by maint bodies:**
- `queries.DATABASE_SIZE_PRETTY` — `size` (pretty=True)
- `queries.DATABASE_SIZE` — `size` (pretty=False)
- `queries.TABLE_SIZE_PRETTY` — `table_size` (pretty=True)
- `queries.TABLE_SIZE` — `table_size` (pretty=False)
- `queries.TABLE_SIZES` — `table_sizes`

**`utils` validators used by maint bodies:**
- `validate_identifiers` — `table_size`, `table_sizes` (implicit via `validate_identifiers(table, schema)` in `vacuum` and `analyze` when table is not None)

**No `base` helpers, no exceptions needed.**

[VERIFIED: live source `database.py:1697-1848`]

### `pycopg/backup.py` imports needed

```python
from __future__ import annotations
import os
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from collections.abc import Sequence   # only if needed — check body signatures
from pycopg.base import build_pg_dump_cmd, build_pg_restore_cmd
from pycopg.utils import validate_identifiers, validate_csv_option
if TYPE_CHECKING:
    from pycopg.database import Database
    from pycopg.async_database import AsyncDatabase
```

**Note on `asyncio` import (async backup):** The async backup bodies use `asyncio.create_subprocess_exec`, `asyncio.subprocess.PIPE`, `asyncio.to_thread`. In `async_database.py` these are top-level `import asyncio`. The `AsyncBackupAccessor` class in `backup.py` must import `asyncio` at module level (not inside method bodies as in the sync `pg_dump`/`pg_restore` which do `import subprocess` locally).

**`base` helpers used by backup bodies:**
- `build_pg_dump_cmd` — `pg_dump`
- `build_pg_restore_cmd` — `pg_restore`

**`utils` validators used by backup bodies:**
- `validate_identifiers` — `copy_to_csv`, `copy_from_csv`
- `validate_csv_option` — `copy_to_csv`, `copy_from_csv`

**No `queries` constants, no exceptions from exceptions.py needed.**

[VERIFIED: live source `database.py:2228-2534`, `async_database.py:2253-2597`]

### Circular-import safety

All three new modules import from `pycopg.base`, `pycopg.utils`, `pycopg.queries`, and `pycopg.exceptions` — the same pattern used by `timescale.py`. None of these import from `pycopg.database` or `pycopg.async_database` at module level. `Database`/`AsyncDatabase` are under `TYPE_CHECKING` only. This is the exact pattern that prevents circular imports, already validated by `timescale.py`.

[VERIFIED: `timescale.py:13-23`]

---

## Wiring Touch-Points

### `database.py` wiring (W2)

**Cache fields in `__init__` (currently line 88 area):**

Current state (verified):
```python
# database.py:84-88
self._engine: Engine | None = None
self._session_conn: psycopg.Connection | None = None
self._spatial: SpatialAccessor | None = None
self._etl: ETLAccessor | None = None
self._timescale: TimescaleAccessor | None = None  # line 88
```

Add after line 88:
```python
self._admin: AdminAccessor | None = None
self._maint: MaintAccessor | None = None
self._backup: BackupAccessor | None = None
```

**`TYPE_CHECKING` block (currently `database.py:54-60`):**

Current:
```python
if TYPE_CHECKING:
    import geopandas as gpd
    import pandas as pd
    from pycopg.etl import ETLAccessor
    from pycopg.spatial import SpatialAccessor
    from pycopg.timescale import TimescaleAccessor
```

Add:
```python
    from pycopg.admin import AdminAccessor
    from pycopg.maint import MaintAccessor
    from pycopg.backup import BackupAccessor
```

**Lazy property blocks — template (timescale, `database.py:275-292`):**

```python
@property
def timescale(self) -> TimescaleAccessor:
    """..."""
    if self._timescale is None:
        from pycopg.timescale import TimescaleAccessor
        self._timescale = TimescaleAccessor(self)
    return self._timescale
```

Replicate 3× for `admin`/`maint`/`backup` after the `timescale` property block.

**`@deprecated_alias` stubs — template (`database.py:1669-1691`):**

Exact current lines:
```python
@deprecated_alias("timescale.create_hypertable")
def create_hypertable(self, *args, **kwargs):
    """Deprecated: use ``db.timescale.create_hypertable`` instead."""

@deprecated_alias("timescale.enable_compression")
def enable_compression(self, *args, **kwargs):
    """Deprecated: use ``db.timescale.enable_compression`` instead."""
# ... 4 more
```

Replicate this pattern for all 21 methods, replacing the full method bodies at their current locations.

[VERIFIED: `database.py:84-88`, `database.py:54-60`, `database.py:275-292`, `database.py:1669-1691`]

### `async_database.py` wiring (W2)

**Cache fields in `__init__` (currently `async_database.py:85-87`):**

Current state (verified):
```python
# async_database.py:83-87
self._session_conn: AsyncConnection | None = None
self._async_engine: AsyncEngine | None = None
self._spatial: AsyncSpatialAccessor | None = None
self._etl: AsyncETLAccessor | None = None
self._timescale: AsyncTimescaleAccessor | None = None  # line 87
```

Add `_admin`, `_maint`, `_backup` cache fields after line 87.

**`TYPE_CHECKING` block (`async_database.py:53-60`):**

Current:
```python
if TYPE_CHECKING:
    import geopandas as gpd
    import pandas as pd
    from sqlalchemy.ext.asyncio import AsyncEngine
    from pycopg.etl import AsyncETLAccessor
    from pycopg.spatial import AsyncSpatialAccessor
    from pycopg.timescale import AsyncTimescaleAccessor
```

Add `AsyncAdminAccessor`, `AsyncMaintAccessor`, `AsyncBackupAccessor`.

**Lazy property blocks — template (`async_database.py:135-152`):**

```python
@property
def timescale(self) -> AsyncTimescaleAccessor:
    """..."""
    if self._timescale is None:
        from pycopg.timescale import AsyncTimescaleAccessor
        self._timescale = AsyncTimescaleAccessor(self)
    return self._timescale
```

Replicate 3× for `admin`/`maint`/`backup`.

**`@deprecated_alias` stubs — template (`async_database.py:1245-1267`):**

```python
@deprecated_alias("timescale.create_hypertable")
async def create_hypertable(self, *args, **kwargs):
    """Deprecated: use ``async_db.timescale.create_hypertable`` instead."""
# ... 5 more
```

Note: the async stubs use `async def` — the `@deprecated_alias` decorator handles the `await` internally (verified in `aliases.py:44-52`). Add 21 async stubs in the same style.

[VERIFIED: `async_database.py:83-87`, `async_database.py:53-60`, `async_database.py:135-152`, `async_database.py:1245-1267`]

### `pycopg/__init__.py` wiring (W2)

Current exports (verified `__init__.py:27-61`):
```python
from pycopg.timescale import AsyncTimescaleAccessor, TimescaleAccessor
# ...
__all__ = [
    ...
    "TimescaleAccessor",
    "AsyncTimescaleAccessor",
    ...
]
```

Add 6 new lines:
```python
from pycopg.admin import AdminAccessor, AsyncAdminAccessor
from pycopg.maint import MaintAccessor, AsyncMaintAccessor
from pycopg.backup import BackupAccessor, AsyncBackupAccessor
```

And 6 entries in `__all__` under a `# Admin`, `# Maint`, `# Backup` comment.

[VERIFIED: `__init__.py:1-81`]

---

## Test Pattern

### `test_timescale_aliases.py` template

The three new alias test modules must mirror `tests/test_timescale_aliases.py` exactly. Key assertions (verified from live source):

1. **Warning category:** `rec.category is DeprecationWarning`
2. **Warning message:** contains `f"db.<accessor>.<method>"` and `"v0.7.0"`
3. **stacklevel proof:** `rec.filename` must be the test file itself (contains `"test_"`), not `"aliases.py"` or `"database.py"`
4. **Delegation:** `getattr(mock_accessor, name).assert_called_once_with(*args)`
5. **Isolation:** Use `warnings.catch_warnings(record=True)` + filter on `f"db.<accessor>.<method>" in str(rec.message)` — do NOT assert `len(w) == 1` on the full record; assert on the filtered alias-specific list

**Sync test pattern (verbatim template):**
```python
db = Database(config)
mock_accessor = MagicMock(spec=AdminAccessor)
db._admin = mock_accessor  # inject into cache field

with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter("always")
    getattr(db, name)(*args)

alias_warnings = [
    rec for rec in w
    if rec.category is DeprecationWarning
    and f"db.admin.{name}" in str(rec.message)
]
assert len(alias_warnings) == 1
```

**Async test pattern:** Replace `MagicMock` with `MagicMock(spec=AsyncAdminAccessor)`, set each method to `AsyncMock()`, inject into `db._admin`, `await getattr(db, name)(...)`.

### `test_parity.py` addition (ACCESSOR_PAIRS)

Current state (verified `tests/test_parity.py:19-22`):
```python
ACCESSOR_PAIRS = [
    (TimescaleAccessor, AsyncTimescaleAccessor),
    (ETLAccessor, AsyncETLAccessor),
]
```

W3 adds:
```python
from pycopg.admin import AdminAccessor, AsyncAdminAccessor
from pycopg.maint import MaintAccessor, AsyncMaintAccessor
from pycopg.backup import BackupAccessor, AsyncBackupAccessor

ACCESSOR_PAIRS = [
    (TimescaleAccessor, AsyncTimescaleAccessor),
    (ETLAccessor, AsyncETLAccessor),
    (AdminAccessor, AsyncAdminAccessor),
    (MaintAccessor, AsyncMaintAccessor),
    (BackupAccessor, AsyncBackupAccessor),
]
```

The `test_accessor_parity` parametrized test at line 25 runs automatically — no further changes needed. [VERIFIED: `test_parity.py:25-51`]

---

## `_psql_restore` Private Companion — Special Note

`_psql_restore` is NOT in the 21 public method names. It is a private helper called from `pg_restore`. The verbatim-move rule (D-06) requires moving `pg_restore` exactly as-is — which means `_psql_restore` must also move into `BackupAccessor` (sync) / `AsyncBackupAccessor` (async) as a private method.

**Inside the moved `pg_restore` body:** `self._psql_restore(input_file)` stays as `self._psql_restore(input_file)` — no rewrite needed because both methods are now on the same accessor class.

**The stub left on `Database`:** Only the 4 public methods (`pg_dump`, `pg_restore`, `copy_to_csv`, `copy_from_csv`) get `@deprecated_alias` stubs. `_psql_restore` is private — it does NOT get a stub on `Database`. The `pg_restore` stub delegates to `db.backup.pg_restore(...)` which in turn calls `self._psql_restore(...)` on the accessor — the chain is correct.

[VERIFIED: `database.py:2339`, `database.py:2369`; `async_database.py:2368`, `async_database.py:2406`]

---

## Subprocess / AsyncIO Pattern in BackupAccessor

The sync `pg_dump` and `pg_restore` bodies do `import subprocess` locally (inside the method). This is the existing pattern — it must be preserved verbatim (D-06). Do NOT move the import to module level.

The async `pg_dump` and `pg_restore` bodies use `asyncio.create_subprocess_exec` — `asyncio` is already a top-level import in `async_database.py`. When moved to `backup.py`, `AsyncBackupAccessor` must import `asyncio` at the module level of `backup.py`.

The async `copy_to_csv`/`copy_from_csv` bodies use `asyncio.to_thread` — also requires `import asyncio` at module level.

**No `self.execute(...)` appears in any backup body** — all I/O is through `subprocess.run`, `asyncio.create_subprocess_exec`, `cur.copy(...)` (cursor-level), or `self.cursor()`. The only accessor-delegation rewrite is `self.cursor()` → `self._db.cursor()` (Bucket B) and `self.config.*` → `self._db.config.*` (attribute).

---

## Gate Surface — Migration Call-Sites

Tests that use the flat names and must be migrated to `db.admin.*` / `db.maint.*` / `db.backup.*` paths in W3:

| Test file | Approx. flat-name references | Primary domains |
|-----------|------------------------------|----------------|
| `tests/test_database.py` | ~98 lines | admin (create_role×16, role_exists×12, alter_role×13, grant×6, revoke×5, grant_role×4, revoke_role×4, drop_role×3, list_role_members×3, list_roles×2), maint (size×2, table_size×6), backup (pg_dump×18, pg_restore×7) |
| `tests/test_async_database.py` | ~164 lines | admin (all 11), maint (size×2, table_size×7, table_sizes×3, vacuum×9, analyze×13, explain×9), backup (pg_dump×15, pg_restore×15, copy_to_csv×11, copy_from_csv×11) |
| `tests/test_database_integration.py` | ~15 lines | maint (size×12, table_size×3, table_sizes×1, vacuum×2, analyze×2), backup (copy_to_csv×3, copy_from_csv×3) |
| `tests/test_sql_injection.py` | ~18 lines | admin (create_role×4, grant×3, revoke×2), maint (vacuum×4, analyze×4), backup (copy_to_csv×1) |
| `tests/test_subprocess_env.py` | ~17 lines | backup (pg_dump×10, pg_restore×9) |

**Total migration surface: ~312 reference lines across 5 test files.** Most are in `test_async_database.py` (~164). The planner should treat W3 migration as the largest W3 task.

---

## Gate Configuration

**`pyproject.toml [tool.pytest.ini_options]` (verified):**
```toml
addopts = "-v --cov=pycopg --cov-report=term-missing --cov-report=html --cov-fail-under=94"
asyncio_mode = "auto"
```

No `filterwarnings` key is set. [VERIFIED: `pyproject.toml:88-91`]

**Phase 21 `-W error::DeprecationWarning` gotcha:** The alias tests use `warnings.catch_warnings(record=True)` + `warnings.simplefilter("always")` inside each test — this is the Phase 21 solution. The test class does NOT set `filterwarnings` globally (which would break the gate by converting all DeprecationWarnings to errors). Instead, each test filters its captured warnings by message content to isolate the alias-specific warning. Phase 22 must replicate this exact isolation pattern. [VERIFIED: `test_timescale_aliases.py:73-91`]

**`interrogate ≥ 95`:** Every method in the new accessor classes needs a numpydoc docstring (moved verbatim from Database — they already have them). Each `@deprecated_alias` stub needs the one-liner `"""Deprecated: use ``db.<accessor>.<method>`` instead."""` docstring. [VERIFIED: `pyproject.toml:114`, `database.py:1671`]

**Coverage ratchet `--cov-fail-under=94`:** The 21 alias stubs + 3 new accessor modules add new lines. The DB-free alias tests (W3) must exercise every stub. No uncovered lines acceptable.

---

## Common Pitfalls

### Pitfall 1: Calling the flat deprecated alias from inside the accessor body
**What goes wrong:** If `AdminAccessor.create_role` calls `self._db.role_exists(...)` instead of `self._db.admin.role_exists(...)`, it routes through the deprecated alias, emitting an internal `DeprecationWarning` that breaks `-W error::DeprecationWarning`.
**Why it happens:** Easy to confuse flat alias with core-flat. `role_exists` is being deprecated; `execute` is not.
**How to avoid:** Use the D-03 bucket classification table in this document. Every Bucket A call must use `self._db.<accessor>.<method>`, never `self._db.<method>`.
**Warning signs:** `DeprecationWarning` appearing in full suite run without a test explicitly triggering one.

### Pitfall 2: Forgetting to move `_psql_restore` with `pg_restore`
**What goes wrong:** `BackupAccessor.pg_restore` body calls `self._psql_restore(...)` which doesn't exist on the accessor.
**Why it happens:** `_psql_restore` is private and not in the 21-method count; easy to forget.
**How to avoid:** Move `_psql_restore` as a private method into both `BackupAccessor` and `AsyncBackupAccessor`. It does NOT get a stub on `Database`.
**Warning signs:** `AttributeError: 'BackupAccessor' object has no attribute '_psql_restore'` at `pg_restore` call time.

### Pitfall 3: `asyncio` not imported in `backup.py`
**What goes wrong:** `AsyncBackupAccessor.pg_dump` uses `asyncio.create_subprocess_exec` but `asyncio` is only imported locally in `async_database.py`.
**Why it happens:** The sync version imports `subprocess` locally; it's natural to miss `asyncio` in the new module.
**How to avoid:** `import asyncio` at module level in `backup.py`.
**Warning signs:** `NameError: name 'asyncio' is not defined` at async pg_dump/pg_restore/copy_to_csv call.

### Pitfall 4: `self.config.*` not rewritten to `self._db.config.*` in backup/maint
**What goes wrong:** `BackupAccessor.pg_dump` accesses `self.config.host` which doesn't exist on the accessor.
**Why it happens:** `self.config` is an attribute access, not a method call — easy to overlook in the rewrite.
**How to avoid:** All `self.config.*` in moved bodies become `self._db.config.*`.
**Warning signs:** `AttributeError: 'BackupAccessor' object has no attribute 'config'`.

### Pitfall 5: `build_role_options` not imported in `admin.py`
**What goes wrong:** `AdminAccessor.create_role` calls `build_role_options(...)` which is in `pycopg.base`, not `pycopg.utils`.
**Why it happens:** `build_pg_dump_cmd` and `build_role_options` are all in `base.py` but it's not obvious.
**How to avoid:** Import `build_role_options` from `pycopg.base` in `admin.py`; import `build_pg_dump_cmd` and `build_pg_restore_cmd` from `pycopg.base` in `backup.py`.
**Warning signs:** `ImportError` or `NameError: name 'build_role_options' is not defined`.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (≥7.0.0) + pytest-cov + pytest-asyncio |
| Config file | `pyproject.toml [tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_admin_aliases.py tests/test_maint_aliases.py tests/test_backup_aliases.py tests/test_parity.py -x -q` |
| Full suite command | `uv run pytest` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ADM-01 | `db.admin.*` methods work | unit (DB-free mock) | `uv run pytest tests/test_admin_aliases.py -x -q` | No — Wave 3 |
| ADM-01 | flat `db.*` aliases warn + delegate | unit (DB-free mock) | same | No — Wave 3 |
| MNT-01 | `db.maint.*` methods work | unit (DB-free mock) | `uv run pytest tests/test_maint_aliases.py -x -q` | No — Wave 3 |
| MNT-01 | flat `db.*` aliases warn + delegate | unit (DB-free mock) | same | No — Wave 3 |
| BKP-01 | `db.backup.*` methods work | unit (DB-free mock) | `uv run pytest tests/test_backup_aliases.py -x -q` | No — Wave 3 |
| BKP-01 | flat `db.*` aliases warn + delegate | unit (DB-free mock) | same | No — Wave 3 |
| All | sync/async parity for all 3 pairs | unit (inspect) | `uv run pytest tests/test_parity.py::test_accessor_parity -x -q` | Exists — append entries |
| All | coverage ≥ 94% | gate | `uv run pytest` | Exists |

### Wave 0 Gaps

- [ ] `tests/test_admin_aliases.py` — 11 sync + 11 async alias tests — Wave 3
- [ ] `tests/test_maint_aliases.py` — 6 sync + 6 async alias tests — Wave 3
- [ ] `tests/test_backup_aliases.py` — 4 sync + 4 async alias tests — Wave 3

*(No new framework install needed — pytest-asyncio already present)*

---

## Architecture Patterns

### Module skeleton for `admin.py` / `maint.py` / `backup.py`

Exact structure from `timescale.py` (copy verbatim, rename):

```python
"""<Accessor name> accessor classes for db.<accessor>.* / async_db.<accessor>.*. """

from __future__ import annotations
from typing import TYPE_CHECKING
# ... domain-specific imports ...
if TYPE_CHECKING:
    from pycopg.async_database import AsyncDatabase
    from pycopg.database import Database


class <Name>Accessor:
    """<Name> helper namespace exposed as ``db.<name>``."""

    def __init__(self, db: Database) -> None:
        """Store the parent database reference.
        ...
        """
        self._db = db

    # ... moved methods with self._db.X() rewrites ...


class Async<Name>Accessor:
    """Async <Name> helper namespace exposed as ``async_db.<name>``."""

    def __init__(self, db: AsyncDatabase) -> None:
        """..."""
        self._db = db

    # ... async moved methods ...
```

### Deprecated alias stub pattern (from `database.py:1669`)

```python
@deprecated_alias("<accessor>.<method>")
def <method>(self, *args, **kwargs):
    """Deprecated: use ``db.<accessor>.<method>`` instead."""
```

Async stubs use `async def`.

---

## Sources

### Primary (HIGH confidence)

- `pycopg/database.py` — live source, all 21 method bodies read directly (lines 1697-2534)
- `pycopg/async_database.py` — async equivalents verified (lines 1273-2597)
- `pycopg/timescale.py` — template module read end-to-end
- `pycopg/aliases.py` — decorator implementation verified
- `pycopg/__init__.py` — current `__all__` verified
- `tests/test_timescale_aliases.py` — full test template verified
- `tests/test_parity.py:1-51` — ACCESSOR_PAIRS registry verified
- `pyproject.toml` — gate configuration verified

### Secondary (MEDIUM confidence)

- `pycopg/base.py` — `build_role_options`, `build_pg_dump_cmd`, `build_pg_restore_cmd` locations verified

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| — | — | — | — |

**All claims in this research were verified from live source files. No assumed knowledge was used for any factual claim about line numbers, method bodies, or import paths.**

---

## Metadata

**Confidence breakdown:**
- D-03 self-call table: HIGH — every method body read directly from source
- Line numbers: HIGH — verified from live source; noted as accurate at research time
- Import matrix: HIGH — derived from method body scan + existing import patterns
- Wiring touch-points: HIGH — current line numbers verified from source
- Test pattern: HIGH — `test_timescale_aliases.py` read end-to-end
- Migration surface counts: HIGH — verified via grep
- Gate config: HIGH — `pyproject.toml` read directly

**Research date:** 2026-06-17
**Valid until:** 2026-07-17 (source-derived; valid until source changes)
