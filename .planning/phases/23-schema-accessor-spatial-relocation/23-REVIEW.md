---
phase: 23-schema-accessor-spatial-relocation
reviewed: 2026-06-18T00:00:00Z
depth: standard
files_reviewed: 18
files_reviewed_list:
  - pycopg/schema.py
  - pycopg/spatial.py
  - pycopg/database.py
  - pycopg/async_database.py
  - pycopg/timescale.py
  - pycopg/etl.py
  - pycopg/__init__.py
  - tests/test_schema_aliases.py
  - tests/test_spatial_aliases.py
  - tests/test_parity.py
  - tests/test_database.py
  - tests/test_async_database.py
  - tests/test_database_integration.py
  - tests/test_integration.py
  - tests/test_postgis_errors.py
  - tests/test_spatial.py
  - tests/test_sql_injection.py
findings:
  critical: 0
  warning: 2
  info: 3
  total: 5
status: issues_found
---

# Phase 23: Code Review Report

**Reviewed:** 2026-06-18T00:00:00Z
**Depth:** standard
**Files Reviewed:** 18
**Status:** issues_found

## Summary

Phase 23 relocates 27 schema/DDL methods into `SchemaAccessor` / `AsyncSchemaAccessor`
(`pycopg/schema.py`) and 2 PostGIS spatial-index methods into the existing
`SpatialAccessor` / `AsyncSpatialAccessor`. Flat `Database` / `AsyncDatabase` methods
became thin `@deprecated_alias` stubs. Internal call-sites
(`from_dataframe`/`from_geodataframe`, `timescale.py`, `etl.py`, the spatial PostGIS
guards) were migrated to accessor paths.

The phase's four focus invariants all hold under verification:

1. **Security guards preserved (T-23-01).** Every relocated DDL method carries its
   original `validate_identifier` / `validate_identifiers` / `validate_extension_name`
   / `validate_index_method` guard verbatim (schema.py lines 70-73, 91, 156-158, 179,
   230-232, 251, 379, 398, 466-468, 517-521, 569-571, 609-612, 638; spatial.py 1879-1881
   / 2803-2805). `tests/test_sql_injection.py` (92 tests) passes against the new
   accessor paths.
2. **Sync↔async parity.** `tests/test_parity.py::test_accessor_parity` registers the
   `(SchemaAccessor, AsyncSchemaAccessor)` pair and passes; full `TestAsyncParity`
   surface check passes (69 parity/alias tests green).
3. **Correct `deprecated_alias` targets.** All 27 schema stubs target `schema.*` and
   both spatial stubs target `spatial.*`; verified by `test_schema_aliases.py` /
   `test_spatial_aliases.py`.
4. **No flat-alias self-call leaks.** Grep confirms zero internal `self.<flat_method>(`
   calls in `database.py`, `async_database.py`, `etl.py`, `spatial.py`, `timescale.py`;
   all internal call-sites use `self.schema.*` / `self.spatial.*`.

`ruff check` passes on all changed source files. The defects below are quality / parity
concerns, not correctness or security regressions.

## Warnings

### WR-01: Deprecated stubs erase the public signature and numpydoc of all 29 relocated methods

**File:** `pycopg/database.py:937-1024` (and parallel `pycopg/async_database.py:730-860`); decorator at `pycopg/aliases.py:46-63`

**Issue:** Every flat alias is now `def create_database(self, *args, **kwargs)` with a
one-line docstring, e.g.:
```python
@deprecated_alias("schema.create_database")
def create_database(self, *args, **kwargs):
    """Deprecated: use ``db.schema.create_database`` instead."""
```
Because `@functools.wraps(fn)` copies `__wrapped__` from the *stub* (not the accessor
implementation), `inspect.signature(db.create_database)` now resolves to
`(self, *args, **kwargs)` and `help(db.create_database)` shows only the one-line
deprecation notice. The methods remain deprecated-but-supported until v0.7.0, so for
roughly a full minor-release window IDE autocomplete, `inspect.signature`, and
generated API docs lose the real parameter names, defaults, type hints, and numpydoc
for all 29 still-public methods. This is a real DX/maintainability regression, not a
style nit — callers using `inspect`-based tooling (argument binding, doc generation,
typed wrappers) against the flat surface will silently see the wrong signature.

Note this also weakens the parity test it passes: `test_method_signatures_match`
compares `(self, *args, **kwargs)` on both sides, so genuine signature drift between
the flat sync and async aliases can no longer be detected by that test for any
relocated method.

**Fix:** Have `deprecated_alias` preserve the accessor's true signature on the stub, or
keep an explicit signature on each stub. Minimal option — resolve and copy the target
signature in the decorator:
```python
def decorator(fn):
    ...
    # after building wrapper, attach the accessor method's signature so
    # inspect.signature(wrapper) reflects the real parameters.
    # (resolve lazily is impossible at decoration time; document the
    #  accessor as the signature source, or re-declare params on the stub.)
```
If lazy resolution is infeasible, restore explicit parameter lists + numpydoc on the
stubs (matching the pre-Phase-23 signatures) so the deprecated surface keeps its
contract until removal.

### WR-02: `test_sql_injection.py` async fixture patches dead attributes, masking guard-ordering regressions

**File:** `tests/test_sql_injection.py:72-81`

**Issue:** The `async_db` fixture sets `db.has_extension = AsyncMock(return_value=True)`
(line 73) and `db.role_exists = AsyncMock(...)` (line 72) directly on the
`AsyncDatabase` instance. After Phase 23, `has_extension` is a `@deprecated_alias` stub
that delegates to `db.schema.has_extension`, and the spatial guard
(`AsyncSpatialAccessor._check_postgis`) reads `self._db.schema.has_extension` — which is
satisfied by the separate patch on `real_schema` (line 79). The `db.has_extension`
patch on line 73 is therefore dead code: nothing in the exercised paths reads it.
Likewise `db.role_exists` no longer exists as a real method (admin operations live on
`db.admin`), so that patch is also a no-op shadow attribute. These dead patches give a
false impression that the fixture controls the extension/role pre-checks, and they will
silently keep "working" even if the guard wiring regresses, reducing the test's value as
a regression guard.

**Fix:** Remove the dead `db.has_extension` and `db.role_exists` patches (lines 72-73),
relying on the `real_schema.has_extension` patch (line 79) which is what the code
actually consults; or, if a role pre-check is still needed for a covered method, patch
`db.admin.role_exists` on the real admin accessor instead.

## Info

### IN-01: `AsyncSchemaAccessor` reorders SCHEMAS/TABLES methods vs the sync class

**File:** `pycopg/schema.py:866-931` (async) vs `pycopg/schema.py:216-281` (sync)

**Issue:** In `SchemaAccessor` the SCHEMAS section is ordered
`create_schema, drop_schema, list_schemas, schema_exists`; in `AsyncSchemaAccessor` it
is `list_schemas, schema_exists, create_schema, drop_schema`. Similarly the TABLES
section orders `table_info`/`row_count`/`drop_table`/`truncate_table` differently. The
methods claim to be "moved verbatim … mirrors `SchemaAccessor` exactly," but the source
order diverges. Behaviour is identical and `test_accessor_parity` (set-based) passes, so
this is cosmetic — but it makes side-by-side sync/async diffing harder during future
maintenance.

**Fix:** Reorder the async methods to match the sync class section-by-section, so the
two classes remain visually mirrored as the docstrings assert.

### IN-02: Stale docstring/comment references to flat `db.create_extension(...)` in guard messages

**File:** `pycopg/timescale.py:80, 124, 177, 214, 240, 268, 332, 376, 432, 469, 494, 522`; `pycopg/spatial.py:966`

**Issue:** The `ExtensionNotAvailable` messages still instruct
`Run db.create_extension('timescaledb')` / `db.create_extension('postgis')`. After
Phase 23 the canonical path is `db.schema.create_extension(...)`; the flat form now
emits a `DeprecationWarning`. The messages are user-facing and steer users onto the
deprecated alias.

**Fix:** Update the guidance strings to `db.schema.create_extension('timescaledb')` /
`db.schema.create_extension('postgis')` to match the new accessor surface.

### IN-03: `validate_index_method` re-exported in `__init__.py` but no longer used by `database.py`

**File:** `pycopg/__init__.py:35, 94`

**Issue:** `validate_index_method` is still imported and listed in `__all__`. After the
relocation its only first-party consumer moved to `pycopg/schema.py` (which imports it
directly from `pycopg.utils`). The top-level re-export is still a valid public utility,
so this is intentional surface — flagged only to confirm it is deliberate and not a
leftover, since the symmetric `validate_extension_name` is *not* re-exported in
`__init__.py`, making the public utility set asymmetric.

**Fix:** None required if the public export is intended; for consistency, decide whether
`validate_extension_name` should also be re-exported, or document why only a subset of
validators is public.

---

_Reviewed: 2026-06-18T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
