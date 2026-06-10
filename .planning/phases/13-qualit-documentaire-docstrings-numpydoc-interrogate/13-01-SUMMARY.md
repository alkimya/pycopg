---
phase: 13-qualit-documentaire-docstrings-numpydoc-interrogate
plan: "01"
subsystem: tooling
tags: [interrogate, mypy, sphinx, napoleon, exceptions, versioning, ci]
dependency_graph:
  requires: []
  provides:
    - interrogate>=1.7.0 dev dep + [tool.interrogate] (fail-under=95)
    - mypy>=2.1.0 dev dep + [tool.mypy] permissive config + 7 overrides
    - pycopg.exceptions.DatabaseExists (foundation for Plan 02)
    - __version__ via importlib.metadata (DOC-10)
    - docs/api-autodoc.md autodoc surface (foundation for DOC-08 guard)
    - napoleon_numpy_docstring = True in docs/conf.py
    - CI steps: interrogate (blocking), sphinx-build -W (blocking), mypy (non-blocking)
  affects:
    - pycopg/__init__.py
    - pycopg/exceptions.py
    - pyproject.toml
    - uv.lock
    - .github/workflows/tests.yml
    - docs/conf.py
    - docs/index.md
    - docs/api-autodoc.md
    - tests/test_version.py
    - pycopg/database.py
    - pycopg/async_database.py
    - pycopg/base.py
    - pycopg/config.py
    - pycopg/migrations.py
    - pycopg/pool.py
tech_stack:
  added:
    - interrogate>=1.7.0 (dev dep — docstring coverage gate)
    - mypy>=2.1.0 (dev dep — progressive type checking)
  patterns:
    - importlib.metadata.version() for package version resolution
    - napoleon_numpy_docstring = True in Sphinx conf for numpydoc support
    - sphinx-build -W --keep-going as CI quality gate
    - interrogate --fail-under 95 as CI quantity gate
    - continue-on-error: true for non-blocking mypy CI step
key_files:
  created:
    - docs/api-autodoc.md
    - tests/test_version.py
  modified:
    - pyproject.toml ([tool.interrogate], [tool.mypy], dev deps)
    - uv.lock (interrogate + mypy added)
    - pycopg/exceptions.py (DatabaseExists added)
    - pycopg/__init__.py (__version__ via importlib.metadata; DatabaseExists exported)
    - docs/conf.py (napoleon_numpy_docstring, show_warning_types)
    - docs/index.md (api-autodoc in toctree)
    - .github/workflows/tests.yml (3 new CI steps)
    - pycopg/database.py (docstrings for __enter__, __exit__)
    - pycopg/async_database.py (docstrings for __aenter__, __aexit__)
    - pycopg/base.py (docstring for __repr__)
    - pycopg/config.py (docstring for __repr__)
    - pycopg/migrations.py (docstrings for Migration.__repr__, Migrator.__repr__)
    - pycopg/pool.py (docstrings for __enter__, __exit__, __repr__, __aenter__, __aexit__, __repr__)
decisions:
  - "interrogate baseline was 94.8% pre-existing (14 undocumented magic/dunder methods); added docstrings to reach 100% rather than lowering fail-under"
  - "Sphinx -W guard mechanism: sphinx-build -W --keep-going exits non-zero on ANY docstring formatting issue (proven empirically); napoleon does not emit module-specific warnings for malformed numpydoc (Sphinx #9142 confirmed) — but -W catches the docutils RST errors these cause"
  - "CI sphinx guard currently exits 1 due to pre-existing Google-style docstring RST warnings (25 warnings); will go green after Plans 03-05 complete numpydoc migration"
  - "napoleon_google_docstring left at default True during migration (Pattern 3); will be disabled at Phase 13 end (Plan 06)"
metrics:
  duration: "467 seconds (~7.8 minutes)"
  completed: "2026-06-10"
  tasks_completed: 4
  files_changed: 14
---

# Phase 13 Plan 01: Tooling Foundation Summary

Tooling and measurement foundation for numpydoc phase: interrogate+mypy installed+configured, 100% docstring coverage (up from 94.8% baseline), DatabaseExists exception type added, __version__ resolved from package metadata, autodoc surface created, Sphinx napoleon guard empirically proven, and three CI gates wired.

## What Was Built

### Task 2: interrogate + mypy dev deps and [tool.*] config

Added `interrogate>=1.7.0` and `mypy>=2.1.0` to `[dependency-groups].dev` in `pyproject.toml`. Appended `[tool.interrogate]` with `fail-under=95` (all scope flags enabled per DOC-07) and `[tool.mypy]` permissive config (no strict, `disallow_untyped_defs=false`) with 7 `[[tool.mypy.overrides]]` sections for optional deps (sqlalchemy, psycopg, psycopg_pool, geopandas, geoalchemy2, shapely, tenacity).

**Measured interrogate baseline: 94.8%** (269 total symbols, 14 missed — all magic/dunder methods). Added one-liner docstrings to the 14 missing symbols across 6 files (Rule 2: foundation correctness). Final coverage: **100.0%**. `uv run interrogate pycopg --fail-under 95 --quiet` exits 0.

### Task 3: DatabaseExists exception, __version__ via importlib.metadata, version test

Added `class DatabaseExists(PycopgError)` with single inheritance (D-03) to `pycopg/exceptions.py`. Exported from `pycopg.__init__` imports block and `__all__`. Replaced hardcoded `__version__ = "0.3.1"` with `importlib.metadata.version("pycopg")` + `PackageNotFoundError` fallback (D-09). Created `tests/test_version.py` (TestVersion class, 3 assertions for DOC-10).

### Task 4: napoleon_numpy_docstring + Sphinx autodoc surface

Added `napoleon_numpy_docstring = True` and `show_warning_types = True` to `docs/conf.py`. Created `docs/api-autodoc.md` with `{eval-rst}` block containing `.. automodule::` directives for all 8 pycopg modules. Added `api-autodoc` to toctree in `docs/index.md`.

**Empirical D-08 guard result:** `sphinx-build -W --keep-going` exits non-zero on docstring formatting issues (proven). Napoleon does NOT emit module-specific warnings for malformed numpydoc sections (Sphinx #9142 confirmed — napoleon silently renders malformed sections differently instead of warning). However, the malformed numpydoc section causes docutils RST parsing errors which `-W` escalates to failures. **Guard mechanism chosen: `sphinx-build -W --keep-going`**. Clean build without `-W` exits 0. Clean build WITH `-W` currently exits 1 due to 25 pre-existing Google-style docstring RST warnings — these will be resolved by Plans 03-05 migration.

### Task 5: CI gates

Added three CI steps to `.github/workflows/tests.yml` after "Run tests":
1. "Check docstring coverage" — `interrogate pycopg --fail-under 95 --quiet` (blocking, no `continue-on-error`)
2. "Build Sphinx docs (napoleon non-regression)" — `pip install -r docs/requirements.txt` + `sphinx-build -W --keep-going -b html docs docs/_build/html` (blocking, no `continue-on-error`)
3. "mypy type check" — `mypy pycopg/` with `continue-on-error: true` (non-blocking per D-05)

`continue-on-error: true` appears exactly once (mypy step only).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] Added docstrings to 14 undocumented magic/dunder methods**
- **Found during:** Task 2 — interrogate baseline measurement
- **Issue:** Baseline was 94.8%, just below the 95% fail-under threshold. 14 magic methods (`__repr__`, `__enter__`/`__exit__`, `__aenter__`/`__aexit__`) across 6 files had no docstrings.
- **Plan direction:** "If the measured baseline is below 95, DO NOT lower fail-under — instead document which private/magic symbols are undocumented and add their docstrings (this is in-scope foundation work)"
- **Fix:** Added one-liner docstrings to all 14 symbols. Coverage went from 94.8% to 100%.
- **Files modified:** pycopg/database.py, pycopg/async_database.py, pycopg/base.py, pycopg/config.py, pycopg/migrations.py, pycopg/pool.py
- **Commit:** e08a63f

**2. [Rule 1 - Documentation finding] sphinx-build -W guard cannot achieve "clean exits 0" pre-migration**
- **Found during:** Task 4 empirical testing
- **Issue:** The `sphinx-build -W --keep-going` command currently exits 1 (not 0) on the clean codebase because the existing Google-style docstrings produce 25 docutils RST warnings when processed through autodoc. The plan's acceptance criterion "clean build exits 0" can only be met without the `-W` flag.
- **Fix:** Documented the finding. Clean build without `-W` exits 0 (confirmed). CI uses `-W` as the guard; it will go green after Plans 03-05 complete the numpydoc migration. `continue-on-error` was NOT added to the sphinx step — it remains blocking per D-08.
- **Files modified:** docs/conf.py (no change needed; finding is documented here)
- **No additional commit:** this is a documentation/SUMMARY-only finding.

## Key Empirical Findings (D-08 guard)

| Test | Result |
|------|--------|
| `sphinx-build -W --keep-going` on clean codebase | EXIT 1 (25 pre-existing docutils warnings from Google-style docstrings) |
| `sphinx-build` (no -W) on clean codebase | EXIT 0 (warnings printed but not fatal) |
| `sphinx-build -W --keep-going` on malformed numpydoc section | EXIT 1 (failure confirmed) |
| napoleon-specific stderr warnings on malformed numpydoc | NONE (napoleon silently handles; Sphinx #9142) |

**Guard mechanism for CI and Plan 06:** `sphinx-build -W --keep-going -b html docs docs/_build/html`. Currently exits 1; will pass after Plans 03-05 migrate all 187 docstrings to numpydoc.

## Known Stubs

None — no stub values or placeholder data introduced in this plan.

## Threat Flags

None — no new network endpoints, auth paths, file access patterns, or schema changes introduced. The new exception type `DatabaseExists` carries only pre-existing message text (T-13-02 accepted).

## Self-Check

## Self-Check: PASSED

- FOUND: .planning/phases/13-qualit-documentaire-docstrings-numpydoc-interrogate/13-01-SUMMARY.md
- FOUND commit e08a63f (Task 2: interrogate + mypy deps + baseline docstrings)
- FOUND commit b667abf (Task 3: DatabaseExists + __version__ + test_version.py)
- FOUND commit 0144c86 (Task 4: napoleon_numpy flag + autodoc surface)
- FOUND commit b26b70d (Task 5: CI gates wired)
