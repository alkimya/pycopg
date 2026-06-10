---
phase: 13-qualit-documentaire-docstrings-numpydoc-interrogate
reviewed: 2026-06-10T00:00:00Z
depth: standard
files_reviewed: 17
files_reviewed_list:
  - pycopg/__init__.py
  - pycopg/async_database.py
  - pycopg/base.py
  - pycopg/config.py
  - pycopg/database.py
  - pycopg/exceptions.py
  - pycopg/migrations.py
  - pycopg/pool.py
  - pycopg/utils.py
  - pyproject.toml
  - docs/conf.py
  - docs/api-autodoc.md
  - docs/index.md
  - .github/workflows/tests.yml
  - tests/test_async_database.py
  - tests/test_database_integration.py
  - tests/test_version.py
findings:
  critical: 1
  warning: 4
  info: 8
  total: 13
status: issues_found
---

# Phase 13: Code Review Report

**Reviewed:** 2026-06-10
**Depth:** standard
**Files Reviewed:** 17
**Status:** issues_found

## Summary

Reviewed the Phase 13 documentation-quality changes (diff base `e08a63f^`). The
"docs-only" claim was verified mechanically: AST comparison with docstrings
stripped shows `base.py`, `config.py`, `utils.py`, `migrations.py`, and
`pool.py` are code-identical to the base — no behavior changes hidden in those
migrations. The code changes in `database.py` / `async_database.py` are exactly
the advertised 16 exception conversions (7 `RuntimeError`→`ExtensionNotAvailable`
+ 1 `ValueError`→`DatabaseExists` per module) plus a `TYPE_CHECKING`-safe
`AsyncEngine` annotation (safe: `from __future__ import annotations` is present
at `async_database.py:7`). Gates were executed locally: interrogate passes at
the 95% threshold, `sphinx-build -W` passes, mypy runs non-blocking, and the
targeted test suites pass (175 passed).

However, the new CI Sphinx gate is broken as written (`uv run pip` cannot work
in a uv-synced venv — reproduced locally), one Google-style docstring residual
survived the migration despite `napoleon_google_docstring = False`, the sync
`Database.create` docstring lacks the `Raises` section its async twin has, and
the exception conversions are an uncompensated backward-compatibility break on
an unbumped 0.3.1 version.

## Critical Issues

### CR-01: New blocking Sphinx CI step uses `uv run pip`, which fails in a uv-synced venv

**File:** `.github/workflows/tests.yml:65`
**Issue:** The "Build Sphinx docs (napoleon non-regression)" step runs
`uv run pip install -r docs/requirements.txt`. `uv sync` creates the project
venv **without pip**, so `uv run pip` fails. Reproduced locally in this repo's
synced venv:

```
$ uv run pip --version
error: Failed to spawn: `pip`
  Caused by: No such file or directory (os error 2)
```

CI performs the identical `uv sync --locked --all-extras --dev` then
`uv run pip ...`, so this blocking step fails on every run, which permanently
reds the pipeline regardless of docs quality. The defect is currently masked
because the `Run tests` step before it is already failing on main (pre-existing
red runs: e.g. run 27224066066), so the new gates have never actually executed
in CI — this gate is unproven and broken on first real execution.
**Fix:**
```yaml
      - name: Build Sphinx docs (napoleon non-regression)
        run: |
          uv pip install -r docs/requirements.txt
          uv run sphinx-build -W --keep-going -b html docs docs/_build/html
```
(`uv pip` is uv's built-in pip interface and operates on the project venv
without requiring pip to be installed.) Verified locally that with this
invocation the `-W --keep-going` build succeeds.

## Warnings

### WR-01: Google-style `Yields:` residual survives the migration and now renders as plain text

**File:** `pycopg/database.py:292`
**Issue:** `Database.transaction()` still has a Google-style section:

```python
        Yields:
            psycopg Connection in a transaction.
```

With `napoleon_google_docstring = False` (docs/conf.py:32), napoleon no longer
parses this; it renders in autodoc as a literal "Yields:" paragraph instead of
a structured field. Sphinx emits **no warning** for this (the `-W` gate passed
locally with the defect present), so the CI gate cannot catch it — it must be
fixed manually. This is the only residual: a scan for
`Args:/Returns:/Yields:/Raises:` etc. across `pycopg/` found no others.
**Fix:**
```python
        Yields
        ------
        psycopg.Connection
            Connection in a transaction.
```

### WR-02: Sync `Database.create` missing `Raises: DatabaseExists` section that its async twin documents

**File:** `pycopg/database.py:95-125`
**Issue:** `Database.create` raises `DatabaseExists` at database.py:149, but
its docstring has no `Raises` section. The async counterpart documents it
(`async_database.py:134-137`). In a phase whose deliverable is docstring
accuracy and whose project advertises "Full Async Parity", the converted
exception must be documented on both sides. (`create_from_env` in both modules
also propagates `DatabaseExists` undocumented.)
**Fix:** Add to the `Database.create` docstring after `Returns`:
```rst
        Raises
        ------
        DatabaseExists
            If the database already exists and if_not_exists is False.
```

### WR-03: Exception conversions are a breaking API change on an unbumped 0.3.1

**File:** `pycopg/exceptions.py:21-43` (and call sites in database.py / async_database.py)
**Issue:** `ExtensionNotAvailable` and `DatabaseExists` derive only from
`PycopgError(Exception)`. Existing consumer code doing
`except RuntimeError:` around hypertable/PostGIS calls or
`except ValueError:` around `Database.create(if_not_exists=False)` silently
stops catching these errors. `pyproject.toml` still declares `version = "0.3.1"`
— shipping this as a patch-level release would break callers without warning.
**Fix:** Either (a) ensure the version is bumped to 0.4.0 before any release
(the milestone plan suggests this is intended — make it explicit now to remove
the risk), or (b) provide a deprecation window via dual inheritance:
```python
class ExtensionNotAvailable(PycopgError, RuntimeError): ...
class DatabaseExists(PycopgError, ValueError): ...
```

### WR-04: Sync `DatabaseExists` conversion site has no test coverage

**File:** `pycopg/database.py:149` / `tests/test_database_integration.py`
**Issue:** The async conversion is verified by
`tests/test_async_database.py:2613-2616`
(`pytest.raises(DatabaseExists, ...)` on `AsyncDatabase.create`), but no test
anywhere exercises the sync `Database.create(..., if_not_exists=False)` path
— a grep for `"already exists"` across `tests/` finds only the async test.
Half of the headline `ValueError`→`DatabaseExists` conversion is unverified.
**Fix:** Add a sync integration test mirroring the async one:
```python
def test_create_raises_when_exists_and_not_if_not_exists(self, db_config):
    with pytest.raises(DatabaseExists, match="already exists"):
        Database.create("pycopg_test", host=db_config.host, port=db_config.port,
                        user=db_config.user, password=db_config.password,
                        if_not_exists=False)
```
This would also consume the currently dead import (see IN-01).

## Info

### IN-01: Unused `DatabaseExists` import introduced this phase

**File:** `tests/test_database_integration.py:12`
**Issue:** `from pycopg.exceptions import ExtensionNotAvailable, DatabaseExists`
— `DatabaseExists` is never used in this file (ruff F401 confirms). Introduced
by commit a155a1d.
**Fix:** Remove it, or better, use it per WR-04.

### IN-02: Stale test docstrings still reference the old exception types

**File:** `tests/test_database_integration.py:867`, `tests/test_async_database.py:731`, `tests/test_async_database.py:2244`, `tests/test_async_database.py:2614`
**Issue:** Test bodies were updated to `ExtensionNotAvailable`/`DatabaseExists`
but their docstrings still say "raises RuntimeError" / "raises ValueError" —
stale documentation produced by the very commits of a documentation-quality
phase.
**Fix:** Update the four docstrings to name the new exception types.

### IN-03: `version` and `PackageNotFoundError` leak into the `pycopg` namespace

**File:** `pycopg/__init__.py:30`
**Issue:** `from importlib.metadata import version, PackageNotFoundError` at
module top level makes `pycopg.version` (a function) and
`pycopg.PackageNotFoundError` importable public-looking attributes.
**Fix:** `del version, PackageNotFoundError` after computing `__version__`, or
use `import importlib.metadata` and qualified access.

### IN-04: `docs/conf.py` hardcodes `release = '0.3.1'`, contradicting the new single-source-of-truth approach

**File:** `docs/conf.py:17`
**Issue:** Phase 13 moved `__version__` to `importlib.metadata` to avoid
duplicated version strings, but the Sphinx `release` remains hardcoded and will
drift at the 0.4.0 bump.
**Fix:** `release = importlib.metadata.version("pycopg")` (with a
PackageNotFoundError fallback).

### IN-05: Incomplete `Raises` sections at sites that still raise ValueError/RuntimeError

**File:** `pycopg/database.py:1444-1475`, `pycopg/database.py:2423`, `pycopg/async_database.py:2047-2074`
**Issue:** `from_geodataframe` documents only `ExtensionNotAvailable` but also
raises `ValueError` on missing/unmappable CRS (database.py:1458, 1465, 1472);
`pg_dump`/`pg_restore`/`_psql_restore` raise `RuntimeError` on subprocess
failure with no `Raises` documentation. Acceptable under the "shallow
migration" scope, but inconsistent with the per-method Raises sections added
elsewhere.
**Fix:** Add the missing `ValueError` / `RuntimeError` entries to those
`Raises` sections.

### IN-06: Interrogate threshold and quiet mode duplicated between CI flags and pyproject

**File:** `.github/workflows/tests.yml:61`, `pyproject.toml:114`
**Issue:** CI passes `--fail-under 95 --quiet` while `[tool.interrogate]`
declares `fail-under = 95` and `quiet = false`. Two sources of truth for the
ratchet threshold can silently drift; the CLI silently wins.
**Fix:** `run: uv run interrogate pycopg` and let pyproject own the threshold.

### IN-07: Deprecated top-level ruff settings emit a warning on every lint run

**File:** `pyproject.toml:85-86`
**Issue:** `select`/`ignore` under `[tool.ruff]` are deprecated; ruff prints a
deprecation warning on every invocation. Pre-existing, but pyproject.toml was
edited this phase and the fix is two lines.
**Fix:** Move them under `[tool.ruff.lint]`.

### IN-08: Unpinned docs dependencies combined with a `-W` blocking gate

**File:** `docs/requirements.txt:1-6`, `.github/workflows/tests.yml:63-66`
**Issue:** `sphinx>=7.0.0`, `myst-parser>=2.0.0`, `furo>=2024.0.0` are floor
pins. The blocking `-W --keep-going` gate makes CI fail whenever a new
Sphinx/myst release introduces a new warning class — unrelated to any code
change. Distinct from CR-01 (which is about the step not running at all).
**Fix:** Pin or upper-bound the docs toolchain (e.g. `sphinx>=7,<9`), or keep a
constraints file refreshed deliberately.

---

_Reviewed: 2026-06-10_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
