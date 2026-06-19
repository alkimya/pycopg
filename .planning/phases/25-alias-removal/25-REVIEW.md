---
phase: 25-alias-removal
reviewed: 2026-06-19T00:00:00Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - pycopg/database.py
  - pycopg/async_database.py
  - pycopg/spatial.py
  - pycopg/timescale.py
  - tests/test_alias_removal.py
  - tests/test_sql_injection.py
findings:
  critical: 0
  warning: 2
  info: 1
  total: 3
status: issues_found
---

# Phase 25: Code Review Report

**Reviewed:** 2026-06-19
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Summary

Phase 25 removes the 56 `@deprecated_alias` flat-method stubs (and the
`from pycopg.aliases import deprecated_alias` import) from both `database.py`
and `async_database.py`, deletes `pycopg/aliases.py`, normalizes all
PostGIS/Timescale guard-error strings from `db.create_extension` to
`db.schema.create_extension`, and adds `tests/test_alias_removal.py`.

The core removal is **clean and correct**. I verified directly that:

- No remaining runtime reference to `deprecated_alias` or `pycopg.aliases`
  exists in any importable code path (only one stale docstring mention — see
  WR-01).
- All 56 removed names are genuinely absent from `Database` and
  `AsyncDatabase`, including via inheritance from `DatabaseBase`/`QueryMixin`
  (none of the base classes define them).
- The interleaved-stub deletion did **not** damage any real method — all
  surviving methods (`fetch_val`, `from_dataframe`, `listen`, `notify`, the
  DataFrame ops, etc.) are intact and the modules import without error.
- `REMOVED_FLAT_NAMES` contains exactly 56 entries, no duplicates, and every
  name has a live migration target on one of the six accessors.
- The guard-string edits are byte-consistent across all 12 Timescale sites,
  the PostGIS spatial sentinel, and both `from_geodataframe` guards.
- `tests/test_alias_removal.py` and `tests/test_sql_injection.py` pass
  (206 passed in 0.48s).

The findings below are quality/maintainability issues, not correctness
breaks. No BLOCKER-tier defects were found.

## Warnings

### WR-01: Stale `pycopg.aliases` reference in `timescale.py` module docstring

**File:** `pycopg/timescale.py:9-10`
**Issue:** The module docstring still reads:

> "The flat ``db.*`` names remain as thin deprecated aliases (see
> :mod:`pycopg.aliases`) until v0.7.0."

This is now false on two counts: `pycopg/aliases.py` was **deleted** in this
phase, and the flat aliases no longer exist. The `:mod:`pycopg.aliases``
cross-reference is a dangling target — if Sphinx/intersphinx resolves module
references strictly, this can produce a doc build warning, and at minimum it
misinforms any reader. This is documentation drift left behind by an
incomplete edit (all the executable references were removed; this docstring
prose was missed).

**Fix:** Update the docstring to reflect the post-removal state, e.g.:
```python
"""TimescaleDB accessor classes for db.timescale.* / async_db.timescale.*.

This module provides :class:`TimescaleAccessor` and
:class:`AsyncTimescaleAccessor` — the implementation of the 6 TimescaleDB
helper methods. As of v0.7.0 the flat ``db.<method>`` aliases have been
removed; use the ``db.timescale.<method>`` namespace exclusively.
"""
```

### WR-02: Dead/misleading stub assignments in the `async_db` test fixture

**File:** `tests/test_sql_injection.py:72-73`
**Issue:** The `async_db` fixture sets:
```python
db.role_exists = AsyncMock(return_value=False)
db.has_extension = AsyncMock(return_value=True)
```
After alias removal, `AsyncDatabase` no longer has `role_exists` or
`has_extension` methods, and **no production code path reads these instance
attributes**. The real pre-checks now route through the accessors:
`admin.create_role` calls `self._db.admin.role_exists(...)` (a real method
backed by the mocked `db.execute`), and the spatial/extension guards call
`self._db.schema.has_extension(...)` (patched separately via
`real_schema.has_extension` on line 79). These two assignments are therefore
dead code that silently attach unused attributes to the instance.

The risk is not a current test failure (the suite passes), but a maintenance
trap: the assignments *look* like they wire up a guard, so a future reader
may assume `db.role_exists`/`db.has_extension` are the active mock seam and
build on a stub that nothing consults — masking a real validation-ordering
regression. The fixture docstring (lines 60-70) still describes stubbing
"``role_exists``, ``has_extension``" on `db`, compounding the confusion.

**Fix:** Delete the two dead assignments (and the corresponding docstring
sentence). Keep only the seams that are actually read:
```python
db = AsyncDatabase(config)
db.execute = AsyncMock(return_value=[])
db.execute_many = AsyncMock(return_value=0)
real_schema = AsyncSchemaAccessor(db)
real_schema.has_extension = AsyncMock(return_value=True)
db._schema = real_schema
return db
```
If a future test needs `admin.role_exists` to return a fixed value, patch it
on the admin accessor (`db.admin.role_exists = AsyncMock(...)`), not on `db`.

## Info

### IN-01: `test_no_varargs` guards rely on `inspect.signature` not raising

**File:** `tests/test_alias_removal.py:110-149`
**Issue:** The two `test_no_varargs_on_*_public_surface` tests wrap the
signature inspection in `try/except (ValueError, TypeError): pass`. This is
correct for skipping builtins/C-level callables that lack introspectable
signatures, but it means that if a future regression somehow makes a
genuine method's signature un-introspectable, the assertion is silently
skipped rather than flagged. Today this is benign (the suite passes and the
removed stubs are gone), but the swallow-and-continue pattern weakens the
guard's adversarial value over time.

**Fix:** Optionally narrow the guard by collecting the set of public method
names actually inspected and asserting it is non-empty / matches an expected
floor, so a wholesale "everything became un-inspectable" regression cannot
pass vacuously. Low priority — informational only.

---

_Reviewed: 2026-06-19_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
