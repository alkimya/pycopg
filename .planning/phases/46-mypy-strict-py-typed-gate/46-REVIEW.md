---
phase: 46-mypy-strict-py-typed-gate
reviewed: 2026-07-02T00:00:00Z
depth: standard
files_reviewed: 19
files_reviewed_list:
  - pycopg/__init__.py
  - pycopg/base.py
  - pycopg/config.py
  - pycopg/utils.py
  - pycopg/exceptions.py
  - pycopg/logging.py
  - pycopg/queries.py
  - pycopg/migrations.py
  - pycopg/admin.py
  - pycopg/backup.py
  - pycopg/maint.py
  - pycopg/schema.py
  - pycopg/spatial.py
  - pycopg/timescale.py
  - pycopg/etl.py
  - pycopg/pool.py
  - pycopg/database.py
  - pycopg/async_database.py
  - tests/test_pool.py
findings:
  critical: 0
  warning: 0
  info: 1
  total: 1
status: clean
---

# Phase 46: Code Review Report

**Reviewed:** 2026-07-02
**Depth:** standard
**Files Reviewed:** 19 (18 pycopg source modules + tests/test_pool.py)
**Status:** clean

## Summary

Phase 46 is a mypy-strict typing pass across all 18 pycopg modules plus one real bug fix
in `pool.py`. I verified the diff against the pre-phase baseline (`75c1895..HEAD`) file by
file and specifically interrogated the four high-priority behavior-risk targets called out
in the review brief, plus the cross-cutting security/API-surface checks.

**Verification performed (not just read-through):**

1. **`pool.py` `AsyncPooledDatabase.resize()` sync→async fix** — confirmed correct and
   complete. `psycopg_pool.AsyncConnectionPool.resize` is genuinely a coroutine function;
   the old `resize()` called it without `await`, silently discarding the coroutine (a real,
   previously-shipped bug — the pool never actually resized for async callers). The fix
   makes `resize()` `async def` + `await self._pool.resize(...)`, matching the sibling
   `check()`/`close()` methods in the same class. `grep`'d every `.resize(` call site in
   the repo (tests, docs, README): the sync `PooledDatabase.resize()` stayed correctly
   synchronous, the async test (`tests/test_pool.py::TestAsyncPooledDatabaseAsync::test_resize`)
   was moved from the *sync* test class into the *async* test class and correctly upgraded
   from a bare `MagicMock` (which cannot detect a missing `await`) to `AsyncMock` +
   `assert_awaited_once_with(...)` — a genuine regression test for the bug, not just a
   type-checker satisfier. Ran `tests/test_pool.py` (38/38 pass) to confirm. No stale
   sync-style `db.resize(...)` (missing `await`) documentation exists for `AsyncPooledDatabase`
   in README.md / docs/connection-pooling.md — the un-awaited-looking examples there are
   under the sync `PooledDatabase` section, which is correct.

2. **`etl.py` `steps` `[no-redef]` claim** — traced the control flow in both `ETLAccessor.run()`
   and `AsyncETLAccessor.run()`. The `dry_run` branch (which owns the first `steps: list[Any]`
   annotation) unconditionally `return`s before the function reaches the second `steps = ...`
   assignment further down in the non-dry-run path. The two assignments are on mutually
   exclusive runtime paths — never a live shadow, never both executed in the same call. Claim
   holds; no behavior change.

3. **`pycopg/__init__.py` `__getattr__` cast** — the `cast("type", getattr(exceptions, new_name))`
   addition does not change the returned object (still `getattr(exceptions, new_name)`,
   verbatim), only its static type. Verified at runtime: `pycopg.DatabaseExists is
   pycopg.DatabaseExistsError` (identity preserved), `AttributeError` still raised for
   unknown names, and the `DeprecationWarning` still fires with `stacklevel=2`. See Info
   item below for a pre-existing (not introduced by this diff) quirk found while probing
   this path.

4. **`@overload` surfaces** (spatial.py 16 methods × 6 overloads = 96, timescale.py 2
   methods × 6 = 12) — every overload group is exactly 3 sync + 3 async signatures
   (`Literal["rows"|"df"] -> concrete`, `Literal["gdf"] -> concrete`, `str -> union`),
   1:1 mirrored between the sync and async accessor classes. Spot-checked `contains()`
   (both sync/async) line-by-line against its runtime implementation signature — exact
   match. `_check_into()`'s `_VALID_INTO = {"rows", "gdf"}` matches the `Literal` values
   used across all spatial overloads. `uv run mypy pycopg` passes with **0 errors across
   18 files** — mypy itself would reject an overload whose signature is incompatible with
   the implementation, which corroborates the spot-check.

5. **`validate_identifiers` / injection-guard audit** — diffed the call count of
   `validate_identifier` (grep) per file between the pre-phase baseline and HEAD across
   every module that builds SQL (`spatial.py`, `timescale.py`, `etl.py`, `database.py`,
   `async_database.py`, `schema.py`, `admin.py`, `backup.py`, `maint.py`, `base.py`) —
   **identical counts in every file**. No guard was dropped or weakened during annotation.

6. **`__all__` additions** — new `__all__` lists were added to `base.py`, `migrations.py`,
   `admin.py`, `backup.py`, `maint.py` (mechanical, matching prior de-facto public
   surface). Cross-checked `pycopg/__init__.py`'s `__all__` (unchanged in this phase except
   the `cast` import) resolves every listed name without `AttributeError`, including the
   four PEP-562 deprecated aliases (`DatabaseExists`, `ExtensionNotAvailable`,
   `TableNotFound`, `InvalidIdentifier`). No symbol was hidden or newly exposed.

7. **`# type: ignore` audit** — 8 occurrences total, all pre-existing or added with an
   inline justification comment referencing a genuinely-unstubbed external edge
   (`geopandas`/`pandas-stubs` `to_sql`/`read_postgis` value-union narrowing,
   `python-dotenv` optional-dependency fallback) or a documented runtime-vs-static-type
   divergence (`psycopg` `Copy.__iter__` typed as bytes-only while a defensive `str`
   branch is kept at runtime; the `Pipeline.conflict_columns` dataclass runtime guards
   against dynamically-typed callers). None of these silence a behavior bug — each guards
   real, still-reachable runtime behavior that mypy's stub view alone cannot see.

**mypy strict gate:** `uv run mypy pycopg` → `Success: no issues found in 18 source files`.

**Tests:** `tests/test_pool.py` 38/38 pass. `tests/test_pool_stress.py` has 6 pre-existing
DB-environment failures (`UndefinedFile: timescaledb-2.28.0`) unrelated to this diff —
matches the known `pycopg_test` DB TimescaleDB-catalog-mismatch issue already tracked in
project memory; reproduced identically against `PGDATABASE=pycopg_test2`, confirming this
is an environment issue, not a phase-46 regression.

## Info

### IN-01: Package-level deprecated-alias `__getattr__` path is untested and double-fires under `from pycopg import X`

**File:** `pycopg/__init__.py:58-90`
**Issue:** While verifying the `cast()` addition (review target #3), I found that
`from pycopg import DatabaseExists` (and the other three PEP-562 package-level aliases)
emits the `DeprecationWarning` **twice** per import statement, whereas a plain attribute
access (`import pycopg; pycopg.DatabaseExists`) correctly emits it once. This is a
CPython import-machinery characteristic of `from module import name` combined with a
module-level `__getattr__` (PEP 562) that is **not evaluating differently before vs.
after this diff** — I reproduced the identical double-fire against the pre-phase
`75c1895` version of `__init__.py`/`exceptions.py`, so it is not a regression introduced
by the `cast()`/annotation change reviewed here. It is, however, an existing gap that
this phase's target function touches without adding coverage for: `tests/test_deprecations.py`
only exercises `pycopg.exceptions.InvalidIdentifier` (the module-level alias, via plain
attribute access), never `pycopg.__getattr__` / the package-level aliases
(`DatabaseExists`, `ExtensionNotAvailable`, `TableNotFound`, `InvalidIdentifier` re-exported
from `pycopg` itself), and never via `from pycopg import X` — so this double-fire has no
regression test either confirming or guarding its (arguably surprising) behavior.
**Fix:** Not a behavior bug worth blocking on, but worth a follow-up test in
`tests/test_deprecations.py` exercising `from pycopg import DatabaseExists` (or
equivalent `pycopg.__getattr__("DatabaseExists")` direct calls covering all four
package-level aliases) to pin the current (double-warn) behavior or fix it if a single
warning is the intended contract — e.g.:
```python
def test_package_level_alias_from_import_warns():
    with pytest.warns(DeprecationWarning):
        from pycopg import DatabaseExists
    assert DatabaseExists is pycopg.DatabaseExistsError
```

---

_Reviewed: 2026-07-02_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
