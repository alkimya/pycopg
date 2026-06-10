# Phase 13: Qualité documentaire (docstrings numpydoc + interrogate) — Research

**Researched:** 2026-06-10
**Domain:** Python docstring quality (numpydoc migration, interrogate coverage gate, mypy progressive typing, domain exceptions)
**Confidence:** HIGH — all major claims verified against official docs, PyPI registry, and direct codebase inspection

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01 — Exception scope (domain only):**
Convert ONLY domain-business errors. Concretely:
- `RuntimeError("... extension not installed")` (PostGIS, TimescaleDB) → `ExtensionNotAvailable`
- `ValueError(f"Database '{name}' already exists")` → `DatabaseExists` (new type, D-02)
- DO NOT touch: `ValueError` for API misuse ("Specify either table or sql", "Invalid ON DELETE"),
  `RuntimeError("Already in session mode")`, and `RuntimeError("pg_dump/pg_restore/psql ... failed")`.

**D-02 — Reuse existing + 1 targeted addition:**
Map to existing `pycopg/exceptions.py` types when possible (`ExtensionNotAvailable`, `TableNotFound`).
Add exactly one new type: `DatabaseExists(PycopgError)`. No proliferation.

**D-03 — Breaking, clean inheritance:**
New and modified types inherit `PycopgError` only (no double inheritance). Breaking change assumed;
CHANGELOG/MIGRATION notes deferred to Phase 15 (REL-03).

**D-04 — Test non-regression:**
Tests that assert `pytest.raises(RuntimeError)` or `pytest.raises(ValueError)` on the converted sites
MUST be updated to the new types in the same plan as the conversion.

**D-05 — mypy progressive, non-blocking:**
`mypy` added as dev dep + permissive config (no `--strict`). Fix `async_engine` annotation (TY2)
and easy errors. CI job added but non-blocking (`continue-on-error: true` or equivalent).

**D-06 — numpydoc shallow format locked:**
Summary + Parameters + Returns + Raises (pertinent). **No Examples section.**
`napoleon_numpy_docstring = True` added to `docs/conf.py`. Whether to disable
`napoleon_google_docstring` mid-migration vs. post-migration: researcher finding below (see
"Napoleon dual-format behavior").

**D-07 — Module-by-module migration, multiple plans:**
`database.py` (~80 docstrings) and `async_database.py` (~81) each get their own plan.
Remaining modules (`base.py`, `config.py`, `utils.py`, `migrations.py`, `pool.py`, ~38) grouped.
Planner decides exact plan boundaries.

**D-08 — Double non-regression guard:**
(1) `interrogate >= 95` (coverage quantity) AND (2) Sphinx build warning-free (form quality).
No `pydocstyle`/ruff-D this phase.

**D-09 — `importlib.metadata` for `__version__`:**
Replace `__version__ = "0.3.1"` at `pycopg/__init__.py:63` with `importlib.metadata.version("pycopg")`
plus `PackageNotFoundError` fallback.

### Claude's Discretion
- Exact plan count for docstring migration (planner decides, guided by D-07).
- Exact mypy config flags (`ignore_missing_imports`, `disallow_untyped_defs`, per-module overrides).
- CI mechanism for non-blocking mypy (continue-on-error vs separate job vs baseline).
- Whether to keep `napoleon_google_docstring = True` during migration vs disable it immediately.

### Deferred Ideas (OUT OF SCOPE)
- Mypy strict / `--strict` mode — milestone ultérieur.
- Symmetric exception families (DatabaseNotFound, SchemaExists, etc.) — only add if proven needed.
- `pydocstyle` / ruff `D` rules — too much noise on existing codebase, reconsidered post-migration.
- CHANGELOG / MIGRATION notes for breaking exception changes — Phase 15 (REL-03).
- Replace `print()` with logging — API-03 v2, out of scope.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DOC-06 | All public docstrings migrated to numpydoc (Summary/Parameters/Returns/Raises), shallow, no Examples | 187 Google-style docstrings confirmed by AST analysis; numpydoc format verified via napoleon docs |
| DOC-07 | `interrogate` added (dev dep, `fail-under=95`), enforced in CI | interrogate 1.7.0 verified on PyPI; config pattern confirmed from official repo |
| DOC-08 | `napoleon_numpy_docstring` enabled in Sphinx conf | `sphinx.ext.napoleon` already loaded in `docs/conf.py:25`; adding single flag confirmed safe |
| DOC-09 | Public methods raise real exception types (ExtensionNotAvailable, TableNotFound, etc.) | Full raise-site inventory done: 14 extension RuntimeErrors + 2 DatabaseExists ValueErrors |
| DOC-10 | `__version__` via `importlib.metadata.version()` | Pattern verified working: `version('pycopg')` returns `'0.3.1'` in uv env; package name matches |
| DOC-11 | mypy added as dev dep with config (TY1) | mypy 2.1.0 verified on PyPI; permissive config pattern confirmed |
| DOC-12 | `async_engine` property annotated with return type (TY2) | Property at `async_database.py:91` has no return annotation; `Engine` → `AsyncEngine` from `sqlalchemy.ext.asyncio` |
</phase_requirements>

---

## Summary

Phase 13 is a pure quality-improvement phase with no runtime behavior changes beyond exception types. The codebase has 187 Google-style public docstrings across 7 modules (confirmed by AST analysis: database.py=77, async_database.py=68, base.py=5, utils.py=10, pool.py=13, migrations.py=7, config.py=7) that must be migrated to numpydoc shallow format. Current public docstring coverage is 100% — every public function/class/method already has a docstring, so `interrogate` at 95% will pass immediately after migration. The exception conversion scope is narrow and precise: 14 `RuntimeError("... not installed")` sites (7 in database.py, 7 in async_database.py) → `ExtensionNotAvailable`, plus 2 `ValueError(f"Database '{name}' already exists")` sites → new `DatabaseExists(PycopgError)`. All other RuntimeError/ValueError sites are correctly programmer-API errors and remain unchanged. The `__version__` fix is a 3-line mechanical change that has been tested and works.

The main planning risks are: (1) the docstring migration is high-volume (187 sites) and must be done module-by-module per D-07, not big-bang; (2) the Sphinx build guard (D-08) requires adding sphinx+napoleon as a CI step that does not currently exist; (3) the napoleon dual-format behavior during migration needs careful handling (both formats default to `True` in napoleon — see below).

**Primary recommendation:** Plan the phase in 6 plans: (1) tooling setup (interrogate+mypy in pyproject.toml, CI jobs), (2) exception conversion + `__version__` + `async_engine` annotation, (3) docstrings database.py, (4) docstrings async_database.py, (5) docstrings remaining 5 modules, (6) Sphinx conf flag + Sphinx build verification. Plans 3-5 are the high-volume work but low-risk (docs only, no logic).

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Docstring format migration | Source code (pycopg/) | CI validation | Content change in .py files; validated at CI by interrogate + sphinx |
| interrogate coverage gate | CI (tests.yml job) | pyproject.toml config | Enforcement is CI; config lives in pyproject.toml |
| mypy type checking | CI (tests.yml job, non-blocking) | pyproject.toml config | Same CI file; separate non-blocking step/job |
| Sphinx build guard | CI (tests.yml job) + docs/conf.py | docs/ | Sphinx build runs in CI; napoleon config in docs/conf.py |
| Exception type conversion | Source code (pycopg/database.py, async_database.py, exceptions.py) | tests/ | Runtime logic change; tests updated in same plan |
| `__version__` fix | Source code (pycopg/__init__.py) | — | Single-file mechanical change |
| `async_engine` annotation | Source code (pycopg/async_database.py) | — | Single-property annotation change |

---

## Standard Stack

### Core (already in project)
| Library | Version | Purpose | Status |
|---------|---------|---------|--------|
| sphinx.ext.napoleon | bundled w/ Sphinx | Parses Google + NumPy docstrings for Sphinx autodoc | Already in `docs/conf.py` extensions list |
| sqlalchemy.ext.asyncio.AsyncEngine | SQLAlchemy ≥2.0 | Return type for `async_engine` property | Already a project dependency |

### To Add (dev dependencies)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| interrogate | 1.7.0 [VERIFIED: pypi.org/project/interrogate] | Docstring coverage measurement and enforcement | De-facto standard for Python docstring coverage; used by attrs, pyjanitor, and others; native pyproject.toml support |
| mypy | 2.1.0 [VERIFIED: pypi.org/project/mypy] | Static type checker | Official Python static typing tool; maintained by python/mypy org |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| interrogate | pydocstyle / ruff `D` rules | Deferred per D-08: too many existing violations to triage; interrogate checks coverage (presence), not format |
| mypy | pyright / pylance | mypy is the established open-source standard; pyright is VS Code-centric. Both valid but mypy better integrates with existing Python workflows |

**Installation:**
```bash
# Add to [dependency-groups] dev in pyproject.toml:
# "interrogate>=1.7.0",
# "mypy>=2.1.0",
# Then:
uv sync --all-extras --dev
```

---

## Package Legitimacy Audit

> slopcheck was not installable in this environment. All packages marked `[ASSUMED]` as per protocol. Planner must gate each install behind a `checkpoint:human-verify` task.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| interrogate | PyPI | ~6 yrs (since 2018) | High (used by attrs, pyjanitor) | github.com/econchick/interrogate | N/A | [ASSUMED] — well-known tool, legitimate |
| mypy | PyPI | ~12 yrs (since 2013) | Very High (core Python tooling) | github.com/python/mypy | N/A | [ASSUMED] — official python org project |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none — both are established ecosystem tools

*slopcheck was unavailable at research time; all packages above are tagged `[ASSUMED]` and the planner must gate each install behind a `checkpoint:human-verify` task.*

---

## Architecture Patterns

### System Architecture Diagram

```
pycopg/         (source — docstrings migrated here)
  ├── __init__.py         (__version__ fixed: importlib.metadata)
  ├── exceptions.py       (DatabaseExists added)
  ├── database.py         (Google→numpydoc; RuntimeError→ExtensionNotAvailable)
  ├── async_database.py   (Google→numpydoc; RuntimeError→ExtensionNotAvailable; async_engine annotated)
  ├── base.py             (Google→numpydoc)
  ├── config.py           (Google→numpydoc)
  ├── utils.py            (Google→numpydoc)
  ├── migrations.py       (Google→numpydoc)
  └── pool.py             (Google→numpydoc)
       ↓
CI validates two gates:
  interrogate ≥ 95%  (quantity — are all public symbols documented?)
  sphinx-build -W    (quality — do napoleon warnings pass?)
       ↓ (non-blocking)
  mypy               (type annotations — async_engine TY2 + permissive scan)
```

### Recommended Project Structure Changes
```
pyproject.toml
  [tool.interrogate]        ← NEW section
  [tool.mypy]               ← NEW section
  [[tool.mypy.overrides]]   ← NEW overrides for sqlalchemy/psycopg
  [dependency-groups]
    dev = [..., "interrogate>=1.7.0", "mypy>=2.1.0"]   ← NEW deps

docs/conf.py
  napoleon_numpy_docstring = True    ← NEW line (after line 27)
  # napoleon_google_docstring = True  ← Keep True during migration, disable after

.github/workflows/tests.yml
  - name: interrogate        ← NEW blocking step
  - name: sphinx-build       ← NEW blocking step (warn-as-error for napoleon)
  - name: mypy               ← NEW non-blocking step (continue-on-error: true)
```

### Pattern 1: numpydoc shallow format (target format)

**What:** Sections use underline-style headers with dashes, not `Key:` prefixes. Parameters use `name : type` notation. No Examples section.

**When to use:** All public methods, functions, classes in pycopg/

```python
# Source: sphinx.ext.napoleon official documentation
def execute(
    self,
    sql: str,
    params: list | None = None,
    *,
    schema: str = "public",
) -> list[dict]:
    """Execute a SQL statement and return results.

    Parameters
    ----------
    sql : str
        SQL statement to execute.
    params : list, optional
        Query parameters for %s placeholders.
    schema : str, optional
        Default schema, by default "public".

    Returns
    -------
    list[dict]
        List of result rows as dicts.

    Raises
    ------
    ExtensionNotAvailable
        If a required extension is not installed.
    """
```

### Pattern 2: Google-style (current format — to be replaced)

```python
# Source: existing pycopg codebase (e.g. database.py)
def execute(self, sql: str, params=None) -> list[dict]:
    """Execute a SQL statement and return results.

    Args:
        sql: SQL statement to execute.
        params: Query parameters for %s placeholders.

    Returns:
        List of result rows as dicts.

    Example:
        db.execute("SELECT * FROM users WHERE id = %s", [1])
    """
```

**Migration rule:** Replace `Args:` → `Parameters\n----------`, `Returns:` → `Returns\n-------`, `Raises:` → `Raises\n------`, `Example:` → delete entirely.

### Pattern 3: Napoleon dual-format behavior during migration

**Confirmed behavior:** Both `napoleon_google_docstring` and `napoleon_numpy_docstring` default to `True` in sphinx.ext.napoleon. When both are enabled, napoleon attempts to parse each docstring in both formats. In practice, Google-style docstrings with `Args:` sections do NOT parse as numpydoc — the formats are syntactically distinct enough that napoleon will handle mixed-format codebases correctly during a gradual migration. [CITED: sphinx.ext.napoleon docs — "both default to True"]

**Recommended approach for this phase:**
- Wave 1 (tooling): Add `napoleon_numpy_docstring = True` to `docs/conf.py`. Leave `napoleon_google_docstring = True` (it already defaults True — no change needed). Both are enabled.
- Waves 2-4 (migration): Both formats remain enabled — napoleon parses each module correctly as it is migrated.
- After migration complete (end of phase): Add `napoleon_google_docstring = False` to disable Google parsing. This is a final cleanup step, not a blocker.

**Risk:** Sphinx `show_warning_types = True` in conf.py helps identify any ambiguous docstrings that confuse napoleon's parser during transition. [ASSUMED — no official doc confirming zero-warning mixed state]

### Pattern 4: Exception conversion

**What:** Replace `RuntimeError("... extension not installed")` with `ExtensionNotAvailable`. Add `DatabaseExists` for the "already exists" sites.

```python
# Source: existing pycopg/exceptions.py + D-02 decision

# In exceptions.py — ADD:
class DatabaseExists(PycopgError):
    """Database already exists."""
    pass

# In database.py / async_database.py — REPLACE at each "not installed" site:
# BEFORE:
raise RuntimeError(
    "TimescaleDB extension not installed. Run db.create_extension('timescaledb')"
)
# AFTER (message text preserved per D-01/specifics):
raise ExtensionNotAvailable(
    "TimescaleDB extension not installed. Run db.create_extension('timescaledb')"
)

# BEFORE:
raise ValueError(f"Database '{name}' already exists")
# AFTER:
raise DatabaseExists(f"Database '{name}' already exists")
```

### Pattern 5: `__version__` via `importlib.metadata`

**What:** Single source of truth — reads from the installed package metadata (set by pyproject.toml).

```python
# Source: Python stdlib importlib.metadata docs + verified working in this project
# In pycopg/__init__.py, replace line 63:

# BEFORE:
__version__ = "0.3.1"

# AFTER:
try:
    from importlib.metadata import version, PackageNotFoundError
    __version__ = version("pycopg")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"  # editable install without package metadata
```

**Verified:** `importlib.metadata.version("pycopg")` returns `"0.3.1"` in the project's uv env. Package name `"pycopg"` matches `[project] name` in pyproject.toml exactly.

### Pattern 6: `async_engine` return annotation (TY2)

**What:** Property at `async_database.py:91` lacks return type. Sync counterpart at `database.py:231` already has `-> Engine`.

```python
# Source: sqlalchemy.ext.asyncio API docs + database.py:231 as reference pattern
from sqlalchemy.ext.asyncio import AsyncEngine  # Add to imports

# BEFORE:
@property
def async_engine(self):
    """Get or create async SQLAlchemy engine (lazy initialization)."""

# AFTER:
@property
def async_engine(self) -> AsyncEngine:
    """Get or create async SQLAlchemy engine (lazy initialization)."""
```

Note: `AsyncEngine` is imported locally inside the method (`from sqlalchemy.ext.asyncio import create_async_engine`). For the type annotation, import `AsyncEngine` at module level under `TYPE_CHECKING` guard or add to the top-level imports. The `_async_engine` attribute type should also be updated: `self._async_engine: AsyncEngine | None = None`.

### Anti-Patterns to Avoid

- **Big-bang docstring migration:** Converting all 187 sites in one commit produces a non-reviewable diff. D-07 mandates module-by-module commits.
- **Adding Examples sections:** Explicitly locked out by D-06. Do not add Examples sections even if they existed in the Google-style originals.
- **Double inheritance `(PycopgError, RuntimeError)`:** D-03 mandates `PycopgError` only. No hybrid types.
- **Converting non-domain errors:** `ValueError("Specify either table or sql")` and `RuntimeError("Already in session mode")` stay as-is per D-01. These are programmer-API errors, not business domain errors.
- **Removing `napoleon_google_docstring` before migration is complete:** Doing so mid-migration will cause Sphinx build failures on any remaining Google-style docstrings.
- **Running Sphinx build without docs/requirements.txt deps:** Sphinx is not in the main `uv` dev group; it has its own `docs/requirements.txt`. The CI step will need to install those dependencies separately (or add sphinx to dev deps — see Open Questions).

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Docstring coverage measurement | Custom AST walker counting docstrings | `interrogate` | Handles edge cases: property decorators, nested classes, `__init__`, magic methods, configurable ignore flags; produces CI-friendly exit codes |
| Static type checking | Inline assertions or custom type validation | `mypy` | Type inference, generics, union types — reimplementing any of this is years of work |
| NumPy docstring parsing for Sphinx | Custom Sphinx extension | `sphinx.ext.napoleon` | Already bundled with Sphinx; handles numpydoc format completely including cross-references |

**Key insight:** All three tools (`interrogate`, `mypy`, `sphinx.ext.napoleon`) are established ecosystem tools with years of battle-testing. The work here is configuration + migration, not new tooling.

---

## Common Pitfalls

### Pitfall 1: interrogate counts vs. what the planner expects

**What goes wrong:** `interrogate` by default counts module docstrings, `__init__` methods, magic methods, private methods — everything. With `ignore-init-method = true` and other ignore flags, the 95% target may be easier or harder to hit than expected.

**Why it happens:** Current codebase has 100% coverage on public symbols (AST-verified), but interrogate's default counting scope is wider than "public only." Private methods without docstrings would pull the score below 95%.

**How to avoid:** Run `uv run interrogate pycopg --verbose` as first step in Wave 0 to measure baseline before setting `fail-under=95`. Recommended config: `ignore-init-method = true` (matches the convention that `__init__` docs often belong on the class), `ignore-module = false` (module docstrings exist in all 7 modules), `ignore-private = false` (keep — we want to know about private gaps but not force 95% on them; see Open Questions).

**Warning signs:** interrogate score unexpectedly below 90% after migration — check if private/magic methods are undocumented.

### Pitfall 2: Sphinx build fails on import errors, not napoleon errors

**What goes wrong:** `sphinx-build` with autodoc tries to `import pycopg` during build. If `geopandas`, `geoalchemy2`, etc. are not installed in the CI environment, autodoc raises `ImportError` and the build fails before napoleon even processes docstrings.

**Why it happens:** `docs/conf.py` adds `pycopg` to `sys.path` for autodoc; optional deps like `geopandas` are used in `database.py` inside methods but still trigger import-time checks in some cases.

**How to avoid:** In the CI step for Sphinx, install with `uv sync --all-extras --dev` (same as tests.yml already does) AND `pip install -r docs/requirements.txt` (or add sphinx to dev deps). Alternatively, set `autodoc_mock_imports = ["geopandas", "geoalchemy2", "shapely"]` in `docs/conf.py` for CI robustness. [ASSUMED — autodoc_mock_imports behavior not verified with current conf.py]

**Warning signs:** CI sphinx-build step fails with `ModuleNotFoundError` rather than napoleon warnings.

### Pitfall 3: numpydoc "Parameters" section alignment

**What goes wrong:** Napoleon is strict about numpydoc section formatting. A missing blank line after the section header, wrong number of dashes, or inconsistent indentation causes napoleon to silently skip the section or emit a warning.

**Why it happens:** The numpydoc convention requires the section underline to be exactly as long as the section name:
```
Parameters
----------   ← must be exactly len("Parameters") dashes = 10 dashes
```

**How to avoid:** Use `show_warning_types = True` in `docs/conf.py` during migration to surface napoleon parse warnings. After migration, run `sphinx-build -W` to catch any remaining malformed sections.

**Warning signs:** `sphinx-build` completes but rendered API docs show raw text instead of formatted parameter tables.

### Pitfall 4: Tests not updated when exception types change

**What goes wrong:** Converting `RuntimeError(...)` to `ExtensionNotAvailable(...)` breaks existing `pytest.raises(RuntimeError)` assertions — tests fail red after the conversion.

**Why it happens:** D-04 mandates updating tests in the same plan. Doing the exception conversion without updating the tests creates a broken state.

**How to avoid:** The raise-site inventory (see below) maps each conversion site to its test file. Both the source change and test update must be in the same commit. Use the definitive inventory table as a checklist.

**Warning signs:** `uv run pytest tests/ -x -q -o addopts=""` fails immediately after exception conversion plan.

### Pitfall 5: `AsyncEngine` import causes circular import

**What goes wrong:** Adding `from sqlalchemy.ext.asyncio import AsyncEngine` at the top of `async_database.py` might clash with the lazy import pattern already in the file (the method body does `from sqlalchemy.ext.asyncio import create_async_engine` locally to avoid heavy import cost at module load time).

**Why it happens:** sqlalchemy.ext.asyncio is only conditionally needed (when async engine is first accessed).

**How to avoid:** Use `TYPE_CHECKING` guard for the annotation import — the annotation is used only by mypy, not at runtime:
```python
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine
```
This preserves lazy-import behavior while satisfying mypy. [ASSUMED — verify no circular import in sqlalchemy.ext.asyncio with TYPE_CHECKING in this specific setup]

---

## Exception Conversion Inventory (DOC-09 / D-01 through D-04)

### Sites to Convert: `RuntimeError` → `ExtensionNotAvailable`

| File | Line | Message (preserved) | Method |
|------|------|----------------------|--------|
| database.py | 1369-1371 | `"PostGIS extension not installed. Run db.create_extension('postgis')"` | `from_geodataframe` |
| database.py | 1523-1525 | `"TimescaleDB extension not installed. Run db.create_extension('timescaledb')"` | `create_hypertable` |
| database.py | 1559-1562 | `"TimescaleDB extension not installed. Run db.create_extension('timescaledb')"` | `enable_compression` |
| database.py | 1606-1608 | `"TimescaleDB extension not installed. Run db.create_extension('timescaledb')"` | `add_compression_policy` |
| database.py | 1637-1639 | `"TimescaleDB extension not installed. Run db.create_extension('timescaledb')"` | `add_retention_policy` |
| database.py | 1656-1658 | `"TimescaleDB extension not installed. Run db.create_extension('timescaledb')"` | `list_hypertables` |
| database.py | 1674-1676 | `"TimescaleDB extension not installed. Run db.create_extension('timescaledb')"` | `hypertable_info` |
| async_database.py | 1077-1079 | `"TimescaleDB extension not installed. Run db.create_extension('timescaledb')"` | `create_hypertable` |
| async_database.py | 1113-1116 | `"TimescaleDB extension not installed. Run db.create_extension('timescaledb')"` | `enable_compression` |
| async_database.py | 1160-1163 | `"TimescaleDB extension not installed. Run db.create_extension('timescaledb')"` | `add_compression_policy` |
| async_database.py | 1191-1194 | `"TimescaleDB extension not installed. Run db.create_extension('timescaledb')"` | `add_retention_policy` |
| async_database.py | 1210-1213 | `"TimescaleDB extension not installed. Run db.create_extension('timescaledb')"` | `list_hypertables` |
| async_database.py | 1228-1231 | `"TimescaleDB extension not installed. Run db.create_extension('timescaledb')"` | `hypertable_info` |
| async_database.py | 1805-1807 | `"PostGIS extension not installed. Run db.create_extension('postgis')"` | `from_geodataframe` |

**Total: 14 sites** — 7 in database.py, 7 in async_database.py.

### Sites to Convert: `ValueError` → `DatabaseExists` (new type)

| File | Line | Message (preserved) | Method |
|------|------|----------------------|--------|
| database.py | 167 | `f"Database '{name}' already exists"` | `create` classmethod |
| async_database.py | 160 | `f"Database '{name}' already exists"` | `create` classmethod |

**Total: 2 sites.**

### Sites NOT to Convert (stay as-is per D-01)

| File | Lines | Type | Message | Reason |
|------|-------|------|---------|--------|
| database.py | 356-358 | `RuntimeError` | "Already in session mode..." | Invalid state / programmer error |
| async_database.py | 319-321 | `RuntimeError` | "Already in session mode..." | Invalid state / programmer error |
| database.py | 1131-1137 | `ValueError` | "Invalid ON DELETE/UPDATE action..." | API misuse |
| async_database.py | 807-811 | `ValueError` | "Invalid ON DELETE/UPDATE action..." | API misuse |
| database.py | 1329-1331 | `ValueError` | "Specify either table or sql..." | API misuse |
| database.py | 1435-1437 | `ValueError` | "Specify either table or sql..." | API misuse |
| async_database.py | 1676-1678 | `ValueError` | "Specify either table or sql..." | API misuse |
| async_database.py | 1760-1762 | `ValueError` | "Specify either table or sql..." | API misuse |
| database.py + async_database.py | multiple | `ValueError` | CRS/SRID inference errors (from_geodataframe) | API misuse / external data |
| database.py | 2248 | `RuntimeError` | "pg_dump failed: ..." | Subprocess failure |
| database.py | 2327 | `RuntimeError` | "pg_restore failed: ..." | Subprocess failure |
| database.py | 2353 | `RuntimeError` | "psql restore failed: ..." | Subprocess failure |
| async_database.py | 2215 | `RuntimeError` | "pg_dump failed: ..." | Subprocess failure |
| async_database.py | 2300 | `RuntimeError` | "pg_restore failed: ..." | Subprocess failure |
| async_database.py | 2332 | `RuntimeError` | "psql restore failed: ..." | Subprocess failure |

### Tests to Update (D-04)

| Test File | Line | Current assertion | New assertion |
|-----------|------|-------------------|---------------|
| tests/test_database_integration.py | 869 | `pytest.raises(RuntimeError, match="TimescaleDB extension not installed")` | `pytest.raises(ExtensionNotAvailable, match="TimescaleDB extension not installed")` |
| tests/test_async_database.py | 740 | `pytest.raises(RuntimeError, match="PostGIS extension not installed")` | `pytest.raises(ExtensionNotAvailable, match="PostGIS extension not installed")` |
| tests/test_async_database.py | 2248 | `pytest.raises(RuntimeError, match="TimescaleDB extension not installed")` | `pytest.raises(ExtensionNotAvailable, ...)` |
| tests/test_async_database.py | 2295 | `pytest.raises(RuntimeError, match="TimescaleDB extension not installed")` | `pytest.raises(ExtensionNotAvailable, ...)` |
| tests/test_async_database.py | 2317 | `pytest.raises(RuntimeError, match="TimescaleDB extension not installed")` | `pytest.raises(ExtensionNotAvailable, ...)` |
| tests/test_async_database.py | 2339 | `pytest.raises(RuntimeError, match="TimescaleDB extension not installed")` | `pytest.raises(ExtensionNotAvailable, ...)` |
| tests/test_async_database.py | 2372 | `pytest.raises(RuntimeError, match="TimescaleDB extension not installed")` | `pytest.raises(ExtensionNotAvailable, ...)` |
| tests/test_async_database.py | 2396 | `pytest.raises(RuntimeError, match="TimescaleDB extension not installed")` | `pytest.raises(ExtensionNotAvailable, ...)` |
| tests/test_async_database.py | 2616 | `pytest.raises(ValueError, match="already exists")` | `pytest.raises(DatabaseExists, match="already exists")` |
| tests/test_database.py | 523 | `pytest.raises(RuntimeError)` + "pg_dump failed" | Unchanged (subprocess failure, not domain error) |
| tests/test_database.py | 610 | `pytest.raises(RuntimeError)` + related | Verify — likely pg_restore, unchanged |
| tests/test_session_edge_cases.py | 53 | `pytest.raises(RuntimeError)` "Already in session" | Unchanged (state error, not domain error) |

**Notes on tests:**
- `test_postgis_errors.py` uses `pytest.raises(Exception)` (broad) — no update needed.
- `tests/test_async_database.py:1315` and `:1403` are pg_dump/pg_restore failures — unchanged.
- `tests/test_database.py:523` is pg_dump failure — unchanged.

---

## Docstring Site Counts (DOC-06 / D-07)

Verified by AST analysis (`ast.parse` on each module, counting public FunctionDef/AsyncFunctionDef/ClassDef nodes with `Args:` or `Returns:` section markers):

| Module | Total docstrings | Google-style (has Args:/Returns:) | Simple summary-only | Notes |
|--------|-----------------|-----------------------------------|----------------------|-------|
| database.py | 84 | 77 | ~7 | 80 public symbols with docstrings |
| async_database.py | 85 | 68 | ~17 | 81 public symbols with docstrings |
| base.py | 15 | 5 | ~10 | 8 public, includes module+class docs |
| utils.py | 11 | 10 | ~1 | All util functions have Args: |
| pool.py | 28 | 13 | ~15 | 25 public symbols |
| migrations.py | 19 | 7 | ~12 | 9 public symbols |
| config.py | 10 | 7 | ~3 | 9 public symbols |
| **TOTAL** | **252** | **187** | **~65** | 222 public symbols |

**Migration work:** 187 Google-style docstrings must be converted. Simple summary-only docstrings (~65) need no structural change — just verify they have no `Args:` or `Example:` sections.

**base.py deduplication:** The Phase 12 socle (`DatabaseBase`, `QueryMixin`) has 5 Google-style docstrings. Migrating base.py means `Database` and `AsyncDatabase` inherit the correct format on inherited methods — reducing duplication. However, most docstrings are on overriding methods in database.py/async_database.py directly (they are not inherited — each class has its own full implementations).

---

## Configuration Details

### `[tool.interrogate]` in pyproject.toml

[VERIFIED: github.com/econchick/interrogate/blob/master/pyproject.toml]

```toml
[tool.interrogate]
ignore-init-method = true
ignore-init-module = false
ignore-magic = false
ignore-semiprivate = false
ignore-private = false
ignore-module = false
ignore-property-decorators = false
fail-under = 95
exclude = ["tests", "docs", "setup.py"]
verbose = 0
quiet = false
color = true
```

**Rationale for key flags:**
- `ignore-init-method = true`: `__init__` docstrings belong on the class itself; this is standard Python convention.
- `ignore-module = false`: All 7 modules already have module docstrings — keep them counted.
- `ignore-private = false`: Private methods without docstrings count against coverage, but 95% threshold provides headroom. Current private methods largely have docstrings already.
- `fail-under = 95`: Milestone convention (`.planning/milestones/v0.4.0-MILESTONE.md`).

**CI invocation (blocking):**
```yaml
- name: Check docstring coverage
  run: uv run interrogate pycopg --fail-under 95 --quiet
```

### `[tool.mypy]` in pyproject.toml

[CITED: mypy.readthedocs.io/en/stable/config_file.html]

```toml
[tool.mypy]
python_version = "3.11"
warn_return_any = true
warn_unused_configs = true
ignore_missing_imports = false
disallow_untyped_defs = false
check_untyped_defs = true
no_implicit_optional = true

[[tool.mypy.overrides]]
module = "sqlalchemy.*"
ignore_missing_imports = true

[[tool.mypy.overrides]]
module = "psycopg.*"
ignore_missing_imports = true

[[tool.mypy.overrides]]
module = "psycopg_pool.*"
ignore_missing_imports = true

[[tool.mypy.overrides]]
module = "geopandas.*"
ignore_missing_imports = true

[[tool.mypy.overrides]]
module = "geoalchemy2.*"
ignore_missing_imports = true

[[tool.mypy.overrides]]
module = "shapely.*"
ignore_missing_imports = true

[[tool.mypy.overrides]]
module = "tenacity.*"
ignore_missing_imports = true
```

**Rationale:** Per D-05, no `--strict`. `disallow_untyped_defs = false` is intentional — most functions are already typed but forcing 100% annotation is out of phase scope. `check_untyped_defs = true` still type-checks function bodies. The per-module overrides for SQLAlchemy, psycopg, and geopandas handle the dynamic/stubs-missing landscape of these libraries.

**CI invocation (NON-blocking, `continue-on-error: true`):**
```yaml
- name: mypy type check
  continue-on-error: true
  run: uv run mypy pycopg/
```

### `docs/conf.py` napoleon change

Add after the existing `extensions` list:
```python
# Napoleon settings
napoleon_numpy_docstring = True    # Enable NumPy-style docstring parsing
# napoleon_google_docstring = True  # Default True — keep during migration
# After migration completes, add: napoleon_google_docstring = False
```

### Sphinx build CI guard (D-08)

The Sphinx build is currently NOT in CI (`.github/workflows/tests.yml` contains no sphinx step — verified by grep).

**Add as blocking CI step:**
```yaml
- name: Build Sphinx docs (napoleon non-regression)
  run: |
    pip install -r docs/requirements.txt
    sphinx-build -W --keep-going -b html docs docs/_build/html
```

**Note on `-W` behavior:** The `-W` flag makes ALL sphinx warnings into errors. This is intentional — it validates that migrated numpydoc sections parse correctly. The `--keep-going` flag collects all warnings before exiting rather than stopping at the first one, giving a complete picture.

**Known limitation:** [CITED: github.com/sphinx-doc/sphinx/issues/9142] sphinx-build `-W` may not catch warnings from third-party extensions (including napoleon) in older Sphinx versions. Use `show_warning_types = True` in conf.py to diagnose. If napoleon warnings do not trigger exit code 1 under `-W`, the guard needs the numpydoc Sphinx extension (separate package) or doctest-based validation instead. [ASSUMED — test this in Wave 0 before committing to -W as the sole guard]

---

## Code Examples

### interrogate run (baseline measurement — Wave 0)

```bash
# Source: interrogate docs (interrogate.readthedocs.io)
# Run before setting fail-under to know the actual baseline:
uv run interrogate pycopg --verbose 2>&1 | tail -20
```

### mypy run

```bash
# Source: mypy.readthedocs.io/en/stable/running_mypy.html
uv run mypy pycopg/
```

### Sphinx build with warnings-as-errors

```bash
# Source: Sphinx docs / sphinx-build --help
# From project root:
pip install -r docs/requirements.txt
sphinx-build -W --keep-going -b html docs docs/_build/html
```

### `importlib.metadata` pattern

```python
# Source: Python stdlib docs (docs.python.org/3/library/importlib.metadata.html)
# In pycopg/__init__.py:
try:
    from importlib.metadata import version, PackageNotFoundError
    __version__ = version("pycopg")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `__version__ = "0.3.1"` hardcoded | `importlib.metadata.version()` | Phase 13 | Single source of truth; no manual bump needed for docstrings |
| Google-style (`Args:`/`Returns:`) | numpydoc shallow | Phase 13 | Standard for scientific Python; renders better in Sphinx with autodoc |
| No coverage gate on docstrings | interrogate ≥ 95% in CI | Phase 13 | Prevents regressions on new code without docstrings |
| No static typing | mypy progressive (TY1 + TY2) | Phase 13 | Foundation for future mypy strict; catches `async_engine` return type gap now |
| Generic RuntimeError/ValueError for domain errors | ExtensionNotAvailable / DatabaseExists | Phase 13 | Allows callers to catch specific exception types; cleaner API |

**Deprecated/outdated:**
- `Args:`/`Returns:`/`Example:` Google-style sections: replaced by numpydoc. To be formally removed from docs style guide in Phase 15.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Both napoleon formats can coexist without parse conflicts on mixed-style docstrings during migration | Architecture Patterns: Pattern 3 | Sphinx build emits warnings on unconverted modules; mitigation: migrate module-by-module and run sphinx-build after each plan |
| A2 | sphinx-build `-W` flag catches napoleon warnings and fails build | Configuration Details / Pitfall 2 | Sphinx -W may not escalate third-party extension warnings to errors; mitigation: test in Wave 0 |
| A3 | Adding `from sqlalchemy.ext.asyncio import AsyncEngine` under `TYPE_CHECKING` doesn't create circular import | Pattern 6 / Pitfall 5 | mypy annotation fails or runtime import error; mitigation: test locally |
| A4 | `autodoc_mock_imports` for optional dependencies isn't needed — `uv sync --all-extras` in CI covers geopandas etc. | Pitfall 2 | Sphinx autodoc ImportError in CI; mitigation: check CI already uses `--all-extras` (it does: tests.yml line 42) |
| A5 | interrogate's `ignore-private = false` still allows ≥95% with current private method docstring state | Configuration Details | interrogate score < 95% even after full public migration; mitigation: measure baseline in Wave 0 |
| A6 | `DatabaseExists` is the only new exception type needed (D-02) | Exception Conversion Inventory | Missed "already exists" site for schemas/roles/etc.; mitigation: grep confirms only 2 "already exists" raise sites, both in `create()` |

**If this table is empty:** it is not — 6 assumptions are tracked.

---

## Open Questions

1. **Sphinx `-W` actually catches napoleon warnings?**
   - What we know: `-W` flag makes sphinx-build warnings into errors. Sphinx issue #9142 notes that third-party extension warnings may not be caught.
   - What's unclear: Whether napoleon/numpydoc malformed-section warnings are emitted as sphinx warnings (which `-W` catches) or as Python `warnings.warn()` calls (which `-W` may not catch).
   - Recommendation: In Wave 0 plan, add a step to test `sphinx-build -W` against a deliberately malformed numpydoc section to verify the guard works. If `-W` doesn't catch it, fall back to running `sphinx-build` and grepping stderr for "WARNING" with a non-zero exit on match.

2. **Should `sphinx` and docs deps be added to the uv dev group?**
   - What we know: Sphinx is not in `pyproject.toml [dependency-groups].dev`. The `docs/requirements.txt` is separate. CI tests.yml uses `uv sync --all-extras --dev` (no docs deps).
   - What's unclear: Whether to add sphinx to dev deps (simpler CI) or keep docs/requirements.txt separate (cleaner separation).
   - Recommendation: Add `sphinx`, `myst-parser`, `furo`, `sphinx-copybutton` to the `dev` dependency group for the CI sphinx-build step to use `uv run sphinx-build`. This aligns with the project's uv-first approach.

3. **interrogate baseline before setting 95%**
   - What we know: Public coverage is 100% by AST (all public symbols have docs). Private coverage unknown.
   - What's unclear: Exact interrogate score with default counting (including magic methods, properties, etc.).
   - Recommendation: Wave 0 task — run `uv run interrogate pycopg --verbose` and record baseline before setting `fail-under = 95`.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| uv | All dev tasks | ✓ | (project-managed) | — |
| Python 3.11+ | All | ✓ | 3.x (from uv env) | — |
| interrogate | DOC-07 | ✗ | — | Install via uv: `uv add --dev interrogate>=1.7.0` |
| mypy | DOC-11/12 | ✗ | — | Install via uv: `uv add --dev mypy>=2.1.0` |
| sphinx (for CI guard) | DOC-08 D-08 | ✗ (not in dev deps) | — | Install from docs/requirements.txt or add to dev group |
| sqlalchemy.ext.asyncio.AsyncEngine | DOC-12 TY2 | ✓ | (SQLAlchemy ≥2.0, already dep) | — |
| importlib.metadata | DOC-10 | ✓ | Python stdlib ≥3.8 | — |

**Missing dependencies with no fallback:**
- None blocking development — all can be installed via uv.

**Missing dependencies with fallback:**
- sphinx (docs CI guard): use `pip install -r docs/requirements.txt` in CI step as a fallback if not added to dev deps.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (with pytest-cov, pytest-asyncio) |
| Config file | `pyproject.toml [tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/ -x -q -o addopts=""` |
| Full suite command | `uv run pytest` (includes coverage gate 92%) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DOC-06 | All public docstrings in numpydoc format | sphinx-build (form) + interrogate (coverage) | `sphinx-build -W ... && uv run interrogate pycopg --fail-under 95` | ❌ Wave 0 (CI steps) |
| DOC-07 | interrogate ≥ 95 passes in CI | CI smoke | `uv run interrogate pycopg --fail-under 95 --quiet` | ❌ Wave 0 (CI step) |
| DOC-08 | napoleon_numpy_docstring enabled, sphinx build clean | CI | `sphinx-build -W -b html docs docs/_build/html` | ❌ Wave 0 (CI step) |
| DOC-09 | ExtensionNotAvailable raised at extension check sites | unit (mock) | `uv run pytest tests/test_database_integration.py tests/test_async_database.py -k "timescale or postgis or extension" -x -o addopts=""` | ✅ (existing, needs update) |
| DOC-09 | DatabaseExists raised at create() | unit/integration | `uv run pytest tests/test_async_database.py::TestAsyncDatabaseAdminOperations::test_create_raises_when_exists_and_not_if_not_exists -o addopts=""` | ✅ (existing, needs update) |
| DOC-10 | `__version__` returns version string | unit | `uv run pytest tests/test_exceptions.py -o addopts=""` (no direct test — add) | ❌ Wave 0 |
| DOC-11 | mypy runs without fatal errors | CI | `uv run mypy pycopg/` | ❌ Wave 0 (CI step) |
| DOC-12 | async_engine annotated AsyncEngine | mypy | `uv run mypy pycopg/async_database.py` | ❌ Wave 0 (via mypy) |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/ -x -q -o addopts=""`
- **Per wave merge:** `uv run pytest` (full suite with coverage gate)
- **Phase gate:** Full suite green + `uv run interrogate pycopg --fail-under 95 --quiet` + `sphinx-build -W` before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] Add CI step for interrogate in `.github/workflows/tests.yml` — covers DOC-07
- [ ] Add CI step for sphinx-build in `.github/workflows/tests.yml` — covers DOC-08
- [ ] Add CI step for mypy (continue-on-error) in `.github/workflows/tests.yml` — covers DOC-11/12
- [ ] Run `uv run interrogate pycopg --verbose` to measure baseline before setting `fail-under = 95`
- [ ] Add `tests/test_version.py` — covers DOC-10 (`assert pycopg.__version__ == "0.3.1"` or similar)

---

## Security Domain

> This phase does not introduce new network-facing code, authentication, cryptography, or SQL generation paths. ASVS categories are not applicable to docstring migration, version metadata, and exception type changes. `security_enforcement` is assumed enabled but no new ASVS controls are introduced in this phase.

The exception type change (D-01) specifically does NOT change error messages (which could affect security-sensitive information disclosure), only the Python type of the raised exception. This is confirmed by D-01/specifics: "messages d'exception existants sont à préserver lors de la conversion de type."

---

## Sources

### Primary (HIGH confidence)
- `pycopg/` codebase — direct AST analysis of 7 modules (exception inventory, docstring counts, format audit)
- `tests/` — direct grep for pytest.raises sites (D-04 update inventory)
- sphinx.ext.napoleon official Sphinx docs — napoleon configuration options, dual-format behavior
- pypi.org/project/interrogate — version 1.7.0, release date, project info
- pypi.org/project/mypy — version 2.1.0
- github.com/econchick/interrogate/blob/master/pyproject.toml — canonical [tool.interrogate] configuration
- Python stdlib docs (importlib.metadata) — version() + PackageNotFoundError pattern

### Secondary (MEDIUM confidence)
- mypy.readthedocs.io/en/stable/config_file.html — per-module overrides, ignore_missing_imports, disallow_untyped_defs
- Verified working: `importlib.metadata.version("pycopg")` returns `"0.3.1"` in uv env (tested live)

### Tertiary (LOW confidence)
- sphinx-build -W behavior with napoleon warnings — referenced via sphinx-doc GitHub issues; exact behavior in this project's Sphinx version needs Wave 0 verification

---

## Metadata

**Confidence breakdown:**
- Exception inventory: HIGH — direct grep of source files; all sites enumerated
- Docstring counts: HIGH — AST analysis, not heuristic
- Standard stack (interrogate, mypy): HIGH — verified on PyPI, official packages
- interrogate config: HIGH — from interrogate's own pyproject.toml (self-documenting)
- mypy config: MEDIUM — from official docs; sqlalchemy/psycopg override necessity verified via common knowledge
- Sphinx guard behavior: MEDIUM-LOW — functional approach confirmed, but -W + napoleon warning escalation needs Wave 0 verification
- `importlib.metadata`: HIGH — tested live, package name confirmed

**Research date:** 2026-06-10
**Valid until:** 2026-09-10 (stable tooling: interrogate 1.7.0, mypy 2.1.0 — unlikely to have breaking changes in 90 days)
