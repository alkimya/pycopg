# Phase 20: Async Parity, Wiring & Release — Research

**Researched:** 2026-06-15
**Domain:** AsyncETLAccessor mirror, lazy property wiring, TestEtlParity, Sphinx/RTD docs, PyPI release v0.5.0
**Confidence:** HIGH

---

## Summary

Phase 20 is almost entirely mechanical: mirror the locked sync `ETLAccessor` (in `pycopg/etl.py`) into an `AsyncETLAccessor` class in the same file, add `_etl: AsyncETLAccessor | None = None` to `AsyncDatabase.__init__`, wire a lazy `async_db.etl` property following the `async_db.spatial` pattern exactly, add a `TestEtlParity` class to `tests/test_parity.py`, then execute the v0.4.0 release playbook adapted for v0.5.0.

The sync surface is fully built and tested. All design decisions are locked. The async accessor reuses all pure module-level functions (`_row_to_result`, `_is_sql_source`, `_build_insert_sql`, `_build_upsert_sql`, `build_truncate_sql`, `_step_label`) byte-for-byte — no duplication, no re-design. The only structural difference from the sync accessor: every method becomes `async def`, `self._db.connect(autocommit=True)` becomes `async with self._db.connect(autocommit=True) as conn`, cursor calls get `await`, and the transform chain in `run()` dispatches callable(s) via `await asyncio.to_thread(step, df)`.

**Primary recommendation:** Four coding tasks (AsyncETLAccessor class, AsyncDatabase wiring, TestEtlParity, `__init__.py` export) followed by the documented release playbook (docs/etl.md, version bump, CHANGELOG, MIGRATION, interrogate, coverage gate, tag, PyPI publish).

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ETL-12 | `await async_db.etl.run(pipeline)` / `await async_db.etl.history(name)` / `await async_db.etl.last_run(name)` / `await async_db.etl.run(pipeline, dry_run=True)` exist and produce results equivalent to sync; sync transform callables dispatched via `asyncio.to_thread`; `TestEtlParity` enumeration passes in CI | `AsyncETLAccessor` class mirrors `ETLAccessor` exactly; `asyncio.to_thread` already used in `async_database.py` at lines 2663–2684; `TestEtlParity` drops into `test_parity.py` following `TestAsyncParity` pattern |
| ETL-13 | `db.etl` returns lazily-created `ETLAccessor`; `async_db.etl` returns lazily-created `AsyncETLAccessor`; both follow `db.spatial`/`async_db.spatial` lazy-creation pattern exactly | `db.etl` already wired (database.py lines 253–271); `async_db.etl` property pattern is `async_db.spatial` at lines 94–110 of async_database.py — trivial copy |
</phase_requirements>

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| AsyncETLAccessor class | API / Backend (`pycopg/etl.py`) | — | Mirrors sync accessor in same module; pure functions already shared |
| Async DB connection (run-log isolation) | API / Backend (`pycopg/async_database.py` `connect(autocommit=True)`) | — | Same separate-connection invariant as sync; must use `AsyncConnection` |
| `async_db.etl` lazy property | API / Backend (`pycopg/async_database.py`) | — | Follows `async_db.spatial` property pattern at lines 94–110 |
| Transform thread-offload | API / Backend (asyncio stdlib) | — | SC-2: `asyncio.to_thread` wraps sync callables; already used in async_database.py |
| `TestEtlParity` | Test layer (`tests/test_parity.py`) | — | Extension to existing `TestAsyncParity` class; same `inspect.getmembers` pattern |
| `docs/etl.md` autodoc page | CDN/Static (Sphinx/RTD) | — | Follows `docs/spatial.md` structure |
| `pycopg/__init__.py` exports | API / Backend (public surface) | — | `AsyncETLAccessor`, `RunResult`, `Pipeline` may need adding |
| Version bump + PyPI release | CDN/Static (packaging) | — | Mirrors Phase 15 v0.4.0 playbook exactly |

---

## Standard Stack

No new packages are installed in Phase 20. All dependencies already in `pyproject.toml`. [VERIFIED: pyproject.toml]

| Tool | Version | Purpose |
|------|---------|---------|
| `asyncio.to_thread` | stdlib (Python ≥ 3.9; project requires ≥ 3.11) | Offload sync callables from async methods [VERIFIED: pyproject.toml `requires-python = ">=3.11"`] |
| `psycopg.AsyncConnection` | `psycopg >=3.1.0` | Async DB connection used throughout async_database.py [VERIFIED: pyproject.toml] |
| `psycopg.rows.dict_row` | `psycopg >=3.1.0` | Already imported in etl.py; same import for async version [VERIFIED: pycopg/etl.py line 34] |
| `interrogate` | `>=1.7.0` (dev dep) | Docstring coverage gate ≥ 95 [VERIFIED: pyproject.toml line 70] |
| sphinx + myst-parser + furo | see docs/requirements.txt | Sphinx build with `-W` [VERIFIED: docs/requirements.txt] |
| `uv build` | via hatchling | Build sdist+wheel for PyPI [VERIFIED: .github/workflows/publish.yml] |

## Package Legitimacy Audit

No new packages are installed in Phase 20. All tools are pre-existing project dependencies. This section is N/A.

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

---

## Code Map: The Sync Mirror Source

### 1. ETLAccessor — Actual Class Name

The class is named **`ETLAccessor`** (not `EtlAccessor`). Confirmed at `pycopg/etl.py` line 508. [VERIFIED: pycopg/etl.py]

### 2. ETLAccessor.__init__ Signature

```python
# pycopg/etl.py line 528
def __init__(self, db: Database) -> None:
    self._db = db
```

The async version must accept `db: AsyncDatabase` and store `self._db = db`. No extension guard (unlike `SpatialAccessor` which checks PostGIS). [VERIFIED: pycopg/etl.py lines 527–538]

### 3. Public Method Surface to Mirror

| Method | Signature | Return type | Notes |
|--------|-----------|-------------|-------|
| `init` | `(self) -> None` | `None` | Creates `pipeline_runs` via DDL; async version: `async def init` |
| `history` | `(self, name: str, limit: int = 100) -> list[RunResult]` | `list[RunResult]` | Reads via `ETL_LIST_RUNS` |
| `last_run` | `(self, name: str) -> RunResult \| None` | `RunResult \| None` | Reads via `ETL_GET_LAST_RUN` |
| `run` | `(self, pipeline: Pipeline, dry_run: bool = False) -> RunResult` | `RunResult` | Full ETL flow |

[VERIFIED: pycopg/etl.py lines 540–1004]

### 4. Private/Internal Methods

| Method | Signature | DB? | Notes |
|--------|-----------|-----|-------|
| `_start_run` | `(self, name: str) -> int` | YES — opens own autocommit conn | Inserts `'running'` row; returns `run_id` |
| `_end_run` | `(self, run_id: int, status: str, rows_extracted: int, rows_loaded: int, error_message: str\|None = None, error_traceback: str\|None = None) -> None` | YES — opens own autocommit conn | Updates final status |
| `_fetch_run_result` | `(self, run_id: int) -> RunResult` | YES — opens own autocommit conn | Re-SELECTs the run row for the returned `RunResult` |

All three open a **dedicated autocommit connection each call** via `self._db.connect(autocommit=True)`. The async version must use `async with self._db.connect(autocommit=True) as conn:` and `await conn.cursor(...)` / `await cur.execute(...)`. [VERIFIED: pycopg/etl.py lines 555–664]

Module-level functions that are **pure (no DB, shared unchanged)**:

- `_row_to_result(row: dict) -> RunResult` — line 480
- `_is_sql_source(source: str) -> bool` — line 239
- `_build_insert_sql(...)` — line 328
- `_build_upsert_sql(...)` — line 393
- `build_truncate_sql(...)` — line 266
- `_step_label(fn: object) -> str` — line 451
- `build_init_sql()` — line 298

These are already at module level. The async accessor **calls them identically** — no change.

### 5. Transform Callable Invocation in `run()` — The Critical Async Difference

The sync `run()` calls transform steps at etl.py lines 912–920 (main path) and 843–851 (dry-run path):

```python
# etl.py line 914–920 (sync)
for i, step in enumerate(steps, start=1):
    try:
        df = step(df)           # ← direct call, blocks event loop if slow
    except Exception as exc:
        raise ETLTransformError(...)
```

SC-2 requires the async version use `asyncio.to_thread` so a slow transform does not block the event loop:

```python
# AsyncETLAccessor async run() — required pattern
for i, step in enumerate(steps, start=1):
    try:
        df = await asyncio.to_thread(step, df)  # ← SC-2 dispatch
    except Exception as exc:
        raise ETLTransformError(...)
```

[VERIFIED: pycopg/etl.py; SC-2 from ROADMAP Phase 20]

### 6. Run-Log Isolation Pattern — Sync Code to Mirror as Async

Every `init`, `_start_run`, `_end_run`, and `_fetch_run_result` method uses this pattern:

```python
# Sync pattern (etl.py) — e.g. _start_run lines 579–585
with self._db.connect(autocommit=True) as conn:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(queries.ETL_INSERT_RUN, [...])
        return cur.fetchone()["run_id"]
```

The async mirror (using `AsyncDatabase.connect`):

```python
# Async pattern required
async with self._db.connect(autocommit=True) as conn:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(queries.ETL_INSERT_RUN, [...])
        return (await cur.fetchone())["run_id"]
```

`AsyncDatabase.connect(autocommit=True)` is confirmed at `async_database.py` lines 262–280. It is an `@asynccontextmanager` returning `AsyncConnection`. [VERIFIED: pycopg/async_database.py lines 262–280]

### 7. Atomic Load Block — Async Mirror

The sync `run()` loads via (etl.py lines 984–990):

```python
with self._db.session():
    with self._db.transaction() as conn:
        with conn.cursor() as cur:
            if pipeline.load_mode == "replace":
                cur.execute(truncate_sql)
            cur.execute(insert_sql, insert_params)
            rows_loaded += cur.rowcount
```

The async mirror must use the async context managers (both are `@asynccontextmanager` on `AsyncDatabase`):

```python
async with self._db.session():
    async with self._db.transaction() as conn:
        async with conn.cursor() as cur:
            if pipeline.load_mode == "replace":
                await cur.execute(truncate_sql)
            await cur.execute(insert_sql, insert_params)
            rows_loaded += cur.rowcount
```

`AsyncDatabase.session()` is at async_database.py lines 317–368. `AsyncDatabase.transaction()` is at lines 381–401. Both are `@asynccontextmanager`. [VERIFIED: pycopg/async_database.py lines 317–401]

### 8. Database method calls inside run() — async versions

| Sync call | Async call | Location in async_database.py |
|-----------|-----------|-------------------------------|
| `self._db.to_dataframe(sql=..., params=...)` | `await self._db.to_dataframe(sql=..., params=...)` | line 1899 |
| `self._db.table_exists(target, schema)` | `await self._db.table_exists(target, schema)` | line 680 |
| `self._db.from_dataframe(df.head(0), target, schema, if_exists="replace")` | `await self._db.from_dataframe(df.head(0), target, schema, if_exists="replace")` | line 1941 |

[VERIFIED: pycopg/async_database.py lines 680, 1899, 1941]

### 9. RunResult Dataclass

Defined at `pycopg/etl.py` lines 202–236. Frozen dataclass. Fields:

```python
@dataclass(frozen=True)
class RunResult:
    run_id: int | None
    pipeline_name: str
    status: str
    rows_extracted: int
    rows_loaded: int
    started_at: datetime
    finished_at: datetime
    error: str | None
```

Shared between sync and async — no duplication needed.

---

## Code Map: Lazy Property Patterns

### 10. db.etl Already Exists

`db.etl` is **already wired** in `pycopg/database.py` at lines 253–271. [VERIFIED: pycopg/database.py]

```python
# database.py lines 253–271 (VERBATIM — already shipped)
@property
def etl(self) -> ETLAccessor:
    """Get or create the ETL run-tracking accessor (lazy initialization)."""
    if self._etl is None:
        from pycopg.etl import ETLAccessor
        self._etl = ETLAccessor(self)
    return self._etl
```

`_etl: ETLAccessor | None = None` is already in `Database.__init__` at line 86. [VERIFIED: pycopg/database.py lines 83–87]

### 11. async_db.etl Does NOT Exist — Phase 20 Adds It

`AsyncDatabase.__init__` (async_database.py lines 72–83) only has:
```python
self._session_conn: AsyncConnection | None = None
self._async_engine: AsyncEngine | None = None
self._spatial: AsyncSpatialAccessor | None = None
# _etl is MISSING — Phase 20 adds it
```

And there is no `etl` property on `AsyncDatabase`. This is confirmed by the Phase 19 verification: `test_all_database_public_methods_exist_in_async` is a pre-existing failure because `async_db.etl` is absent. [VERIFIED: pycopg/async_database.py lines 72–83; 19-VERIFICATION.md]

### 12. Template to Follow: async_db.spatial Property

```python
# async_database.py lines 94–110 (VERBATIM — the exact template)
@property
def spatial(self) -> AsyncSpatialAccessor:
    """Get or create the async spatial accessor (lazy initialization).

    The PostGIS guard is deferred to the first helper call (an async
    check cannot run inside a property).

    Returns
    -------
    AsyncSpatialAccessor
        Async spatial helper namespace bound to this database.
    """
    if self._spatial is None:
        from pycopg.spatial import AsyncSpatialAccessor
        self._spatial = AsyncSpatialAccessor(self)
    return self._spatial
```

The `async_db.etl` property must follow this pattern exactly (SC-3). No PostGIS guard needed (ETL is core, not an extension — D-08 from Phase 17). [VERIFIED: pycopg/async_database.py lines 94–110]

---

## Code Map: TestEtlParity

### 13. Existing test_parity.py Structure

`tests/test_parity.py` has one primary class: `TestAsyncParity` (lines 13–173). It uses `inspect.getmembers` to enumerate `Database` and `AsyncDatabase` surfaces. [VERIFIED: tests/test_parity.py]

Key pattern — `test_all_database_public_methods_exist_in_async`:

```python
# tests/test_parity.py lines 34–52
def test_all_database_public_methods_exist_in_async(self):
    db_methods = set(
        name for name, _ in inspect.getmembers(Database) if not name.startswith("_")
    )
    async_methods = set(
        name
        for name, _ in inspect.getmembers(AsyncDatabase)
        if not name.startswith("_")
    )
    expected_in_async = db_methods - self.SYNC_ONLY_METHODS
    missing = expected_in_async - async_methods
    assert not missing, f"Methods in Database but missing in AsyncDatabase: {sorted(missing)}"
```

Public = `not name.startswith("_")`. This is the filter for `TestEtlParity` to mirror.

### 14. TestEtlParity — Drop-In Structure

`TestEtlParity` must be a **new top-level class** in `tests/test_parity.py`, following the same pattern. SC-4 says it "enumerates `EtlAccessor` vs `AsyncETLAccessor` method surfaces and asserts full parity". Required structure:

```python
class TestEtlParity:
    """ETL-12/ETL-13: EtlAccessor and AsyncETLAccessor have identical public method surfaces."""

    def test_etl_accessor_public_methods_match(self):
        from pycopg.etl import AsyncETLAccessor, ETLAccessor
        sync_methods = {
            name for name, _ in inspect.getmembers(ETLAccessor)
            if not name.startswith("_")
        }
        async_methods = {
            name for name, _ in inspect.getmembers(AsyncETLAccessor)
            if not name.startswith("_")
        }
        missing_in_async = sync_methods - async_methods
        assert not missing_in_async, f"Missing in AsyncETLAccessor: {sorted(missing_in_async)}"
        extra_in_async = async_methods - sync_methods
        assert not extra_in_async, f"Extra in AsyncETLAccessor: {sorted(extra_in_async)}"
```

Note: The existing `TestAsyncParity.test_known_exceptions_documented` will also pass once `async_db.etl` is wired, because `etl` will no longer be sync-only. The planner must account for the fact that after Phase 20 code is complete, the pre-existing `test_all_database_public_methods_exist_in_async` and `test_known_exceptions_documented` failures become green — not just TestEtlParity. [VERIFIED: tests/test_parity.py; 19-VERIFICATION.md]

---

## Code Map: Async asyncio.to_thread Pattern

### 15. asyncio.to_thread — Confirmed in Codebase

`asyncio.to_thread` is already used at `pycopg/async_database.py` lines 2663, 2667, 2682, 2684, 2750, 2758, 2763. The in-repo idiom:

```python
# async_database.py line 2663
await asyncio.to_thread(output_file.parent.mkdir, parents=True, exist_ok=True)

# async_database.py line 2667–2669
file_handle = await asyncio.to_thread(
    open, output_file, "w", encoding=encoding
)
```

For transform dispatch the equivalent pattern is:

```python
df = await asyncio.to_thread(step, df)
```

Python `>=3.11` is the floor (pyproject.toml `requires-python = ">=3.11"`); `asyncio.to_thread` requires `>=3.9`. No compatibility concern. [VERIFIED: pycopg/async_database.py lines 2663–2684; pyproject.toml]

---

## Code Map: Release Playbook

### 16. Version String Locations

| File | Line | Current Value | Must Become |
|------|------|---------------|-------------|
| `pyproject.toml` | 6 | `version = "0.4.0"` | `version = "0.5.0"` |
| `docs/conf.py` | 17 | `release = '0.4.0'` | `release = '0.5.0'` |
| `pycopg/__init__.py` | uses `importlib.metadata` | resolves to `0.4.0` at runtime | auto-resolves from pyproject after bump |

`pycopg/__init__.py.__version__` is resolved via `importlib.metadata.version("pycopg")` — it reads the installed package version. After bumping `pyproject.toml` and running `uv sync`, it will resolve to `0.5.0` without any code change in `__init__.py`. [VERIFIED: pycopg/__init__.py lines 34–38]

CLAUDE.md states `pycopg v0.3.1` but `pyproject.toml` says `0.4.0` (v0.4.0 shipped). The current actual version is `0.4.0`. [VERIFIED: pyproject.toml line 6]

### 17. CHANGELOG.md Format

`CHANGELOG.md` uses Keep a Changelog format. Structure:

```markdown
## [0.5.0] - 2026-06-XX

### Added
- `db.etl.*` / `async_db.etl.*` namespace: ETL pipeline runner (`run`, `history`,
  `last_run`, `dry_run`) with full sync/async parity ...
- `ETLAccessor`, `AsyncETLAccessor`, `RunResult`, `Pipeline` exported from top-level
- `Pipeline` frozen dataclass ...
- `pipeline_runs` auto-created on first `run()` ...
- ...
```

The `## [Unreleased]` section is currently empty (confirmed by CHANGELOG.md read). The v0.5.0 entry summarizes Phases 16-20 features. [VERIFIED: CHANGELOG.md]

### 18. MIGRATION.md

`MIGRATION.md` exists. v0.5.0 adds no breaking changes (ETL is additive). The entry is a short "New Features" section (no breaking changes table needed). Structure mirrors the "New Features" section in the v0.3.0 migration guide. [VERIFIED: MIGRATION.md lines 1–50]

### 19. Sphinx Docs — etl.md

`docs/spatial.md` is the template. `docs/etl.md` does not yet exist — Phase 20 creates it. The file must follow the same structure as `spatial.md`:

1. Intro paragraph explaining `db.etl.*` / `async_db.etl.*`
2. Access pattern (sync + async code examples)
3. Sections per method: `run`, `history`, `last_run`, `dry_run`
4. Autodoc section (optional — spatial.md does NOT use autodoc directives; it is prose + code examples only)

`docs/index.md` toctree must add `etl` between `spatial` and `timescaledb`:

```
spatial
etl
timescaledb
```

[VERIFIED: docs/index.md lines 1–22; docs/spatial.md]

### 20. Sphinx Build Command (warnings-as-errors)

```bash
uv run sphinx-build -W --keep-going -b html docs docs/_build/html
```

This is the exact command in `.github/workflows/tests.yml` line 66. [VERIFIED: .github/workflows/tests.yml]

### 21. interrogate Gate

```bash
uv run interrogate pycopg --fail-under 95 --quiet
```

`[tool.interrogate]` in pyproject.toml: `fail-under = 95`, `exclude = ["tests", "docs", "setup.py"]`, `ignore-init-method = true`. Every public method and every class in `pycopg/etl.py` (including `AsyncETLAccessor`) must have a numpydoc docstring. [VERIFIED: pyproject.toml lines 107–118; .github/workflows/tests.yml line 61]

### 22. Coverage Gate

```bash
uv run pytest
# invokes: pytest -v --cov=pycopg --cov-report=term-missing --cov-report=html --cov-fail-under=94
```

Coverage gate is `--cov-fail-under=94` in pyproject.toml `[tool.pytest.ini_options]` `addopts` line 90. This measures the full test suite. [VERIFIED: pyproject.toml lines 88–91]

**Known pre-existing full-suite failures** that are NOT regressions (from project memory):
- `test_parity.py::TestBehavioralParity::test_create_constructor_parity` — teardown `ObjectInUse` race
- `test_integration.py::TestAsyncIntegration::test_async_transaction_fix` — `UndefinedTable` / bad connection state
- `test_postgis_errors.py::TestPostGISErrorHandling::test_create_spatial_index_name_parameter` — `UndefinedTable`

Phase 19 verification also identified: `test_parity.py::TestAsyncParity::test_all_database_public_methods_exist_in_async` and `test_parity.py::TestAsyncParity::test_known_exceptions_documented` — both caused by the missing `async_db.etl` property, which Phase 20 fixes. After Phase 20 code is complete, these two become green. The other three pre-existing failures remain. Net result: full suite should show ≤ 3 pre-existing failures (down from 4-5 currently). [VERIFIED: pycopg-flaky-db-tests memory; 19-VERIFICATION.md]

**RISK:** The coverage gate (`--cov-fail-under=94`) runs against the full suite including the 3 pre-existing flaky tests. If those tests fail, pytest exits non-zero regardless of coverage. Strategy: measure coverage separately if needed with `uv run pytest --co -q | grep "3 failed" && uv run pytest --cov=pycopg --no-cov-on-fail` — but the CI environment (clean PG) passes all tests cleanly. The local env flakiness is environment-specific.

### 23. PyPI Publish Playbook

From `.github/workflows/publish.yml` and v0.4.0 memory:

1. Bump version in `pyproject.toml` + `docs/conf.py`
2. Update `uv.lock`: `uv lock`
3. Commit version bump
4. Tag: `git tag v0.5.0`
5. Push tag: `git push origin v0.5.0`
6. Create GitHub Release (triggers `publish.yml` workflow via `on: release: types: [published]`)
7. Workflow runs: `uv build` → `pypa/gh-action-pypi-publish@release/v1` using OIDC trusted publishing

Local build (for verification before tagging):
```bash
uv build
# Produces dist/pycopg-0.5.0-py3-none-any.whl and dist/pycopg-0.5.0.tar.gz
```

[VERIFIED: .github/workflows/publish.yml; v040-shipped memory]

---

## Code Map: __init__.py Exports

### 24. What Needs Adding to __init__.py

Current `pycopg/__init__.py` exports (lines 1–71):
- `ETLError`, `ETLTargetNotFoundError`, `ETLTransformError` — already exported
- `SpatialAccessor`, `AsyncSpatialAccessor` — already exported (precedent)
- `ETLAccessor` — NOT yet exported
- `AsyncETLAccessor` — NOT yet exported
- `RunResult` — NOT yet exported
- `Pipeline` — NOT yet exported

SC-5 requires `docs/etl.md` render without warnings. The autodoc references in `docs/etl.md` will need these symbols to resolve. Following `spatial.py` precedent (`SpatialAccessor` and `AsyncSpatialAccessor` are both in `__all__`), Phase 20 should add:

- `AsyncETLAccessor` (import from `pycopg.etl`, add to `__all__`)
- `ETLAccessor` (import from `pycopg.etl`, add to `__all__`)
- `RunResult` (import from `pycopg.etl`, add to `__all__`)
- `Pipeline` (import from `pycopg.etl`, add to `__all__`)

[VERIFIED: pycopg/__init__.py lines 1–71]

---

## Architecture Patterns

### Recommended File Changes

```
pycopg/
├── etl.py              # ADD AsyncETLAccessor class at bottom (after ETLAccessor)
├── async_database.py   # ADD _etl field to __init__ + etl property
└── __init__.py         # ADD AsyncETLAccessor, ETLAccessor, RunResult, Pipeline exports

tests/
└── test_parity.py      # ADD TestEtlParity class at bottom

docs/
├── etl.md              # CREATE (new file, follows spatial.md structure)
└── index.md            # ADD 'etl' to toctree
```

### Pattern: AsyncETLAccessor Location

`AsyncSpatialAccessor` lives at the bottom of `spatial.py` (line 1859). Following this exact pattern, `AsyncETLAccessor` belongs at the bottom of `etl.py`, after `ETLAccessor`. [VERIFIED: pycopg/spatial.py line 1859]

### Pattern: TYPE_CHECKING Import

`etl.py` already uses `TYPE_CHECKING` guard for `Database`:
```python
# etl.py lines 40–42
if TYPE_CHECKING:
    from pycopg.database import Database
```

`AsyncETLAccessor` will need `AsyncDatabase` added to this block:
```python
if TYPE_CHECKING:
    from pycopg.database import Database
    from pycopg.async_database import AsyncDatabase
```

[VERIFIED: pycopg/etl.py lines 40–42]

### Pattern: asyncio import

`etl.py` does not currently import `asyncio`. The async class adds `import asyncio` at module level (following the async_database.py convention). [VERIFIED: pycopg/etl.py lines 25–38; pycopg/async_database.py line 1 area]

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Thread-safe sync callable dispatch from async | Custom thread pool / manual executor | `asyncio.to_thread(fn, *args)` (stdlib, Python ≥ 3.9) | Already used in codebase; no new import needed beyond `asyncio` |
| Async context manager for DB connection | Custom connection wrapper | `async with self._db.connect(autocommit=True)` | Already defined on `AsyncDatabase`; exact same API as sync |
| Async cursor with dict rows | Custom cursor factory | `async with conn.cursor(row_factory=dict_row)` | psycopg3 native; same as sync but `async with` |
| Public method enumeration for parity test | Custom reflection | `inspect.getmembers(cls)` with `not name.startswith("_")` | Already used in `TestAsyncParity`; zero-effort copy |

---

## Common Pitfalls

### Pitfall 1: Using `async with` without `await` on psycopg cursor calls

**What goes wrong:** `conn.cursor(row_factory=dict_row)` returns an `AsyncCursor` context manager. Inside it, `cur.execute(...)` and `cur.fetchone()` are coroutines that need `await`. Forgetting `await cur.execute(...)` will silently return a coroutine object instead of executing the query.

**How to avoid:** Every psycopg async call needs `await`: `await cur.execute(...)`, `await cur.fetchone()`, `await cur.fetchall()`.

**Warning signs:** Test shows `None` result or `TypeError: 'coroutine' object is not subscriptable`.

### Pitfall 2: `asyncio.to_thread` wraps the callable + args, not the result

**What goes wrong:** `await asyncio.to_thread(step(df))` evaluates `step(df)` synchronously on the current thread before passing the result (not a callable) to `to_thread`. This defeats the purpose.

**How to avoid:** Always `await asyncio.to_thread(step, df)` — pass the callable and its arguments separately.

**Warning signs:** The transform still blocks the event loop; no `TypeError` (it silently works wrong).

### Pitfall 3: `self._db.session()` in `AsyncETLAccessor.run()` must be `async with`

**What goes wrong:** The sync load block uses `with self._db.session()`. In the async version this must be `async with self._db.session()`. Using `with` (non-async) on an `@asynccontextmanager` raises `AttributeError: __enter__`.

**How to avoid:** Mirror the sync block as `async with self._db.session(): async with self._db.transaction() as conn: async with conn.cursor() as cur:`.

### Pitfall 4: TestAsyncParity SYNC_ONLY_METHODS list needs no change

**What goes wrong:** After `async_db.etl` is wired, `TestAsyncParity.test_known_exceptions_documented` will fail if `etl` is still listed in `SYNC_ONLY_METHODS`. It is NOT listed there — the current failure is because `etl` is missing from `AsyncDatabase`, not because it's in the exclusion list. After Phase 20 adds the property, this test fixes itself. [VERIFIED: tests/test_parity.py lines 19–31]

**How to avoid:** Do not touch `SYNC_ONLY_METHODS`. Just add the property and the test becomes green.

### Pitfall 5: Coverage gate with `-o addopts=""` does NOT measure full coverage

**What goes wrong:** For targeted ETL test runs, the project convention is `uv run pytest tests/test_etl_accessor.py -o addopts=""` (strips coverage flags). This is intentional for fast iteration. But for the SC-5 coverage gate check, you MUST run `uv run pytest` (full suite with the default addopts) — not a targeted run with `-o addopts=""`.

**How to avoid:** The SC-5 coverage task must explicitly use `uv run pytest` without `-o addopts=""`.

### Pitfall 6: `docs/etl.md` must be added to `docs/index.md` toctree

**What goes wrong:** Creating `docs/etl.md` alone does not make it appear in RTD navigation. Sphinx will emit a warning (`WARNING: document isn't included in any toctree`) which with `-W` (warnings-as-errors) causes the build to fail.

**How to avoid:** Add `etl` to the toctree in `docs/index.md` in the same commit as `docs/etl.md`.

---

## State of the Art

| Aspect | Current State | Notes |
|--------|---------------|-------|
| `db.etl` lazy property | SHIPPED (Phase 17) | database.py lines 253–271 |
| `async_db.etl` property | NOT PRESENT | Phase 20 deliverable |
| `ETLAccessor` | SHIPPED (Phases 17–19) | Complete public surface |
| `AsyncETLAccessor` | NOT PRESENT | Phase 20 deliverable |
| `RunResult` in `__all__` | NOT PRESENT | Phase 20 adds |
| `Pipeline` in `__all__` | NOT PRESENT | Phase 20 adds |
| `docs/etl.md` | NOT PRESENT | Phase 20 creates |
| version in pyproject.toml | `0.4.0` | Phase 20 bumps to `0.5.0` |
| CHANGELOG v0.5.0 entry | NOT PRESENT (`## [Unreleased]` empty) | Phase 20 writes |

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL (`pycopg_test`) | ETL integration tests | ✓ (local env) | 17 (via timescaledb-ha) | — |
| `uv` | Build + test commands | ✓ | per uv sync | — |
| `interrogate` | Docstring gate | ✓ (dev dep) | `>=1.7.0` | — |
| `sphinx` + docs deps | Docs build | ✓ via `docs/requirements.txt` | see docs/requirements.txt | — |
| GitHub Actions (for PyPI publish) | Trusted publishing | ✓ | OIDC configured | local `uv build` + manual twine as last resort |

**Missing dependencies with no fallback:** None.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest with pytest-asyncio |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run (targeted, no cov) | `uv run pytest tests/test_parity.py tests/test_etl_accessor.py -o addopts="" -x -q` |
| Full suite command | `uv run pytest` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ETL-12 | `await async_db.etl.run(pipeline)` returns `RunResult` equivalent to sync | integration | `uv run pytest tests/test_parity.py::TestEtlParity -o addopts="" -x` | ❌ Wave 0: `TestEtlParity` class in `test_parity.py` |
| ETL-12 | `await async_db.etl.history(name)` returns `list[RunResult]` | integration | `uv run pytest tests/test_parity.py::TestEtlParity -o addopts="" -x` | ❌ Wave 0 |
| ETL-12 | `await async_db.etl.last_run(name)` returns `RunResult \| None` | integration | `uv run pytest tests/test_parity.py::TestEtlParity -o addopts="" -x` | ❌ Wave 0 |
| ETL-12 | Transform callables dispatched via `asyncio.to_thread` (non-blocking) | unit / behavioral | `uv run pytest tests/test_parity.py::TestEtlParity -o addopts="" -x` | ❌ Wave 0 |
| ETL-13 | `db.etl` lazy property returns `ETLAccessor` | unit | Already green in existing `TestETLAccessorUnit` | ✅ |
| ETL-13 | `async_db.etl` lazy property returns `AsyncETLAccessor` | unit | `uv run pytest tests/test_parity.py::TestEtlParity -o addopts="" -x` | ❌ Wave 0 |
| ETL-13 | `TestEtlParity` enumerates and asserts full surface parity | structural | `uv run pytest tests/test_parity.py::TestEtlParity -o addopts="" -x` | ❌ Wave 0 |
| SC-5 | Coverage ≥ 94% | gate | `uv run pytest` (full suite) | N/A |
| SC-5 | interrogate ≥ 95 | gate | `uv run interrogate pycopg --fail-under 95 --quiet` | N/A |
| SC-5 | Sphinx build clean with `-W` | gate | `uv run sphinx-build -W --keep-going -b html docs docs/_build/html` | N/A |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/test_parity.py tests/test_etl_accessor.py -o addopts="" -x -q`
- **Per wave merge:** Same, plus `uv run pytest tests/test_etl.py -o addopts="" -x -q`
- **Phase gate:** `uv run pytest` (full suite, ≥ 94% coverage); `uv run interrogate pycopg --fail-under 95 --quiet`; `uv run sphinx-build -W --keep-going -b html docs docs/_build/html`

### Wave 0 Gaps

- [ ] `TestEtlParity` class in `tests/test_parity.py` — covers ETL-12, ETL-13
- [ ] (Optional) `tests/test_etl_accessor.py::TestAsyncRunResultSurface` — behavioral parity tests for async run/history/last_run/dry_run against real DB (SC-1..SC-4 async equivalent); may be added if SC-5 coverage is at risk

---

## Security Domain

No new security concerns in Phase 20. The `AsyncETLAccessor` reuses all SQL from the sync accessors — same SQL constants (`ETL_INSERT_RUN`, `ETL_UPDATE_RUN`, `ETL_LIST_RUNS`, `ETL_GET_LAST_RUN`, `ETL_GET_RUN`) with parameterized queries, and the same `validate_identifiers` calls in the pure builders. No new identifier interpolation paths. ASVS V5 (input validation) is covered by the unchanged builder layer. [VERIFIED: pycopg/etl.py SQL builder functions]

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `docs/etl.md` should be prose + code examples only (no `autoclass::` directives), following `docs/spatial.md` convention | Release Playbook §19 | Low — spatial.md is verified as prose-only; if autodoc directives are needed the Sphinx `-W` build will surface it |
| A2 | A behavioral parity test class (`TestAsyncRunResultSurface`) analogous to Phase 19's `TestRunResultSurface` is optional for Phase 20 — `TestEtlParity` (structural surface check) is sufficient for SC-4 | Validation Architecture | Low — SC-4 text says "enumerates … method surfaces and asserts full parity"; structural is sufficient; behavioral coverage comes from the async methods being exercised via coverage |

---

## Open Questions (RESOLVED)

1. **Does `TestEtlParity` need behavioral (real-DB) tests in addition to structural surface enumeration?**
   - What we know: SC-4 says "enumerates `EtlAccessor` vs `AsyncETLAccessor` method surfaces and asserts full parity" — this is a structural check.
   - What's unclear: Whether a behavioral test (actually calling `await async_db.etl.run(pipeline)` against a real DB) is required for the SC-4 green bar or just for coverage confidence.
   - Recommendation: Add a minimal behavioral test class (3–4 tests: run/history/last_run/dry_run) in `test_etl_accessor.py` or `test_parity.py`. This ensures async paths are exercised by the coverage gate and avoids the risk of the structural test passing but the async code being dead. The planner should include this as a task in the async accessor wave.

2. **Should `ETLAccessor` and `AsyncETLAccessor` be split into separate files?**
   - What we know: `SpatialAccessor` and `AsyncSpatialAccessor` both live in `spatial.py` — one file (confirmed at spatial.py lines 1023 and 1859). The research objective says to mirror this pattern.
   - Recommendation: Keep `AsyncETLAccessor` in `etl.py` (same file as `ETLAccessor`). No split needed.

---

## Sources

### Primary (HIGH confidence)

- `pycopg/etl.py` (read in full) — complete sync accessor surface, method signatures, run-log isolation code
- `pycopg/async_database.py` (lines 60–401, 1895–1960, 2655–2690) — async connection API, `spatial` property template, `asyncio.to_thread` usage
- `pycopg/database.py` (lines 54–271) — existing `etl` lazy property (already shipped)
- `tests/test_parity.py` (read in full) — `TestAsyncParity` structure for `TestEtlParity` pattern
- `pyproject.toml` (read in full) — version, coverage gate, interrogate config, Python floor
- `.github/workflows/tests.yml` (read in full) — CI commands: interrogate, sphinx -W, pytest
- `.github/workflows/publish.yml` (read in full) — PyPI publish playbook
- `pycopg/__init__.py` (read in full) — current exports, what needs adding
- `pycopg/spatial.py` (lines 1859–1999) — `AsyncSpatialAccessor` as exact structural template
- `docs/conf.py` (read in full) — Sphinx config, release version location
- `docs/index.md` (read in full) — toctree for adding `etl`
- `.readthedocs.yaml` (read in full) — RTD build config

### Secondary (MEDIUM confidence)

- `19-VERIFICATION.md` — pre-existing failing tests catalogue (confirmed 4 failures including 2 that Phase 20 fixes)
- `pycopg-flaky-db-tests` memory — pre-existing flaky test identities
- `v040-shipped` memory — v0.4.0 release playbook details (OIDC publish, tag → Release → CI)

---

## Metadata

**Confidence breakdown:**
- AsyncETLAccessor code map: HIGH — sync source read in full; async API patterns verified in async_database.py
- Lazy property wiring: HIGH — template at exact lines in database.py and async_database.py
- TestEtlParity structure: HIGH — test_parity.py read in full; drop-in pattern clear
- Release playbook: HIGH — workflows read in full; v0.4.0 memory confirms same process
- __init__.py exports: HIGH — file read in full; SpatialAccessor precedent clear

**Research date:** 2026-06-15
**Valid until:** 2026-07-15 (stable codebase — no fast-moving dependencies)
